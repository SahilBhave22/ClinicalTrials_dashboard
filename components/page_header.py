"""
Page header component: title + subtitle + optional breadcrumb.
"""
from __future__ import annotations
import streamlit as st

def page_header(title: str, subtitle: str = "", icon: str = "", breadcrumb: str = "") -> None:
    bc_html = (
        f'<div style="font-size:0.75rem;color:#9CA3AF;margin-bottom:4px;">{breadcrumb}</div>'
        if breadcrumb else ""
    )
    icon_part = f'<span style="font-size:2rem;vertical-align:middle;margin-right:10px;">{icon}</span>' if icon else ""
    sub_html = (
        f'<div style="margin-top:6px;font-size:0.9rem;color:#6B7280;max-width:720px;">{subtitle}</div>'
        if subtitle else ""
    )
    html = (
        f'<div style="padding:12px 0 20px 0;border-bottom:2px solid #E5E7EB;margin-bottom:24px;">'
        f'{bc_html}'
        f'{icon_part}'
        f'<span style="font-size:1.75rem;font-weight:700;color:#0F4C81;vertical-align:middle;">{title}</span>'
        f'{sub_html}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
