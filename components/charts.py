"""
Reusable Plotly chart builders.
All functions accept a DataFrame and return a Plotly Figure.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config.settings import (
    CATEGORICAL_PALETTE, PHASE_COLORS, STATUS_COLORS,
    PRIMARY_COLOR, NEUTRAL_COLOR,
)

# ── Layout defaults ───────────────────────────────────────────────────────────
_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans, system-ui, sans-serif", size=12, color="#1A1A2E"),
    height=380,
    margin=dict(l=40, r=20, t=65, b=40),
    hoverlabel=dict(bgcolor="white", font_size=12),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        font=dict(size=10),
        tracegroupgap=2,
        itemsizing="constant",
    ),
)

_AXIS = dict(
    showgrid=True,
    gridcolor="#F3F4F6",
    gridwidth=1,
    showline=True,
    linecolor="#E5E7EB",
    tickfont=dict(size=11),
    title_font=dict(size=12, color="#1A1A2E"),
    automargin=True,
)

_AXIS_X = dict(
    showgrid=False,
    showline=True,
    linecolor="#E5E7EB",
    tickfont=dict(size=11),
    title_font=dict(size=12, color="#1A1A2E"),
    automargin=True,
)

# Max characters shown in an axis tick label before truncation
_TICK_MAXLEN = 22


def _clip(labels: list, maxlen: int = _TICK_MAXLEN) -> list[str]:
    """Truncate long tick label strings with an ellipsis."""
    return [f"{str(s)[:maxlen]}…" if len(str(s)) > maxlen else str(s) for s in labels]


def _apply_category_axis(fig: go.Figure, labels: list, axis: str = "y") -> None:
    """
    Set truncated tick labels on a categorical axis while keeping the full
    value available in the hover via the original data.
    `axis` is "x" or "y".
    """
    clipped = _clip(labels)
    update = dict(
        tickmode="array",
        tickvals=labels,
        ticktext=clipped,
        automargin=True,
    )
    if axis == "y":
        fig.update_yaxes(**update)
    else:
        fig.update_xaxes(**update, tickangle=-40)


def _base_fig(title: str = "") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(title=dict(text=title, font=dict(size=14, color="#0F4C81")), **_LAYOUT)
    return fig


# ── Bar charts ────────────────────────────────────────────────────────────────

def bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    color: str = PRIMARY_COLOR,
    orientation: str = "v",
    text_auto: bool = True,
) -> go.Figure:
    if df.empty:
        return _base_fig(title)
    if orientation == "h":
        fig = px.bar(df, y=x, x=y, orientation="h",
                     title=title, color_discrete_sequence=[color],
                     text_auto=text_auto)
        fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=14, color="#0F4C81")))
        fig.update_layout(margin=dict(l=20, r=24, t=50, b=28))
        fig.update_xaxes(**_AXIS_X)
        _apply_category_axis(fig, df[x].tolist(), axis="y")
        fig.update_yaxes(autorange="reversed", automargin=True)
    else:
        fig = px.bar(df, x=x, y=y, orientation="v",
                     title=title, color_discrete_sequence=[color],
                     text_auto=text_auto)
        fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=14, color="#0F4C81")))
        fig.update_yaxes(**_AXIS)
        _apply_category_axis(fig, df[x].tolist(), axis="x")
    fig.update_traces(marker_line_width=0)
    return fig


def grouped_bar(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str,
    title: str = "",
    barmode: str = "group",
) -> go.Figure:
    if df.empty:
        return _base_fig(title)
    fig = px.bar(df, x=x, y=y, color=color, barmode=barmode,
                 title=title, color_discrete_sequence=CATEGORICAL_PALETTE)
    n_cats = df[color].nunique() if color in df.columns else 1
    top_margin = 90 if n_cats > 5 else 65
    fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=14, color="#0F4C81")))
    fig.update_layout(margin=dict(l=40, r=20, t=top_margin, b=40))
    fig.update_yaxes(**_AXIS)
    _apply_category_axis(fig, df[x].unique().tolist(), axis="x")
    fig.update_traces(marker_line_width=0)
    return fig


def stacked_bar(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str,
    title: str = "",
    color_map: dict | None = None,
) -> go.Figure:
    if df.empty:
        return _base_fig(title)
    kw: dict = dict(x=x, y=y, color=color, barmode="stack", title=title)
    if color_map:
        kw["color_discrete_map"] = color_map
    else:
        kw["color_discrete_sequence"] = CATEGORICAL_PALETTE
    fig = px.bar(df, **kw)
    n_cats = df[color].nunique() if color in df.columns else 1
    top_margin = 90 if n_cats > 5 else 65
    fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=14, color="#0F4C81")))
    fig.update_layout(margin=dict(l=40, r=20, t=top_margin, b=40))
    fig.update_yaxes(**_AXIS)
    _apply_category_axis(fig, df[x].unique().tolist(), axis="x")
    fig.update_traces(marker_line_width=0)
    return fig


# ── Pie / donut ───────────────────────────────────────────────────────────────

def donut_chart(
    df: pd.DataFrame,
    names: str,
    values: str,
    title: str = "",
    color_map: dict | None = None,
) -> go.Figure:
    if df.empty:
        return _base_fig(title)
    kw = dict(names=names, values=values, title=title, hole=0.45)
    if color_map:
        kw["color"] = names
        kw["color_discrete_map"] = color_map
    else:
        kw["color_discrete_sequence"] = CATEGORICAL_PALETTE
    fig = px.pie(df, **kw)
    fig.update_traces(textposition="inside", textinfo="percent+label",
                      hovertemplate="%{label}: %{value} (%{percent})")
    fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=14, color="#0F4C81")))
    # Vertical right-side legend keeps the donut from being crushed vertically
    fig.update_layout(
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.02,
            font=dict(size=10),
        ),
        margin=dict(l=10, r=10, t=50, b=10),
    )
    return fig


# ── Line / area ───────────────────────────────────────────────────────────────

def line_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    color: str = PRIMARY_COLOR,
) -> go.Figure:
    if df.empty:
        return _base_fig(title)
    fig = px.line(df, x=x, y=y, title=title, color_discrete_sequence=[color])
    fig.update_traces(line_width=2, mode="lines+markers", marker_size=5)
    fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=14, color="#0F4C81")))
    fig.update_xaxes(**_AXIS_X)
    fig.update_yaxes(**_AXIS)
    return fig


def area_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    color: str = PRIMARY_COLOR,
) -> go.Figure:
    if df.empty:
        return _base_fig(title)
    fig = px.area(df, x=x, y=y, title=title, color_discrete_sequence=[color])
    fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=14, color="#0F4C81")))
    fig.update_xaxes(**_AXIS_X)
    fig.update_yaxes(**_AXIS)
    return fig


# ── Treemap / sunburst ────────────────────────────────────────────────────────

def treemap_chart(
    df: pd.DataFrame,
    path: list[str],
    values: str,
    title: str = "",
) -> go.Figure:
    if df.empty:
        return _base_fig(title)
    fig = px.treemap(df, path=path, values=values, title=title,
                     color_discrete_sequence=CATEGORICAL_PALETTE)
    fig.update_traces(textinfo="label+value+percent parent")
    fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=14, color="#0F4C81")))
    fig.update_layout(height=440, margin=dict(l=10, r=10, t=50, b=10))
    return fig


def sunburst_chart(
    df: pd.DataFrame,
    path: list[str],
    values: str,
    title: str = "",
) -> go.Figure:
    if df.empty:
        return _base_fig(title)
    fig = px.sunburst(df, path=path, values=values, title=title,
                      color_discrete_sequence=CATEGORICAL_PALETTE)
    fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=14, color="#0F4C81")))
    fig.update_layout(height=440, margin=dict(l=10, r=10, t=50, b=10))
    return fig


# ── Scatter / bubble ─────────────────────────────────────────────────────────

def scatter_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None = None,
    size: str | None = None,
    hover_name: str | None = None,
    title: str = "",
) -> go.Figure:
    if df.empty:
        return _base_fig(title)
    kw: dict = dict(x=x, y=y, title=title, color_discrete_sequence=CATEGORICAL_PALETTE)
    if color:
        kw["color"] = color
    if size:
        kw["size"] = size
    if hover_name:
        kw["hover_name"] = hover_name
    fig = px.scatter(df, **kw)
    fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=14, color="#0F4C81")))
    fig.update_xaxes(**_AXIS_X)
    fig.update_yaxes(**_AXIS)
    return fig


# ── Box plot ──────────────────────────────────────────────────────────────────

def box_plot(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None = None,
    title: str = "",
    points: str = "outliers",
) -> go.Figure:
    if df.empty:
        return _base_fig(title)
    kw: dict = dict(x=x, y=y, title=title, points=points,
                    color_discrete_sequence=CATEGORICAL_PALETTE)
    if color:
        kw["color"] = color
    fig = px.box(df, **kw)
    fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=14, color="#0F4C81")))
    if color:
        # Side legend prevents the horizontal legend from compressing the plot area
        fig.update_layout(
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02,
                font=dict(size=10),
            ),
            margin=dict(l=40, r=130, t=50, b=40),
        )
    fig.update_yaxes(**_AXIS)
    _apply_category_axis(fig, df[x].unique().tolist(), axis="x")
    return fig


# ── Heatmap ───────────────────────────────────────────────────────────────────

def heatmap_chart(
    df_pivot: pd.DataFrame,
    title: str = "",
    x_label: str = "",
    y_label: str = "",
    colorscale: str = "Blues",
) -> go.Figure:
    if df_pivot.empty:
        return _base_fig(title)
    n_rows = len(df_pivot)
    n_cols = len(df_pivot.columns)
    # Scale height with data density; minimum 380, ~28px per row
    dynamic_height = max(380, n_rows * 28 + 120)
    # Rotate x-axis labels when there are many columns or long names
    x_angle = -40 if n_cols > 6 else 0
    x_labels = _clip(df_pivot.columns.tolist())
    y_labels = _clip(df_pivot.index.tolist())
    fig = go.Figure(
        data=go.Heatmap(
            z=df_pivot.values,
            x=x_labels,
            y=y_labels,
            colorscale=colorscale,
            hoverongaps=False,
            hovertemplate="%{y} × %{x}: %{z}<extra></extra>",
        )
    )
    fig.update_layout(
        **_LAYOUT,
        title=dict(text=title, font=dict(size=14, color="#0F4C81")),
        showlegend=False,
        xaxis=dict(**_AXIS_X, title=x_label, tickangle=x_angle),
        yaxis=dict(**_AXIS, title=y_label),
    )
    fig.update_layout(height=dynamic_height, margin=dict(l=20, r=20, t=55, b=60 if x_angle else 40))
    return fig


# ── Funnel ────────────────────────────────────────────────────────────────────

def funnel_chart(
    df: pd.DataFrame,
    y: str,
    x: str,
    title: str = "",
) -> go.Figure:
    if df.empty:
        return _base_fig(title)
    fig = px.funnel(df, y=y, x=x, title=title,
                    color_discrete_sequence=CATEGORICAL_PALETTE)
    fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(size=14, color="#0F4C81")))
    return fig


# ── Phase color helper ────────────────────────────────────────────────────────

def phase_bar(df: pd.DataFrame, x: str, y: str, title: str = "") -> go.Figure:
    """Bar chart with per-phase colour coding."""
    if df.empty:
        return _base_fig(title)
    color_map = {k: v for k, v in PHASE_COLORS.items()}
    fig = px.bar(df, x=x, y=y, color=x, title=title,
                 color_discrete_map=color_map)
    fig.update_layout(
        **_LAYOUT,
        title=dict(text=title, font=dict(size=14, color="#0F4C81")),
        showlegend=False,  # x-axis already labels each phase; legend is redundant
    )
    fig.update_layout(margin=dict(l=40, r=20, t=50, b=40))
    fig.update_yaxes(**_AXIS)
    _apply_category_axis(fig, df[x].tolist(), axis="x")
    fig.update_traces(marker_line_width=0)
    return fig


def status_bar(df: pd.DataFrame, x: str, y: str, title: str = "") -> go.Figure:
    """Bar chart with per-status colour coding."""
    if df.empty:
        return _base_fig(title)
    fig = px.bar(df, x=x, y=y, color=x, title=title,
                 color_discrete_map=STATUS_COLORS)
    fig.update_layout(
        **_LAYOUT,
        title=dict(text=title, font=dict(size=14, color="#0F4C81")),
        showlegend=False,  # x-axis already labels each status; legend is redundant
    )
    fig.update_layout(margin=dict(l=40, r=20, t=50, b=40))
    fig.update_yaxes(**_AXIS)
    _apply_category_axis(fig, df[x].tolist(), axis="x")
    fig.update_traces(marker_line_width=0)
    return fig
