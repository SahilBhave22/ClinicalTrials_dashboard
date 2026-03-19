"""
Table rendering: AG Grid (via streamlit-aggrid) with fallback to st.dataframe.
Provides consistent styling and export capability.
"""
from __future__ import annotations
import io
import pandas as pd
import streamlit as st

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
    _HAS_AGGRID = True
except ImportError:
    _HAS_AGGRID = False


def _col_defs(df: pd.DataFrame) -> list[dict]:
    """Auto-generate AG Grid column definitions."""
    defs = []
    for col in df.columns:
        d: dict = {"field": col, "headerName": col.replace("_", " ").title()}
        if pd.api.types.is_numeric_dtype(df[col]):
            d["type"] = "numericColumn"
            d["filter"] = "agNumberColumnFilter"
        else:
            d["filter"] = "agTextColumnFilter"
            d["width"] = 160
        defs.append(d)
    return defs


def ag_table(
    df: pd.DataFrame,
    height: int = 400,
    fit_columns: bool = False,
    key: str = "ag_table",
) -> None:
    """Render a DataFrame in AG Grid with sorting, filtering, and pagination."""
    if df.empty:
        st.info("No data to display.")
        return

    if not _HAS_AGGRID:
        st.dataframe(df, use_container_width=True)
        return

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(
        resizable=True,
        filterable=True,
        sortable=True,
        editable=False,
    )
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=25)
    gb.configure_side_bar(filters_panel=True, columns_panel=False)
    gb.configure_selection(selection_mode="single", use_checkbox=False)
    grid_opts = gb.build()

    AgGrid(
        df,
        gridOptions=grid_opts,
        height=height,
        fit_columns_on_grid_load=fit_columns,
        update_mode=GridUpdateMode.NO_UPDATE,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        allow_unsafe_jscode=False,
        theme="streamlit",
        key=key,
    )


def styled_table(df: pd.DataFrame, height: int = 400) -> None:
    """Fallback styled Streamlit dataframe."""
    if df.empty:
        st.info("No data to display.")
        return
    st.dataframe(df, use_container_width=True, height=height)


def csv_download_button(df: pd.DataFrame, filename: str = "export.csv",
                         label: str = "⬇ Download CSV") -> None:
    """Render a download button for the given DataFrame."""
    if df.empty:
        return
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.download_button(
        label=label,
        data=buf.getvalue().encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        use_container_width=True,
    )
