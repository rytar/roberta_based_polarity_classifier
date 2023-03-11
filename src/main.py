import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, random_split, DataLoader

import numpy as np
import os
import pandas as pd
import random
import regex
import sudachipy
import warnings
from tqdm import tqdm
from transformers import AutoTokenizer
from unicodedata import normalize
from model_definition import BERTBasedBinaryClassifier

warnings.simplefilter("ignore", UserWarning)

class EarlyStopping():

    def __init__(self, patience=10, verbose=False):
        self.patience = patience
        self.verbose = verbose

        self.prev_loss = 1e9
        self.epochs = 0
        self.count = 0
    
    def __call__(self, loss: float):
        self.epochs += 1
        self.count += 1

        if self.prev_loss > loss:
            self.prev_loss = loss
            self.count = 0

            return False
        
        if self.count > self.patience:
            if self.verbose:
                print(f"early stopping: {self.epochs} epochs")
            
            return True

        return False

def fix_seed(seed=0):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)

def get_dataloader(batch_size: int):
    df_tweet = pd.read_csv("./data/tweet_dataset.csv").dropna()
    df_amazon = pd.read_csv("./data/amazon-polarity.csv").dropna()
    df_rt = pd.read_csv("./data/rt-polarity.csv").dropna()
    df = pd.concat([ df_tweet, df_amazon, df_rt ])

    with open("./data/Japanese.txt", 'r') as f:
        stop_words = regex.split(r"\s+", f.read().strip())

    input_ids_list: list[torch.Tensor] = []
    attention_mask_list: list[torch.Tensor] = []
    token_type_ids_list: list[torch.Tensor] = []
    labels: list[int] = []

    tokenizer = sudachipy.Dictionary(dict="full").create(mode=sudachipy.Tokenizer.SplitMode.A)
    
    delete_chars = regex.compile(r"\s|" + '|'.join(stop_words))

    encoder = AutoTokenizer.from_pretrained("nlp-waseda/roberta-base-japanese")
    max_length = 512

    for i in tqdm(range(len(df)), desc="create data"):
        text = df.iloc[i]["text"]
        polarity = df.iloc[i]["polarity"]

        text = normalize("NFKC", text)
        text = text.casefold()
        text = delete_chars.sub('', text)
        text = regex.sub(r"\d+", '0', text)
        text = ' '.join([ m.normalized_form() for m in tokenizer.tokenize(text) if not m.part_of_speech()[0] in ["補助記号", "空白"] ])

        encoding = encoder(text, return_tensors="pt", max_length=max_length, padding="max_length", truncation=True)

        input_ids_list.append(encoding.input_ids)
        attention_mask_list.append(encoding.attention_mask)
        token_type_ids_list.append(encoding.token_type_ids)
        labels.append(polarity)
    
    input_ids_tensor = torch.cat(input_ids_list)
    attention_mask_tensor = torch.cat(attention_mask_list)
    token_type_ids_tensor = torch.cat(token_type_ids_list)
    labels_tensor = torch.unsqueeze(torch.tensor(labels), 1)

    print(f"input_ids: {input_ids_tensor.size()}, {input_ids_tensor.dtype}")
    print(f"attention_mask: {attention_mask_tensor.size()}, {attention_mask_tensor.dtype}")
    print(f"token_type_ids: {token_type_ids_tensor.size()}, {token_type_ids_tensor.dtype}")
    print(f"labels: {labels_tensor.size()}, {labels_tensor.dtype}")

    dataset = TensorDataset(input_ids_tensor, attention_mask_tensor, token_type_ids_tensor, labels_tensor)

    g = torch.Generator()
    g.manual_seed(0)

    val_size = int(0.1 * len(labels))
    test_size = val_size
    train_size = len(labels) - val_size - test_size

    print(f"[train, val, test]: [{train_size}, {val_size}, {test_size}]")

    train, val, test = random_split(dataset, [train_size, val_size, test_size], generator=g)

    train_loader = DataLoader(train, batch_size=batch_size, shuffle=True, num_workers=os.cpu_count() or 0, generator=g)
    val_loader = DataLoader(val, batch_size=batch_size, shuffle=False, num_workers=os.cpu_count() or 0, generator=g)
    test_loader = DataLoader(test, batch_size=batch_size, shuffle=False, num_workers=os.cpu_count() or 0, generator=g)

    return train_loader, val_loader, test_loader

