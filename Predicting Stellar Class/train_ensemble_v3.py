from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
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
LABEL_TO_ID = {label: idx for idx, label in enumerate(CLASS_LABELS)}
ID_TO_LABEL = np.array(CLASS_LABELS)
MAG_COLS = ["u", "g", "r", "i", "z"]
CAT_COLS = ["spectral_type", "galaxy_population"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a diverse stellar-class ensemble.")
    parser.add_argument("--models", default="lightgbm,xgboost", help="Comma-separated: lightgbm,xgboost,catboost.")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--iterations", type=int, default=2500)
    parser.add_argument("--learning-rate", type=float, default=0.035)
    parser.add_argument("--early-stopping-rounds", type=int, default=150)
    parser.add_argument("--thread-count", type=int, default=-1)
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--devices", default=None)
    parser.add_argument("--lgb-num-leaves", type=int, default=128)
    parser.add_argument("--xgb-max-depth", type=int, default=8)
    parser.add_argument("--xgb-min-child-weight", type=float, default=6.0)
    parser.add_argument("--galaxy-weight-mult", type=float, default=1.0)
    parser.add_argument("--qso-weight-mult", type=float, default=1.0)
    parser.add_argument("--star-weight-mult", type=float, default=1.0)
    parser.add_argument("--weight-search", action="store_true", help="Search model ensemble weights on OOF.")
    parser.add_argument("--weight-search-step", type=float, default=0.05)
    parser.add_argument("--auto-bias", action="store_true")
    parser.add_argument("--bias-search-min", type=float, default=0.80)
    parser.add_argument("--bias-search-max", type=float, default=1.20)
    parser.add_argument("--bias-search-step", type=float, default=0.02)
    parser.add_argument("--quick", action="store_true")
    return parser.parse_args()


def ensure_dirs() -> None:
    for path in [SUBMISSIONS_DIR, REPORTS_DIR, MODELS_DIR]:
        path.mkdir(exist_ok=True)


def selected_models(args: argparse.Namespace) -> list[str]:
    models = [model.strip().lower() for model in args.models.split(",") if model.strip()]
    valid = {"lightgbm", "xgboost", "catboost"}
    unknown = sorted(set(models) - valid)
    if unknown:
        raise ValueError(f"Unknown models: {unknown}. Valid models: {sorted(valid)}")
    if not models:
        raise ValueError("At least one model must be selected.")
    return models


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return pd.read_csv(TRAIN_PATH), pd.read_csv(TEST_PATH), pd.read_csv(SAMPLE_SUBMISSION_PATH)


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
        if set(train[col].unique()) != set(test[col].unique()):
            raise ValueError(f"Category mismatch in {col}.")


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
    out["u_i"] = out["u"] - out["i"]
    out["g_z_over_u_z"] = out["g_z"] / (out["u_z"].abs() + 1e-6)

    mags = out[MAG_COLS]
    out["mag_mean"] = mags.mean(axis=1)
    out["mag_std"] = mags.std(axis=1)
    out["mag_min"] = mags.min(axis=1)
    out["mag_max"] = mags.max(axis=1)
    out["mag_range"] = out["mag_max"] - out["mag_min"]
    out["mag_skew_proxy"] = out["mag_mean"] - out["r"]

    redshift_clipped = out["redshift"].clip(lower=0)
    out["redshift_clipped"] = redshift_clipped
    out["redshift_log1p"] = np.log1p(redshift_clipped)
    out["redshift_abs"] = out["redshift"].abs()
    out["redshift_x_u_g"] = out["redshift"] * out["u_g"]
    out["redshift_x_g_r"] = out["redshift"] * out["g_r"]
    out["redshift_x_r_i"] = out["redshift"] * out["r_i"]
    out["redshift_x_i_z"] = out["redshift"] * out["i_z"]
    out["redshift_x_mag_range"] = out["redshift"] * out["mag_range"]

    out["alpha_sin"] = np.sin(np.deg2rad(out["alpha"]))
    out["alpha_cos"] = np.cos(np.deg2rad(out["alpha"]))
    out["delta_sin"] = np.sin(np.deg2rad(out["delta"]))
    out["delta_cos"] = np.cos(np.deg2rad(out["delta"]))
    return out


def prepare_features(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    train_fe = add_features(train)
    test_fe = add_features(test)
    feature_cols = [col for col in test_fe.columns if col != ID_COL]
    train_feature_cols = [col for col in train_fe.columns if col not in [ID_COL, TARGET]]
    if feature_cols != train_feature_cols:
        raise ValueError("Feature columns do not align between train and test.")
    x_train = train_fe[feature_cols].replace([np.inf, -np.inf], np.nan)
    x_test = test_fe[feature_cols].replace([np.inf, -np.inf], np.nan)
    if x_train.isna().any().any() or x_test.isna().any().any():
        raise ValueError("Feature engineering introduced null or infinite values.")
    return x_train, x_test, feature_cols


def class_weight_map(args: argparse.Namespace) -> dict[int, float]:
    return {
        LABEL_TO_ID["GALAXY"]: args.galaxy_weight_mult,
        LABEL_TO_ID["QSO"]: args.qso_weight_mult,
        LABEL_TO_ID["STAR"]: args.star_weight_mult,
    }


def sample_weights(y_encoded: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    counts = np.bincount(y_encoded, minlength=len(CLASS_LABELS))
    base_weights = len(y_encoded) / (len(CLASS_LABELS) * counts)
    multipliers = np.array(
        [args.galaxy_weight_mult, args.qso_weight_mult, args.star_weight_mult],
        dtype=np.float32,
    )
    return base_weights[y_encoded] * multipliers[y_encoded]


def categorical_for_tree_models(x_train: pd.DataFrame, x_test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_out = x_train.copy()
    test_out = x_test.copy()
    for col in CAT_COLS:
        categories = sorted(set(train_out[col].unique()) | set(test_out[col].unique()))
        train_out[col] = pd.Categorical(train_out[col], categories=categories)
        test_out[col] = pd.Categorical(test_out[col], categories=categories)
    return train_out, test_out


def fit_predict_lightgbm(
    x_train: pd.DataFrame,
    y_train: np.ndarray,
    x_valid: pd.DataFrame,
    y_valid: np.ndarray,
    x_test: pd.DataFrame,
    weights: np.ndarray,
    args: argparse.Namespace,
) -> tuple[np.ndarray, np.ndarray, int | None]:
    import lightgbm as lgb

    train_lgb, test_lgb = categorical_for_tree_models(pd.concat([x_train, x_valid]), x_test)
    train_part = train_lgb.iloc[: len(x_train)]
    valid_part = train_lgb.iloc[len(x_train) :]

    model = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=len(CLASS_LABELS),
        n_estimators=args.iterations,
        learning_rate=args.learning_rate,
        num_leaves=args.lgb_num_leaves,
        max_depth=-1,
        min_child_samples=35,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_alpha=0.05,
        reg_lambda=2.0,
        random_state=args.seed,
        n_jobs=args.thread_count,
        verbosity=-1,
    )
    model.fit(
        train_part,
        y_train,
        sample_weight=weights,
        eval_set=[(valid_part, y_valid)],
        eval_metric="multi_logloss",
        categorical_feature=CAT_COLS,
        callbacks=[lgb.early_stopping(args.early_stopping_rounds), lgb.log_evaluation(100)],
    )
    return model.predict_proba(valid_part), model.predict_proba(test_lgb), model.best_iteration_


def fit_predict_xgboost(
    x_train: pd.DataFrame,
    y_train: np.ndarray,
    x_valid: pd.DataFrame,
    y_valid: np.ndarray,
    x_test: pd.DataFrame,
    weights: np.ndarray,
    args: argparse.Namespace,
) -> tuple[np.ndarray, np.ndarray, int | None]:
    from xgboost import XGBClassifier

    train_xgb, test_xgb = categorical_for_tree_models(pd.concat([x_train, x_valid]), x_test)
    train_part = train_xgb.iloc[: len(x_train)]
    valid_part = train_xgb.iloc[len(x_train) :]

    tree_method = "hist"
    device = "cuda" if args.task_type == "GPU" else "cpu"
    model = XGBClassifier(
        objective="multi:softprob",
        num_class=len(CLASS_LABELS),
        n_estimators=args.iterations,
        learning_rate=args.learning_rate,
        max_depth=args.xgb_max_depth,
        min_child_weight=args.xgb_min_child_weight,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_alpha=0.05,
        reg_lambda=2.0,
        random_state=args.seed,
        n_jobs=args.thread_count,
        tree_method=tree_method,
        device=device,
        enable_categorical=True,
        eval_metric="mlogloss",
        early_stopping_rounds=args.early_stopping_rounds,
    )
    model.fit(
        train_part,
        y_train,
        sample_weight=weights,
        eval_set=[(valid_part, y_valid)],
        verbose=100,
    )
    best_iteration = getattr(model, "best_iteration", None)
    return model.predict_proba(valid_part), model.predict_proba(test_xgb), best_iteration


def fit_predict_catboost(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_valid: pd.DataFrame,
    y_valid: pd.Series,
    x_test: pd.DataFrame,
    args: argparse.Namespace,
) -> tuple[np.ndarray, np.ndarray, int | None]:
    from catboost import CatBoostClassifier, Pool

    cat_feature_indices = [x_train.columns.tolist().index(col) for col in CAT_COLS]
    params = {
        "loss_function": "MultiClass",
        "eval_metric": "Accuracy",
        "iterations": args.iterations,
        "learning_rate": args.learning_rate,
        "depth": 8,
        "l2_leaf_reg": 5.0,
        "random_seed": args.seed,
        "class_names": CLASS_LABELS,
        "class_weights": [
            args.galaxy_weight_mult,
            args.qso_weight_mult,
            args.star_weight_mult,
        ],
        "thread_count": args.thread_count,
        "allow_writing_files": False,
        "verbose": 100,
        "task_type": args.task_type,
    }
    if args.task_type == "GPU" and args.devices is not None:
        params["devices"] = args.devices

    train_pool = Pool(x_train, y_train, cat_features=cat_feature_indices)
    valid_pool = Pool(x_valid, y_valid, cat_features=cat_feature_indices)
    test_pool = Pool(x_test, cat_features=cat_feature_indices)
    model = CatBoostClassifier(**params)
    model.fit(
        train_pool,
        eval_set=valid_pool,
        use_best_model=True,
        early_stopping_rounds=args.early_stopping_rounds,
    )
    return model.predict_proba(valid_pool), model.predict_proba(test_pool), model.best_iteration_


def apply_proba_bias(proba: np.ndarray, bias: np.ndarray) -> np.ndarray:
    adjusted = proba * bias
    return adjusted / adjusted.sum(axis=1, keepdims=True)


def balanced_accuracy_from_indices(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    n_classes = len(CLASS_LABELS)
    flat = y_true * n_classes + y_pred
    matrix = np.bincount(flat, minlength=n_classes * n_classes).reshape(n_classes, n_classes)
    supports = matrix.sum(axis=1)
    recalls = np.divide(np.diag(matrix), supports, out=np.zeros(n_classes), where=supports != 0)
    return float(recalls.mean())


def optimize_bias(oof_proba: np.ndarray, y_encoded: np.ndarray, args: argparse.Namespace) -> tuple[np.ndarray, float]:
    if not args.auto_bias:
        bias = np.ones(len(CLASS_LABELS), dtype=np.float32)
        return bias, balanced_accuracy_from_indices(y_encoded, oof_proba.argmax(axis=1))

    values = np.round(
        np.arange(args.bias_search_min, args.bias_search_max + args.bias_search_step / 2, args.bias_search_step),
        6,
    )
    best_score = -1.0
    best_bias = np.ones(len(CLASS_LABELS), dtype=np.float32)

    print("")
    print("Searching ensemble OOF probability bias...")
    for galaxy_bias in values:
        for qso_bias in values:
            for star_bias in values:
                bias = np.array([galaxy_bias, qso_bias, star_bias], dtype=np.float32)
                pred = apply_proba_bias(oof_proba, bias).argmax(axis=1)
                score = balanced_accuracy_from_indices(y_encoded, pred)
                if score > best_score:
                    best_score = score
                    best_bias = bias

    print(
        "Best bias: "
        f"GALAXY={best_bias[0]:.4f}, QSO={best_bias[1]:.4f}, STAR={best_bias[2]:.4f}, "
        f"balanced_accuracy={best_score:.6f}"
    )
    return best_bias, best_score


def weight_candidates(n_models: int, step: float) -> list[np.ndarray]:
    if n_models == 1:
        return [np.ones(1, dtype=np.float32)]
    values = np.round(np.arange(0.0, 1.0 + step / 2, step), 6)
    candidates = []
    if n_models == 2:
        for first in values:
            candidates.append(np.array([first, 1.0 - first], dtype=np.float32))
        return candidates
    if n_models == 3:
        for first in values:
            for second in values:
                third = 1.0 - first - second
                if third < -1e-9:
                    continue
                candidates.append(np.array([first, second, max(0.0, third)], dtype=np.float32))
        return candidates
    raise ValueError("Weight search supports up to 3 models.")


def combine_model_probabilities(model_probas: dict[str, np.ndarray], models: list[str], weights: np.ndarray) -> np.ndarray:
    combined = np.zeros_like(model_probas[models[0]], dtype=np.float32)
    for model_name, weight in zip(models, weights):
        combined += model_probas[model_name] * weight
    return combined


def optimize_model_weights(
    model_oof: dict[str, np.ndarray],
    y_encoded: np.ndarray,
    models: list[str],
    args: argparse.Namespace,
) -> tuple[np.ndarray, float]:
    if not args.weight_search or len(models) == 1:
        weights = np.ones(len(models), dtype=np.float32) / len(models)
        proba = combine_model_probabilities(model_oof, models, weights)
        score = balanced_accuracy_from_indices(y_encoded, proba.argmax(axis=1))
        return weights, score

    best_score = -1.0
    best_weights = np.ones(len(models), dtype=np.float32) / len(models)
    print("")
    print("Searching model ensemble weights...")
    for weights in weight_candidates(len(models), args.weight_search_step):
        proba = combine_model_probabilities(model_oof, models, weights)
        score = balanced_accuracy_from_indices(y_encoded, proba.argmax(axis=1))
        if score > best_score:
            best_score = score
            best_weights = weights

    weight_text = ", ".join(f"{model}={weight:.3f}" for model, weight in zip(models, best_weights))
    print(f"Best model weights: {weight_text}, raw_balanced_accuracy={best_score:.6f}")
    return best_weights, best_score


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
    models = selected_models(args)

    if args.quick:
        train = train.groupby(TARGET, group_keys=False).sample(n=5000, random_state=args.seed)
        args.iterations = min(args.iterations, 300)
        args.early_stopping_rounds = min(args.early_stopping_rounds, 50)

    x_train, x_test, feature_cols = prepare_features(train, test)
    y = train[TARGET]
    y_encoded = y.map(LABEL_TO_ID).to_numpy(dtype=np.int32)
    weights = sample_weights(y_encoded, args)

    model_oof = {model_name: np.zeros((len(x_train), len(CLASS_LABELS)), dtype=np.float32) for model_name in models}
    model_test = {model_name: np.zeros((len(x_test), len(CLASS_LABELS)), dtype=np.float32) for model_name in models}
    fold_reports = []

    folds = StratifiedKFold(n_splits=args.folds, shuffle=True, random_state=args.seed)
    for fold, (train_idx, valid_idx) in enumerate(folds.split(x_train, y), start=1):
        print("")
        print(f"Fold {fold}/{args.folds}")

        fold_oof = np.zeros((len(valid_idx), len(CLASS_LABELS)), dtype=np.float32)

        x_tr = x_train.iloc[train_idx]
        x_va = x_train.iloc[valid_idx]
        y_tr_encoded = y_encoded[train_idx]
        y_va_encoded = y_encoded[valid_idx]
        y_tr_labels = y.iloc[train_idx]
        y_va_labels = y.iloc[valid_idx]
        fold_weights = weights[train_idx]

        for model_name in models:
            print("")
            print(f"Training {model_name} fold {fold}")
            if model_name == "lightgbm":
                valid_proba, test_fold_proba, best_iteration = fit_predict_lightgbm(
                    x_tr, y_tr_encoded, x_va, y_va_encoded, x_test, fold_weights, args
                )
            elif model_name == "xgboost":
                valid_proba, test_fold_proba, best_iteration = fit_predict_xgboost(
                    x_tr, y_tr_encoded, x_va, y_va_encoded, x_test, fold_weights, args
                )
            elif model_name == "catboost":
                valid_proba, test_fold_proba, best_iteration = fit_predict_catboost(
                    x_tr, y_tr_labels, x_va, y_va_labels, x_test, args
                )
            else:
                raise ValueError(f"Unsupported model: {model_name}")

            pred = valid_proba.argmax(axis=1)
            score = balanced_accuracy_from_indices(y_va_encoded, pred)
            print(f"{model_name} fold {fold} balanced accuracy: {score:.6f}")
            fold_reports.append(
                {
                    "fold": fold,
                    "model": model_name,
                    "balanced_accuracy": float(score),
                    "best_iteration": None if best_iteration is None else int(best_iteration),
                }
            )
            model_oof[model_name][valid_idx] = valid_proba
            model_test[model_name] += test_fold_proba / args.folds
            fold_oof += valid_proba / len(models)

        ensemble_pred = fold_oof.argmax(axis=1)
        ensemble_score = balanced_accuracy_from_indices(y_va_encoded, ensemble_pred)
        print(f"Ensemble fold {fold} raw balanced accuracy: {ensemble_score:.6f}")
        fold_reports.append(
            {
                "fold": fold,
                "model": "ensemble",
                "balanced_accuracy": float(ensemble_score),
                "best_iteration": None,
            }
        )

    model_weights, raw_score = optimize_model_weights(model_oof, y_encoded, models, args)
    oof_proba = combine_model_probabilities(model_oof, models, model_weights)
    test_proba = combine_model_probabilities(model_test, models, model_weights)
    best_bias, final_score = optimize_bias(oof_proba, y_encoded, args)
    final_oof = apply_proba_bias(oof_proba, best_bias)
    final_test = apply_proba_bias(test_proba, best_bias)
    final_pred = final_oof.argmax(axis=1)
    final_labels = ID_TO_LABEL[final_pred]

    cv_score = balanced_accuracy_score(y, final_labels)
    if abs(cv_score - final_score) > 1e-12:
        raise ValueError("Internal final score check failed.")

    report = classification_report(y, final_labels, labels=CLASS_LABELS, output_dict=True, zero_division=0)
    matrix = confusion_matrix(y, final_labels, labels=CLASS_LABELS)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    score_tag = f"{cv_score:.6f}".replace(".", "_")
    submission = pd.DataFrame({ID_COL: sample_submission[ID_COL], TARGET: ID_TO_LABEL[final_test.argmax(axis=1)]})
    validate_submission(submission, sample_submission)
    submission_path = SUBMISSIONS_DIR / f"ensemble_v3_{score_tag}_{timestamp}.csv"
    submission.to_csv(submission_path, index=False)

    report_payload = {
        "cv_balanced_accuracy": float(cv_score),
        "raw_oof_balanced_accuracy": float(raw_score),
        "models": models,
        "model_weights": {model: float(weight) for model, weight in zip(models, model_weights)},
        "folds": fold_reports,
        "class_labels": CLASS_LABELS,
        "classification_report": report,
        "confusion_matrix": matrix.tolist(),
        "feature_count": len(feature_cols),
        "features": feature_cols,
        "selected_proba_bias": {
            "GALAXY": float(best_bias[0]),
            "QSO": float(best_bias[1]),
            "STAR": float(best_bias[2]),
        },
        "class_weight_multipliers": {
            "GALAXY": args.galaxy_weight_mult,
            "QSO": args.qso_weight_mult,
            "STAR": args.star_weight_mult,
        },
        "args": vars(args),
        "submission": str(submission_path),
    }
    report_path = REPORTS_DIR / f"ensemble_v3_{score_tag}_{timestamp}.json"
    report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")

    print("")
    print(f"Raw OOF balanced accuracy: {raw_score:.6f}")
    print(f"Final OOF balanced accuracy: {cv_score:.6f}")
    print(
        "Selected probability bias: "
        f"GALAXY={best_bias[0]:.4f}, QSO={best_bias[1]:.4f}, STAR={best_bias[2]:.4f}"
    )
    print(f"Submission saved to: {submission_path}")
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    train_model(parse_args())
