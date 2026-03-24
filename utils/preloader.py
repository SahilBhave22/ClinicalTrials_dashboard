"""
Background data preloader — warms up @st.cache_data before the user logs in.
Spawns a single daemon thread once per process to pre-fetch sidebar + home tab data.
"""
import threading
import logging

_preload_started: bool = False
_preload_lock: threading.Lock = threading.Lock()


def _preload_worker() -> None:
    log = logging.getLogger("preloader")
    try:
        from data.repository import (
            get_overview_kpis,
            get_trials_by_phase,
            get_trials_over_time,
            get_top_sponsors,
            get_top_conditions,
        )
        from utils.filters import FilterState

        default_fs = FilterState()

        # Note: sidebar filter options now load from static catalogs (no DB needed).
        # Only pre-warm the data queries used on the home/overview tab.
        for fn, args, label in [
            (get_overview_kpis,      (default_fs,), "get_overview_kpis"),
            (get_trials_by_phase,    (default_fs,), "get_trials_by_phase"),
            (get_trials_over_time,   (default_fs,), "get_trials_over_time"),
            (get_top_sponsors,       (default_fs,), "get_top_sponsors"),
            (get_top_conditions,     (default_fs,), "get_top_conditions"),
        ]:
            try:
                fn(*args)
                log.info("preloader: %s done", label)
            except Exception:
                log.exception("preloader: %s failed", label)

    except Exception:
        log.exception("preloader: unexpected error in worker setup")


def start_background_preload() -> None:
    """Spawn the preload thread once per process. Safe to call on every rerun."""
    global _preload_started
    with _preload_lock:
        if _preload_started:
            return
        _preload_started = True

    threading.Thread(
        target=_preload_worker,
        name="data-preloader",
        daemon=True,
    ).start()
