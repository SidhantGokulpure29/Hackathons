# Predicting Stellar Class

Kaggle Playground Series - Season 6 Episode 6.

This folder contains a reproducible baseline pipeline for predicting stellar object class from tabular astronomy-style features.

The goal is to predict the `class` label for every row in `test.csv`.

Valid labels:

- `GALAXY`
- `QSO`
- `STAR`

Kaggle evaluates submissions with balanced accuracy, so minority-class recall matters. Do not optimize only for normal accuracy.

## Current State

The project already contains the three Kaggle CSV files:

- `train.csv`: training data with target column `class`
- `test.csv`: test data without target labels
- `sample_submission.csv`: required submission shape, `id,class`

A CatBoost baseline pipeline has already been created in:

- `train_catboost_baseline.py`

A quick smoke test has already passed with OOF balanced accuracy `0.945500`, but that run used a small sampled dataset. It proves the pipeline works, but it is not a leaderboard-worthy submission.

A full local 5-fold CatBoost CPU run has also completed:

- OOF balanced accuracy: `0.963994`
- Submission: `submissions/catboost_baseline_0_963994_20260605_142842.csv`
- Decision: do not upload this yet because the target public leaderboard score is around `0.97127`

Full-run per-class recall:

- `GALAXY`: `0.951656`
- `QSO`: `0.975406`
- `STAR`: `0.964919`

Main diagnosis: the model is over-predicting `STAR` for some true `GALAXY` rows. `STAR` recall is good, but `STAR` precision is weak, so the next experiments should recover `GALAXY` recall without damaging `QSO` and `STAR` too much.

A stronger Colab T4 GPU run has also completed:

- Command: `python train_catboost_baseline.py --folds 5 --iterations 5000 --learning-rate 0.025 --depth 9 --task-type GPU --devices 0`
- OOF balanced accuracy: `0.963208`
- Submission: `/content/Predicting Stellar Class/submissions/catboost_baseline_0_963208_20260605_101438.csv`
- Decision: do not upload; this is slightly worse than the local CPU baseline `0.963994`

T4 run per-class recall:

- `GALAXY`: `0.951788`
- `QSO`: `0.974595`
- `STAR`: `0.963239`

T4 confusion matrix, rows=true and cols=pred with labels `['GALAXY', 'QSO', 'STAR']`:

```text
[359281, 5681, 12518]
[1768, 114167, 1208]
[2586, 455, 79683]
```

Current conclusion: simply increasing depth/iterations on GPU did not improve the score. The next change should be targeted model behavior, especially class weighting or probability adjustment for the `GALAXY` vs `STAR` confusion.

Do not upload the smoke-test submission. Also do not upload the current `0.963994` CPU baseline or `0.963208` T4 GPU run unless a leaderboard anchor is explicitly needed.

## Folder Layout

Expected files:

```text
Predicting Stellar Class/
  train.csv
  test.csv
  sample_submission.csv
  train_catboost_baseline.py
  requirements.txt
  README.md
```

Generated output folders:

```text
Predicting Stellar Class/
  submissions/
  reports/
  models/
```

What the outputs mean:

- `submissions/*.csv`: Kaggle submission files. Upload these to Kaggle.
- `reports/*.json`: CV score, fold scores, confusion matrix, features, parameters, and submission path.
- `models/*.cbm`: CatBoost fold models, created only when `--save-models` is used.

## What The Pipeline Does

`train_catboost_baseline.py` does the following:

- Loads `train.csv`, `test.csv`, and `sample_submission.csv`.
- Validates columns, IDs, missing values, target labels, and categorical levels.
- Engineers compact astronomy-style features:
  - color indices such as `u_g`, `g_r`, `r_i`, `i_z`, `u_r`, `g_i`, `r_z`
  - magnitude aggregates such as mean, standard deviation, min, max, and range
  - redshift transforms and redshift-color interactions
  - sine/cosine transforms for sky coordinates
