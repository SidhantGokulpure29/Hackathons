from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sklearn.metrics import balanced_accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold


PROJECT_DIR = Path(__file__).resolve().parent
TRAIN_PATH = PROJECT_DIR / "train.csv"
TEST_PATH = PROJECT_DIR / "test.csv"
SAMPLE_SUBMISSION_PATH = PROJECT_DIR / "sample_submission.csv"
SUBMISSIONS_DIR = PROJECT_DIR / "submissions"
REPORTS_DIR = PROJECT_DIR / "reports"
MODELS_DIR = PROJECT_DIR / "models"

TARGET = "class"
ID_COL = "id"
CLASS_LABELS = ["GALAXY", "QSO", "STAR"]
MAG_COLS = ["u", "g", "r", "i", "z"]
CAT_COLS = ["spectral_type", "galaxy_population"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a CatBoost stellar class baseline.")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--seeds", default=None, help="Comma-separated seeds for seed averaging, e.g. 42,777,2026.")
    parser.add_argument("--iterations", type=int, default=3000)
    parser.add_argument("--learning-rate", type=float, default=0.035)
    parser.add_argument("--depth", type=int, default=8)
    parser.add_argument("--l2-leaf-reg", type=float, default=5.0)
    parser.add_argument("--early-stopping-rounds", type=int, default=200)
    parser.add_argument("--thread-count", type=int, default=-1)
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--devices", default=None, help="GPU device id, for example 0 in Colab.")
    parser.add_argument("--galaxy-weight-mult", type=float, default=1.0)
    parser.add_argument("--qso-weight-mult", type=float, default=1.0)
    parser.add_argument("--star-weight-mult", type=float, default=1.0)
    parser.add_argument("--galaxy-proba-bias", type=float, default=1.0)
    parser.add_argument("--qso-proba-bias", type=float, default=1.0)
    parser.add_argument("--star-proba-bias", type=float, default=1.0)
    parser.add_argument("--auto-bias", action="store_true", help="Search OOF probability bias after training.")
    parser.add_argument("--bias-search-min", type=float, default=0.80)
    parser.add_argument("--bias-search-max", type=float, default=1.20)
    parser.add_argument("--bias-search-step", type=float, default=0.02)
    parser.add_argument("--save-models", action="store_true")
    parser.add_argument("--save-oof", action="store_true")
    parser.add_argument("--quick", action="store_true", help="Run a fast smoke test on a balanced sample.")
    return parser.parse_args()


def ensure_dirs() -> None:
    for path in [SUBMISSIONS_DIR, REPORTS_DIR, MODELS_DIR]:
        path.mkdir(exist_ok=True)


def parse_seeds(args: argparse.Namespace) -> list[int]:
    if args.seeds is None:
        return [args.seed]
    seeds = [int(seed.strip()) for seed in args.seeds.split(",") if seed.strip()]
    if not seeds:
        raise ValueError("--seeds was provided but no valid seed values were found.")
    return seeds


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = pd.read_csv(TRAIN_PATH)
    test = pd.read_csv(TEST_PATH)
    sample_submission = pd.read_csv(SAMPLE_SUBMISSION_PATH)
    return train, test, sample_submission