def train(model: nn.Module, device: torch.device, optimizer, criterion: nn.Module, epochs: int, train_loader: DataLoader, val_loader: DataLoader | None = None, early_stopping: EarlyStopping | None = None):
    for epoch in range(epochs):
        bar = tqdm(total = len(train_loader) + len(val_loader))
        bar.set_description(f"Epochs {epoch + 1}/{epochs}")

        running_loss = 0.
        running_total = 0
        running_correct = 0

        model.train()
        for input_ids, attention_mask, token_type_ids, labels in train_loader:
            input_ids: torch.Tensor = input_ids.to(device)
            attention_mask: torch.Tensor = attention_mask.to(device)
            token_type_ids: torch.Tensor = token_type_ids.to(device)
            labels: torch.Tensor = labels.to(device)

            optimizer.zero_grad()
            outputs: torch.Tensor = model(input_ids, attention_mask, token_type_ids)
            loss: torch.Tensor = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item()
            pred = (torch.sigmoid(outputs) > 0.5).float()
            running_total += labels.size(0)
            running_correct += (pred == labels).sum().item()

            bar.set_postfix(train_loss = running_loss / len(train_loader), train_acc = running_correct / running_total)
            bar.update(1)

        if val_loader is None: continue
        
        val_loss = 0.
        val_total = 0
        val_correct = 0

        model.eval()
        with torch.no_grad():
            for input_ids, attention_mask, token_type_ids, labels in val_loader:
                input_ids: torch.Tensor = input_ids.to(device)
                attention_mask: torch.Tensor = attention_mask.to(device)
                token_type_ids: torch.Tensor = token_type_ids.to(device)
                labels: torch.Tensor = labels.to(device)

                outputs: torch.Tensor = model(input_ids, attention_mask, token_type_ids)
                loss: torch.Tensor = criterion(outputs, labels)

                val_loss += loss.item()
                pred = (torch.sigmoid(outputs) > 0.5).float()
                val_total += labels.size(0)
                val_correct += (pred == labels).sum().item()

                bar.set_postfix(train_loss = running_loss / len(val_loader), train_acc = running_correct / running_total, val_loss = val_loss / len(val_loader), val_acc = val_correct / val_total)
                bar.update(1)
        
        bar.close()
        
        if early_stopping is not None and early_stopping(val_loss / len(val_loader)):
            break

def test(model: nn.Module, device: torch.device, criterion: nn.Module, test_loader: DataLoader):
    test_loss = 0.
    test_total = 0
    test_correct = 0

    with torch.no_grad():
        for input_ids, attention_mask, token_type_ids, labels in test_loader:
            input_ids: torch.Tensor = input_ids.to(device)
            attention_mask: torch.Tensor = attention_mask.to(device)
            token_type_ids: torch.Tensor = token_type_ids.to(device)
            labels: torch.Tensor = labels.to(device)

            outputs: torch.Tensor = model(input_ids, attention_mask, token_type_ids)
            loss: torch.Tensor = criterion(outputs, labels)

            test_loss += loss.item()
            pred = (torch.sigmoid(outputs) > 0.5).float()
            test_total += labels.size(0)
            test_correct += (pred == labels).sum().item()
    
    print(f"test loss: {test_loss / len(test_loader):.2f}")
    print(f"test acc: {test_correct / test_total:.3f}")

def main():
    os.environ["TOKENIZERS_PARALLELISM"] = "true"

    fix_seed()
    
    epochs = 100
    batch_size = 16
    test_mode = False

    train_loader, val_loader, test_loader = get_dataloader(batch_size)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    model = BERTBasedBinaryClassifier("nlp-waseda/roberta-base-japanese")

    for param in model.bert.parameters():
        param.requires_glad = False

    for param in model.bert.encoder.layer[-1].parameters():
        param.requires_glad = True

    for param in model.bert.pooler.parameters():
        param.requires_glad = True

    model.to(device)

    early_stopping = EarlyStopping(verbose=True)
    optimizer = torch.optim.Adam([
        {"params": model.bert.encoder.layer[-1].parameters(), "lr": 5e-5},
        {"params": model.bert.pooler.parameters(), "lr": 1e-3},
        {"params": model.conv1.parameters(), "lr": 1e-3},
        {"params": model.conv2.parameters(), "lr": 1e-3}
    ], betas=(0.9, 0.999))
    criterion = nn.BCEWithLogitsLoss()

    if not test_mode: train(model, device, optimizer, criterion, epochs, train_loader, val_loader, early_stopping)
    test(model, device, criterion, test_loader)

    save_path = "./model/model.pth"
    print(f"save to {save_path}")
    torch.save(model.to("cpu"), save_path)

if __name__ == "__main__":
    main()