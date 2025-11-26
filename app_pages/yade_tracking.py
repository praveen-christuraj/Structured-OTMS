from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from db import get_session
from ui import header
from auth import AuthManager
from permission_manager import PermissionManager
from location_manager import LocationManager
from models import YadeVoyage, TOAYadeStage
from location_config import get_page_section_config


def _canonical_location_tokens(value: str | None) -> set[str]:
    tokens: set[str] = set()
    if value is None:
        return tokens
    try:
        raw = str(value).strip().upper()
    except Exception:
        return tokens
    if not raw:
        return tokens
    cleaned = raw.replace(".", "")
    variants = {
        cleaned,
        cleaned.replace(" ", ""),
        cleaned.replace("-", ""),
        cleaned.replace("_", ""),
    }
    variants.add(cleaned.replace("JETTY", "").strip())
    tokens.update({v for v in variants if v})
    return tokens


_YADE_TRACKING_TARGETS = {
    "ASEMOKU": {"label": "Asemoku Jetty", "tokens": {"ASEMOKU", "ASEMOKUJETTY", "JETTY"}},
    "NDONI": {"label": "Ndoni", "tokens": {"NDONI"}},
    "AGGE": {"label": "Agge", "tokens": {"AGGE"}},
}


def _resolve_yade_tracking_locations(session) -> Dict[str, Optional[Dict[str, Any]]]:
    matches: Dict[str, Optional[Dict[str, Any]]] = {k: None for k in _YADE_TRACKING_TARGETS}
    from models import Location
    all_locations = session.query(Location).all()

    for loc in all_locations:
        loc_tokens = _canonical_location_tokens(getattr(loc, "code", None))
        loc_tokens.update(_canonical_location_tokens(getattr(loc, "name", None)))
        if not loc_tokens:
            continue
        for key, meta in _YADE_TRACKING_TARGETS.items():
            if matches[key]:
                continue
            if loc_tokens & set(meta["tokens"]):
                matches[key] = {"id": loc.id, "name": loc.name, "code": loc.code}
    return matches


def _load_yade_tracking_rows(session, location_ids: List[int]) -> List[Dict[str, Any]]:
    if not location_ids:
        return []
    voyages = (
        session.query(YadeVoyage)
        .filter(YadeVoyage.location_id.in_(location_ids))
        .order_by(YadeVoyage.date.desc(), YadeVoyage.time.desc())
        .all()
    )
    if not voyages:
        return []
    voyage_ids = [v.id for v in voyages]
    stage_rows = session.query(TOAYadeStage).filter(TOAYadeStage.voyage_id.in_(voyage_ids)).all()
    stage_map: Dict[int, Dict[str, TOAYadeStage]] = {}
    for stage_row in stage_rows:
        stage_key = (stage_row.stage or "").strip().lower()
        stage_map.setdefault(stage_row.voyage_id, {})[stage_key] = stage_row

    def _stage_nsv(stage_obj: Optional[TOAYadeStage]) -> Optional[float]:
        if not stage_obj:
            return None
        try:
            return round(float(getattr(stage_obj, "nsv_bbl", 0.0) or 0.0), 2)
        except Exception:
            return None

    rows: List[Dict[str, Any]] = []
    for voyage in voyages:
        per_stage = stage_map.get(voyage.id, {})
        loading_berth = voyage.loading_berth
        if hasattr(loading_berth, "value"):
            loading_berth = loading_berth.value
        rows.append(
            {
                "voyage.date": voyage.date,
                "voyage.convoy_no": voyage.convoy_no or "",
                "voyage.yade_name": voyage.yade_name or "",
                "toa.before.nsv_bbl": _stage_nsv(per_stage.get("before")),
                "toa.after.nsv_bbl": _stage_nsv(per_stage.get("after")),
                "voyage.loading_berth": loading_berth or "",
                "voyage.location_id": voyage.location_id,
                "voyage.id": voyage.id,
            }
        )
    return rows