def validate_raw_data(train: pd.DataFrame, test: pd.DataFrame, sample_submission: pd.DataFrame) -> None:
    required_train_cols = {ID_COL, TARGET, *MAG_COLS, "alpha", "delta", "redshift", *CAT_COLS}
    required_test_cols = required_train_cols - {TARGET}
    if not required_train_cols.issubset(train.columns):
        raise ValueError(f"train.csv missing columns: {sorted(required_train_cols - set(train.columns))}")
    if not required_test_cols.issubset(test.columns):
        raise ValueError(f"test.csv missing columns: {sorted(required_test_cols - set(test.columns))}")
    if train[ID_COL].duplicated().any() or test[ID_COL].duplicated().any():
        raise ValueError("Duplicate ids found.")
    if train.isna().any().any() or test.isna().any().any():
        raise ValueError("Missing values found.")
    if sorted(train[TARGET].unique()) != sorted(CLASS_LABELS):
        raise ValueError(f"Unexpected target labels: {sorted(train[TARGET].unique())}")
    if not sample_submission[ID_COL].equals(test[ID_COL]):
        raise ValueError("sample_submission ids do not match test ids.")
    for col in CAT_COLS:
        train_levels = set(train[col].unique())
        test_levels = set(test[col].unique())
        if train_levels != test_levels:
            raise ValueError(f"Category mismatch in {col}: train={train_levels}, test={test_levels}")


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["u_g"] = out["u"] - out["g"]
    out["g_r"] = out["g"] - out["r"]
    out["r_i"] = out["r"] - out["i"]
    out["i_z"] = out["i"] - out["z"]
    out["u_r"] = out["u"] - out["r"]
    out["g_i"] = out["g"] - out["i"]
    out["r_z"] = out["r"] - out["z"]
    out["u_z"] = out["u"] - out["z"]
    out["g_z"] = out["g"] - out["z"]

    mags = out[MAG_COLS]
    out["mag_mean"] = mags.mean(axis=1)
    out["mag_std"] = mags.std(axis=1)
    out["mag_min"] = mags.min(axis=1)
    out["mag_max"] = mags.max(axis=1)
    out["mag_range"] = out["mag_max"] - out["mag_min"]

    redshift_clipped = out["redshift"].clip(lower=0)
    out["redshift_clipped"] = redshift_clipped
    out["redshift_log1p"] = np.log1p(redshift_clipped)
    out["redshift_abs"] = out["redshift"].abs()
    out["redshift_x_u_g"] = out["redshift"] * out["u_g"]
    out["redshift_x_g_r"] = out["redshift"] * out["g_r"]
    out["redshift_x_r_i"] = out["redshift"] * out["r_i"]
    out["redshift_x_i_z"] = out["redshift"] * out["i_z"]

    out["alpha_sin"] = np.sin(np.deg2rad(out["alpha"]))
    out["alpha_cos"] = np.cos(np.deg2rad(out["alpha"]))
    out["delta_sin"] = np.sin(np.deg2rad(out["delta"]))
    out["delta_cos"] = np.cos(np.deg2rad(out["delta"]))
    return out


def prepare_features(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[int]]:
    train_fe = add_features(train)
    test_fe = add_features(test)
    feature_cols = [col for col in test_fe.columns if col != ID_COL]
    train_feature_cols = [col for col in train_fe.columns if col not in [ID_COL, TARGET]]
    if feature_cols != train_feature_cols:
        raise ValueError("Feature columns do not align between train and test.")
    cat_feature_indices = [feature_cols.index(col) for col in CAT_COLS]
    x_train = train_fe[feature_cols].replace([np.inf, -np.inf], np.nan)
    x_test = test_fe[feature_cols].replace([np.inf, -np.inf], np.nan)
    if x_train.isna().any().any() or x_test.isna().any().any():
        raise ValueError("Feature engineering introduced null or infinite values.")
    return x_train, x_test, feature_cols, cat_feature_indices


def class_weights(y: pd.Series, args: argparse.Namespace) -> list[float]:
    counts = y.value_counts().reindex(CLASS_LABELS)
    weights = len(y) / (len(CLASS_LABELS) * counts)
    multipliers = pd.Series(
        {
            "GALAXY": args.galaxy_weight_mult,
            "QSO": args.qso_weight_mult,
            "STAR": args.star_weight_mult,
        }
    )
    weights = weights * multipliers.reindex(CLASS_LABELS)
    return weights.to_list()


def manual_bias(args: argparse.Namespace) -> np.ndarray:
    return np.array(
        [args.galaxy_proba_bias, args.qso_proba_bias, args.star_proba_bias],
        dtype=np.float32,
    )


def apply_proba_bias(proba: np.ndarray, bias: np.ndarray) -> np.ndarray:
    adjusted = proba * bias
    row_sums = adjusted.sum(axis=1, keepdims=True)
    return adjusted / row_sums


def label_indices(y: pd.Series) -> np.ndarray:
    label_to_idx = {label: idx for idx, label in enumerate(CLASS_LABELS)}
    return y.map(label_to_idx).to_numpy(dtype=np.int32)


def balanced_accuracy_from_indices(y_true_idx: np.ndarray, y_pred_idx: np.ndarray) -> float:
    n_classes = len(CLASS_LABELS)
    flat = y_true_idx * n_classes + y_pred_idx
    matrix = np.bincount(flat, minlength=n_classes * n_classes).reshape(n_classes, n_classes)
    supports = matrix.sum(axis=1)
    recalls = np.divide(
        np.diag(matrix),
        supports,
        out=np.zeros(n_classes, dtype=np.float64),
        where=supports != 0,
    )
    return float(recalls.mean())


def bias_values(args: argparse.Namespace) -> np.ndarray:
    count = int(round((args.bias_search_max - args.bias_search_min) / args.bias_search_step)) + 1
    return np.round(args.bias_search_min + np.arange(count) * args.bias_search_step, 6)


