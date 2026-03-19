"""
Trial design analysis helpers.
"""
from __future__ import annotations
import pandas as pd


def allocation_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "allocation" not in df.columns:
        return pd.DataFrame()
    return (
        df.groupby("allocation")["trial_count"]
        .sum().reset_index()
        .sort_values("trial_count", ascending=False)
    )


def intervention_model_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "intervention_model" not in df.columns:
        return pd.DataFrame()
    return (
        df.groupby("intervention_model")["trial_count"]
        .sum().reset_index()
        .sort_values("trial_count", ascending=False)
    )


def primary_purpose_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "primary_purpose" not in df.columns:
        return pd.DataFrame()
    return (
        df.groupby("primary_purpose")["trial_count"]
        .sum().reset_index()
        .sort_values("trial_count", ascending=False)
    )
