import streamlit as st
from typing import Dict, Any, List, Optional

from db import get_session
from models import ReportDefinition
from permission_manager import PermissionManager
from security import SecurityManager
from location_config import (
    get_page_section_config,
    set_page_section_config,
)
from models import create_custom_tab_table, drop_custom_tab_table
from report_engine import get_available_data_sources, get_columns_for_source
from task_manager import TaskManager
from logger import log_error


def _st_safe_rerun():
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass

def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in [" ", "-", "/", "_"]:
            out.append("_")
    r = "".join(out)
    while "__" in r:
        r = r.replace("__", "_")
    return r.strip("_")


def _load_terminals(location_id: int) -> List[str]:
    with get_session() as s:
        cfg = get_page_section_config(s, location_id, "export_operations", "terminals") or {}
        items = cfg.get("items") or []
        return [str(x) for x in items if str(x).strip()]

def _save_terminals(location_id: int, items: List[str]) -> None:
    with get_session() as s:
        set_page_section_config(s, location_id, "export_operations", "terminals", {"items": items})

def _render_terminal_manager(active_location_id: int, user: Dict[str, Any]) -> None:
    st.markdown("#### Terminals")
    existing = _load_terminals(0)
    c1, c2 = st.columns([3, 1])
    with c1:
        new_term = st.text_input("Add Terminal", key="export_new_terminal")
    with c2:
        if st.button("➕", key="export_add_terminal", help="Add Terminal"):
            name = (new_term or "").strip()
            if not name:
                st.error("Terminal name required")
            else:
                items = existing.copy()
                if name not in items:
                    items.append(name)
                    _save_terminals(0, items)
                    st.success(f"Added terminal '{name}'")
                    _st_safe_rerun()
                    try:
                        SecurityManager.log_audit(None, (st.session_state.get("auth_user") or {}).get("username", "system"), "CREATE", resource_type="ExportTerminal", resource_id=name, details=f"Added export terminal {name}", user_id=(st.session_state.get("auth_user") or {}).get("id"), location_id=0, ip_address=str(st.session_state.get("client_ip") or "N/A"))
                    except Exception:
                        pass
                else:
                    st.info("Terminal already exists")
    if existing:
        st.caption("Available")
        for t in existing:
            d1, d2 = st.columns([5, 1])
            with d1:
                st.text(t)
            with d2:
                if st.button("🗑️", key=f"del_term_{t}", help="Delete Terminal"):
                    st.session_state[f"confirm_del_term_{t}"] = True
            if st.session_state.get(f"confirm_del_term_{t}"):
                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button("✅", key=f"y_del_term_{t}", help="Yes, delete"):
                        items = [x for x in existing if x != t]
                        _save_terminals(0, items)
                        st.success(f"Deleted terminal '{t}'")
                        st.session_state.pop(f"confirm_del_term_{t}", None)
                        _st_safe_rerun()
                        try:
                            SecurityManager.log_audit(None, (st.session_state.get("auth_user") or {}).get("username", "system"), "DELETE", resource_type="ExportTerminal", resource_id=t, details=f"Deleted export terminal {t}", user_id=(st.session_state.get("auth_user") or {}).get("id"), location_id=0, ip_address=str(st.session_state.get("client_ip") or "N/A"))
                        except Exception:
                            pass
                with c2:
                    if st.button("❌", key=f"n_del_term_{t}", help="Cancel"):
                        st.session_state.pop(f"confirm_del_term_{t}", None)
                        _st_safe_rerun()


def _guard(user: Optional[Dict]) -> bool:
    role = (user or {}).get("role", "")
    if role != "admin-operations":
        st.error("Only admin-operations can customize exports.")
        return False
    if not PermissionManager.can_access_export_operations(user):
        st.error("Export Operations access flag is required.")
        return False
    return True


def _tabs_cfg_key(terminal_label: str) -> str:
    uid = int((st.session_state.get("auth_user") or {}).get("id") or 0)
    return f"{_slug(terminal_label)}_tabs_{uid}"


def _load_tabs_cfg(location_id: int, terminal_label: str) -> Dict[str, Any]:
    with get_session() as s:
        return get_page_section_config(s, location_id, "export_operations", _tabs_cfg_key(terminal_label)) or {}


def _save_tabs_cfg(location_id: int, terminal_label: str, cfg: Dict[str, Any]) -> None:
    with get_session() as s:
        set_page_section_config(s, location_id, "export_operations", _tabs_cfg_key(terminal_label), cfg or {})


