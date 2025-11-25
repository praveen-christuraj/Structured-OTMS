import streamlit as st
from datetime import time as dt_time
from typing import Dict, Any, Optional

from db import get_session
from models import Location
from permission_manager import PermissionManager
from location_config import get_page_section_config, set_page_section_config, list_operations
from report_engine import get_available_data_sources, get_columns_for_source


def _guard_admin(user: Optional[Dict[str, Any]]) -> bool:
    """Allow only management roles to access MB Customization."""
    if not user or not PermissionManager.can_access_management_pages(user):
        st.error("You do not have permission to access Material Balance Customization.")
        return False
    return True


def _pick_location(active_location_id: Optional[int]) -> tuple[Optional[Location], Optional[str]]:
    """Pick a location to configure (prefer active, but allow override)."""
    if not active_location_id:
        st.warning("No active location selected on Home. Pick a location here for customization.")
        with get_session() as s:
            locs = s.query(Location).order_by(Location.name.asc()).all()
        if not locs:
            st.error("No locations found. Create one in Manage Locations.")
            return None, None

        labels = [f"{l.name} ({l.code})" for l in locs]
        label_to_id = {labels[i]: locs[i].id for i in range(len(locs))}
        sel = st.selectbox("Select location", labels, key="mb_loc_pick")
        lid = label_to_id.get(sel)
        if not lid:
            return None, None
        with get_session() as s:
            loc = s.query(Location).get(lid)
        return loc, f"{loc.name} ({loc.code})" if loc else (None, None)

    with get_session() as s:
        loc = s.query(Location).get(active_location_id)
    if not loc:
        st.error("Active location not found. Re-select on Home.")
        return None, None
    return loc, f"{loc.name} ({loc.code})"


def _parse_time_str(val: str, default: dt_time) -> dt_time:
    """Parse 'HH:MM' or 'HH:MM:SS' into time, with safe fallback."""
    if not val:
        return default
    try:
        parts = [int(p) for p in str(val).split(":")]
        if len(parts) == 2:
            h, m = parts
            return dt_time(h, m)
        if len(parts) >= 3:
            h, m, s = parts[0], parts[1], parts[2]
            return dt_time(h, m, s)
    except Exception:
        return default
    return default


