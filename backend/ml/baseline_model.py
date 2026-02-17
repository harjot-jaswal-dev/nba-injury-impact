"""
Baseline model training and evaluation.

Trains HistGradientBoostingRegressor (one per target stat) using only
baseline features (no injury context). Also trains Ridge regression
for comparison. Saves HGB models + metrics; Ridge metrics only.

Run via: python -m backend.ml.baseline_model
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.ml.config import (
    load_processed_data, BASELINE_FEATURES, TARGET_COLS, STAT_NAMES,
    SPLIT_DATE, MODELS_DIR, ML_DIR,
)
from backend.ml.feature_builder import build_feature_matrix


def train_and_evaluate():
    """Train baseline models and evaluate on test set."""
    print("=" * 60)
    print("BASELINE MODEL TRAINING")
    print("=" * 60)

    # Load data
    print("\nLoading processed data...")
    df = load_processed_data()
    print(f"Loaded: {df.shape[0]} rows x {df.shape[1]} columns")

    # Time-based split
    train_df = df[df["game_date"] < SPLIT_DATE].copy()
    test_df = df[df["game_date"] >= SPLIT_DATE].copy()
    print(f"Train: {len(train_df)} rows (before {SPLIT_DATE})")
    print(f"Test:  {len(test_df)} rows (from {SPLIT_DATE})")

    # Build feature matrices using shared feature builder
    print(f"\nBuilding feature matrices ({len(BASELINE_FEATURES)} features)...")
    X_train_full = build_feature_matrix(train_df, BASELINE_FEATURES)
    X_test_full = build_feature_matrix(test_df, BASELINE_FEATURES)
    print(f"X_train shape: {X_train_full.shape}")
    print(f"X_test shape: {X_test_full.shape}")

    # Ensure models directory exists
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Save feature list (defines column order for inference)
    features_path = MODELS_DIR / "baseline_features.json"
    with open(features_path, "w") as f:
        json.dump(BASELINE_FEATURES, f, indent=2)
    print(f"Saved feature list to {features_path}")

    # Training loop — one model per target stat
    hgb_results = {}
    ridge_results = {}

    print("\n" + "-" * 60)
    print("Training models for each target stat...")
    print("-" * 60)

    for target_col, stat_name in zip(TARGET_COLS, STAT_NAMES):
        print(f"\n--- {stat_name.upper()} ---")

        # Get target values and drop NaN rows
        y_train = train_df[target_col].values
        y_test = test_df[target_col].values

        # Mask for non-NaN targets
        train_mask = ~np.isnan(y_train)
        test_mask = ~np.isnan(y_test)

        X_tr = X_train_full[train_mask]
        y_tr = y_train[train_mask]
        X_te = X_test_full[test_mask]
        y_te = y_test[test_mask]

        print(f"  Train samples: {len(y_tr)}, Test samples: {len(y_te)}")

        # --- HistGradientBoosting ---
        hgb = HistGradientBoostingRegressor(
            max_iter=500,
            max_depth=6,
            learning_rate=0.05,
            min_samples_leaf=20,
            l2_regularization=1.0,
            early_stopping=True,
            n_iter_no_change=20,
            validation_fraction=0.1,
            random_state=42,
        )
        hgb.fit(X_tr, y_tr)
        hgb_pred = hgb.predict(X_te)

        hgb_mae = mean_absolute_error(y_te, hgb_pred)
        hgb_rmse = np.sqrt(mean_squared_error(y_te, hgb_pred))
        hgb_r2 = r2_score(y_te, hgb_pred)

        hgb_results[stat_name] = {
            "mae": hgb_mae, "rmse": hgb_rmse, "r2": hgb_r2,
        }

        # Save HGB model
        model_path = MODELS_DIR / f"baseline_{stat_name}.joblib"
        joblib.dump(hgb, model_path)

        # --- Ridge Regression (comparison only) ---
        ridge_pipe = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("ridge", Ridge(alpha=1.0)),
        ])
        ridge_pipe.fit(X_tr, y_tr)
        ridge_pred = ridge_pipe.predict(X_te)

        ridge_mae = mean_absolute_error(y_te, ridge_pred)
        ridge_rmse = np.sqrt(mean_squared_error(y_te, ridge_pred))
        ridge_r2 = r2_score(y_te, ridge_pred)

        ridge_results[stat_name] = {
            "mae": ridge_mae, "rmse": ridge_rmse, "r2": ridge_r2,
        }

        # Print comparison
        print(f"  HGB   — MAE: {hgb_mae:.3f}, RMSE: {hgb_rmse:.3f}, R²: {hgb_r2:.4f}")
        print(f"  Ridge — MAE: {ridge_mae:.3f}, RMSE: {ridge_rmse:.3f}, R²: {ridge_r2:.4f}")

        lift = hgb_r2 - ridge_r2
        print(f"  HGB lift over Ridge (R²): {lift:+.4f}"
              f" {'(substantial)' if abs(lift) > 0.02 else '(minimal)'}")

    # --- Comparison table ---
    print("\n" + "=" * 60)
    print("BASELINE MODEL COMPARISON: HistGradientBoosting vs Ridge")
    print("=" * 60)
    header = f"{'Stat':<10} {'HGB MAE':>9} {'Ridge MAE':>10} {'HGB R²':>8} {'Ridge R²':>9} {'Lift':>8} {'Note':>14}"
    print(header)
    print("-" * len(header))

    for stat_name in STAT_NAMES:
        h = hgb_results[stat_name]
        r = ridge_results[stat_name]
        lift = h["r2"] - r["r2"]
        note = "substantial" if abs(lift) > 0.02 else "minimal"
        print(f"  {stat_name:<8} {h['mae']:>9.3f} {r['mae']:>10.3f} "
              f"{h['r2']:>8.4f} {r['r2']:>9.4f} {lift:>+8.4f} {note:>14}")

    # --- Save evaluation results (Critical Fix #8) ---
    eval_path = ML_DIR / "evaluation_results.txt"
    with open(eval_path, "w") as f:
        f.write("Baseline Model Evaluation Results\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Train set: games before {SPLIT_DATE}\n")
        f.write(f"Test set: games from {SPLIT_DATE}\n")
        f.write(f"Features: {len(BASELINE_FEATURES)} baseline features (no injury context)\n\n")

        f.write("HistGradientBoosting vs Ridge Comparison\n")
        f.write("-" * 70 + "\n")
        f.write(f"{'Stat':<10} {'HGB MAE':>9} {'Ridge MAE':>10} {'HGB RMSE':>10} "
                f"{'Ridge RMSE':>11} {'HGB R²':>8} {'Ridge R²':>9} {'Note':>14}\n")
        f.write("-" * 70 + "\n")

        for stat_name in STAT_NAMES:
            h = hgb_results[stat_name]
            r = ridge_results[stat_name]
            lift = h["r2"] - r["r2"]
            note = "substantial" if abs(lift) > 0.02 else "minimal"
            f.write(f"{stat_name:<10} {h['mae']:>9.3f} {r['mae']:>10.3f} "
                    f"{h['rmse']:>10.3f} {r['rmse']:>11.3f} "
                    f"{h['r2']:>8.4f} {r['r2']:>9.4f} {note:>14}\n")

        f.write("\n\nInterpretation:\n")
        f.write("- 'substantial' = HGB R² lift over Ridge > 0.02 (tree model captures non-linearities)\n")
        f.write("- 'minimal' = HGB R² lift over Ridge <= 0.02 (linear model nearly as good)\n")
        f.write("- Counting stats (pts, ast, reb) typically show more lift from tree models.\n")
        f.write("- Percentage stats (fg_pct, ft_pct) have inherently low signal due to single-game variance.\n")
        f.write("\nTakeaway for interview: Model complexity is justified when the lift is\n")
        f.write("substantial. For stats with minimal difference, a simpler linear model\n")
        f.write("may be preferred in production (easier to maintain, faster inference).\n")

    print(f"\nEvaluation results saved to {eval_path}")

    # --- Star player predictions ---
    print("\n" + "=" * 60)
    print("STAR PLAYER PREDICTIONS (last 5 test games)")
    print("=" * 60)

    star_names = ["LeBron James", "Stephen Curry", "Nikola Jokic",
                  "Luka Doncic", "Jayson Tatum"]

    for star_name in star_names:
        star_df = test_df[test_df["player_name"] == star_name]
        if star_df.empty:
            print(f"\n{star_name}: not found in test set")
            continue

        star_recent = star_df.tail(5)
        X_star = build_feature_matrix(star_recent, BASELINE_FEATURES)

        print(f"\n{star_name} ({len(star_df)} test games, showing last 5):")

        for idx, (_, row) in enumerate(star_recent.iterrows()):
            date_str = row["game_date"].strftime("%Y-%m-%d")
            print(f"\n  Game {idx+1} ({date_str} vs {row.get('opponent', '?')}):")
            print(f"    {'Stat':<10} {'Predicted':>10} {'Actual':>8} {'Error':>8}")

            for target_col, stat_name in zip(TARGET_COLS, STAT_NAMES):
                model_path = MODELS_DIR / f"baseline_{stat_name}.joblib"
                model = joblib.load(model_path)
                pred = model.predict(X_star[idx:idx+1])[0]
                actual = row[target_col]
                error = pred - actual
                print(f"    {stat_name:<10} {pred:>10.1f} {actual:>8.1f} {error:>+8.1f}")

    # Summary
    print("\n" + "=" * 60)
    print("BASELINE TRAINING COMPLETE")
    print("=" * 60)
    print(f"Models saved: {len(TARGET_COLS)} .joblib files in {MODELS_DIR}")
    print(f"Feature list: {features_path}")
    print(f"Evaluation: {eval_path}")


if __name__ == "__main__":
    train_and_evaluate()