def _render_tab_creator(active_location_id: int, terminal_label: str):
    st.markdown("#### Add New Export Tab")
    tab_name = st.text_input("Tab Name *", key=f"exp_tab_name_{terminal_label}")
    slug = _slug(tab_name)
    layout_cols = st.number_input("Form columns per row", min_value=1, max_value=10, value=4, step=1, key=f"exp_form_cols_{terminal_label}")
    layout_rows = st.number_input("Form rows", min_value=1, max_value=10, value=1, step=1, key=f"exp_form_rows_{terminal_label}")
    layout_fit = st.checkbox("Fit all fields in a single row", value=False, key=f"exp_form_fit_{terminal_label}")

    col_cnt = st.number_input("Number of columns", min_value=1, max_value=40, value=3, step=1, key=f"exp_col_cnt_{terminal_label}")
    cols: List[Dict[str, Any]] = []
    for i in range(int(col_cnt)):
        c1, c2, c3 = st.columns(3)
        with c1:
            label = st.text_input("Label", key=f"exp_col_label_{terminal_label}_{i}")
        with c2:
            name = st.text_input("Field name", value=_slug(label or f"col_{i+1}"), key=f"exp_col_name_{terminal_label}_{i}")
        with c3:
            dtype = st.selectbox("Type", ["text", "number", "date", "dropdown"], key=f"exp_col_type_{terminal_label}_{i}")
        required = st.checkbox("Required", value=False, key=f"exp_col_req_{terminal_label}_{i}")
        dd_opts = None
        if dtype == "dropdown":
            st.caption("Configure dropdown options")
            dd_cnt = st.number_input("Items", min_value=1, max_value=50, value=3, step=1, key=f"exp_col_dd_cnt_{terminal_label}_{i}")
            dd_list = []
            for j in range(int(dd_cnt)):
                dd_list.append(st.text_input(f"Option {j+1}", key=f"exp_col_dd_opt_{terminal_label}_{i}_{j}"))
            dd_opts = [o for o in dd_list if (o or "").strip()]
        with st.expander("Formula (optional)", expanded=False):
            use_formula = st.checkbox("Enable", key=f"exp_col_formula_use_{terminal_label}_{i}")
            formula_cfg = None
            if use_formula:
                op = st.selectbox("Operation", ["sum", "subtract", "multiply", "divide", "percentage", "maximum", "minimum", "average"], key=f"exp_col_formula_op_{terminal_label}_{i}")
                selected_labels = st.multiselect("Columns", options=[c.get("label") for c in cols if c.get("label")], key=f"exp_col_formula_cols_{terminal_label}_{i}")
                if selected_labels:
                    formula_cfg = {"operation": op, "columns": selected_labels}
        col_def = {"name": name, "label": label or name, "type": dtype, "required": required}
        if dtype == "dropdown" and dd_opts:
            col_def["options"] = dd_opts
        if use_formula and formula_cfg:
            col_def["formula"] = formula_cfg
        cols.append(col_def)

    st.markdown("##### Filters (optional)")
    filt_cnt = st.number_input("Number of filters", min_value=0, max_value=30, value=0, step=1, key=f"exp_filters_cnt_{terminal_label}")
    filters_cfg: List[Dict[str, Any]] = []
    base_field_opts = [c.get("name") or c.get("label") for c in cols if (c.get("name") or c.get("label"))]
    for i in range(int(filt_cnt)):
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            flabel = st.text_input("Label", key=f"exp_filter_label_{terminal_label}_{i}")
        with fc2:
            ffield = st.selectbox("Field", options=base_field_opts, key=f"exp_filter_field_{terminal_label}_{i}")
        with fc3:
            ftype = st.selectbox("Type", ["text", "number", "date"], key=f"exp_filter_type_{terminal_label}_{i}")
        with fc4:
            if ftype == "text":
                fmode = st.selectbox("Mode", ["equals", "contains", "starts_with", "ends_with"], key=f"exp_filter_mode_{terminal_label}_{i}")
            elif ftype == "number":
                fmode = st.selectbox("Mode", ["equals", "min_max"], key=f"exp_filter_mode_{terminal_label}_{i}")
            else:
                fmode = st.selectbox("Mode", ["equals", "date_range"], key=f"exp_filter_mode_{terminal_label}_{i}")
        filters_cfg.append({"label": flabel or ffield, "field": ffield, "type": ftype, "mode": fmode})

    st.markdown("##### Filters Layout")
    filt_layout_cols = st.number_input("Filters columns per row", min_value=1, max_value=10, value=4, step=1, key=f"exp_filters_layout_cols_{terminal_label}")
    filt_layout_rows = st.number_input("Filters rows", min_value=1, max_value=10, value=1, step=1, key=f"exp_filters_layout_rows_{terminal_label}")
    filt_layout_fit = st.checkbox("Fit filters in a single row", value=False, key=f"exp_filters_layout_fit_{terminal_label}")

    if st.button("✅", key=f"exp_create_tab_btn_{terminal_label}", help="Create tab and database table"):
        errors = []
        if not tab_name:
            errors.append("Tab name required")
        if not cols:
            errors.append("Define at least one column")
        if errors:
            for e in errors:
                st.error(e)
            return
        uid = int((st.session_state.get("auth_user") or {}).get("id") or 0)
        table_name = f"export_{_slug(terminal_label)}_{slug}_u{uid}" if slug else f"export_{_slug(terminal_label)}_u{uid}"
        try:
            ok = create_custom_tab_table(table_name, cols, 0)
            if not ok:
                st.error("Table creation failed")
                return
            cfg = _load_tabs_cfg(0, terminal_label)
            tabs = list(cfg.get("tabs") or [])
            tabs.append({
                "label": tab_name,
                "table": table_name,
                "columns": cols,
                "layout": {"rows": int(layout_rows), "cols": int(layout_cols), "fit_single_row": bool(layout_fit)},
                "filters": filters_cfg,
                "filters_layout": {"rows": int(filt_layout_rows), "cols": int(filt_layout_cols), "fit_single_row": bool(filt_layout_fit)}
            })
            cfg["tabs"] = tabs
            _save_tabs_cfg(0, terminal_label, cfg)
            st.success(f"Tab '{tab_name}' created as table '{table_name}'")
            try:
                SecurityManager.log_audit(None, (st.session_state.get("auth_user") or {}).get("username", "system"), "CREATE", resource_type="ExportTab", resource_id=table_name, details=f"Created export tab {tab_name} for {terminal_label}", user_id=(st.session_state.get("auth_user") or {}).get("id"), location_id=0)
            except Exception:
                pass
        except Exception as exc:
            st.error(str(exc))