- Keeps `spectral_type` and `galaxy_population` as categorical features for CatBoost.
- Trains CatBoost multiclass models with `StratifiedKFold`.
- Reports balanced accuracy for each fold and overall OOF predictions.
- Averages test probabilities across folds.
- Writes a valid Kaggle submission with columns exactly `id,class`.

## Local Windows Setup

Use a project-local virtual environment. Do not install packages into global Python.

```powershell
cd "D:\Notes\All Materials\Hackthons\Predicting Stellar Class"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run a quick smoke test:

```powershell
.\.venv\Scripts\python.exe train_catboost_baseline.py --quick --folds 3
```

Run the full baseline:

```powershell
.\.venv\Scripts\python.exe train_catboost_baseline.py --folds 5 --iterations 3000
```

Optionally save fold models:

```powershell
.\.venv\Scripts\python.exe train_catboost_baseline.py --folds 5 --iterations 3000 --save-models
```

## Colab / Gemini Handoff

If running in Google Colab, do not upload the local `.venv` folder. Colab should install dependencies fresh.

Important context: Antigravity opened the notebook, but the notebook kernel was running in `/content` and could not see the Windows project folder at `D:\Notes\All Materials\Hackthons\Predicting Stellar Class`. Because of that, the recommended GPU path is to use Google Colab directly, upload/sync the project there, and run with the T4 GPU.

Recommended Colab workflow:

1. Zip and upload the project folder to Google Drive, or upload the files directly to Colab.
2. Exclude generated/local-only folders:
   - `.venv`
   - `__pycache__`
   - old `reports`
   - old `submissions`
3. Make sure these files are available in the Colab project directory:
   - `train.csv`
   - `test.csv`
   - `sample_submission.csv`
   - `train_catboost_baseline.py`
   - `requirements.txt`
   - `Predicting Stellar Class.ipynb`
   - `README.md`
4. In Colab, change into that directory.
5. Install dependencies.
6. Run the full GPU baseline.

Example Colab commands if the folder already exists under `/content`:

```python
%cd /content/Predicting\ Stellar\ Class
!pip install -r requirements.txt
!python train_catboost_baseline.py --folds 5 --iterations 3000
```

If the folder is in Google Drive:

```python
from google.colab import drive
drive.mount("/content/drive")
%cd "/content/drive/MyDrive/Predicting Stellar Class"
!pip install -r requirements.txt
!python train_catboost_baseline.py --folds 5 --iterations 3000
```

If the project was uploaded as a zip in Google Drive:

```python
from google.colab import drive
drive.mount("/content/drive")

