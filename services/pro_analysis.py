"""
PRO analysis helpers.
"""
from __future__ import annotations
import pandas as pd
from services.analytics import aggregate_pro_usage


def pro_adoption_rate(total_trials: int, pro_trials: int) -> float:
    if not total_trials:
        return 0.0
    return round(100.0 * pro_trials / total_trials, 1)


def top_instruments(df_agg: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Return top-n instruments by total (planned + reported)."""
    if df_agg.empty:
        return pd.DataFrame()
    return df_agg.nlargest(n, "total").reset_index(drop=True)


def planned_vs_reported_pivot(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    From the UNION of planned + reported PRO data, produce a melted
    DataFrame for a grouped bar chart: instrument_name | stage | trial_count.
    """
    agg = aggregate_pro_usage(df_raw)
    if agg.empty:
        return pd.DataFrame()
    melted = agg.melt(
        id_vars="instrument_name",
        value_vars=["planned_count", "reported_count"],
        var_name="stage",
        value_name="trial_count",
    )
    melted["stage"] = melted["stage"].map(
        {"planned_count": "Planned", "reported_count": "Reported"}
    )
    return melted[melted["trial_count"] > 0].reset_index(drop=True)


def domain_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot domain_score_match data for heatmap: instrument × domain."""
    if df.empty or "instrument_name" not in df.columns or "domain" not in df.columns:
        return pd.DataFrame()
    return df.pivot_table(
        index="instrument_name",
        columns="domain",
        values="trial_count",
        aggfunc="sum",
        fill_value=0,
    )
