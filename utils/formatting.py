"""
Number, date, and string formatting utilities.
"""
from __future__ import annotations
import math
from typing import Optional


def fmt_number(n, decimals: int = 0) -> str:
    """Format a number with thousands separator."""
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return "—"
    try:
        return f"{float(n):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(n)


def fmt_pct(numerator, denominator, decimals: int = 1) -> str:
    """Format a percentage from numerator / denominator."""
    try:
        if not denominator:
            return "—"
        return f"{100.0 * float(numerator) / float(denominator):.{decimals}f}%"
    except (TypeError, ValueError, ZeroDivisionError):
        return "—"


def fmt_delta(value, baseline, decimals: int = 1) -> str:
    """Format a change from baseline with sign."""
    try:
        d = float(value) - float(baseline)
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def fmt_median(val, decimals: int = 1) -> str:
    """Format median value."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "—"
    try:
        return f"{float(val):.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def truncate(text: Optional[str], max_len: int = 80) -> str:
    if not text:
        return ""
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def title_case(text: Optional[str]) -> str:
    if not text:
        return ""
    return text.replace("_", " ").title()


def fmt_phase(phase: Optional[str]) -> str:
    mapping = {
        "EARLY_PHASE1": "Early Ph.1",
        "PHASE1":       "Phase 1",
        "PHASE2":       "Phase 2",
        "PHASE3":       "Phase 3",
        "PHASE4":       "Phase 4",
    }
    return mapping.get(phase or "", phase or "—")


def fmt_status(status: Optional[str]) -> str:
    mapping = {
        "COMPLETED":             "Completed",
        "RECRUITING":            "Recruiting",
        "ACTIVE_NOT_RECRUITING": "Active (NR)",
        "TERMINATED":            "Terminated",
        "SUSPENDED":             "Suspended",
        "WITHDRAWN":             "Withdrawn",
    }
    return mapping.get(status or "", status or "—")


def safe_int(val) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def safe_float(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0
