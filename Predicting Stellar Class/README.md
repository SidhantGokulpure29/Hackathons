# Predicting Stellar Class

Machine learning project for the Kaggle competition **Playground Series - Season 6, Episode 6: Predicting Stellar Class**.

Competition link: https://www.kaggle.com/competitions/playground-series-s6e6

## Overview

The objective is to predict the stellar object class for each row in the test set. This is a multiclass tabular classification task with three possible labels:

- `GALAXY`
- `QSO`
- `STAR`

Kaggle evaluates submissions using **balanced accuracy**, so the solution must perform well across all classes, not only the majority class.

Competition timeline:

- Start date: June 1, 2026
- Final submission deadline: June 30, 2026 at 11:59 PM UTC
- Public leaderboard: approximately 20% of the test data
- Private leaderboard: remaining hidden 80% of the test data

## Dataset

The competition data is inspired by the Stellar Classification Dataset, with synthetic feature distributions close to but not identical to the original source.

Expected Kaggle files:

```text
train.csv
test.csv
sample_submission.csv
```

Main columns:

- `id`: unique row identifier
- `alpha`, `delta`: sky position features
- `u`, `g`, `r`, `i`, `z`: magnitude features
- `redshift`: redshift value
- `spectral_type`: categorical feature
- `galaxy_population`: categorical feature
- `class`: target column in `train.csv`

The generated submission must contain exactly:

```text
id,class
```

## Project Structure

```text
Predicting Stellar Class/
  train.csv
  test.csv
  sample_submission.csv
  requirements.txt
  train_catboost_baseline.py
  train_ensemble_v3.py
  submissions/
  reports/
  models/
```

Generated folders:

- `submissions/`: Kaggle-ready CSV files
- `reports/`: JSON reports with CV scores, fold metrics, parameters, confusion matrices, and selected probability biases
- `models/`: optional saved model files

Large data files and generated outputs are not required to be committed to GitHub.

## Environment Setup

Create a local virtual environment:

```powershell
cd "D:\Notes\All Materials\Hackthons\Predicting Stellar Class"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Dependencies include:

- `pandas`
- `numpy`
- `scikit-learn`
- `catboost`
- `lightgbm`
- `xgboost`
- `optuna`
- `matplotlib`
- `seaborn`

## Training Scripts

### CatBoost Baseline

`train_catboost_baseline.py` trains a CatBoost multiclass model with stratified folds, feature engineering, optional GPU support, class-weight controls, and OOF probability-bias optimization.

Example:

```powershell
.\.venv\Scripts\python.exe train_catboost_baseline.py --folds 5 --iterations 3000 --learning-rate 0.035 --depth 8 --auto-bias
```

### Ensemble V3

`train_ensemble_v3.py` trains a LightGBM/XGBoost/CatBoost ensemble, averages fold probabilities, searches model weights, applies OOF probability-bias optimization, and writes a Kaggle submission.

Best current workflow:

```powershell
.\.venv\Scripts\python.exe train_ensemble_v3.py --models lightgbm,xgboost --folds 5 --iterations 2000 --learning-rate 0.035 --weight-search --weight-search-step 0.05 --auto-bias --bias-search-min 0.50 --bias-search-max 1.70 --bias-search-step 0.05
```

Optional larger model-diversity run:

```powershell
.\.venv\Scripts\python.exe train_ensemble_v3.py --models lightgbm,xgboost,catboost --folds 5 --iterations 2000 --learning-rate 0.035 --weight-search --weight-search-step 0.05 --auto-bias --bias-search-min 0.50 --bias-search-max 1.70 --bias-search-step 0.05
```

## Feature Engineering

The scripts generate compact tabular astronomy features:

- color indices such as `u_g`, `g_r`, `r_i`, `i_z`, `u_r`, `g_i`, `r_z`
- magnitude aggregates such as mean, standard deviation, min, max, and range
- redshift transforms such as clipped redshift and `log1p`
- redshift-color interactions
- sine/cosine transforms for sky coordinates
- categorical handling for `spectral_type` and `galaxy_population`

## Results So Far

Best submitted model:

- Script: `train_ensemble_v3.py`
- Models: LightGBM + XGBoost
- Local OOF balanced accuracy: `0.966189`
- Kaggle public leaderboard score: `0.96722`
- Submission file: `submissions/ensemble_v3_0_966189_20260608_183001.csv`

Best local CV seen so far:

- Local OOF balanced accuracy: `0.966202`
- Submission files:
  - `submissions/ensemble_v3_0_966202_20260611_142515.csv`
  - `submissions/ensemble_v3_0_966202_20260611_221354.csv`
  - `submissions/ensemble_v3_0_966202_20260613_114213.csv`

Baseline history:

- CatBoost smoke test: `0.945500`
- CatBoost 5-fold baseline: `0.963994`
- CatBoost stronger GPU-style run: `0.963208`
- LightGBM/XGBoost ensemble with OOF bias: around `0.9662`

## Submission Workflow

After training finishes, upload the newest valid CSV from:

```text
submissions/
```

Do not upload:

- JSON report files
- notebooks
- `train.csv`
- `test.csv`
- `sample_submission.csv`
- model files

Only upload CSV files with exactly two columns:

```text
id,class
```

## Notes

- Public leaderboard performance can differ from final private leaderboard performance because public scoring uses only about 20% of the test set.
- Local cross-validation is treated as the main guide for model selection.
- The current LightGBM/XGBoost ensemble appears plateaued around `0.9662` local CV.
- Further improvement likely requires additional model diversity, stronger feature engineering, or careful ensemble/seed averaging.
