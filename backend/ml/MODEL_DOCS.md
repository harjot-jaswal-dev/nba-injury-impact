# Model Documentation — NBA Injury Impact Analyzer

## 1. Overview

The ML pipeline uses a **two-model approach** to predict player stats and injury ripple effects:

1. **Baseline Model**: Predicts a player's stats based on their historical performance, matchup, and context — assuming a fully healthy team.
2. **Ripple Effect Model**: Uses the same player features PLUS injury context features. The **ripple effect** is computed as the difference between the ripple model's prediction (with injuries) and its prediction with injury features zeroed out (counterfactual healthy scenario).

Both models are `HistGradientBoostingRegressor` (scikit-learn), trained per target stat (8 models each, 16 total).

## 2. Data

- **Source**: NBA API via `nba_api` — player game logs, rosters, computed absences
- **Size**: ~90K player-game rows × 73 columns
- **Seasons**: 2022-23, 2023-24, 2024-25
- **Feature engineering**: Rolling averages (season, last-5, last-10), home/away splits, per-opponent averages, minutes trend, injury context (19 features encoding teammate absences)
- **Leakage prevention**: All rolling averages use `.shift(1)` to exclude the current game

## 3. Feature Sets

### Baseline Features (37)

| Category | Count | Features |
|----------|-------|----------|
| Season rolling averages | 11 | `season_avg_{pts,ast,reb,stl,blk,tov,fg_pct,ft_pct,fg3_pct,plus_minus,minutes}` |
| Last-5 game averages | 6 | `last5_avg_{pts,ast,reb,minutes,fg_pct,plus_minus}` |
| Last-10 game averages | 6 | `last10_avg_{pts,ast,reb,minutes,fg_pct,plus_minus}` |
| Home/away splits | 3 | `home_avg_pts`, `away_avg_pts`, `home_away_pts_diff` |
| Per-opponent averages | 3 | `vs_opp_avg_{pts,reb,ast}` |
| Trend/context | 4 | `minutes_trend`, `games_played_season`, `age`, `experience` |
| Derived binary | 1 | `is_home` (from `home_away` column) |
| Position dummies | 3 | `pos_G`, `pos_F`, `pos_C` (multi-label one-hot from `position`) |

### Injury Features (17 additional)

| Category | Count | Features |
|----------|-------|----------|
| Binary absence | 6 | `n_starters_out`, `starter_{1-5}_out` |
| Role-based | 6 | `ball_handler_out`, `primary_scorer_out`, `primary_rebounder_out`, `primary_defender_out`, `sixth_man_out`, `n_rotation_players_out` |
| Talent loss | 4 | `total_{pts,ast,reb,minutes}_lost` |
| Config experience | 1 | `games_with_this_config` |

### Ripple Features = Baseline + Injury (54 total)

### Encoding Decisions

- **Position**: Multi-label one-hot (`G-F` → `pos_G=1, pos_F=1, pos_C=0`). Encoded inside the shared `feature_builder.py` to guarantee identical logic in training and inference.
- **Home/away**: Binary `is_home` derived from the `home_away` column.
- **`injury_config_hash` dropped**: High-cardinality string (thousands of unique values). The numeric injury features (`n_starters_out`, talent loss, role flags) already capture the same signal without the curse of dimensionality.

## 4. Train/Test Split

- **Train**: Games before 2024-10-01 (2022-23 + 2023-24 seasons)
- **Test**: Games from 2024-10-01 onward (2024-25 season)
- **Rationale**: Time-based split prevents leakage from rolling averages and respects the temporal structure of sports data.

## 5. Model Choice: HistGradientBoosting vs Ridge

Both HistGradientBoostingRegressor and Ridge regression were trained on the baseline feature set.

**HistGradientBoosting hyperparameters**:
```
max_iter=500, max_depth=6, learning_rate=0.05,
min_samples_leaf=20, l2_regularization=1.0,
early_stopping=True, n_iter_no_change=20,
validation_fraction=0.1, random_state=42
```

**Ridge**: Wrapped in a Pipeline with SimpleImputer(median) + StandardScaler + Ridge(alpha=1.0).

**Actual results** (from `evaluation_results.txt`):

| Stat | HGB MAE | Ridge MAE | HGB R² | Ridge R² | HGB Lift | Note |
|------|---------|-----------|--------|----------|----------|------|
| pts | 4.619 | 4.614 | 0.5307 | 0.5312 | -0.0005 | minimal |
| ast | 1.346 | 1.343 | 0.5139 | 0.5157 | -0.0018 | minimal |
| reb | 1.921 | 1.921 | 0.4645 | 0.4670 | -0.0025 | minimal |
| stl | 0.717 | 0.715 | 0.1091 | 0.1113 | -0.0022 | minimal |
| blk | 0.528 | 0.525 | 0.1932 | 0.1960 | -0.0027 | minimal |
| fg_pct | 0.184 | 0.185 | 0.0840 | 0.0784 | +0.0056 | minimal |
| ft_pct | 0.334 | 0.335 | 0.2069 | 0.2031 | +0.0037 | minimal |
| minutes | 4.956 | 4.951 | 0.6414 | 0.6401 | +0.0013 | minimal |

Key observations:

- **All stats show minimal lift** from HGB over Ridge (<0.02 R² difference). The relationship between historical averages and next-game performance is largely linear.
- **Minutes predicted best** (R²=0.64) — playing time is the most consistent stat. **Points next** (R²=0.53), then assists and rebounds.
- **Percentage stats show lowest signal** (fg_pct R²=0.08, ft_pct R²=0.21) — single-game variance dominates.
- **Interview takeaway**: For this feature set, a linear model performs equally well. The tree model is retained because (1) it handles NaN natively (no imputation needed), and (2) when injury features are added (ripple model), non-linear interactions become more relevant.

