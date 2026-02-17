"""
Single code path for feature vector construction.

This module ensures that training and inference use IDENTICAL feature
construction logic, eliminating train/serve skew (Critical Fix #1).

Training: build_feature_matrix(df, feature_list)  — vectorized batch
Inference: build_feature_vector(row_data, feature_list) — single row
Both produce features in the exact same order.
"""

import numpy as np
import pandas as pd


def _encode_position(position_value) -> dict:
    """Encode position string into multi-label one-hot dummies.

    "G-F" -> pos_G=1, pos_F=1, pos_C=0
    "C"   -> pos_G=0, pos_F=0, pos_C=1
    NaN   -> pos_G=0, pos_F=0, pos_C=0

    Args:
        position_value: Position string from CSV (e.g., "G", "F-C", "G-F").

    Returns:
        Dict with keys pos_G, pos_F, pos_C.
    """
    pos_g, pos_f, pos_c = 0, 0, 0
    if pd.notna(position_value):
        pos_str = str(position_value).upper()
        if "G" in pos_str:
            pos_g = 1
        if "F" in pos_str:
            pos_f = 1
        if "C" in pos_str:
            pos_c = 1
    return {"pos_G": pos_g, "pos_F": pos_f, "pos_C": pos_c}


def _encode_home_away(home_away_value) -> int:
    """Encode home_away string to binary.

    Args:
        home_away_value: "HOME" or "AWAY" string.

    Returns:
        1 if HOME, 0 otherwise.
    """
    if pd.notna(home_away_value):
        return int(str(home_away_value).upper() == "HOME")
    return 0


def build_feature_vector(row_data: dict, feature_list: list) -> np.ndarray:
    """Build a feature vector from a data dictionary.

    This is the SINGLE code path for feature construction.
    Training calls this per-row. Inference calls this same function.

    Args:
        row_data: Dict with raw column values from the processed CSV
                  (or constructed at inference time).
        feature_list: Ordered list of feature names (from saved JSON).

    Returns:
        1D numpy array of feature values in feature_list order.
    """
    # Derive encoded columns
    derived = {}
    derived.update(_encode_position(row_data.get("position")))
    derived["is_home"] = _encode_home_away(row_data.get("home_away"))

    # Build feature vector in exact feature_list order
    values = []
    for name in feature_list:
        if name in derived:
            values.append(derived[name])
        elif name in row_data:
            val = row_data[name]
            # Coerce to numeric (matches build_feature_matrix's pd.to_numeric)
            numeric_val = pd.to_numeric(val, errors="coerce")
            values.append(numeric_val)
        else:
            # Missing feature — leave as NaN (HistGradientBoosting handles natively)
            values.append(np.nan)

    return np.array(values, dtype=np.float64)


def build_feature_matrix(df: pd.DataFrame, feature_list: list) -> np.ndarray:
    """Vectorized version for batch feature construction (training).

    Applies the same encoding logic as build_feature_vector but
    operates on the full DataFrame at once for performance.

    Args:
        df: DataFrame with raw columns from the processed CSV.
        feature_list: Ordered list of feature names.

    Returns:
        2D numpy array of shape (n_rows, n_features).
    """
    # Derive encoded columns using vectorized pandas ops
    result_df = pd.DataFrame(index=df.index)

    # Position encoding (vectorized)
    if "position" in df.columns:
        pos_str = df["position"].fillna("").astype(str).str.upper()
        result_df["pos_G"] = pos_str.str.contains("G").astype(int)
        result_df["pos_F"] = pos_str.str.contains("F").astype(int)
        result_df["pos_C"] = pos_str.str.contains("C").astype(int)
    else:
        result_df["pos_G"] = 0
        result_df["pos_F"] = 0
        result_df["pos_C"] = 0

    # Home/away encoding (vectorized)
    if "home_away" in df.columns:
        result_df["is_home"] = (
            df["home_away"].fillna("").astype(str).str.upper() == "HOME"
        ).astype(int)
    else:
        result_df["is_home"] = 0

    # Extract columns in feature_list order
    matrix_cols = []
    for name in feature_list:
        if name in result_df.columns:
            matrix_cols.append(result_df[name].values)
        elif name in df.columns:
            matrix_cols.append(pd.to_numeric(df[name], errors="coerce").values)
        else:
            # Missing feature column — fill with NaN
            matrix_cols.append(np.full(len(df), np.nan))

    return np.column_stack(matrix_cols).astype(np.float64)
