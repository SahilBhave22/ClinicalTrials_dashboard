"""
Chart tile wrapper component.

Renders a Plotly figure inside a styled tile with an optional header
(title + subtitle). The tile border/shadow comes from the global CSS rule
targeting [data-testid="stPlotlyChart"] in app.py.
Chart tile header styles (.chart-tile-*) are also defined in app.py.
"""
from __future__ import annotations
import streamlit as st
from plotly.graph_objects import Figure


def chart_tile(
    fig: Figure,
    title: str = "",
    subtitle: str = "",
    height: int | None = None,
) -> None:
    """
    Render a Plotly figure with a styled tile header.

    The tile card effect (border, shadow, radius) comes from the global CSS
    targeting [data-testid="stPlotlyChart"], so no extra wrapper is needed.

    Args:
        fig:      Plotly Figure to render.
        title:    Optional bold header above the chart.
        subtitle: Optional muted sub-header.
        height:   Optional explicit pixel height passed to st.plotly_chart.
    """
    if title:
        sub_html = (
            f'<div class="chart-tile-subtitle">{subtitle}</div>' if subtitle else ""
        )
        st.markdown(
            f'<div class="chart-tile-header">'
            f'<div class="chart-tile-title">{title}</div>'
            f'{sub_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

    kwargs: dict = {"use_container_width": True}
    if height:
        kwargs["height"] = height
    st.plotly_chart(fig, **kwargs)
