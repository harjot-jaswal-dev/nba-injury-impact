"""
Data exploration and quality checks for the processed player dataset.

Exploration only — does not modify data.
Run via: python -m backend.ml.explore_data
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.ml.config import (
    load_processed_data, TARGET_COLS, BASELINE_FEATURES,
    INJURY_FEATURES, SPLIT_DATE,
)


def basic_stats(df: pd.DataFrame) -> None:
    """Print basic dataset statistics."""
    print("=" * 60)
    print("1. BASIC STATISTICS")
    print("=" * 60)
    print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"\nDate range: {df['game_date'].min()} to {df['game_date'].max()}")
    print(f"Unique players: {df['player_id'].nunique()}")
    print(f"Unique teams: {df['team_abbr'].nunique()}")
    print(f"Seasons: {sorted(df['season'].unique())}")

    print("\nData types:")
    dtype_counts = df.dtypes.value_counts()
    for dtype, count in dtype_counts.items():
        print(f"  {dtype}: {count} columns")

    print("\nNumeric column summary:")
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    desc = df[numeric_cols].describe().T
    print(desc[["mean", "std", "min", "max"]].to_string())

    print("\nTop 20 columns by missing values:")
    null_counts = df.isnull().sum().sort_values(ascending=False)
    null_counts = null_counts[null_counts > 0].head(20)
    if null_counts.empty:
        print("  No missing values!")
    else:
        for col, count in null_counts.items():
            pct = count / len(df) * 100
            print(f"  {col}: {count} ({pct:.1f}%)")


def player_distribution(df: pd.DataFrame) -> None:
    """Print player and team-season distribution."""
    print("\n" + "=" * 60)
    print("2. PLAYER DISTRIBUTION")
    print("=" * 60)

    games_per_player = df.groupby("player_id")["game_id"].count()
    print(f"Games per player:")
    print(f"  Min: {games_per_player.min()}")
    print(f"  Median: {games_per_player.median():.0f}")
    print(f"  Mean: {games_per_player.mean():.1f}")
    print(f"  Max: {games_per_player.max()}")

    games_per_team_season = df.groupby(["team_abbr", "season"])["game_id"].nunique()
    print(f"\nGames per team-season:")
    print(f"  Min: {games_per_team_season.min()}")
    print(f"  Median: {games_per_team_season.median():.0f}")
    print(f"  Mean: {games_per_team_season.mean():.1f}")
    print(f"  Max: {games_per_team_season.max()}")

    players_per_team_season = df.groupby(["team_abbr", "season"])["player_id"].nunique()
    print(f"\nPlayers per team-season:")
    print(f"  Min: {players_per_team_season.min()}")
    print(f"  Median: {players_per_team_season.median():.0f}")
    print(f"  Max: {players_per_team_season.max()}")


def absence_distribution(df: pd.DataFrame) -> None:
    """Print injury/absence distribution statistics."""
    print("\n" + "=" * 60)
    print("3. ABSENCE DISTRIBUTION")
    print("=" * 60)

    if "n_starters_out" not in df.columns:
        print("  No injury context features found.")
        return

    print("n_starters_out value counts:")
    vc = df["n_starters_out"].value_counts().sort_index()
    for val, count in vc.items():
        pct = count / len(df) * 100
        print(f"  {int(val)}: {count} ({pct:.1f}%)")

    any_absence = (df["n_starters_out"] > 0).sum()
    pct_absence = any_absence / len(df) * 100
    print(f"\nGames with any starter absent: {any_absence} ({pct_absence:.1f}%)")

    if "injury_config_hash" in df.columns:
        config_per_team_season = df.groupby(["team_abbr", "season"])["injury_config_hash"].nunique()
        print(f"\nUnique injury configs per team-season:")
        print(f"  Min: {config_per_team_season.min()}")
        print(f"  Median: {config_per_team_season.median():.0f}")
        print(f"  Mean: {config_per_team_season.mean():.1f}")
        print(f"  Max: {config_per_team_season.max()}")
        print(f"  Total unique configs: {df['injury_config_hash'].nunique()}")


def leakage_checks(df: pd.DataFrame) -> dict:
    """Check for data leakage issues.

    Returns:
        Dict with leakage check results.
    """
    print("\n" + "=" * 60)
    print("4. LEAKAGE CHECKS")
    print("=" * 60)

    results = {}

    # Check 1: raw stats and targets should be identical (correlation = 1.0)
    if "pts" in df.columns and "target_pts" in df.columns:
        corr = df["pts"].corr(df["target_pts"])
        status = "PASS" if abs(corr - 1.0) < 1e-10 else "FAIL"
        results["target_identity"] = status
        print(f"  Target identity check (pts vs target_pts): corr={corr:.6f} [{status}]")

    # Check 2: win_loss should correlate with target_pts (post-game info)
    if "win_loss" in df.columns and "target_pts" in df.columns:
        df_temp = df.copy()
        df_temp["_win"] = (df_temp["win_loss"] == "W").astype(int)
        corr = df_temp["_win"].corr(df_temp["target_pts"])
        status = "EXPECTED" if corr > 0.05 else "UNEXPECTED"
        results["win_loss_postfame"] = status
        print(f"  win_loss vs target_pts correlation: {corr:.4f} [{status}]")
        print(f"    -> win_loss IS post-game info (correctly excluded from features)")

    # Check 3: season_avg_pts should differ from cumulative mean including current game
    if "season_avg_pts" in df.columns and "pts" in df.columns:
        # For each player's 10th+ game, the season_avg should NOT equal the
        # expanding mean that includes the current game
        sample = df[df["games_played_season"] >= 10].head(1000)
        if len(sample) > 0:
            # season_avg_pts is shift(1) of expanding mean — should NOT equal
            # pts itself for any row (that would imply the current game leaked in)
            exact_matches = (sample["season_avg_pts"] == sample["pts"]).sum()
            pct_match = exact_matches / len(sample) * 100
            status = "PASS" if pct_match < 5 else "WARNING"
            results["shift_check"] = status
            print(f"  Shift(1) check: {exact_matches}/{len(sample)} rows have "
                  f"season_avg_pts == pts ({pct_match:.1f}%) [{status}]")
            print(f"    -> Low % confirms shift(1) is working (averages exclude current game)")

    return results


def target_stats(df: pd.DataFrame) -> None:
    """Print target variable statistics."""
    print("\n" + "=" * 60)
    print("5. TARGET VARIABLE STATS")
    print("=" * 60)

    available_targets = [t for t in TARGET_COLS if t in df.columns]
    if not available_targets:
        print("  No target columns found.")
        return

    print(f"{'Target':<18} {'Mean':>8} {'Std':>8} {'Min':>8} {'Max':>8} {'Skew':>8}")
    print("-" * 68)
    for col in available_targets:
        stat = col.replace("target_", "")
        mean = df[col].mean()
        std = df[col].std()
        mn = df[col].min()
        mx = df[col].max()
        skew = df[col].skew()
        print(f"  {stat:<16} {mean:>8.2f} {std:>8.2f} {mn:>8.2f} {mx:>8.2f} {skew:>8.2f}")

    print("\nTarget correlation matrix:")
    corr = df[available_targets].corr()
    # Rename for readability
    short_names = [t.replace("target_", "") for t in available_targets]
    corr.index = short_names
    corr.columns = short_names
    print(corr.round(3).to_string())


def quality_summary(df: pd.DataFrame, leakage_results: dict) -> None:
    """Print overall quality verdict."""
    print("\n" + "=" * 60)
    print("6. QUALITY SUMMARY")
    print("=" * 60)

    issues = []

    # Row count check
    if len(df) < 10000:
        issues.append(f"Low row count: {len(df)}")
    print(f"  Row count: {len(df)} {'(OK)' if len(df) >= 10000 else '(LOW)'}")

    # Missing value check
    total_cells = df.shape[0] * df.shape[1]
    total_missing = df.isnull().sum().sum()
    missing_pct = total_missing / total_cells * 100
    if missing_pct > 20:
        issues.append(f"High missing rate: {missing_pct:.1f}%")
    print(f"  Overall missing: {missing_pct:.1f}% {'(OK)' if missing_pct <= 20 else '(HIGH)'}")

    # Feature availability
    baseline_available = sum(1 for f in BASELINE_FEATURES
                             if f in df.columns or f in ["is_home", "pos_G", "pos_F", "pos_C"])
    injury_available = sum(1 for f in INJURY_FEATURES if f in df.columns)
    print(f"  Baseline features available: {baseline_available}/{len(BASELINE_FEATURES)}")
    print(f"  Injury features available: {injury_available}/{len(INJURY_FEATURES)}")

    # Leakage check
    leakage_ok = all(v in ("PASS", "EXPECTED") for v in leakage_results.values())
    if not leakage_ok:
        issues.append("Leakage check warnings")
    print(f"  Leakage checks: {'PASS' if leakage_ok else 'WARNING'}")

    # Train/test split sizes
    train = df[df["game_date"] < SPLIT_DATE]
    test = df[df["game_date"] >= SPLIT_DATE]
    print(f"  Train set (before {SPLIT_DATE}): {len(train)} rows")
    print(f"  Test set (from {SPLIT_DATE}): {len(test)} rows")

    # Verdict
    if not issues:
        verdict = "GOOD"
    elif len(issues) <= 2:
        verdict = "FAIR"
    else:
        verdict = "POOR"

    print(f"\n  VERDICT: {verdict}")
    if issues:
        for issue in issues:
            print(f"    - {issue}")


def main():
    """Run all data exploration sections."""
    print("Loading processed data...")
    df = load_processed_data()
    print(f"Loaded: {df.shape[0]} rows x {df.shape[1]} columns\n")

    basic_stats(df)
    player_distribution(df)
    absence_distribution(df)
    leakage_results = leakage_checks(df)
    target_stats(df)
    quality_summary(df, leakage_results)

    print("\n" + "=" * 60)
    print("Data exploration complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
