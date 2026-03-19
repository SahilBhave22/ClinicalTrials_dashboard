"""
General analytics helpers used across multiple pages.
Pure Python/pandas transformations on DataFrames returned by the repository.
"""
from __future__ import annotations
import pandas as pd


def pivot_phase_sponsor(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot sponsor × phase DataFrame for stacked bar chart."""
    if df.empty or "sponsor" not in df.columns or "phase" not in df.columns:
        return pd.DataFrame()
    return df.pivot_table(
        index="sponsor", columns="phase", values="trial_count",
        aggfunc="sum", fill_value=0,
    ).reset_index()


def compute_completion_rate(total: int, completed: int) -> float:
    if not total:
        return 0.0
    return round(100.0 * completed / total, 1)


def compute_results_rate(total: int, with_results: int) -> float:
    if not total:
        return 0.0
    return round(100.0 * with_results / total, 1)


def top_n(df: pd.DataFrame, col: str, n: int = 10) -> pd.DataFrame:
    """Return top-n rows by a numeric column, descending."""
    if df.empty or col not in df.columns:
        return df
    return df.nlargest(n, col).reset_index(drop=True)


def aggregate_pro_usage(df: pd.DataFrame) -> pd.DataFrame:
    """
    From the UNION result of planned + reported PRO queries,
    aggregate to instrument_name with planned_count and reported_count columns.
    """
    if df.empty:
        return pd.DataFrame()
    agg = (
        df.groupby("instrument_name", as_index=False)
        .agg(planned_count=("planned_count", "sum"),
             reported_count=("reported_count", "sum"))
    )
    agg["total"] = agg["planned_count"] + agg["reported_count"]
    return agg.sort_values("total", ascending=False).reset_index(drop=True)


def compute_pro_funnel(planned_n: int, reported_n: int) -> pd.DataFrame:
    return pd.DataFrame({
        "stage": ["Planned PROs", "Reported PROs"],
        "trial_count": [planned_n, reported_n],
    })


def year_from_date_col(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Parse a datetime column to year int."""
    if df.empty or col not in df.columns:
        return df
    df = df.copy()
    df[col] = pd.to_datetime(df[col], errors="coerce")
    df["year"] = df[col].dt.year
    return df


def pivot_heatmap(df: pd.DataFrame, index: str, columns: str, values: str) -> pd.DataFrame:
    """Pivot for heatmap chart."""
    if df.empty:
        return pd.DataFrame()
    return df.pivot_table(
        index=index, columns=columns, values=values,
        aggfunc="sum", fill_value=0,
    )