def render_mb_customization_page(user: Dict[str, Any]):
    """Material Balance Customization (per location)."""
    st.markdown("### ⚙️ Material Balance Customization")

    if not _guard_admin(user):
        return

    active_location_id = st.session_state.get("active_location_id")
    loc, loc_label = _pick_location(active_location_id)
    if not loc:
        return

    st.caption(f"Configuring Material Balance for **{loc_label}**")
    st.markdown("---")

    # -------- Load existing window configuration --------
    with get_session() as s:
        cfg = get_page_section_config(s, loc.id, page="material_balance", section="window") or {}

    use_custom = bool(cfg.get("use_custom_window", False))
    start_str = str(cfg.get("start_time") or "06:01")
    end_str = str(cfg.get("end_time") or "06:00")

    default_start = dt_time(6, 1)
    default_end = dt_time(6, 0)
    start_time_val = _parse_time_str(start_str, default_start)
    end_time_val = _parse_time_str(end_str, default_end)

    st.subheader("Daily Window (per day)")
    st.caption(
        "Define how each Material Balance day is calculated. "
        "Default is **06:01** to **06:00 (next day)**, matching the legacy logic."
    )

    use_custom = st.checkbox(
        "Use custom window for this location",
        value=use_custom,
        help="If unchecked, the system will use the global default 06:01–06:00 window.",
        key=f"mb_window_custom_{loc.id}",
    )

    col1, col2 = st.columns(2)
    with col1:
        start_time = st.time_input(
            "Start Time",
            value=start_time_val,
            disabled=not use_custom,
            key=f"mb_window_start_{loc.id}",
        )
    with col2:
        end_time = st.time_input(
            "End Time",
            value=end_time_val,
            disabled=not use_custom,
            key=f"mb_window_end_{loc.id}",
        )

    st.caption(
        "If End Time is **earlier than or equal to** Start Time, "
        "the window will automatically roll over into the next calendar day."
    )

    if st.button("💾 Save Material Balance Settings", type="primary", key=f"mb_save_{loc.id}"):
        payload = {
            "use_custom_window": bool(use_custom),
            "start_time": start_time.strftime("%H:%M"),
            "end_time": end_time.strftime("%H:%M"),
        } if use_custom else {
            "use_custom_window": False
        }

        try:
            with get_session() as s:
                set_page_section_config(s, loc.id, page="material_balance", section="window", cfg=payload)
            st.success("Material Balance window settings saved for this location.")
        except Exception as ex:
            st.error(f"Failed to save settings: {ex}")

    st.markdown("---")
    st.subheader("Columns Configuration")
    st.caption("Define receipt/dispatch columns and map them to data sources.")

    with get_session() as s:
        mb_cols_cfg = get_page_section_config(s, loc.id, page="material_balance", section="columns") or {}

    existing_cols = list(mb_cols_cfg.get("columns", []))

    c_add = st.expander("➕ Add New Column", expanded=False)
    with c_add:
        col1, col2 = st.columns([0.5, 0.5])
        with col1:
            new_label = st.text_input("Column Label", key=f"mb_col_label_{loc.id}")
            new_type = st.selectbox("Type", ["Opening", "Closing", "Receipt", "Dispatch", "Compute"], index=2, key=f"mb_col_type_{loc.id}")
            sources = get_available_data_sources()
            show_source = new_type in ["Opening", "Closing", "Receipt", "Dispatch"]
            if show_source:
                new_source = st.selectbox("Data Source", options=sources, index=(sources.index("otr_records") if "otr_records" in sources else 0), key=f"mb_col_src_{loc.id}")
                columns = get_columns_for_source(new_source) if new_source else []
                field_options = [c.get("field") for c in columns]
                field_labels = {c.get("field"): f"{c.get('field')} ({c.get('type')})" for c in columns}
                new_field = st.selectbox(
                    "Source Field",
                    options=field_options or [""],
                    format_func=lambda f: field_labels.get(f, f),
                    index=0,
                    key=f"mb_col_field_{loc.id}"
                )
            else:
                new_source = None
                new_field = None
            comp_op = None
            comp_cols = []
            comp_expr = None
            if new_type == "Compute":
                comp_op = st.selectbox("Operation", ["sum", "subtract", "multiply", "divide", "average", "percentage", "equation"], index=0, key=f"mb_col_comp_op_{loc.id}")
                existing_labels = [c.get("label") for c in existing_cols]
                if comp_op == "equation":
                    comp_expr = st.text_area("Equation", placeholder="Opening + Receipt A + Receipt B - Dispatch X", key=f"mb_col_comp_expr_{loc.id}")
                else:
                    comp_cols = st.multiselect("Operands", options=existing_labels, key=f"mb_col_comp_cols_{loc.id}")
        with col2:
            selected_ops = []
            if new_type in ["Receipt", "Dispatch"]:
                with get_session() as s:
                    ops = list_operations(s, loc.id, asset="tank", category=("Receipt" if new_type == "Receipt" else "Dispatch"))
                op_names = [o.get("name", "").strip() for o in ops if o.get("active", True)]
                selected_ops = st.multiselect(
                    "Operations to include",
                    options=op_names,
                    default=op_names,
                    key=f"mb_col_ops_{loc.id}"
                )
        if st.button("Add Column", key=f"mb_add_col_btn_{loc.id}"):
            if (new_label or "").strip():
                col_def = {
                    "label": new_label.strip(),
                    "type": new_type.lower(),
                    "data_source": new_source,
                    "field": new_field,
                    "operations": selected_ops,
                }
                if new_type == "Compute" and comp_op:
                    if comp_op == "equation" and comp_expr:
                        col_def["formula"] = {"op": comp_op, "expr": comp_expr}
                    elif comp_cols:
                        col_def["formula"] = {"op": comp_op, "cols": comp_cols}
                existing_cols.append(col_def)
                try:
                    with get_session() as s:
                        set_page_section_config(s, loc.id, page="material_balance", section="columns", cfg={"columns": existing_cols})
                    st.success("Column added.")
                except Exception as ex:
                    st.error(f"Failed to add column: {ex}")

    st.markdown("### Existing Columns")
    if not existing_cols:
        st.info("No custom columns defined yet.")
    else:
        for idx, cdef in enumerate(existing_cols):
            row_key = f"mb_col_row_{loc.id}_{idx}"
            col_a, col_b, col_c, col_d = st.columns([0.3, 0.2, 0.3, 0.2])
            with col_a:
                st.text_input("Label", value=str(cdef.get("label", "")), disabled=True, key=f"{row_key}_label")
            with col_b:
                st.text_input("Type", value=str(cdef.get("type", "")), disabled=True, key=f"{row_key}_type")
            with col_c:
                src_val = "computed" if cdef.get("formula") else f"{cdef.get('data_source')}:{cdef.get('field')}"
                st.text_input("Source", value=src_val, disabled=True, key=f"{row_key}_src")
            with col_d:
                del_flag = st.checkbox("Delete", value=False, key=f"{row_key}_del")
            if del_flag:
                d1, d2 = st.columns([0.5, 0.5])
                with d1:
                    if st.button("✅ Confirm Delete", key=f"{row_key}_confirm"):
                        new_list = [x for j, x in enumerate(existing_cols) if j != idx]
                        try:
                            with get_session() as s:
                                set_page_section_config(s, loc.id, page="material_balance", section="columns", cfg={"columns": new_list})
                            st.success("Column deleted.")
                        except Exception as ex:
                            st.error(f"Failed to delete column: {ex}")
                with d2:
                    st.button("❌ Cancel", key=f"{row_key}_cancel")