def _render_tabs_list(active_location_id: int, terminal_label: str):
    cfg = _load_tabs_cfg(0, terminal_label)
    tabs = list(cfg.get("tabs") or [])
    if not tabs:
        st.info("No export tabs yet.")
        return
    for idx, t in enumerate(tabs):
        tab_label = t.get("label")
        table_name = t.get("table")
        columns = list(t.get("columns") or [])
        layout = t.get("layout") or {"rows": 1, "cols": max(1, min(len(columns), 4))}
        filters = list(t.get("filters") or [])
        filters_layout = t.get("filters_layout") or {}
        with st.expander(f"{tab_label} → {table_name}", expanded=False):
            c1, c2 = st.columns([3, 1])
            with c1:
                new_label = st.text_input("Tab Label", value=tab_label or "", key=f"exp_tab_edit_label_{terminal_label}_{idx}")
            with c2:
                st.caption("Actions")
            lr1, lr2 = st.columns(2)
            with lr1:
                new_rows = st.number_input("Form rows", min_value=1, max_value=10, value=int(layout.get("rows") or 1), step=1, key=f"exp_tab_edit_rows_{terminal_label}_{idx}")
            with lr2:
                new_cols = st.number_input("Form columns per row", min_value=1, max_value=10, value=int(layout.get("cols") or 4), step=1, key=f"exp_tab_edit_cols_{terminal_label}_{idx}")
            new_fit = st.checkbox("Fit all fields in a single row", value=bool(layout.get("fit_single_row") or False), key=f"exp_tab_edit_fit_{terminal_label}_{idx}")

            st.markdown("##### Columns")
            new_cols_list: List[Dict[str, Any]] = []
            for j, col in enumerate(columns):
                cc1, cc2, cc3, cc4 = st.columns([3, 3, 2, 2])
                with cc1:
                    lbl = st.text_input("Label", value=col.get("label") or col.get("name") or f"col_{j+1}", key=f"exp_tab_col_lbl_{terminal_label}_{idx}_{j}")
                with cc2:
                    nm = st.text_input("Field name", value=col.get("name") or _slug(lbl), key=f"exp_tab_col_name_{terminal_label}_{idx}_{j}")
                with cc3:
                    tp = st.selectbox("Type", ["text", "number", "date", "dropdown"], index=["text","number","date","dropdown"].index(col.get("type") or "text"), key=f"exp_tab_col_type_{terminal_label}_{idx}_{j}")
                with cc4:
                    req = st.checkbox("Required", value=bool(col.get("required")), key=f"exp_tab_col_req_{terminal_label}_{idx}_{j}")
                dd_opts = None
                if tp == "dropdown":
                    st.caption("Dropdown options")
                    dd_cnt = st.number_input("Items", min_value=1, max_value=50, value=len(col.get("options") or []) or 3, step=1, key=f"exp_tab_col_dd_cnt_{terminal_label}_{idx}_{j}")
                    dd_list = []
                    for k in range(int(dd_cnt)):
                        dd_list.append(st.text_input(f"Option {k+1}", value=(col.get("options") or [None]*int(dd_cnt))[k] if k < len(col.get("options") or []) else "", key=f"exp_tab_col_dd_opt_{terminal_label}_{idx}_{j}_{k}"))
                    dd_opts = [o for o in dd_list if (o or "").strip()]
                col_def = {"name": nm, "label": lbl or nm, "type": tp, "required": req}
                if tp == "dropdown" and dd_opts:
                    col_def["options"] = dd_opts
                new_cols_list.append(col_def)

            st.markdown("##### Filters")
            edit_filters: List[Dict[str, Any]] = []
            ef_cnt = st.number_input("Number of filters", min_value=0, max_value=30, value=len(filters) or 0, step=1, key=f"exp_tab_edit_filters_cnt_{terminal_label}_{idx}")
            base_field_opts = [c.get("name") or c.get("label") for c in new_cols_list if (c.get("name") or c.get("label"))]
            for j in range(int(ef_cnt)):
                ef1, ef2, ef3, ef4 = st.columns(4)
                cur = (filters[j] if j < len(filters) else {}) or {}
                with ef1:
                    flbl = st.text_input("Label", value=cur.get("label") or "", key=f"exp_tab_edit_filter_lbl_{terminal_label}_{idx}_{j}")
                with ef2:
                    ffld = st.selectbox("Field", options=base_field_opts, index=max(0, base_field_opts.index(cur.get("field")) if cur.get("field") in base_field_opts else 0), key=f"exp_tab_edit_filter_field_{terminal_label}_{idx}_{j}")
                with ef3:
                    ftyp = st.selectbox("Type", ["text", "number", "date"], index=["text","number","date"].index(cur.get("type") or "text"), key=f"exp_tab_edit_filter_type_{terminal_label}_{idx}_{j}")
                with ef4:
                    if ftyp == "text":
                        fmode = st.selectbox("Mode", ["equals", "contains", "starts_with", "ends_with"], index=["equals","contains","starts_with","ends_with"].index(cur.get("mode") or "equals"), key=f"exp_tab_edit_filter_mode_{terminal_label}_{idx}_{j}")
                    elif ftyp == "number":
                        fmode = st.selectbox("Mode", ["equals", "min_max"], index=["equals","min_max"].index(cur.get("mode") or "equals"), key=f"exp_tab_edit_filter_mode_{terminal_label}_{idx}_{j}")
                    else:
                        fmode = st.selectbox("Mode", ["equals", "date_range"], index=["equals","date_range"].index(cur.get("mode") or "equals"), key=f"exp_tab_edit_filter_mode_{terminal_label}_{idx}_{j}")
                edit_filters.append({"label": flbl or ffld, "field": ffld, "type": ftyp, "mode": fmode})

            st.markdown("##### Filters Layout")
            new_filt_rows = st.number_input("Filters rows", min_value=1, max_value=10, value=int(filters_layout.get("rows") or 1), step=1, key=f"exp_tab_edit_filter_rows_{terminal_label}_{idx}")
            new_filt_cols = st.number_input("Filters columns per row", min_value=1, max_value=10, value=int(filters_layout.get("cols") or max(1, min(len(edit_filters) or len(filters), 4))), step=1, key=f"exp_tab_edit_filter_cols_{terminal_label}_{idx}")
            new_filt_fit = st.checkbox("Fit filters in a single row", value=bool(filters_layout.get("fit_single_row") or False), key=f"exp_tab_edit_filter_fit_{terminal_label}_{idx}")

            b1, b2, b3 = st.columns([0.3, 0.3, 0.4])
            with b1:
                if st.button("💾 Save", key=f"exp_tab_edit_save_{terminal_label}_{idx}", type="primary"):
                    tabs[idx] = {
                        "label": new_label or tab_label,
                        "table": table_name,
                        "columns": new_cols_list,
                        "layout": {"rows": int(new_rows), "cols": int(new_cols), "fit_single_row": bool(new_fit)},
                        "filters": edit_filters,
                        "filters_layout": {"rows": int(new_filt_rows), "cols": int(new_filt_cols), "fit_single_row": bool(new_filt_fit)}
                    }
                    cfg["tabs"] = tabs
                    _save_tabs_cfg(0, terminal_label, cfg)
                    st.success("Tab updated")
                    _st_safe_rerun()
            with b2:
                if st.button("🗑️ Delete", key=f"exp_tab_delete_{terminal_label}_{idx}"):
                    st.session_state[f"exp_tab_delete_confirm_{terminal_label}_{idx}"] = True
            with b3:
                from models import get_custom_table_model
                from db import flex_engine
                if st.button("🛠️ Apply schema changes", key=f"exp_tab_apply_schema_{terminal_label}_{idx}"):
                    try:
                        Model = get_custom_table_model(table_name)
                        existing_cols = [c.name for c in Model.__table__.columns] if Model else []
                        add_cols = [c for c in new_cols_list if (c.get("name") not in existing_cols)]
                        if not add_cols:
                            st.info("No new columns to add.")
                        else:
                            type_map = {"date": "DATE", "number": "REAL", "text": "TEXT", "dropdown": "TEXT"}
                            from sqlalchemy import text
                            with flex_engine.connect() as conn:
                                for c in add_cols:
                                    nm = c.get("name")
                                    tp = type_map.get(c.get("type") or "text", "TEXT")
                                    conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN "{nm}" {tp}'))
                            st.success("Schema updated (added missing columns)")
                    except Exception as ex:
                        st.error(str(ex))

            if st.session_state.get(f"exp_tab_delete_confirm_{terminal_label}_{idx}"):
                st.warning("Delete this tab? Choose whether to also delete its database table.")
                dc1, dc2, dc3 = st.columns([0.3,0.3,0.4])
                with dc1:
                    del_tbl = st.checkbox("Delete database table", value=True, key=f"exp_tab_delete_tbl_{terminal_label}_{idx}")
                with dc2:
                    if st.button("✅ Yes", key=f"exp_tab_delete_yes_{terminal_label}_{idx}", type="primary"):
                        try:
                            # Remove from config
                            tabs = [tt for k, tt in enumerate(tabs) if k != idx]
                            cfg["tabs"] = tabs
                            _save_tabs_cfg(0, terminal_label, cfg)
                            # Optionally drop table
                            if del_tbl and table_name:
                                drop_custom_tab_table(table_name)
                            st.success("Tab deleted")
                            st.session_state.pop(f"exp_tab_delete_confirm_{terminal_label}_{idx}", None)
                            _st_safe_rerun()
                        except Exception as ex:
                            st.error(str(ex))
                with dc3:
                    if st.button("❌ No", key=f"exp_tab_delete_no_{terminal_label}_{idx}"):
                        st.session_state.pop(f"exp_tab_delete_confirm_{terminal_label}_{idx}", None)
                        _st_safe_rerun()