def optimize_bias(oof_proba: np.ndarray, y: pd.Series, args: argparse.Namespace) -> tuple[np.ndarray, float]:
    if not args.auto_bias:
        bias = manual_bias(args)
        pred_idx = apply_proba_bias(oof_proba, bias).argmax(axis=1)
        score = balanced_accuracy_from_indices(label_indices(y), pred_idx)
        return bias, score

    y_idx = label_indices(y)
    values = bias_values(args)
    qso_bias = args.qso_proba_bias
    best_score = -1.0
    best_bias = manual_bias(args)

    print("")
    print("Searching OOF probability bias...")
    print(f"Galaxy/star grid: {args.bias_search_min:.3f} to {args.bias_search_max:.3f} step {args.bias_search_step:.3f}")
    print(f"QSO bias fixed at {qso_bias:.3f}")

    for galaxy_bias in values:
        for star_bias in values:
            bias = np.array([galaxy_bias, qso_bias, star_bias], dtype=np.float32)
            pred_idx = apply_proba_bias(oof_proba, bias).argmax(axis=1)
            score = balanced_accuracy_from_indices(y_idx, pred_idx)
            if score > best_score:
                best_score = score
                best_bias = bias

    print(
        "Best OOF bias: "
        f"GALAXY={best_bias[0]:.4f}, QSO={best_bias[1]:.4f}, STAR={best_bias[2]:.4f}, "
        f"balanced_accuracy={best_score:.6f}"
    )
    return best_bias, best_score


def validate_submission(submission: pd.DataFrame, sample_submission: pd.DataFrame) -> None:
    if list(submission.columns) != [ID_COL, TARGET]:
        raise ValueError("Submission columns must be exactly id,class.")
    if len(submission) != len(sample_submission):
        raise ValueError("Submission row count does not match sample submission.")
    if not submission[ID_COL].equals(sample_submission[ID_COL]):
        raise ValueError("Submission ids do not match sample submission.")
    if not set(submission[TARGET].unique()).issubset(CLASS_LABELS):
        raise ValueError("Submission contains unexpected class labels.")


