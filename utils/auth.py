"""
utils/auth.py

Authentication and session helpers for the per-user access control system.
Credentials are read from st.secrets["users"].
Per-user access policy is read from config/user_access.py.
"""
from __future__ import annotations

import warnings
import streamlit as st

from config.user_access import USER_ACCESS


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_users() -> dict:
    """Return the [users] section from st.secrets, or {} if missing."""
    try:
        return dict(st.secrets["users"])
    except KeyError:
        return {}


def _valid_user_access(username: str) -> bool:
    """Return True if username has an entry in USER_ACCESS."""
    return username in USER_ACCESS


# ── Public API ────────────────────────────────────────────────────────────────

def authenticate(username: str, password: str) -> tuple[bool, dict]:
    """
    Validate credentials against st.secrets["users"].

    Returns (True, user_access_dict) on success, (False, {}) on failure.
    Rejects logins where the username has no entry in USER_ACCESS (misconfiguration guard).
    """
    users = _load_users()
    if not users or username not in users:
        return False, {}

    user_cfg = users[username]
    if user_cfg.get("password", "") != password:
        return False, {}

    if not _valid_user_access(username):
        warnings.warn(
            f"User '{username}' authenticated via secrets.toml but has no entry in "
            "config/user_access.py. Login blocked. Add an entry to USER_ACCESS.",
            stacklevel=2,
        )
        return False, {}

    return True, dict(USER_ACCESS[username])


def get_current_user() -> tuple[str | None, dict]:
    """
    Return (username, user_access_dict) from session_state.
    Returns (None, {}) if not authenticated.
    """
    if not st.session_state.get("authenticated", False):
        return None, {}
    username = st.session_state.get("username")
    user_access = st.session_state.get("user_access", {})
    return username, user_access


def get_user_access() -> dict:
    """Return the USER_ACCESS config dict for the currently logged-in user."""
    return st.session_state.get("user_access", {})


def _tab_text(label: str) -> str:
    """Strip leading emoji + space from a tab label, returning the plain text portion.
    e.g. '🏠 Home' -> 'Home',  'Home' -> 'Home',  'Drug Detail' -> 'Drug Detail'
    Only strips the first token if it is non-ASCII (i.e. an emoji), so multi-word
    plain-text names like 'Drug Pricing' are returned unchanged.
    """
    parts = label.split(" ", 1)
    if len(parts) > 1 and not parts[0].isascii():
        return parts[1]
    return label


def get_allowed_tabs(username: str | None, page_map: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    Filter page_map to the entries allowed for the given username.

    Tab names in user_access.py may be written with or without the leading emoji
    (e.g. 'Home' and '🏠 Home' both match the page_map entry '🏠 Home').

    Supports two configuration modes (inclusion wins if both are set):
    - tabs=[...] — show only these tabs
    - tabs_exclude=[...] — show all tabs EXCEPT these
    - tabs=None and no tabs_exclude — show all tabs

    Unknown username returns only the Home tab as a safe fallback.
    """
    if not username or username not in USER_ACCESS:
        fallback = [entry for entry in page_map if _tab_text(entry[0]) == "Home"]
        return fallback or ([page_map[0]] if page_map else [])

    cfg = USER_ACCESS[username]
    allowed_tabs  = cfg.get("tabs")
    excluded_tabs = cfg.get("tabs_exclude")

    if allowed_tabs is not None:
        # Inclusion list takes precedence over any exclude list
        allowed_text = {_tab_text(t) for t in allowed_tabs}
        return [entry for entry in page_map if _tab_text(entry[0]) in allowed_text]

    if excluded_tabs is not None:
        # Exclusion mode — all tabs except the listed ones
        excluded_text = {_tab_text(t) for t in excluded_tabs}
        return [entry for entry in page_map if _tab_text(entry[0]) not in excluded_text]

    return list(page_map)


def logout() -> None:
    """Clear all auth-related session_state keys and rerun."""
    for key in ("authenticated", "username", "user_access", "_login_attempted"):
        st.session_state.pop(key, None)
    st.rerun()


def render_login_form(logo_b64: str) -> None:
    """
    Render the centered login card. Calls st.stop() if the user is not authenticated.

    On successful sign-in, writes to session_state:
        authenticated = True
        username      = <str>
        user_access   = <dict>   ← full USER_ACCESS entry for this user
    then calls st.rerun().
    """
    if st.session_state.get("authenticated", False):
        return

    _login_slot = st.empty()
    with _login_slot.container():
        st.markdown(f"""
        <style>
        section[data-testid="stSidebar"] {{ display: none !important; }}
        .block-container {{ padding-top: 0 !important; }}

        div[data-testid="stMainBlockContainer"]
            div[data-testid="stHorizontalBlock"]
            > div[data-testid="stColumn"]:nth-child(2)
            > div[data-testid="stVerticalBlock"] {{
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 16px;
                box-shadow: 0 4px 32px rgba(15,76,129,0.12);
                padding: 40px 36px 36px !important;
                margin-top: 80px;
        }}

        div[data-testid="stMainBlockContainer"] .stButton > button {{
            background: #0F4C81 !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            font-size: 15px !important;
            height: 44px !important;
            letter-spacing: 0.01em;
            margin-top: 4px;
        }}
        div[data-testid="stMainBlockContainer"] .stButton > button:hover {{
            background: #0D3F6E !important;
        }}
        </style>

        <div style="height:0"></div>
        """, unsafe_allow_html=True)

        _, col, _ = st.columns([1, 1.4, 1])
        with col:
            st.markdown(f"""
            <div style="text-align:center; margin-bottom:24px;">
                <img src="data:image/png;base64,{logo_b64}"
                     style="height:52px; margin-bottom:18px; display:block; margin-left:auto; margin-right:auto;">
                <div style="font-size:21px; font-weight:700; color:#0F4C81; margin-bottom:5px; letter-spacing:-0.01em;">
                    Clinical Trials Intelligence Platform
                </div>
                <div style="font-size:14px; color:#6B7280;">
                    Sign in to continue
                </div>
            </div>
            <hr style="border:none; border-top:1px solid #E5E7EB; margin:0 0 20px 0;">
            """, unsafe_allow_html=True)

            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", placeholder="Enter your password", type="password")

            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

            if st.button("Sign in", use_container_width=True):
                ok, user_access = authenticate(username, password)
                if ok:
                    st.session_state["authenticated"] = True
                    st.session_state["username"] = username
                    st.session_state["user_access"] = user_access
                    st.session_state.pop("_login_attempted", None)
                    st.rerun()
                else:
                    st.session_state["_login_attempted"] = True
                    st.rerun()

            if st.session_state.get("_login_attempted", False):
                st.error("Incorrect username or password.")

    st.stop()


def render_user_badge() -> None:
    """
    Render the user info block at the top of the sidebar.
    Shows display_name and a Sign out button.
    Must be called before render_sidebar().
    """
    username, user_access = get_current_user()
    if not username:
        return

    display_name = user_access.get("display_name", username.capitalize())

    with st.sidebar:
        st.markdown(f"""
        <div style="padding: 4px 0 8px 0; text-align: center;">
            <div style="font-size: 13px; color: #CBD5E1; margin-bottom: 4px;">
                Signed in as
            </div>
            <div style="font-size: 15px; font-weight: 700; color: #FFFFFF; margin-bottom: 8px;">
                {display_name}
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        if st.button("Sign out", use_container_width=True):
            logout()
