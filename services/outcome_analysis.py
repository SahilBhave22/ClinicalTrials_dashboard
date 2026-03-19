"""
Outcome score analysis helpers.
"""
from __future__ import annotations
import pandas as pd
from utils.constants import BASELINE_CLASSIFICATIONS


def flag_baseline_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Add a boolean 'is_baseline' column."""
    if df.empty or "classification" not in df.columns:
        return df
    df = df.copy()
    df["is_baseline"] = df["classification"].str.lower().isin(BASELINE_CLASSIFICATIONS)
    return df


def unit_consistency_check(df: pd.DataFrame) -> dict:
    """Check how many unique units are present per category."""
    if df.empty or "units" not in df.columns:
        return {}
    result: dict = {}
    for cat, grp in df.groupby("category"):
        unique_units = grp["units"].dropna().unique().tolist()
        result[cat] = unique_units
    return result


def is_comparable(df: pd.DataFrame) -> bool:
    """Return True if all rows share the same unit and param_type."""
    if df.empty:
        return True
    units = df["units"].dropna().unique() if "units" in df.columns else []
    ptypes = df["param_type"].dropna().unique() if "param_type" in df.columns else []
    return len(units) <= 1 and len(ptypes) <= 1


def score_summary_by_group(df: pd.DataFrame) -> pd.DataFrame:
    """Compute median, mean, n per brand_name."""
    if df.empty or "param_value_num" not in df.columns:
        return pd.DataFrame()
    return (
        df.groupby("brand_name")["param_value_num"]
        .agg(
            median="median",
            mean="mean",
            n="count",
            min="min",
            max="max",
        )
        .reset_index()
        .sort_values("median", ascending=False)
    )


def prepare_boxplot_data(df: pd.DataFrame, group_col: str = "brand_name") -> pd.DataFrame:
    """Return subset with only needed columns for box plot."""
    needed = [group_col, "param_value_num", "units", "category"]
    cols = [c for c in needed if c in df.columns]
    return df[cols].dropna(subset=["param_value_num"]).reset_index(drop=True)
