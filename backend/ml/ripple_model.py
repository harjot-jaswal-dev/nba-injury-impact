"""
Ripple effect model training and evaluation.

Trains models using the full 55-feature set (baseline + injury context).
Evaluates Approach A (full model) vs Approach B (delta model) and selects
the better one based on median ripple sensitivity across ALL targets.

Run via: python -m backend.ml.ripple_model
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.ml.config import (
    load_processed_data, BASELINE_FEATURES, INJURY_FEATURES,
    RIPPLE_FEATURES, TARGET_COLS, STAT_NAMES,
    SPLIT_DATE, MODELS_DIR, ML_DIR,
)
from backend.ml.feature_builder import build_feature_matrix


def _train_approach_a(train_df, test_df):
    """Train Approach A: Full model with injury features.

    Returns:
        Tuple of (models_dict, metrics_dict, X_test, test_df_filtered_per_stat).
    """
    print("\n--- APPROACH A: Full Model with Injury Features ---")
    print(f"Feature count: {len(RIPPLE_FEATURES)}")

    X_train_full = build_feature_matrix(train_df, RIPPLE_FEATURES)
    X_test_full = build_feature_matrix(test_df, RIPPLE_FEATURES)

    models = {}
    metrics = {}

    for target_col, stat_name in zip(TARGET_COLS, STAT_NAMES):
        y_train = train_df[target_col].values
        y_test = test_df[target_col].values

        train_mask = ~np.isnan(y_train)
        test_mask = ~np.isnan(y_test)

        X_tr = X_train_full[train_mask]
        y_tr = y_train[train_mask]
        X_te = X_test_full[test_mask]
        y_te = y_test[test_mask]

        hgb = HistGradientBoostingRegressor(
            max_iter=500, max_depth=6, learning_rate=0.05,
            min_samples_leaf=20, l2_regularization=1.0,
            early_stopping=True, n_iter_no_change=20,
            validation_fraction=0.1, random_state=42,
        )
        hgb.fit(X_tr, y_tr)
        pred = hgb.predict(X_te)

        mae = mean_absolute_error(y_te, pred)
        rmse = np.sqrt(mean_squared_error(y_te, pred))
        r2 = r2_score(y_te, pred)

        models[stat_name] = hgb
        metrics[stat_name] = {"mae": mae, "rmse": rmse, "r2": r2}
        print(f"  {stat_name:<8} MAE: {mae:.3f}, RMSE: {rmse:.3f}, R²: {r2:.4f}")

    return models, metrics, X_test_full


def _train_approach_b(train_df, test_df):
    """Train Approach B: Delta model (predicts stat - season_avg using only injury features).

    Returns:
        Tuple of (models_dict, metrics_dict).
    """
    print("\n--- APPROACH B: Delta Model (injury features only) ---")
    print(f"Feature count: {len(INJURY_FEATURES)}")

    # Build delta targets: actual - season_avg for injury games
    X_train_full = build_feature_matrix(train_df, INJURY_FEATURES)
    X_test_full = build_feature_matrix(test_df, INJURY_FEATURES)

    models = {}
    metrics = {}

    stat_to_avg = {
        "pts": "season_avg_pts", "ast": "season_avg_ast",
        "reb": "season_avg_reb", "stl": "season_avg_stl",
        "blk": "season_avg_blk", "fg_pct": "season_avg_fg_pct",
        "ft_pct": "season_avg_ft_pct", "minutes": "season_avg_minutes",
    }

    for target_col, stat_name in zip(TARGET_COLS, STAT_NAMES):
        avg_col = stat_to_avg[stat_name]

        # Delta = actual - season average
        y_train_delta = (train_df[target_col] - train_df[avg_col]).values
        y_test_actual = test_df[target_col].values
        season_avg_test = test_df[avg_col].values

        train_mask = ~np.isnan(y_train_delta)
        test_mask = ~np.isnan(y_test_actual) & ~np.isnan(season_avg_test)

        X_tr = X_train_full[train_mask]
        y_tr = y_train_delta[train_mask]
        X_te = X_test_full[test_mask]
        y_te_actual = y_test_actual[test_mask]
        s_avg = season_avg_test[test_mask]

        hgb = HistGradientBoostingRegressor(
            max_iter=500, max_depth=6, learning_rate=0.05,
            min_samples_leaf=20, l2_regularization=1.0,
            early_stopping=True, n_iter_no_change=20,
            validation_fraction=0.1, random_state=42,
        )
        hgb.fit(X_tr, y_tr)
        delta_pred = hgb.predict(X_te)

        # Final prediction = season_avg + predicted_delta
        pred = s_avg + delta_pred

        mae = mean_absolute_error(y_te_actual, pred)
        rmse = np.sqrt(mean_squared_error(y_te_actual, pred))
        r2 = r2_score(y_te_actual, pred)

        models[stat_name] = hgb
        metrics[stat_name] = {"mae": mae, "rmse": rmse, "r2": r2}
        print(f"  {stat_name:<8} MAE: {mae:.3f}, RMSE: {rmse:.3f}, R²: {r2:.4f}")

    return models, metrics


def _evaluate_ripple_sensitivity(models_a, test_df):
    """Evaluate ripple sensitivity for Approach A across ALL targets.

    Computes the difference between predictions with actual injury features
    vs injury features zeroed out, on test games where n_starters_out > 0.

    Returns:
        Dict mapping stat_name -> {mean_ripple, max_ripple, pct_above_1}.
    """
    print("\n--- RIPPLE SENSITIVITY ANALYSIS (Approach A) ---")

    # Filter to injury games in test set
    injury_test = test_df[test_df["n_starters_out"] > 0].copy()
    print(f"Injury games in test set: {len(injury_test)}")

    if injury_test.empty:
        print("  No injury games found in test set!")
        return {}

    # Build features WITH actual injury context
    X_with = build_feature_matrix(injury_test, RIPPLE_FEATURES)

    # Build features with injury features ZEROED OUT
    zeroed_df = injury_test.copy()
    for col in INJURY_FEATURES:
        if col in zeroed_df.columns:
            zeroed_df[col] = 0
    X_without = build_feature_matrix(zeroed_df, RIPPLE_FEATURES)

    sensitivity = {}
    print(f"\n  {'Stat':<10} {'Mean |Ripple|':>14} {'Max |Ripple|':>13} {'Games >1.0':>12}")
    print("  " + "-" * 52)

    for stat_name in STAT_NAMES:
        model = models_a[stat_name]
        pred_with = model.predict(X_with)
        pred_without = model.predict(X_without)
        ripple = np.abs(pred_with - pred_without)

        mean_ripple = ripple.mean()
        max_ripple = ripple.max()
        pct_above_1 = (ripple > 1.0).mean() * 100

        sensitivity[stat_name] = {
            "mean_ripple": float(mean_ripple),
            "max_ripple": float(max_ripple),
            "pct_above_1": float(pct_above_1),
        }
        print(f"  {stat_name:<10} {mean_ripple:>14.2f} {max_ripple:>13.2f} {pct_above_1:>11.1f}%")

    # Decision criterion: median of mean |ripple| across all targets
    mean_ripples = [s["mean_ripple"] for s in sensitivity.values()]
    median_ripple = float(np.median(mean_ripples))
    print(f"\n  Median mean |ripple| across all targets: {median_ripple:.3f}")
    print(f"  Threshold for Approach A: > 0.3")
    print(f"  Decision: {'Approach A (sufficient sensitivity)' if median_ripple >= 0.3 else 'Approach B (insufficient sensitivity)'}")

    return sensitivity


def _compute_feature_importance(models, test_df, feature_list, n_repeats=5):
    """Compute permutation importance on the test set.

    Returns:
        Dict mapping stat_name -> list of (feature_name, importance) tuples.
    """
    print("\n--- FEATURE IMPORTANCE (Permutation) ---")

    X_test = build_feature_matrix(test_df, feature_list)
    importances = {}

    for stat_name in STAT_NAMES:
        target_col = f"target_{stat_name}"
        y_test = test_df[target_col].values
        mask = ~np.isnan(y_test)
        X_te = X_test[mask]
        y_te = y_test[mask]

        result = permutation_importance(
            models[stat_name], X_te, y_te,
            n_repeats=n_repeats, random_state=42, n_jobs=-1,
        )

        # Sort by importance
        sorted_idx = result.importances_mean.argsort()[::-1]
        top_features = [
            (feature_list[i], result.importances_mean[i])
            for i in sorted_idx[:10]
        ]
        importances[stat_name] = top_features

    # Print top features for pts and ast (most interesting)
    for stat_name in ["pts", "ast", "reb"]:
        print(f"\n  Top 10 features for {stat_name}:")
        for feat, imp in importances[stat_name]:
            marker = " ***" if feat in INJURY_FEATURES else ""
            print(f"    {feat:<35} {imp:.4f}{marker}")

    return importances


def _ripple_demonstration(models, test_df, feature_list):
    """Show ripple effect on specific historical games with key absences."""
    print("\n--- RIPPLE EFFECT DEMONSTRATION ---")

    injury_test = test_df[test_df["n_starters_out"] >= 1].copy()
    if injury_test.empty:
        print("  No injury games available for demonstration.")
        return

    # Select games with highest total_pts_lost (most impactful absences)
    demo_games = injury_test.nlargest(5, "total_pts_lost")

    for idx, (_, row) in enumerate(demo_games.iterrows()):
        player = row.get("player_name", "Unknown")
        date_str = row["game_date"].strftime("%Y-%m-%d")
        opp = row.get("opponent", "?")
        n_out = int(row["n_starters_out"])
        pts_lost = row.get("total_pts_lost", 0)

        print(f"\n  Game {idx+1}: {player} on {date_str} vs {opp}")
        print(f"  Context: {n_out} starter(s) out, {pts_lost:.1f} total pts lost")

        # Ripple prediction (with injury context)
        X_ripple = build_feature_matrix(
            pd.DataFrame([row]), feature_list
        )

        # Counterfactual (injury features zeroed)
        row_zeroed = row.copy()
        for col in INJURY_FEATURES:
            if col in row_zeroed.index:
                row_zeroed[col] = 0
        X_counter = build_feature_matrix(
            pd.DataFrame([row_zeroed]), feature_list
        )

        print(f"    {'Stat':<10} {'Ripple Pred':>12} {'No-Injury':>10} {'Delta':>8} {'Actual':>8}")
        for stat_name in ["pts", "ast", "reb", "minutes"]:
            model = models[stat_name]
            ripple_pred = model.predict(X_ripple)[0]
            counter_pred = model.predict(X_counter)[0]
            delta = ripple_pred - counter_pred
            actual = row.get(f"target_{stat_name}", np.nan)
            print(f"    {stat_name:<10} {ripple_pred:>12.1f} {counter_pred:>10.1f} "
                  f"{delta:>+8.1f} {actual:>8.1f}")


def train_and_evaluate():
    """Train ripple models and evaluate."""
    print("=" * 60)
    print("RIPPLE EFFECT MODEL TRAINING")
    print("=" * 60)

    # Load data
    print("\nLoading processed data...")
    df = load_processed_data()
    print(f"Loaded: {df.shape[0]} rows x {df.shape[1]} columns")

    # Time-based split
    train_df = df[df["game_date"] < SPLIT_DATE].copy()
    test_df = df[df["game_date"] >= SPLIT_DATE].copy()
    print(f"Train: {len(train_df)} rows, Test: {len(test_df)} rows")

    # Injury game stats
    train_injury = (train_df["n_starters_out"] > 0).sum()
    test_injury = (test_df["n_starters_out"] > 0).sum()
    print(f"Injury games — Train: {train_injury}, Test: {test_injury}")

    # --- Train both approaches ---
    models_a, metrics_a, X_test_a = _train_approach_a(train_df, test_df)
    models_b, metrics_b = _train_approach_b(train_df, test_df)

    # --- Evaluate ripple sensitivity (Critical Fix #5 — all targets) ---
    sensitivity = _evaluate_ripple_sensitivity(models_a, test_df)

    # --- Decision: Approach A or B ---
    mean_ripples = [s["mean_ripple"] for s in sensitivity.values()] if sensitivity else [0]
    median_ripple = float(np.median(mean_ripples))
    use_approach_a = median_ripple >= 0.3

    chosen = "A" if use_approach_a else "B"
    chosen_models = models_a if use_approach_a else models_b
    chosen_metrics = metrics_a if use_approach_a else metrics_b
    chosen_features = RIPPLE_FEATURES if use_approach_a else INJURY_FEATURES

    print(f"\n{'=' * 60}")
    print(f"DECISION: Using Approach {chosen}")
    print(f"{'=' * 60}")
    if use_approach_a:
        print("Approach A selected: Full model with injury features.")
        print(f"Median ripple sensitivity ({median_ripple:.3f}) >= 0.3 threshold.")
    else:
        print("Approach B selected: Delta model with injury features only.")
        print(f"Median ripple sensitivity ({median_ripple:.3f}) < 0.3 threshold.")
        print("Injury features showed insufficient signal in the full model.")

    # --- Comparison table ---
    print(f"\n{'Stat':<10} {'A MAE':>8} {'B MAE':>8} {'A R²':>8} {'B R²':>8} {'Better':>8}")
    print("-" * 50)
    for stat_name in STAT_NAMES:
        a = metrics_a[stat_name]
        b = metrics_b[stat_name]
        better = "A" if a["r2"] >= b["r2"] else "B"
        print(f"  {stat_name:<8} {a['mae']:>8.3f} {b['mae']:>8.3f} "
              f"{a['r2']:>8.4f} {b['r2']:>8.4f} {better:>8}")

    # --- Save chosen models ---
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for stat_name in STAT_NAMES:
        model_path = MODELS_DIR / f"ripple_{stat_name}.joblib"
        joblib.dump(chosen_models[stat_name], model_path)
    print(f"\nSaved {len(STAT_NAMES)} ripple models to {MODELS_DIR}")

    # Save feature list
    features_path = MODELS_DIR / "ripple_features.json"
    with open(features_path, "w") as f:
        json.dump(chosen_features, f, indent=2)
    print(f"Saved feature list to {features_path}")

    # Save approach metadata
    meta_path = MODELS_DIR / "ripple_metadata.json"
    with open(meta_path, "w") as f:
        json.dump({
            "chosen_approach": chosen,
            "median_ripple_sensitivity": median_ripple,
            "threshold": 0.3,
            "per_stat_sensitivity": sensitivity,
        }, f, indent=2)

    # --- Feature importance ---
    importances = _compute_feature_importance(
        chosen_models, test_df, chosen_features
    )

    # --- Ripple demonstration ---
    _ripple_demonstration(chosen_models, test_df, chosen_features)

    # --- Honest assessment ---
    print("\n" + "=" * 60)
    print("HONEST ASSESSMENT")
    print("=" * 60)
    if median_ripple < 1.0:
        print("Note: Ripple effects are relatively small. Possible reasons:")
        print("  - Limited injury variation in 3 seasons of data")
        print("  - NBA stat variance masks the injury signal game-to-game")
        print("  - Most games have 0-1 starters absent (low injury frequency)")
        print("  - Players' individual skill dominates context effects")
    else:
        print("Ripple effects are measurable across most target stats.")
        print("Injury context adds meaningful predictive signal.")

    # --- Save evaluation results ---
    eval_path = ML_DIR / "ripple_evaluation_results.txt"
    with open(eval_path, "w") as f:
        f.write("Ripple Effect Model Evaluation Results\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Chosen Approach: {chosen}\n")
        f.write(f"Median ripple sensitivity: {median_ripple:.3f}\n")
        f.write(f"Decision threshold: 0.3\n\n")

        f.write("Approach A vs B Comparison\n")
        f.write("-" * 70 + "\n")
        f.write(f"{'Stat':<10} {'A MAE':>8} {'B MAE':>8} {'A RMSE':>8} {'B RMSE':>8} "
                f"{'A R²':>8} {'B R²':>8}\n")
        f.write("-" * 70 + "\n")
        for stat_name in STAT_NAMES:
            a = metrics_a[stat_name]
            b = metrics_b[stat_name]
            f.write(f"{stat_name:<10} {a['mae']:>8.3f} {b['mae']:>8.3f} "
                    f"{a['rmse']:>8.3f} {b['rmse']:>8.3f} "
                    f"{a['r2']:>8.4f} {b['r2']:>8.4f}\n")

        f.write("\n\nPer-Stat Ripple Sensitivity (Approach A)\n")
        f.write("-" * 70 + "\n")
        f.write(f"{'Stat':<10} {'Mean |Ripple|':>14} {'Max |Ripple|':>13} {'Games >1.0':>12}\n")
        f.write("-" * 70 + "\n")
        for stat_name in STAT_NAMES:
            if stat_name in sensitivity:
                s = sensitivity[stat_name]
                f.write(f"{stat_name:<10} {s['mean_ripple']:>14.2f} "
                        f"{s['max_ripple']:>13.2f} {s['pct_above_1']:>11.1f}%\n")

        f.write(f"\nMedian of mean |ripple| across all targets: {median_ripple:.3f}\n")

        f.write("\n\nTop Features by Permutation Importance\n")
        f.write("-" * 70 + "\n")
        for stat_name in STAT_NAMES:
            f.write(f"\n{stat_name}:\n")
            for feat, imp in importances.get(stat_name, [])[:5]:
                marker = " [INJURY]" if feat in INJURY_FEATURES else ""
                f.write(f"  {feat:<35} {imp:.4f}{marker}\n")

    print(f"\nEvaluation results saved to {eval_path}")
    print("\n" + "=" * 60)
    print("RIPPLE MODEL TRAINING COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    train_and_evaluate()
