# Feature Dictionary

## Overview

This document describes all features in the processed player dataset.
Each row represents one player-game: a single player's stats and context
for a single NBA game.

## Identifier Columns

| Feature | Type | Description |
|---------|------|-------------|
| player_id | int | NBA unique player ID |
| player_name | str | Player full name |
| team_id | int | NBA team ID |
| team_abbr | str | Team abbreviation (e.g., 'LAL') |
| game_id | str | NBA unique game ID |
| game_date | date | Game date |
| season | str | Season (e.g., '2022-23') |
| opponent | str | Opponent team abbreviation |
| matchup | str | Full matchup string (e.g., 'LAL vs. BOS') |
| win_loss | str | Game result: 'W' or 'L' |
| home_away | str | 'HOME' or 'AWAY' |

## Raw Game Stats

| Feature | Type | Description |
|---------|------|-------------|
| pts | float | Points scored |
| ast | float | Assists |
| reb | float | Total rebounds |
| oreb | float | Offensive rebounds |
| dreb | float | Defensive rebounds |
| stl | float | Steals |
| blk | float | Blocks |
| tov | float | Turnovers |
| fgm | float | Field goals made |
| fga | float | Field goals attempted |
| fg_pct | float | Field goal percentage (0-1) |
| fg3m | float | 3-point field goals made |
| fg3a | float | 3-point field goals attempted |
| fg3_pct | float | 3-point percentage (0-1) |
| ftm | float | Free throws made |
| fta | float | Free throws attempted |
| ft_pct | float | Free throw percentage (0-1) |
| plus_minus | float | Plus/minus for the game |
| pf | float | Personal fouls |
| minutes | float | Minutes played |

## Season Rolling Averages (11 features)

Computed as `expanding().mean().shift(1)` per (player_id, season).
Each value is the player's average of that stat in all PRIOR games
this season (excludes current game to prevent future leakage).

| Feature | Description |
|---------|-------------|
| season_avg_pts | Season average points |
| season_avg_ast | Season average assists |
| season_avg_reb | Season average rebounds |
| season_avg_stl | Season average steals |
| season_avg_blk | Season average blocks |
| season_avg_tov | Season average turnovers |
| season_avg_fg_pct | Season average FG% |
| season_avg_ft_pct | Season average FT% |
| season_avg_fg3_pct | Season average 3PT% |
| season_avg_plus_minus | Season average plus/minus |
| season_avg_minutes | Season average minutes |

## Last-5 Game Averages (6 features)

Computed as `rolling(5, min_periods=1).mean().shift(1)` per (player_id, season).
Captures recent form.

| Feature | Description |
|---------|-------------|
| last5_avg_pts | Average points over last 5 games |
| last5_avg_ast | Average assists over last 5 games |
| last5_avg_reb | Average rebounds over last 5 games |
| last5_avg_minutes | Average minutes over last 5 games |
| last5_avg_fg_pct | Average FG% over last 5 games |
| last5_avg_plus_minus | Average plus/minus over last 5 games |

## Last-10 Game Averages (6 features)

Same as last-5 but over a 10-game window.

| Feature | Description |
|---------|-------------|
| last10_avg_pts | Average points over last 10 games |
| last10_avg_ast | Average assists over last 10 games |
| last10_avg_reb | Average rebounds over last 10 games |
| last10_avg_minutes | Average minutes over last 10 games |
| last10_avg_fg_pct | Average FG% over last 10 games |
| last10_avg_plus_minus | Average plus/minus over last 10 games |

## Home/Away Splits (3 features)

| Feature | Type | Description |
|---------|------|-------------|
| home_avg_pts | float | Player's average PTS in prior home games this season |
| away_avg_pts | float | Player's average PTS in prior away games this season |
| home_away_pts_diff | float | home_avg_pts - away_avg_pts |

## Per-Opponent Averages (3 features)

Computed as `expanding().mean().shift(1)` per (player_id, opponent)
across ALL seasons in the dataset. Captures matchup-specific tendencies.

| Feature | Description |
|---------|-------------|
| vs_opp_avg_pts | Career average PTS vs this opponent |
| vs_opp_avg_reb | Career average REB vs this opponent |
| vs_opp_avg_ast | Career average AST vs this opponent |

## Trend & Context (5 features)

| Feature | Type | Description |
|---------|------|-------------|
| minutes_trend | float | Slope of linear fit on minutes over last 10 games. Positive = gaining minutes. |
| games_played_season | int | Number of games played this season before this game |
| age | float | Player age for this season |
| experience | int | Years of NBA experience (0 = rookie) |
| position | str | Position (G, F, C, G-F, F-C, etc.) |

## Injury Context Features (19 features) — THE CORE

These features encode the injury state of the player's TEAMMATES for
each game. They are the foundation of the Injury Ripple Effect model.

### Binary Absence Flags

| Feature | Type | Description |
|---------|------|-------------|
| n_starters_out | int | Count of team's starters who are absent (0-4) |
| starter_1_out | int | 1 if the starter with most avg minutes is absent |
| starter_2_out | int | 1 if the 2nd-most-minutes starter is absent |
| starter_3_out | int | 1 if the 3rd-most-minutes starter is absent |
| starter_4_out | int | 1 if the 4th-most-minutes starter is absent |
| starter_5_out | int | 1 if the 5th-most-minutes starter is absent |

### Role-Based Absence Flags

| Feature | Type | Description |
|---------|------|-------------|
| ball_handler_out | int | 1 if the primary ball handler (highest AST starter) is absent |
| primary_scorer_out | int | 1 if the primary scorer (highest PTS starter) is absent |
| primary_rebounder_out | int | 1 if the primary rebounder (highest REB starter) is absent |
| primary_defender_out | int | 1 if the primary defender (highest STL+BLK starter) is absent |
| sixth_man_out | int | 1 if the sixth man (top non-starter by minutes) is absent |
| n_rotation_players_out | int | Count of top-8-minutes players who are absent |

### Talent Loss Metrics

| Feature | Type | Description |
|---------|------|-------------|
| total_pts_lost | float | Sum of season avg PTS for all absent players |
| total_ast_lost | float | Sum of season avg AST for all absent players |
| total_reb_lost | float | Sum of season avg REB for all absent players |
| total_minutes_lost | float | Sum of season avg minutes for all absent players |

### Configuration Features

| Feature | Type | Description |
|---------|------|-------------|
| injury_config_hash | str | MD5 hash of sorted absent player IDs. Same hash = same lineup configuration. 'healthy' if no absences. |
| games_with_this_config | int | Number of prior games this team played with this exact set of absences. Higher = more lineup experience. |

## Target Variables (8 features)

These are the stats the ML model will predict. They are copies of the
raw game stats with a `target_` prefix.

| Feature | Description |
|---------|-------------|
| target_pts | Points to predict |
| target_ast | Assists to predict |
| target_reb | Rebounds to predict |
| target_stl | Steals to predict |
| target_blk | Blocks to predict |
| target_fg_pct | FG% to predict |
| target_ft_pct | FT% to predict |
| target_minutes | Minutes to predict |
