"""
Data access wrapper — thin layer over utils/db_conn.py.

All application code imports from here, not from utils.db_conn directly.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd

# Import the existing db_conn utilities
from utils.db_conn import exec_sql, get_engine  # noqa: F401 (re-export)
from config.settings import DB_AACT, DB_DRUGS


@st.cache_data(ttl=300, show_spinner=False)
def query_aact(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Execute a read-only SQL query against the AACT database with caching."""
    try:
        return exec_sql(sql, DB_AACT, params)
    except Exception as e:
        st.error(f"AACT query error: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def query_drugs(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Execute a read-only SQL query against the Drugs database with caching."""
    try:
        return exec_sql(sql, DB_DRUGS, params)
    except Exception as e:
        st.error(f"Drugs DB query error: {e}")
        return pd.DataFrame()


def query_aact_uncached(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Execute without cache – used for NL queries and one-off fetches."""
    try:
        return exec_sql(sql, DB_AACT, params)
    except Exception as e:
        st.error(f"AACT query error: {e}")
        return pd.DataFrame()
