# app_pages/page_customization.py
import streamlit as st
from typing import Dict, Any
from db import get_session
from models import Location
from permission_manager import PermissionManager

# Pull + Save helpers from location_config
from location_config import (
    get_page_section_config,
    set_page_section_config,
)

def _guard_admin(user) -> bool:
    if not user or not PermissionManager.can_access_management_pages(user):
        st.error("You do not have permission to access Page Customization.")
        return False
    return True

def _pick_location(active_location_id: int):
    """Return (loc, label). If no active location, let admin pick."""
    if not active_location_id:
        st.warning("No active location selected on Home. Pick a location here for customization.")
        with get_session() as s:
            locs = s.query(Location).order_by(Location.name.asc()).all()
        if not locs:
            st.error("No locations found. Create one in Manage Locations.")
            return None, None

        labels = [f"{l.name} ({l.code})" for l in locs]
        lab2id = {labels[i]: locs[i].id for i in range(len(locs))}
        sel = st.selectbox("Select location", labels, key="pc_loc_pick")
        lid = lab2id.get(sel)
        if not lid:
            return None, None
        with get_session() as s:
            loc = s.query(Location).get(lid)
        return loc, f"{loc.name} ({loc.code})"

    with get_session() as s:
        loc = s.query(Location).get(active_location_id)
    if not loc:
        st.error("Active location not found. Re-select on Home.")
        return None, None
    return loc, f"{loc.name} ({loc.code})"


def _ensure_len(labels, n, filler_prefix):
    labels = list(labels or [])
    if len(labels) < n:
        labels += [f"{filler_prefix} {i+1}" for i in range(len(labels), n)]
    elif len(labels) > n:
        labels = labels[:n]
    return labels


def render_page_customization(user: Dict[str, Any]):
    st.markdown("### ⚙️ Page Customization")

    if not _guard_admin(user):
        return

    # Resolve location (use current active if present)
    active_location_id = st.session_state.get("active_location_id")
    loc, loc_label = _pick_location(active_location_id)
    if not loc:
        return

    st.caption(f"Configuring for **{loc_label}**")
    st.markdown("---")

    # Use a stable location-based suffix so keys are unique across locations
    loc_key = f"{loc.id}"

    # ================================
    # Tank Transactions → Condensate
    # ================================
    with st.expander("🧪 Condensate Records", expanded=True):
        with get_session() as s:
            cond_cfg = get_page_section_config(s, loc.id, page="tank_transactions", section="condensate")

        cond_streams = int(cond_cfg.get("streams", 1))
        cond_labels = list(cond_cfg.get("labels", [f"Meter {i+1}" for i in range(cond_streams)]))
        cond_labels = _ensure_len(cond_labels, cond_streams, "Meter")

        # UNIQUE KEY for number_input (avoid duplicate id)
        ncond = st.number_input(
            "Number of streams",
            min_value=1, max_value=12, value=cond_streams, step=1,
            key=f"pc_cond_streams_{loc_key}"
        )

        cond_labels = _ensure_len(cond_labels, int(ncond), "Meter")
        for i in range(int(ncond)):
            cond_labels[i] = st.text_input(
                f"Label for stream {i+1}",
                value=cond_labels[i],
                key=f"pc_cond_label_{loc_key}_{i}"
            )

        if st.button("💾 Save Condensate Config", type="primary", key=f"pc_cond_save_{loc_key}"):
            try:
                with get_session() as s:
                    set_page_section_config(
                        s, loc.id,
                        page="tank_transactions",
                        section="condensate",
                        new_config={"streams": int(ncond), "labels": cond_labels},
                    )
                st.success("Condensate configuration saved.")
            except Exception as ex:
                st.error(f"Save failed: {ex}")

    st.markdown("---")

    # =======================================
    # Tank Transactions → Produced Water
    # =======================================
    with st.expander("💧 Produced Water Records", expanded=True):
        with get_session() as s:
            pw_cfg = get_page_section_config(s, loc.id, page="tank_transactions", section="produced_water")

        pw_streams = int(pw_cfg.get("streams", 1))
        pw_labels = list(pw_cfg.get("labels", [f"Stream {i+1}" for i in range(pw_streams)]))
        pw_labels = _ensure_len(pw_labels, pw_streams, "Stream")

        npw = st.number_input(
            "Number of streams",
            min_value=1, max_value=12, value=pw_streams, step=1,
            key=f"pc_pw_streams_{loc_key}"          # <-- UNIQUE KEY
        )

        pw_labels = _ensure_len(pw_labels, int(npw), "Stream")
        for i in range(int(npw)):
            pw_labels[i] = st.text_input(
                f"Label for stream {i+1}",
                value=pw_labels[i],
                key=f"pc_pw_label_{loc_key}_{i}"     # <-- UNIQUE KEY
            )

        if st.button("💾 Save Produced Water Config", type="primary", key=f"pc_pw_save_{loc_key}"):
            try:
                with get_session() as s:
                    set_page_section_config(
                        s, loc.id,
                        page="tank_transactions",
                        section="produced_water",
                        new_config={"streams": int(npw), "labels": pw_labels},
                    )
                st.success("Produced water configuration saved.")
            except Exception as ex:
                st.error(f"Save failed: {ex}")

    st.markdown("---")

    # =======================================
    # Tank Transactions → Production
    # =======================================
    with st.expander("🏭 Production", expanded=True):
        with get_session() as s:
            prod_cfg = get_page_section_config(s, loc.id, page="tank_transactions", section="production")

        prod_rows = int(prod_cfg.get("streams", 1))
        prod_labels = list(prod_cfg.get("labels", [f"Item {i+1}" for i in range(prod_rows)]))
        prod_labels = _ensure_len(prod_labels, prod_rows, "Item")

        nprod = st.number_input(
            "Number of rows",
            min_value=1, max_value=20, value=prod_rows, step=1,
            key=f"pc_prod_rows_{loc_key}"           # <-- UNIQUE KEY
        )

        prod_labels = _ensure_len(prod_labels, int(nprod), "Item")
        for i in range(int(nprod)):
            prod_labels[i] = st.text_input(
                f"Label for row {i+1}",
                value=prod_labels[i],
                key=f"pc_prod_label_{loc_key}_{i}"   # <-- UNIQUE KEY
            )

        if st.button("💾 Save Production Config", type="primary", key=f"pc_prod_save_{loc_key}"):
            try:
                with get_session() as s:
                    set_page_section_config(
                        s, loc.id,
                        page="tank_transactions",
                        section="production",
                        new_config={"streams": int(nprod), "labels": prod_labels},
                    )
                st.success("Production configuration saved.")
            except Exception as ex:
                st.error(f"Save failed: {ex}")

    st.info("All changes take effect immediately on the corresponding pages.")
