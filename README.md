# Polarity Predictor
[![CC BY-SA 4.0][cc-by-sa-shield]][cc-by-sa]

This repository is for training the polarity classification model for Japanese language and for building a simple API server as a docker image that can make predictions with the model.

## Test Environment
- Ubuntu 20.04.5 (LTS)
- Python 3.10.8

## Dataset in use
The dataset used are as follows:

- [Twitter日本語評判分析データセット](https://www.db.info.gifu-u.ac.jp/sentiment_analysis/)
- [amazon_polarity](https://huggingface.co/datasets/amazon_polarity)
- [Sentence Polarity Dataset v1.0](https://www.kaggle.com/datasets/nltkdata/sentence-polarity)

This repository doesn't include these data.
If you want to train the model with these datasets, you should place the data as follows:

```
- data/
  - tweet_dataset.csv
  - amazon-polarity.csv
  - rt-polarity.csv
```

## Base Model
The model is based on the pretrained model [nlp_waseda/roberta-base-japanese](https://huggingface.co/nlp-waseda/roberta-base-japanese).

## Training
```sh
$ pip install -r requirements.txt
$ python ./src/main.py
```

## Building & Running
```sh
$ docker build -t polarity_predictor .
$ docker run --name polarity_predictor -d -p 5000:5000 polarity_predictor
```

---
## License
This work is licensed under a
[Creative Commons Attribution-ShareAlike 4.0 International License][cc-by-sa].

[![CC BY-SA 4.0][cc-by-sa-image]][cc-by-sa]

[cc-by-sa]: http://creativecommons.org/licenses/by-sa/4.0/
[cc-by-sa-image]: https://licensebuttons.net/l/by-sa/4.0/88x31.png
[cc-by-sa-shield]: https://img.shields.io/badge/License-CC%20BY--SA%204.0-lightgrey.svg