def _render_report_builder(user: Dict[str, Any], active_location_id: int, terminal_label: str):
    st.markdown("### Create Export Report")
    sources = get_available_data_sources()
    export_sources = [s for s in sources if s.startswith(f"export_{_slug(terminal_label)}_") or s.startswith(f"export_{_slug(terminal_label)}")]
    base_opt = st.selectbox("Base table", options=export_sources or sources, key=f"exp_report_base_{terminal_label}")
    base_cols = get_columns_for_source(base_opt) if base_opt else []

    col_count = st.number_input("Number of columns", min_value=1, max_value=50, value=4, step=1, key=f"exp_report_cols_{terminal_label}")
    cols_out: List[Dict[str, Any]] = []
    for i in range(int(col_count)):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            label = st.text_input("Label", key=f"exp_rep_lbl_{terminal_label}_{i}")
        with c2:
            field = st.text_input("Field name", value=_slug(label or f"col_{i+1}"), key=f"exp_rep_field_{terminal_label}_{i}")
        with c3:
            dtype = st.selectbox("Type", ["string", "numeric", "date", "datetime", "boolean"], key=f"exp_rep_type_{terminal_label}_{i}")
        with c4:
            source_field = st.selectbox("Source field", options=[c["field"] for c in base_cols] if base_cols else [], key=f"exp_rep_src_{terminal_label}_{i}")
        cols_out.append({"label": label or field, "field": field, "type": dtype, "source_table": base_opt, "source_field": source_field})

    rel_count = st.number_input("Related tables", min_value=0, max_value=10, value=1, step=1, key=f"exp_report_rels_{terminal_label}")
    relationships: List[Dict[str, Any]] = []
    for i in range(int(rel_count)):
        r1, r2, r3 = st.columns(3)
        with r1:
            src_tbl = st.selectbox("Join table", options=sources, key=f"exp_rep_join_tbl_{terminal_label}_{i}")
            src_cols = get_columns_for_source(src_tbl) if src_tbl else []
        with r2:
            jk_primary = st.selectbox("Primary key", options=[c["field"] for c in base_cols] if base_cols else [], key=f"exp_rep_jk_base_{terminal_label}_{i}")
        with r3:
            jk_source = st.selectbox("Source key", options=[c["field"] for c in src_cols] if src_cols else [], key=f"exp_rep_jk_src_{terminal_label}_{i}")
        if src_tbl and jk_primary and jk_source:
            relationships.append({"table": src_tbl, "join_keys": [{"primary": jk_primary, "source": jk_source}], "join_type": "left"})

    report_name = st.text_input("Report Name *", key=f"exp_rep_name_{terminal_label}")
    slug = _slug(report_name) or f"export_{_slug(terminal_label)}_report"

    if st.button("💾", key=f"exp_rep_save_{terminal_label}", help="Save Export Report"):
        if not report_name or not base_opt or not cols_out:
            st.error("Name, base table and columns are required")
            return
        cfg = {
            "report_type": "custom",
            "data_source": {"table": base_opt, "base_location_mode": "current", "base_location_id": active_location_id, "joins": relationships},
            "columns": cols_out,
            "filters": [],
            "sorting": [],
            "grouping": [],
            "aggregations": {},
            "show_totals": False,
            "export_formats": ["xlsx", "pdf"],
        }
        try:
            with get_session() as s:
                rd = ReportDefinition(location_id=active_location_id, name=report_name, slug=slug, config_json=json_dumps(cfg), created_by=(st.session_state.get("auth_user") or {}).get("username", "system"))
                s.add(rd)
                s.commit()
            st.success("Export report saved")
        except Exception as exc:
            st.error(str(exc))


