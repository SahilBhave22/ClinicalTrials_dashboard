"""
KPI / metric card components rendered with custom HTML.
"""
from __future__ import annotations
import streamlit as st
from utils.formatting import fmt_number, fmt_pct


_CARD_CSS = """
<style>
.metric-card {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-left: 4px solid #0F4C81;
    border-radius: 12px;
    padding: 20px 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    /* Flex column so label min-height keeps value aligned across all tiles */
    height: 130px;
    box-sizing: border-box;
    position: relative;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: box-shadow .2s ease, transform .2s ease;
}
.metric-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,.10), 0 12px 32px rgba(15,76,129,.08);
    transform: translateY(-2px);
}
.metric-card::before {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 80px; height: 80px;
    background: radial-gradient(circle at top right, rgba(15,76,129,.06) 0%, transparent 70%);
    pointer-events: none;
}
.metric-card .label {
    font-size: 13px;
    font-weight: 500;
    letter-spacing: .03em;
    color: #6B7280;
    text-transform: uppercase;
    margin-bottom: 4px;
    /* Reserve 2-line height so the KPI value starts at the same position
       whether the label is one line or two lines */
    min-height: 2.4em;
    flex-shrink: 0;
    /* Prevent label text from running under the icon */
    padding-right: 44px;
}
.metric-card .value {
    font-size: 32px;
    font-weight: 700;
    color: #0F4C81;
    line-height: 1.1;
    margin-top: 4px;
}
.metric-card .delta {
    font-size: 12px;
    margin-top: 4px;
    color: #6B7280;
}
.metric-card .delta.positive { color: #2A9D8F; }
.metric-card .delta.negative { color: #E76F51; }
.metric-card .icon {
    font-size: 1.15rem;
    /* Absolute so it sits top-right without affecting the flex column flow */
    position: absolute;
    top: 16px;
    right: 16px;
    float: none;
    background: rgba(15,76,129,0.08);
    border-radius: 8px;
    padding: 6px 8px;
    line-height: 1;
    opacity: .95;
}
</style>
"""

def _inject_css():
    # Always inject on every rerun. The module-level flag pattern breaks across
    # Streamlit reruns because module globals persist while the DOM is wiped.
    # Duplicate <style> blocks are harmless in HTML.
    st.markdown(_CARD_CSS, unsafe_allow_html=True)


def metric_card(
    label: str,
    value: str | int | float,
    delta: str | None = None,
    delta_positive: bool | None = None,
    icon: str = "",
    fmt: bool = True,
    accent_color: str = "#0F4C81",
    _skip_css: bool = False,
) -> None:
    if not _skip_css:
        _inject_css()
    value_str = fmt_number(value) if fmt and isinstance(value, (int, float)) else str(value)
    delta_html = ""
    if delta is not None:
        cls = ""
        if delta_positive is True:
            cls = "positive"
        elif delta_positive is False:
            cls = "negative"
        delta_html = f'<div class="delta {cls}">{delta}</div>'

    icon_html = f'<span class="icon">{icon}</span>' if icon else ""
    style = f'style="border-left-color:{accent_color};"' if accent_color != "#0F4C81" else ""
    html = f"""
    <div class="metric-card" {style}>
        {icon_html}
        <div class="label">{label}</div>
        <div class="value">{value_str}</div>
        {delta_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def kpi_row(metrics: list[dict]) -> None:
    """
    Render a row of KPI cards.

    Each metric dict:
        label, value, [delta], [delta_positive], [icon], [fmt], [accent_color]
    """
    # Inject CSS here — BEFORE st.columns — so the <style> block is not
    # placed inside any column (which would create an extra element-container
    # with margin-bottom, shifting the first card down).
    _inject_css()
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            metric_card(
                label=m["label"],
                value=m["value"],
                delta=m.get("delta"),
                delta_positive=m.get("delta_positive"),
                icon=m.get("icon", ""),
                fmt=m.get("fmt", True),
                accent_color=m.get("accent_color", "#0F4C81"),
                _skip_css=True,
            )
