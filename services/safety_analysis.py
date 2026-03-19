"""
Safety / adverse event analysis helpers.
"""
from __future__ import annotations
import pandas as pd


def incidence_rate(subjects_affected: int, subjects_at_risk: int) -> float | None:
    if not subjects_at_risk:
        return None
    return round(100.0 * subjects_affected / subjects_at_risk, 2)


def top_ae_terms(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    if df.empty:
        return df
    col = "total_affected" if "total_affected" in df.columns else df.columns[-1]
    return df.nlargest(n, col).reset_index(drop=True)


def organ_system_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given AE detail rows, aggregate by organ_system:
    total_affected, trial_count, unique_terms.
    """
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby("organ_system", as_index=False)
        .agg(
            total_affected=("subjects_affected", "sum"),
            trial_count=("nct_id", "nunique"),
            unique_terms=("adverse_event_term", "nunique"),
        )
        .sort_values("total_affected", ascending=False)
    )


def add_incidence_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add an incidence_rate column if both affected and at_risk are present."""
    if df.empty:
        return df
    if "subjects_affected" in df.columns and "subjects_at_risk" in df.columns:
        df = df.copy()
        df["incidence_pct"] = df.apply(
            lambda r: incidence_rate(r["subjects_affected"], r["subjects_at_risk"]),
            axis=1,
        )
    return df