def render_yade_tracking_page(active_location_id: int | None, user: Dict[str, Any] | None) -> None:
    header("Yade Tracking")

    if not active_location_id:
        st.error("No active location selected. Select a location on Home.")
        st.stop()

    user = user or {}
    if user:
        if not AuthManager.can_access_location(user, active_location_id):
            st.error("You do not have access to this location.")
            st.stop()

    with get_session() as s:
        loc = LocationManager.get_location_by_id(s, active_location_id)
        if not loc:
            st.error("Location not found.")
            st.stop()
        st.info(f"Active Location: {loc.name} ({loc.code})")

        role = user.get("role", "operator")
        can_view = PermissionManager.can_access_operational_pages(user) and PermissionManager.can_access_feature(
            s, active_location_id, "yade_transactions", role
        )

        if not can_view:
            allowed = PermissionManager.get_allowed_locations_for_feature(s, "yade_transactions")
            st.error("Access Denied")
            st.warning(f"Yade Tracking is not available at {loc.name}")
            if allowed:
                st.info(f"Available at: {', '.join(allowed)}")
            st.caption(f"Current Location: {loc.name} ({loc.code})")
            st.stop()

        tracking_meta = _resolve_yade_tracking_locations(s)
        missing_targets = [m["label"] for k, m in _YADE_TRACKING_TARGETS.items() if not tracking_meta.get(k)]

        cfg = get_page_section_config(s, loc.id, page="yade_tracking", section="customization") or {}
        tables = list(cfg.get("tables") or [])
        if not tables:
            tables = [
                {
                    "title": "Jetty Departure",
                    "sources": [k for k in ("ASEMOKU", "NDONI") if tracking_meta.get(k)],
                    "columns": [
                        {"label": "Date", "source": "voyage.date"},
                        {"label": "Convoy No", "source": "voyage.convoy_no"},
                        {"label": "Yade No", "source": "voyage.yade_name"},
                        {"label": "ROB qty", "source": "toa.before.nsv_bbl"},
                        {"label": "TOB qty", "source": "toa.after.nsv_bbl"},
                        {"label": "Loading berth", "source": "voyage.loading_berth"},
                    ],
                    "filters": [
                        {"label": "Date", "source": "voyage.date"},
                        {"label": "Convoy No", "source": "voyage.convoy_no"},
                        {"label": "Yade No", "source": "voyage.yade_name"},
                        {"label": "Loading berth", "source": "voyage.loading_berth"},
                    ],
                },
                {
                    "title": "Agge Arrival",
                    "sources": [k for k in ("AGGE",) if tracking_meta.get(k)],
                    "columns": [
                        {"label": "Date", "source": "voyage.date"},
                        {"label": "Convoy No", "source": "voyage.convoy_no"},
                        {"label": "Yade No", "source": "voyage.yade_name"},
                        {"label": "ROB qty", "source": "toa.after.nsv_bbl"},
                        {"label": "TOB qty", "source": "toa.before.nsv_bbl"},
                        {"label": "Loading berth", "source": "voyage.loading_berth"},
                    ],
                    "filters": [
                        {"label": "Date", "source": "voyage.date"},
                        {"label": "Convoy No", "source": "voyage.convoy_no"},
                        {"label": "Yade No", "source": "voyage.yade_name"},
                        {"label": "Loading berth", "source": "voyage.loading_berth"},
                    ],
                },
            ]

        def _ids_for_sources(src_keys: List[str]) -> List[int]:
            ids: List[int] = []
            for k in (src_keys or []):
                m = tracking_meta.get(k)
                if m and m.get("id"):
                    ids.append(m["id"])
            return ids

    if missing_targets:
        st.warning("Locations missing from the database: " + ", ".join(missing_targets))

    def _source_labels(keys: List[str]) -> List[str]:
        labels: List[str] = []
        for key in keys:
            meta = tracking_meta.get(key)
            if meta:
                labels.append(meta.get("name") or meta.get("code") or _YADE_TRACKING_TARGETS[key]["label"])
        return labels

    def _render_tracking_table(title: str, rows: List[Dict[str, Any]], key_prefix: str, keys: List[str], columns: List[Dict[str, str]], filters: List[Dict[str, str]]):
        st.markdown(f"### {title}")
        sources = _source_labels(keys)
        if sources:
            st.caption("Data sources: " + ", ".join(sources))
        if not rows:
            st.info("No YADE voyages captured yet.")
            return
        df = pd.DataFrame(rows)
        if df.empty:
            st.info("No YADE voyages captured yet.")
            return
        def _fmt_date_cell(val):
            if isinstance(val, (datetime, date)):
                return val.strftime("%Y-%m-%d")
            if not val:
                return ""
            try:
                return pd.to_datetime(val).date().strftime("%Y-%m-%d")
            except Exception:
                return str(val)
        # Build filter projection columns based on config
        for fl in (filters or []):
            src = fl.get("source")
            lab = fl.get("label") or src
            proj_name = f"_flt_{lab}"
            if src.endswith("date"):
                df[proj_name] = df[src].apply(_fmt_date_cell)
            else:
                df[proj_name] = df[src].fillna("").astype(str)
        f_cols = st.columns(4)
        # Render dynamic filters
        filter_selections: Dict[str, List[str]] = {}
        for idx, fl in enumerate(filters[:4]):
            lab = fl.get("label") or fl.get("source")
            proj_name = f"_flt_{lab}"
            opts = sorted([x for x in df[proj_name].unique() if x])
            sel = f_cols[idx].multiselect(lab, options=opts, default=[], key=f"{key_prefix}_flt_{idx}")
            if sel:
                df = df[df[proj_name].isin(sel)]

        # Build display columns from config
        display_df = pd.DataFrame()
        for col in (columns or []):
            lab = col.get("label") or col.get("source")
            src = col.get("source")
            display_df[lab] = df[src]
        # Format quantities nicely if present
        for lab, src in [(c.get("label"), c.get("source")) for c in (columns or [])]:
            if src in ("toa.before.nsv_bbl", "toa.after.nsv_bbl"):
                display_df[lab] = display_df[lab].apply(lambda v: f"{v:,.2f}" if v is not None else "")
        st.dataframe(display_df, hide_index=True, use_container_width=True)
        st.caption(f"{len(display_df)} voyage(s) shown")

    # Render per customization tables
    cols = st.columns(2)
    for i, t in enumerate(tables):
        keys = list(t.get("sources") or [])
        ids = _ids_for_sources(keys)
        with (cols[i % 2]):
            rows = _load_yade_tracking_rows(s, ids)
            _render_tracking_table(t.get("title") or f"Table {i+1}", rows, f"yt_track_{i}", keys, t.get("columns") or [], t.get("filters") or [])