def train_model(args: argparse.Namespace) -> None:
    ensure_dirs()
    train, test, sample_submission = load_data()
    validate_raw_data(train, test, sample_submission)

    if args.quick:
        train = train.groupby(TARGET, group_keys=False).sample(n=4000, random_state=args.seed)
        args.iterations = min(args.iterations, 300)
        args.early_stopping_rounds = min(args.early_stopping_rounds, 50)

    seeds = parse_seeds(args)
    x_train, x_test, feature_cols, cat_feature_indices = prepare_features(train, test)
    y = train[TARGET]

    oof_proba = np.zeros((len(x_train), len(CLASS_LABELS)), dtype=np.float32)
    test_proba = np.zeros((len(x_test), len(CLASS_LABELS)), dtype=np.float32)
    fold_reports = []
    raw_fold_scores = []

    base_params = {
        "loss_function": "MultiClass",
        "eval_metric": "Accuracy",
        "iterations": args.iterations,
        "learning_rate": args.learning_rate,
        "depth": args.depth,
        "l2_leaf_reg": args.l2_leaf_reg,
        "class_names": CLASS_LABELS,
        "class_weights": class_weights(y, args),
        "thread_count": args.thread_count,
        "allow_writing_files": False,
        "verbose": 100,
        "task_type": args.task_type,
    }
    if args.task_type == "GPU" and args.devices is not None:
        base_params["devices"] = args.devices

    for seed in seeds:
        print("")
        print(f"Starting seed {seed}")
        seed_oof = np.zeros((len(x_train), len(CLASS_LABELS)), dtype=np.float32)
        folds = StratifiedKFold(n_splits=args.folds, shuffle=True, random_state=seed)
        params = {**base_params, "random_seed": seed}

        for fold, (train_idx, valid_idx) in enumerate(folds.split(x_train, y), start=1):
            print("")
            print(f"Seed {seed} fold {fold}/{args.folds}")
            train_pool = Pool(x_train.iloc[train_idx], y.iloc[train_idx], cat_features=cat_feature_indices)
            valid_pool = Pool(x_train.iloc[valid_idx], y.iloc[valid_idx], cat_features=cat_feature_indices)
            test_pool = Pool(x_test, cat_features=cat_feature_indices)

            model = CatBoostClassifier(**params)
            model.fit(
                train_pool,
                eval_set=valid_pool,
                use_best_model=True,
                early_stopping_rounds=args.early_stopping_rounds,
            )

            valid_proba = model.predict_proba(valid_pool)
            fold_pred = np.array(CLASS_LABELS)[valid_proba.argmax(axis=1)]
            fold_score = balanced_accuracy_score(y.iloc[valid_idx], fold_pred)
            print(f"Seed {seed} fold {fold} raw balanced accuracy: {fold_score:.6f}")

            seed_oof[valid_idx] = valid_proba
            test_proba += model.predict_proba(test_pool) / (len(seeds) * args.folds)
            raw_fold_scores.append(fold_score)
            fold_reports.append(
                {
                    "seed": seed,
                    "fold": fold,
                    "raw_balanced_accuracy": float(fold_score),
                    "best_iteration": model.best_iteration_,
                }
            )

            if args.save_models:
                model.save_model(MODELS_DIR / f"catboost_seed{seed}_fold{fold}.cbm")

        oof_proba += seed_oof / len(seeds)

    raw_oof_pred = np.array(CLASS_LABELS)[oof_proba.argmax(axis=1)]
    raw_oof_score = balanced_accuracy_score(y, raw_oof_pred)

    best_bias, biased_oof_score = optimize_bias(oof_proba, y, args)
    biased_oof_proba = apply_proba_bias(oof_proba, best_bias)
    biased_test_proba = apply_proba_bias(test_proba, best_bias)
    oof_pred = np.array(CLASS_LABELS)[biased_oof_proba.argmax(axis=1)]

    if not set(oof_pred).issubset(CLASS_LABELS):
        raise ValueError("OOF predictions contain unexpected labels.")

    cv_score = balanced_accuracy_score(y, oof_pred)
    if abs(cv_score - biased_oof_score) > 1e-12:
        raise ValueError("Internal bias score check failed.")

    report = classification_report(y, oof_pred, labels=CLASS_LABELS, output_dict=True, zero_division=0)
    matrix = confusion_matrix(y, oof_pred, labels=CLASS_LABELS)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    score_tag = f"{cv_score:.6f}".replace(".", "_")

    test_pred = np.array(CLASS_LABELS)[biased_test_proba.argmax(axis=1)]
    submission = pd.DataFrame({ID_COL: sample_submission[ID_COL], TARGET: test_pred})
    validate_submission(submission, sample_submission)

    submission_path = SUBMISSIONS_DIR / f"catboost_v2_{score_tag}_{timestamp}.csv"
    submission.to_csv(submission_path, index=False)

    oof_path = None
    if args.save_oof:
        oof_path = REPORTS_DIR / f"catboost_v2_oof_{score_tag}_{timestamp}.csv"
        oof_df = pd.DataFrame(oof_proba, columns=[f"proba_{label}" for label in CLASS_LABELS])
        oof_df.insert(0, ID_COL, train[ID_COL].to_numpy())
        oof_df.insert(1, TARGET, y.to_numpy())
        oof_df["prediction"] = oof_pred
        oof_df.to_csv(oof_path, index=False)

    report_payload = {
        "cv_balanced_accuracy": float(cv_score),
        "raw_oof_balanced_accuracy": float(raw_oof_score),
        "mean_raw_fold_balanced_accuracy": float(np.mean(raw_fold_scores)),
        "folds": fold_reports,
        "class_labels": CLASS_LABELS,
        "classification_report": report,
        "confusion_matrix": matrix.tolist(),
        "feature_count": len(feature_cols),
        "features": feature_cols,
        "cat_features": CAT_COLS,
        "params": base_params,
        "seeds": seeds,
        "class_weight_multipliers": {
            "GALAXY": args.galaxy_weight_mult,
            "QSO": args.qso_weight_mult,
            "STAR": args.star_weight_mult,
        },
        "manual_proba_bias": {
            "GALAXY": args.galaxy_proba_bias,
            "QSO": args.qso_proba_bias,
            "STAR": args.star_proba_bias,
        },
        "selected_proba_bias": {
            "GALAXY": float(best_bias[0]),
            "QSO": float(best_bias[1]),
            "STAR": float(best_bias[2]),
        },
        "auto_bias": args.auto_bias,
        "submission": str(submission_path),
        "oof": str(oof_path) if oof_path is not None else None,
    }
    report_path = REPORTS_DIR / f"catboost_v2_{score_tag}_{timestamp}.json"
    report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

    print("")
    print(f"Raw OOF balanced accuracy: {raw_oof_score:.6f}")
    print(f"Final OOF balanced accuracy: {cv_score:.6f}")
    print(
        "Selected probability bias: "
        f"GALAXY={best_bias[0]:.4f}, QSO={best_bias[1]:.4f}, STAR={best_bias[2]:.4f}"
    )
    print(f"Submission saved to: {submission_path}")
    print(f"Report saved to: {report_path}")
    if oof_path is not None:
        print(f"OOF probabilities saved to: {oof_path}")


if __name__ == "__main__":
    train_model(parse_args())