## 6. Ripple Effect Approach

The training pipeline evaluates two approaches:

- **Approach A (Full Model)**: Uses all 55 features. Ripple = `predict(with_injuries) - predict(injuries_zeroed)`.
- **Approach B (Delta Model)**: Trains on `actual - season_avg` using only 17 injury features. At inference: `prediction = baseline + predicted_delta`.

**Decision criterion**: Median of mean |ripple effect| across all 8 target stats on injury test games. If median ≥ 0.3, Approach A is chosen (injury features have sufficient signal in the full model). Otherwise, Approach B provides a more focused signal.

**Actual result**: Approach B was chosen. Median ripple sensitivity = 0.258 (< 0.3 threshold).

Per-stat ripple sensitivity (Approach A on injury test games):

| Stat | Mean |Ripple| | Max |Ripple| | Games >1.0 shift |
|------|----------------|---------------|------------------|
| pts | 1.84 | 11.04 | 66.4% |
| ast | 0.40 | 3.08 | 8.6% |
| reb | 0.73 | 4.65 | 22.7% |
| stl | 0.11 | 0.91 | 0.0% |
| blk | 0.08 | 1.47 | 0.1% |
| fg_pct | 0.01 | 0.22 | 0.0% |
| ft_pct | 0.06 | 0.48 | 0.0% |
| minutes | 4.56 | 31.94 | 96.5% |

Points and minutes show the largest injury sensitivity. Percentage stats and counting stats (stl, blk) show near-zero effects. Full details in `ripple_evaluation_results.txt`.

## 7. Feature Importance

Computed via `permutation_importance` on the test set. Full results are in `ripple_evaluation_results.txt`.

Top features for the ripple (delta) model by permutation importance:

**Points**: `total_pts_lost` (0.0097), `total_reb_lost` (0.0064), `primary_scorer_out` (0.0039), `games_with_this_config` (0.0038)

**Rebounds**: `total_reb_lost` (0.0551), `n_rotation_players_out` (0.0185), `starter_2_out` (0.0044), `primary_rebounder_out` (0.0035)

**Assists**: `total_pts_lost` (0.0069), `n_rotation_players_out` (0.0022)

Talent loss metrics (`total_pts_lost`, `total_reb_lost`) are the most important injury features. Binary role flags contribute less on their own.

## 8. Evaluation Summary

**Dataset**: 76,921 rows (51,184 train / 25,737 test). 757 players, 30 teams, 3 seasons. 49.8% of games had at least one starter absent.

**Baseline model R²**: pts=0.53, ast=0.51, reb=0.46, minutes=0.64, ft_pct=0.21, blk=0.19, stl=0.11, fg_pct=0.08

**Ripple model**: Approach B chosen (delta model with 17 injury features). Points and minutes show meaningful injury sensitivity; other stats show smaller effects.

Detailed metrics in:
- `backend/ml/evaluation_results.txt` — Baseline HGB vs Ridge comparison
- `backend/ml/ripple_evaluation_results.txt` — Ripple model metrics + sensitivity analysis

## 9. Known Limitations

1. **Static CSV limitation**: Predictions reflect data from the last pipeline run, not real-time stats. In production, a daily refresh pipeline would re-run `process_data.py` to update rolling averages.

2. **Counterfactual zeroing bias**: Zeroing injury features produces a "healthy team" prediction, not a true neutral baseline. The model learns with injury features at various levels; zeroing them creates an input that may not perfectly represent "no injuries." In production, matched-pair analysis or causal inference methods (e.g., difference-in-differences) could provide cleaner counterfactuals.

3. **No temporal cross-validation**: With only 3 seasons of data, meaningful temporal cross-validation is limited. The single time-based train/test split is appropriate for this data volume. With more seasons, rolling-window CV would be preferred.

4. **Percentage stats low signal**: FG% and FT% have inherently low predictive signal due to single-game variance (a player shooting 2/5 vs 3/5 is a 20% swing from small sample). Counting stats (pts, ast, reb) are more reliably predicted. Leading with counting stats in the UI provides more trustworthy predictions.

5. **Early stopping validation split**: The HistGradientBoosting early stopping uses a random 10% validation fraction rather than a temporal validation window. In production with more data, a temporal validation split (e.g., last month of training data) would better reflect real-world deployment conditions.

6. **Inference role approximation**: At training time, player roles are computed from true full-season averages (mean of ALL games in a season). At inference time, roles use cumulative `season_avg_*` values from the latest CSV row (expanding mean up to the last game). Late in the season these converge closely. Early in the season, inference-time role assignments may differ from training-time roles. This is an unavoidable limitation of not having future data.

7. **1-game stale features**: Rolling averages at inference time are approximately 1 game behind due to the `shift(1)` applied during preprocessing. The model was trained on shifted features, so this is consistent — but it means the prediction doesn't account for the player's most recent game.

## 10. Retraining Instructions

To add a new season of data and retrain:

```bash
# 1. Collect new season data
python -m backend.scripts.collect_player_stats
python -m backend.scripts.collect_injury_data

# 2. Re-run feature engineering
python -m backend.scripts.process_data

# 3. Optionally explore the updated dataset
python -m backend.ml.explore_data

# 4. Retrain models (updates SPLIT_DATE in config.py if needed)
python -m backend.ml.baseline_model
python -m backend.ml.ripple_model

# 5. Verify predictions still work
python -c "from backend.ml.predict import predict_baseline; print(predict_baseline(2544, 'BOS', 'HOME'))"
```

Model files in `backend/models/` will be overwritten. The old models are not versioned — consider backing up before retraining.