def json_dumps(obj: Dict[str, Any]) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


def render_export_customization_page(active_location_id: Optional[int], user: Optional[Dict]):
    if not _guard(user):
        return
    st.markdown("### Export Customization")
    st.caption("Manage terminals, tabs, tables and export reports")
    uid = int((user or {}).get("id") or 0)
    loc_bucket = 0

    _render_terminal_manager(int(loc_bucket), user or {})
    terms = _load_terminals(int(loc_bucket))
    
    # Debug information
    with st.expander("🔧 Debug Information", expanded=False):
        st.write(f"**Location ID (loc_bucket):** {loc_bucket}")
        st.write(f"**Terminals saved/loaded:** {terms}")
        st.write(f"**User ID:** {uid}")
        if st.button("Refresh Terminal List", key="debug_refresh_customization"):
            st.rerun()
    
    if not terms:
        st.info("Add a terminal to begin customizing exports")
        return
    term = st.selectbox("Terminal", terms, key="export_term_select")

    def _load_pipeline_cfg(location_id: int, terminal_label: str) -> Dict[str, Any]:
        with get_session() as s:
            return get_page_section_config(s, location_id, "export_operations", f"pipeline_{_slug(terminal_label)}_{uid}") or {}

    def _save_pipeline_cfg(location_id: int, terminal_label: str, cfg: Dict[str, Any]) -> None:
        with get_session() as s:
            set_page_section_config(s, location_id, "export_operations", f"pipeline_{_slug(terminal_label)}_{uid}", cfg or {})

    t_tabs, t_reports, t_pipeline = st.tabs(["Export Tabs", "Export Reports", "Export Process Flow"])
    with t_tabs:
        _render_tab_creator(int(loc_bucket), term)
        st.markdown("---")
        _render_tabs_list(int(loc_bucket), term)
    with t_reports:
        _render_report_builder(user or {}, int(loc_bucket), term)
    with t_pipeline:
        st.markdown("#### Export Process Flow")
        cfg = _load_pipeline_cfg(int(loc_bucket), term)
        ss_key = f"exp_pipeline_stages_{term}"
        if ss_key not in st.session_state:
            st.session_state[ss_key] = list(cfg.get("stages") or [])
        stages = list(st.session_state[ss_key] or [])
        scount = st.number_input("Number of stages", min_value=1, max_value=40, value=max(1, len(stages) or 6), step=1, key=f"exp_pipeline_count_{term}")
        if len(stages) < int(scount):
            for i in range(len(stages), int(scount)):
                stages.append({"code": f"STAGE_{i+1}", "name": f"Stage {i+1}", "statuses": ["Pending","In Progress","Completed"], "mandatory": True, "uploads": [], "completion_statuses": ["Completed"]})
            st.session_state[ss_key] = stages
        elif len(stages) > int(scount):
            stages = stages[: int(scount)]
            st.session_state[ss_key] = stages
        for i in range(int(scount)):
            st.markdown(f"Stage {i+1}")
            c1, c2, c3 = st.columns([0.30, 0.40, 0.30])
            with c1:
                stages[i]["code"] = _slug(st.text_input("Code", value=stages[i].get("code") or f"STAGE_{i+1}", key=f"exp_pl_code_{term}_{i}") or f"STAGE_{i+1}")
            with c2:
                stages[i]["name"] = st.text_input("Name", value=stages[i].get("name") or f"Stage {i+1}", key=f"exp_pl_name_{term}_{i}")
            with c3:
                stages[i]["mandatory"] = st.checkbox("Mandatory to proceed", value=bool(stages[i].get("mandatory", True)), key=f"exp_pl_mand_{term}_{i}")
            # Reorder/Delete controls
            rc1, rc2, rc3, rc4 = st.columns([0.15, 0.15, 0.15, 0.55])
            with rc1:
                if st.button("↑", key=f"exp_pl_move_up_{term}_{i}", help="Move stage up") and i > 0:
                    stages[i-1], stages[i] = stages[i], stages[i-1]
                    st.session_state[ss_key] = stages
                    _st_safe_rerun()
            with rc2:
                if st.button("↓", key=f"exp_pl_move_down_{term}_{i}", help="Move stage down") and i < len(stages)-1:
                    stages[i+1], stages[i] = stages[i], stages[i+1]
                    st.session_state[ss_key] = stages
                    _st_safe_rerun()
            with rc3:
                if st.button("🗑️", key=f"exp_pl_delete_{term}_{i}", help="Delete stage"):
                    stages = stages[:i] + stages[i+1:]
                    st.session_state[ss_key] = stages
                    _st_safe_rerun()
            with rc4:
                if st.button("＋ Insert below", key=f"exp_pl_insert_{term}_{i}", help="Insert new stage below"):
                    new_def = {"code": f"STAGE_{i+2}", "name": f"Stage {i+2}", "statuses": ["Pending","In Progress","Completed"], "mandatory": True, "uploads": [], "completion_statuses": ["Completed"]}
                    stages = stages[:i+1] + [new_def] + stages[i+1:]
                    st.session_state[ss_key] = stages
                    _st_safe_rerun()
            c3a, c3b, c3c, c3d = st.columns([0.25, 0.25, 0.25, 0.25])
            with c3a:
                stages[i]["require_due_date"] = st.checkbox("Require due date", value=bool(stages[i].get("require_due_date", False)), key=f"exp_pl_req_due_{term}_{i}")
            with c3b:
                stages[i]["default_due_days"] = int(st.number_input("Default due days", min_value=0, max_value=365, value=int(stages[i].get("default_due_days") or 0), step=1, key=f"exp_pl_due_days_{term}_{i}"))
            with c3c:
                stages[i]["require_remarks"] = st.checkbox("Require remarks", value=bool(stages[i].get("require_remarks", False)), key=f"exp_pl_req_remarks_{term}_{i}")
            with c3d:
                stages[i]["notify_on_due"] = st.checkbox("Notify on due", value=bool(stages[i].get("notify_on_due", True)), key=f"exp_pl_notify_due_{term}_{i}")
            st.checkbox("Require overdue reason when completed past due", value=bool(stages[i].get("require_overdue_reason", True)), key=f"exp_pl_req_overdue_{term}_{i}")
            stages[i]["require_overdue_reason"] = bool(st.session_state.get(f"exp_pl_req_overdue_{term}_{i}", True))
            c4a, c4b, c4c, c4d = st.columns([0.25, 0.25, 0.25, 0.25])
            with c4a:
                # Map display labels to internal values
                due_source_options = {
                    "Today": "today",
                    "Previous Stage": "previous_stage",
                    "Specific Stage": "specific_stage",
                    "Laycan Day 1": "laycan_start"
                }
                reverse_map = {v: k for k, v in due_source_options.items()}
                current_val = stages[i].get("due_source") or "today"
                display_labels = list(due_source_options.keys())
                current_label = reverse_map.get(current_val, "Today")
                selected_label = st.selectbox("Due date source", options=display_labels, index=display_labels.index(current_label), key=f"exp_pl_due_src_{term}_{i}")
                stages[i]["due_source"] = due_source_options[selected_label]
                if stages[i]["due_source"] == "laycan_start":
                    st.caption("Due date will be calculated from Laycan Day 1 of the shipment MINUS the 'Default due days' offset.")
            with c4b:
                prev_codes = [stages[j].get("code") for j in range(i)] if i > 0 else []
                anchor_default = stages[i].get("due_anchor_code") or (prev_codes[-1] if prev_codes else "")
                stages[i]["due_anchor_code"] = st.selectbox("Anchor stage (specific)", options=prev_codes or [""], index=max(0, (prev_codes or [""]).index(anchor_default) if anchor_default in (prev_codes or [""]) else 0), key=f"exp_pl_due_anchor_{term}_{i}") if (stages[i].get("due_source") or "today") == "specific_stage" else stages[i].get("due_anchor_code")
            with c4c:
                stages[i]["completion_date_mode"] = st.selectbox("Completion date mode", options=["auto", "manual_required"], index=["auto","manual_required"].index(stages[i].get("completion_date_mode") or "auto"), key=f"exp_pl_comp_mode_{term}_{i}")
            with c4d:
                # Check if any other stage has sets_laycan enabled
                other_laycan_stages = [j for j in range(len(stages)) if j != i and stages[j].get("sets_laycan", False)]
                laycan_disabled = len(other_laycan_stages) > 0
                
                if laycan_disabled:
                    st.caption(f"⚠️ Stage {other_laycan_stages[0]+1} already sets laycan")
                    stages[i]["sets_laycan"] = False
                else:
                    stages[i]["sets_laycan"] = st.checkbox("Stage sets laycan dates", value=bool(stages[i].get("sets_laycan", False)), key=f"exp_pl_sets_laycan_{term}_{i}")
                
                if stages[i]["sets_laycan"]:
                    st.caption("When this stage is completed, the user will be prompted to input the 2-day laycan window (Day 1 and Day 2).")
            c4, c5 = st.columns([0.50, 0.50])
            with c4:
                st.caption("Allowed statuses")
                s_cnt = st.number_input("Status count", min_value=1, max_value=20, value=len(stages[i].get("statuses") or ["Pending","In Progress","Completed"]), step=1, key=f"exp_pl_stat_cnt_{term}_{i}")
                stat_list = list(stages[i].get("statuses") or [])
                if len(stat_list) < int(s_cnt):
                    for j in range(len(stat_list), int(s_cnt)):
                        stat_list.append(f"Status {j+1}")
                elif len(stat_list) > int(s_cnt):
                    stat_list = stat_list[: int(s_cnt)]
                for j in range(int(s_cnt)):
                    stat_list[j] = st.text_input(f"Status {j+1}", value=stat_list[j], key=f"exp_pl_stat_{term}_{i}_{j}")
                stages[i]["statuses"] = [str(x).strip() for x in stat_list if str(x).strip()]
            with c5:
                st.caption("Completion statuses")
                cs_cnt = st.number_input("Completion status count", min_value=1, max_value=10, value=len(stages[i].get("completion_statuses") or ["Completed"]), step=1, key=f"exp_pl_comp_cnt_{term}_{i}")
                comp_list = list(stages[i].get("completion_statuses") or ["Completed"])
                if len(comp_list) < int(cs_cnt):
                    for j in range(len(comp_list), int(cs_cnt)):
                        comp_list.append("Completed")
                elif len(comp_list) > int(cs_cnt):
                    comp_list = comp_list[: int(cs_cnt)]
                for j in range(int(cs_cnt)):
                    comp_list[j] = st.text_input(f"Completion {j+1}", value=comp_list[j], key=f"exp_pl_comp_{term}_{i}_{j}")
                stages[i]["completion_statuses"] = [str(x).strip() for x in comp_list if str(x).strip()]
            st.markdown("Uploads")
            upds = list(stages[i].get("uploads") or [])
            u_cnt = st.number_input("Upload definitions", min_value=0, max_value=20, value=len(upds or []), step=1, key=f"exp_pl_up_cnt_{term}_{i}")
            if len(upds) < int(u_cnt):
                for j in range(len(upds), int(u_cnt)):
                    upds.append({"name": f"Upload {j+1}", "visibility": "global", "assignees": []})
            elif len(upds) > int(u_cnt):
                upds = upds[: int(u_cnt)]
            for j in range(int(u_cnt)):
                u1, u2, u3 = st.columns([0.40, 0.30, 0.30])
                with u1:
                    upds[j]["name"] = st.text_input("Upload name", value=upds[j].get("name") or f"Upload {j+1}", key=f"exp_pl_up_name_{term}_{i}_{j}")
                with u2:
                    upds[j]["visibility"] = st.selectbox("Visibility", options=["global","restricted"], index=["global","restricted"].index(upds[j].get("visibility") or "global"), key=f"exp_pl_up_vis_{term}_{i}_{j}")
                with u3:
                    assignees_text = st.text_input("Assignees (comma usernames)", value=",".join(upds[j].get("assignees") or []), key=f"exp_pl_up_assign_{term}_{i}_{j}")
                    upds[j]["assignees"] = [a.strip() for a in assignees_text.split(",") if a and upds[j].get("visibility") == "restricted"]
                stages[i]["uploads"] = upds
            st.markdown("---")
        if st.button("💾", key=f"exp_pl_save_{term}", type="primary", help="Save Process Flow"):
            try:
                cfg["stages"] = list(st.session_state.get(ss_key) or stages)
                _save_pipeline_cfg(int(loc_bucket), term, cfg)
                
                # Audit log the pipeline configuration save
                try:
                    with get_session() as s:
                        SecurityManager.log_audit(
                            s,
                            (st.session_state.get("auth_user") or {}).get("username", "system"),
                            "UPDATE",
                            resource_type="ExportPipeline",
                            resource_id=term,
                            details=f"Saved export process flow for terminal '{term}' with {len(cfg.get('stages', []))} stages",
                            user_id=(st.session_state.get("auth_user") or {}).get("id"),
                            location_id=int(loc_bucket),
                            ip_address=str(st.session_state.get("client_ip") or "N/A")
                        )
                except Exception as log_ex:
                    log_error(f"Failed to log audit for pipeline save: {log_ex}", exc_info=True)
                
                st.success("Export Process Flow saved")
            except Exception as ex:
                log_error(f"Failed to save export process flow: {ex}", exc_info=True)
                st.error(str(ex))
                try:
                    TaskManager.create_error_task(
                        error_message=str(ex),
                        context="Export Process Flow Save",
                        user=st.session_state.get("auth_user"),
                        location_id=int(loc_bucket),
                        severity="HIGH",
                        additional_info=f"Terminal: {term}"
                    )
                except Exception as task_ex:
                    log_error(f"Failed to create error task: {task_ex}", exc_info=True)
