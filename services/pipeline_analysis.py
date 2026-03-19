"""
Pipeline landscape analysis helpers.
"""
from __future__ import annotations
import pandas as pd


def pipeline_by_sponsor_sorted(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.sort_values("pipeline_trials", ascending=False).reset_index(drop=True)


def sponsor_indication_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot sponsor × condition for heatmap."""
    if df.empty or "sponsor" not in df.columns or "condition" not in df.columns:
        return pd.DataFrame()
    return df.pivot_table(
        index="sponsor",
        columns="condition",
        values="trial_count",
        aggfunc="sum",
        fill_value=0,
    )


def compute_pipeline_diversity_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each sponsor: compute diversity = number of unique indications / total trials.
    Returns df with diversity_score column.
    """
    if df.empty:
        return df
    df = df.copy()
    if "unique_assets" in df.columns and "pipeline_trials" in df.columns:
        df["asset_concentration"] = df["unique_assets"] / df["pipeline_trials"].clip(lower=1)
    return df