!mkdir -p "/content/Predicting Stellar Class"
!unzip -o "/content/drive/MyDrive/Predicting Stellar Class.zip" -d "/content/Predicting Stellar Class"
%cd "/content/Predicting Stellar Class"
!ls -lh
```

Colab GPU note:

- Enable GPU in `Runtime > Change runtime type > GPU`.
- The current script is CPU-compatible and should run as-is.
- To force CatBoost GPU training, run with `--task-type GPU --devices 0`.
- If GPU mode fails in Colab, fall back to CPU rather than changing the data or submission format.

The current Colab GPU is expected to be a T4. A T4 should be faster than the local CPU when running with `--task-type GPU --devices 0`.

## What To Upload

After a full run, upload the newest CSV in:

```text
submissions/
```

The filename will look like:

```text
catboost_baseline_0_xxxxxx_YYYYMMDD_HHMMSS.csv
```

Only upload files with this exact column format:

```text
id,class
577347,STAR
577348,GALAXY
577349,QSO
```

Never change the `id` order. The script already preserves the `sample_submission.csv` order.

## Public vs Private Leaderboard

The public leaderboard uses approximately 20% of the test data. The final leaderboard uses the hidden remaining 80%.

This means:

- Do not overfit to public leaderboard feedback.
- Trust local cross-validation more than one public score.
- Record both local CV score and public LB score for each uploaded submission.
- Prefer robust CV improvements over tiny public LB improvements.

The public top score seen so far is around `0.97127`, but that score is only on the public slice. The final private leaderboard can move.

## Next Best Action

The first full 5-fold baseline has already been run locally and scored `0.963994`. A stronger T4 GPU run scored `0.963208`, so the next best action is targeted class behavior tuning rather than simply adding more iterations/depth.

The script now supports:

- `--task-type CPU/GPU`
- `--devices 0`
- class-weight multipliers: `--galaxy-weight-mult`, `--qso-weight-mult`, `--star-weight-mult`
- prediction probability bias: `--galaxy-proba-bias`, `--qso-proba-bias`, `--star-proba-bias`

The next experiment should reduce false `STAR` predictions for true `GALAXY` rows.

Already tried T4 experiment:

```python
!python train_catboost_baseline.py --folds 5 --iterations 5000 --learning-rate 0.025 --depth 9 --task-type GPU --devices 0
```

Result: `0.963208`, not worth uploading.

Next experiment:

```python
!python train_catboost_baseline.py --folds 5 --iterations 5000 --learning-rate 0.025 --depth 9 --task-type GPU --devices 0 --galaxy-weight-mult 1.12 --star-proba-bias 0.94
```

If this increases `GALAXY` recall but hurts `STAR` too much, try a milder variant:

```python
!python train_catboost_baseline.py --folds 5 --iterations 5000 --learning-rate 0.025 --depth 9 --task-type GPU --devices 0 --galaxy-weight-mult 1.06 --star-proba-bias 0.97
```

The current CPU command still works:

```powershell
.\.venv\Scripts\python.exe train_catboost_baseline.py --folds 5 --iterations 3000
```

Then inspect:

- terminal `OOF balanced accuracy`
- per-fold scores
- `reports/*.json`
- generated CSV in `submissions/`

Decision guide:

- If OOF is around `0.970+`, upload one full-run submission.
- If OOF is `0.965` to `0.970`, upload cautiously, then tune or ensemble.
- If OOF is below `0.965`, improve features/model settings before spending more submissions.

Current decision: do not upload the `0.963994` CPU baseline or the `0.963208` T4 GPU run.

## Working Loop With Codex

This README is the handoff document between Codex locally and Gemini/Colab remotely.

The intended workflow:

1. Codex updates this folder and README locally.
2. User uploads or syncs the updated project folder to Colab.
3. Gemini/Colab runs the experiment using this README and notebook.
4. User sends Codex the terminal output and report JSON.
5. Codex updates the README with the new result and next experiment.

When reporting a Colab run back to Codex, include:

- full command used
- OOF balanced accuracy
- all fold balanced accuracy scores
- per-class precision/recall/F1
- confusion matrix
- class-weight multipliers and probability bias values used
- generated submission filename
- public leaderboard score, only if submitted

Do not upload a Kaggle submission unless the local OOF score or model diversity makes it worth spending a submission.

## Rules And Safety Notes

- Do not use external data unless explicitly approved.
- Do not privately share competition code outside the official Kaggle team.
- Keep submission columns exactly `id,class`.
- Keep labels exactly `GALAXY`, `QSO`, `STAR`.
- Do not hand-label or manually infer test labels.
- Use local CV and private leaderboard robustness as the main strategy.

## Notes For Gemini

You are taking over a Kaggle tabular multiclass classification project in Colab. The important file is `train_catboost_baseline.py`.

Before making changes, read the script and preserve these invariants:

- `sample_submission.csv` ID order must be preserved.
- `class` predictions must be one of `GALAXY`, `QSO`, `STAR`.
- Validation must remain based on balanced accuracy.
- The generated submission must have exactly two columns: `id,class`.
- The first serious run should be the full 5-fold baseline before tuning.

Good next improvements after the full baseline:

- Use the existing CatBoost GPU CLI flags for T4 runs.
- Try seed averaging.
- Try LightGBM and XGBoost variants.
- Ensemble model probabilities.
- Tune CatBoost hyperparameters with Optuna only after the baseline score is known.

Current known best local CV score is `0.963994`. The stronger T4 GPU run scored `0.963208`, so the immediate next implementation should add class-weight adjustment for the `GALAXY` vs `STAR` confusion and compare several controlled variants.
