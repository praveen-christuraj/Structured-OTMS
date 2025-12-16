from __future__ import annotations

from datetime import date, timedelta
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from db import get_session
from models import Location
from permission_manager import PermissionManager
from security import SecurityManager
from stock_analysis_engine import (
    AnalysisConfigManager,
    AnalysisResultWriter,
    AnalysisSchemaManager,
    AnalyticsQueryBuilder,
    VisualizationHelper,
    get_all_database_tables,
)
from ui import header
from ui_components import TableDisplay


def _audit(
    user: Optional[Dict[str, Any]],
    *,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: str = "",
    location_id: Optional[int] = None,
    success: bool = True,
    session=None,
) -> None:
    try:
        SecurityManager.log_audit(
            session=session,
            username=(user or {}).get("username", "system"),
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=details,
            user_id=(user or {}).get("id"),
            location_id=int(location_id) if location_id is not None else None,
            ip_address=str(st.session_state.get("client_ip") or "N/A"),
            success=bool(success),
        )
    except Exception:
        pass


def _guard_admin(user: Optional[Dict[str, Any]]) -> bool:
    if not user or not PermissionManager.can_access_management_pages(user):
        st.error("You do not have permission to access Stock Analysis Customization.")
        return False
    return True


def _pick_location(active_location_id: Optional[int]) -> Tuple[Optional[Location], Optional[str]]:
    if active_location_id:
        with get_session() as session:
            loc = session.query(Location).get(int(active_location_id))
        if not loc:
            st.error("Active location not found. Re-select a location on Home.")
            return None, None
        return loc, f"{loc.name} ({loc.code})"

    st.warning("No active location selected on Home. Pick a location here for customization.")
    with get_session() as session:
        locs = session.query(Location).order_by(Location.name.asc()).all()
    if not locs:
        st.error("No locations found. Create one in Manage Locations.")
        return None, None

    labels = [f"{loc.name} ({loc.code})" for loc in locs]
    label_to_id = {labels[i]: locs[i].id for i in range(len(locs))}
    selected = st.selectbox("Select location", labels, key="sa_cust_loc_pick")
    loc_id = label_to_id.get(selected)
    if not loc_id:
        return None, None
    with get_session() as session:
        loc = session.query(Location).get(int(loc_id))
    return loc, f"{loc.name} ({loc.code})" if loc else (None, None)


def _slugify_identifier(value: str, fallback: str = "field") -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        return fallback
    if not re.match(r"^[a-z][a-z0-9_]*$", value):
        value = re.sub(r"^[^a-z]+", "", value)
        value = value or fallback
    return value


def _parse_qualified(ref: str) -> Tuple[Optional[str], Optional[str]]:
    if not ref or "." not in ref:
        return None, None
    left, right = ref.split(".", 1)
    return left.strip() or None, right.strip() or None


def _list_tables() -> List[str]:
    tables = [t for t in (get_all_database_tables() or []) if t and not t.startswith("sqlite_")]
    return tables


def _columns_for_table(table_name: str) -> List[Dict[str, Any]]:
    if not table_name:
        return []
    return AnalysisSchemaManager.get_table_columns(table_name) or []


def _field_options(alias_map: Dict[str, str]) -> List[str]:
    opts: List[str] = []
    for alias, table_name in (alias_map or {}).items():
        for col in _columns_for_table(table_name):
            name = col.get("name")
            if not name:
                continue
            opts.append(f"{alias}.{name}")
    return sorted(set(opts))


def _location_field_options(alias_map: Dict[str, str]) -> List[str]:
    opts: List[str] = []
    for alias, table_name in (alias_map or {}).items():
        for col in _columns_for_table(table_name):
            if (col.get("name") or "").lower() == "location_id":
                opts.append(f"{alias}.location_id")
    return sorted(set(opts))


def _date_field_options(alias_map: Dict[str, str]) -> List[str]:
    opts: List[str] = []
    for alias, table_name in (alias_map or {}).items():
        for col in _columns_for_table(table_name):
            name = (col.get("name") or "").strip()
            if not name:
                continue
            ctype = (col.get("type") or "").lower()
            if ctype in {"date", "datetime"} or "date" in name.lower():
                opts.append(f"{alias}.{name}")
    return sorted(set(opts))


def _chart_type_options() -> List[Tuple[str, str]]:
    # value, label
    allowed = {"table", "line", "bar", "area", "pie", "donut", "scatter", "metric", "histogram"}
    opts = []
    for item in VisualizationHelper.get_chart_options():
        if item.get("value") in allowed:
            opts.append((item["value"], item.get("label") or item["value"]))
    # stable ordering
    order = ["table", "metric", "line", "bar", "area", "pie", "donut", "scatter", "histogram"]
    order_idx = {k: i for i, k in enumerate(order)}
    opts.sort(key=lambda x: order_idx.get(x[0], 999))
    return opts


def _validate_analysis_tab_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    tab_name = (payload.get("name") or "").strip()
    if not tab_name:
        errors.append("Tab name is required.")

    sources = list(payload.get("source_tables") or [])
    if not sources or not isinstance(sources[0], dict):
        errors.append("Select a primary table.")
    else:
        primary = sources[0]
        if not (primary.get("name") or "").strip():
            errors.append("Primary table is required.")
        if not (primary.get("alias") or "").strip():
            errors.append("Primary alias is required.")

    table_name = (payload.get("table_name") or "").strip()
    if table_name:
        ok, msg = AnalysisSchemaManager.validate_table_name(table_name)
        if not ok:
            errors.append(f"Invalid materialized table name: {msg}")

    joins = payload.get("joins") or []
    if joins and not isinstance(joins, list):
        errors.append("Joins must be a list.")
    else:
        for idx, j in enumerate(joins or [], 1):
            if not isinstance(j, dict):
                errors.append(f"Join #{idx}: invalid config.")
                continue
            if not (j.get("left_table") or "").strip():
                errors.append(f"Join #{idx}: left table alias is required.")
            if not (j.get("right_table") or "").strip():
                errors.append(f"Join #{idx}: right table is required.")
            if not (j.get("right_alias") or "").strip():
                errors.append(f"Join #{idx}: right alias is required.")
            conditions = j.get("conditions") or []
            if not conditions:
                errors.append(f"Join #{idx}: at least one join condition is required.")

    cols = payload.get("columns") or []
    if not cols:
        errors.append("At least one output column is required.")
        return errors

    seen = set()
    for idx, col in enumerate(cols, 1):
        if not isinstance(col, dict):
            errors.append(f"Column #{idx}: invalid definition.")
            continue
        name = (col.get("alias") or "").strip()
        if not name:
            errors.append(f"Column #{idx}: output column name is required.")
            continue
        if not re.match(r"^[a-z][a-z0-9_]*$", name):
            errors.append(f"Column #{idx}: '{name}' is not a valid identifier (use letters/numbers/underscore).")
        if name in seen:
            errors.append(f"Duplicate output column name: '{name}'.")
        seen.add(name)

        if (col.get("type") or "").strip().lower() == "computed":
            if not (col.get("formula") or "").strip():
                errors.append(f"Column #{idx} ('{name}'): computed formula is required.")
        else:
            source_ref = (col.get("source") or "").strip()
            if not source_ref or "." not in source_ref:
                errors.append(f"Column #{idx} ('{name}'): pick a valid source field.")

    return errors


def render_stock_analysis_customization_page(user: Optional[Dict[str, Any]], active_location_id: Optional[int] = None):
    header("Stock Analysis Customization")

    if not _guard_admin(user):
        return

    if active_location_id is None:
        active_location_id = st.session_state.get("active_location_id")

    loc, loc_label = _pick_location(active_location_id)
    if not loc:
        return

    st.caption(f"Configuring Stock Analysis for **{loc_label}**")
    st.markdown("---")

    view_key = f"_audit_view_stock_analysis_customization_{loc.id}"
    if not st.session_state.get(view_key):
        _audit(
            user,
            action="VIEW",
            resource_type="StockAnalysisCustomization",
            resource_id=str(loc.id),
            details=f"Viewed Stock Analysis Customization for {loc_label}",
            location_id=loc.id,
            success=True,
        )
        st.session_state[view_key] = True

    st.info(
        "This page defines your Stock Analysis tabs. Each tab has:\n"
        "- A dataset (built by joining tables and selecting columns)\n"
        "- Optional visual widgets (charts / metrics / tables)\n"
        "- Optional materialization (write the results into a new DB table)"
    )

    with get_session() as session:
        existing_tabs = AnalysisConfigManager.load_analysis_tabs(session, loc.id, include_inactive=True)

    tab_label_to_id: Dict[str, Optional[str]] = {"New analysis tab": None}
    for t in existing_tabs:
        name = (t.get("name") or "Unnamed").strip() or "Unnamed"
        tid = str(t.get("id") or "")
        tab_label_to_id[f"{name} ({tid[:8]})"] = tid

    selected_label = st.selectbox(
        "Select an analysis tab to edit",
        options=list(tab_label_to_id.keys()),
        key=f"sa_cust_tab_select_{loc.id}",
    )
    selected_id = tab_label_to_id.get(selected_label)
    selected_tab = next((t for t in existing_tabs if str(t.get("id") or "") == str(selected_id or "")), None)
    tab_config: Dict[str, Any] = dict(selected_tab or {})

    key_prefix = f"sa_cust_{loc.id}_{selected_id or 'new'}"

    # -------------------- 1) Tab Info --------------------
    with st.expander("1) Tab Info", expanded=True):
        default_name = (tab_config.get("name") or "").strip()
        tab_name = st.text_input("Tab name *", value=default_name, key=f"{key_prefix}_name")
        tab_desc = st.text_area("Description (optional)", value=(tab_config.get("description") or ""), key=f"{key_prefix}_desc")
        tab_active = st.checkbox("Active", value=bool(tab_config.get("active", True)), key=f"{key_prefix}_active")

    # -------------------- 2) Dataset (tables + joins) --------------------
    all_tables = _list_tables()
    if not all_tables:
        st.error("No database tables found.")
        return

    existing_sources = list(tab_config.get("source_tables") or [])
    existing_primary = existing_sources[0] if existing_sources else {}
    existing_primary_table = existing_primary.get("name")
    existing_primary_alias = existing_primary.get("alias") or "t1"

    with st.expander("2) Dataset Builder (tables + joins)", expanded=True):
        st.caption("Define which tables to use and how they relate (joins).")

        primary_table = st.selectbox(
            "Primary table (drives FROM clause)",
            options=all_tables,
            index=(all_tables.index(existing_primary_table) if existing_primary_table in all_tables else 0),
            key=f"{key_prefix}_primary_table",
        )
        primary_alias = st.text_input(
            "Primary alias (used in column selections)",
            value=str(existing_primary_alias or "t1"),
            key=f"{key_prefix}_primary_alias",
            help="Example: t1. You will reference columns like t1.tx_date.",
        ).strip() or "t1"

        alias_map: Dict[str, str] = {primary_alias: primary_table}

        joins_existing = list(tab_config.get("joins") or [])
        join_count_default = len(joins_existing)
        join_count = int(
            st.number_input(
                "Number of joins",
                min_value=0,
                max_value=12,
                value=join_count_default,
                step=1,
                key=f"{key_prefix}_join_count",
            )
        )

        joins_out: List[Dict[str, Any]] = []
        for j in range(join_count):
            j_existing = joins_existing[j] if j < len(joins_existing) else {}
            st.markdown(f"**Join {j + 1}**")

            left_alias_default = (j_existing.get("left_table") or primary_alias)
            left_alias = st.selectbox(
                "Left table alias",
                options=list(alias_map.keys()),
                index=(list(alias_map.keys()).index(left_alias_default) if left_alias_default in alias_map else 0),
                key=f"{key_prefix}_join_{j}_left_alias",
            )
            left_table_name = alias_map.get(left_alias)

            join_type = st.selectbox(
                "Join type",
                options=["left", "inner"],
                index=(0 if (j_existing.get("type") or "left").lower() != "inner" else 1),
                key=f"{key_prefix}_join_{j}_type",
            )

            right_table_default = j_existing.get("right_table")
            right_table = st.selectbox(
                "Right table",
                options=all_tables,
                index=(all_tables.index(right_table_default) if right_table_default in all_tables else 0),
                key=f"{key_prefix}_join_{j}_right_table",
            )

            right_alias_default = (j_existing.get("right_alias") or _slugify_identifier(right_table, fallback=f"t{j + 2}"))
            right_alias = st.text_input(
                "Right alias",
                value=str(right_alias_default),
                key=f"{key_prefix}_join_{j}_right_alias",
                help="Example: t2. You will reference columns like t2.tank_id.",
            ).strip() or right_alias_default

            # Columns for join key picks
            left_cols = [c.get("name") for c in _columns_for_table(left_table_name) if c.get("name")]
            right_cols = [c.get("name") for c in _columns_for_table(right_table) if c.get("name")]

            # Normalize existing join conditions
            existing_conditions = list(j_existing.get("conditions") or [])
            if not existing_conditions and j_existing.get("left_field") and j_existing.get("right_field"):
                existing_conditions = [{"left_field": j_existing.get("left_field"), "right_field": j_existing.get("right_field")}]

            cond_count_default = max(1, len(existing_conditions) or 1)
            cond_count = int(
                st.number_input(
                    "Join conditions (keys)",
                    min_value=1,
                    max_value=6,
                    value=cond_count_default,
                    step=1,
                    key=f"{key_prefix}_join_{j}_cond_count",
                )
            )

            conditions_out: List[Dict[str, str]] = []
            for cidx in range(cond_count):
                cond_existing = existing_conditions[cidx] if cidx < len(existing_conditions) else {}
                c1, c2 = st.columns(2)
                with c1:
                    left_field = st.selectbox(
                        f"Left field #{cidx + 1}",
                        options=left_cols,
                        index=(left_cols.index(cond_existing.get("left_field")) if cond_existing.get("left_field") in left_cols else 0) if left_cols else 0,
                        key=f"{key_prefix}_join_{j}_cond_{cidx}_left",
                    ) if left_cols else ""
                with c2:
                    right_field = st.selectbox(
                        f"Right field #{cidx + 1}",
                        options=right_cols,
                        index=(right_cols.index(cond_existing.get("right_field")) if cond_existing.get("right_field") in right_cols else 0) if right_cols else 0,
                        key=f"{key_prefix}_join_{j}_cond_{cidx}_right",
                    ) if right_cols else ""
                if left_field and right_field:
                    conditions_out.append({"left_field": left_field, "right_field": right_field})

            joins_out.append(
                {
                    "type": join_type,
                    "left_table": left_alias,
                    "right_table": right_table,
                    "right_alias": right_alias,
                    "conditions": conditions_out,
                }
            )

            # Make this alias available for subsequent joins/columns
            alias_map[right_alias] = right_table

            st.markdown("---")

    # -------------------- 3) Columns + query options --------------------
    columns_existing = list(tab_config.get("columns") or [])
    group_by_existing = list(tab_config.get("group_by") or [])
    order_by_existing = list(tab_config.get("order_by") or [])
    limit_existing = tab_config.get("limit")

    with st.expander("3) Output Columns (schema of your analysis)", expanded=True):
        st.caption("These columns define the analysis dataset and also become the columns of the optional saved table.")
        col_count_default = len(columns_existing) if columns_existing else 6
        col_count = int(
            st.number_input(
                "Number of output columns",
                min_value=1,
                max_value=80,
                value=col_count_default,
                step=1,
                key=f"{key_prefix}_col_count",
            )
        )

        all_field_opts = _field_options(alias_map)
        output_cols: List[Dict[str, Any]] = []
        output_names: List[str] = []

        agg_opts = ["", "sum", "avg", "count", "min", "max"]

        for idx in range(col_count):
            existing_col = columns_existing[idx] if idx < len(columns_existing) else {}
            existing_kind = "computed" if (existing_col.get("type") == "computed") else "source"
            st.markdown(f"**Column {idx + 1}**")

            kind = st.selectbox(
                "Column type",
                options=["source", "computed"],
                index=(1 if existing_kind == "computed" else 0),
                key=f"{key_prefix}_col_{idx}_kind",
            )

            default_output = (existing_col.get("alias") or existing_col.get("label") or "")
            output_name = st.text_input(
                "Output column name * (DB-safe: letters/numbers/underscore)",
                value=str(default_output or ""),
                key=f"{key_prefix}_col_{idx}_out",
                help="Example: opening_stock_bbl. This will be the DataFrame/DB column name.",
            )
            output_name = _slugify_identifier(output_name, fallback=f"col_{idx + 1}")
            output_label = st.text_input(
                "Display label (optional)",
                value=str(existing_col.get("label") or output_name),
                key=f"{key_prefix}_col_{idx}_label",
            )

            if kind == "computed":
                formula = st.text_area(
                    "SQL formula (use aliases, e.g. t1.opening_stock + t1.receipt - t1.dispatch)",
                    value=str(existing_col.get("formula") or ""),
                    key=f"{key_prefix}_col_{idx}_formula",
                )
                output_cols.append(
                    {
                        "type": "computed",
                        "formula": (formula or "").strip(),
                        "alias": output_name,
                        "label": output_label,
                    }
                )
            else:
                default_source = str(existing_col.get("source") or "")
                src_alias, src_field = _parse_qualified(default_source)
                if all_field_opts:
                    default_ref = f"{src_alias}.{src_field}" if src_alias and src_field else ""
                    source_ref = st.selectbox(
                        "Source field",
                        options=all_field_opts,
                        index=(all_field_opts.index(default_ref) if default_ref in all_field_opts else 0),
                        key=f"{key_prefix}_col_{idx}_source",
                    )
                else:
                    source_ref = ""

                agg_default = str(existing_col.get("aggregation") or "")
                aggregation = st.selectbox(
                    "Aggregation (optional)",
                    options=agg_opts,
                    index=(agg_opts.index(agg_default) if agg_default in agg_opts else 0),
                    key=f"{key_prefix}_col_{idx}_agg",
                    help="If you choose an aggregation, set Group By fields below.",
                )

                output_cols.append(
                    {
                        "source": source_ref,
                        "alias": output_name,
                        "label": output_label,
                        "aggregation": aggregation or None,
                    }
                )

            output_names.append(output_name)
            st.markdown("---")

        group_by = st.multiselect(
            "Group By (optional)",
            options=output_names,
            default=[g for g in group_by_existing if g in output_names],
            key=f"{key_prefix}_group_by",
        )

        sort_count_default = len(order_by_existing) if order_by_existing else 0
        sort_count = int(
            st.number_input(
                "Number of ORDER BY fields",
                min_value=0,
                max_value=10,
                value=sort_count_default,
                step=1,
                key=f"{key_prefix}_sort_count",
            )
        )
        order_by: List[Dict[str, str]] = []
        for sidx in range(sort_count):
            existing_sort = order_by_existing[sidx] if sidx < len(order_by_existing) else {}
            c1, c2 = st.columns(2)
            with c1:
                field = st.selectbox(
                    f"Sort field #{sidx + 1}",
                    options=output_names,
                    index=(output_names.index(existing_sort.get("field")) if existing_sort.get("field") in output_names else 0),
                    key=f"{key_prefix}_sort_{sidx}_field",
                )
            with c2:
                direction = st.selectbox(
                    f"Direction #{sidx + 1}",
                    options=["ASC", "DESC"],
                    index=(1 if str(existing_sort.get("direction") or "ASC").upper() == "DESC" else 0),
                    key=f"{key_prefix}_sort_{sidx}_dir",
                )
            order_by.append({"field": field, "direction": direction})

        limit_val = st.number_input(
            "Limit (optional)",
            min_value=0,
            max_value=200000,
            value=int(limit_existing) if isinstance(limit_existing, int) and limit_existing > 0 else 0,
            step=100,
            key=f"{key_prefix}_limit",
            help="0 means no limit.",
        )

    # -------------------- 4) Runtime filters --------------------
    runtime_existing = dict(tab_config.get("runtime_filters") or {})
    with st.expander("4) Runtime Filters (location/date)", expanded=True):
        st.caption("These power the end-user filters on the Stock Analysis page.")

        loc_field_opts = _location_field_options(alias_map)
        default_loc_field = str(runtime_existing.get("location_field") or "")
        loc_field = st.selectbox(
            "Location filter field",
            options=(loc_field_opts or [""]),
            index=(loc_field_opts.index(default_loc_field) if default_loc_field in loc_field_opts else 0) if loc_field_opts else 0,
            key=f"{key_prefix}_rt_loc_field",
            help="Which column should be filtered to the active location_id.",
        )

        date_field_opts = _date_field_options(alias_map)
        date_choices = ["(disable date filter)"] + date_field_opts
        default_date_field = str(runtime_existing.get("date_field") or "")
        date_idx = 0
        if default_date_field and default_date_field in date_field_opts:
            date_idx = date_choices.index(default_date_field)
        date_field_choice = st.selectbox(
            "Date filter field",
            options=date_choices,
            index=date_idx,
            key=f"{key_prefix}_rt_date_field",
            help="Pick which date column should respond to Date From / Date To filters.",
        )
        date_field = None if date_field_choice == "(disable date filter)" else date_field_choice

    # -------------------- 5) Visualizations --------------------
    viz_existing = list(tab_config.get("visualizations") or [])
    chart_opts = _chart_type_options()
    chart_values = [c[0] for c in chart_opts]
    chart_labels = {c[0]: c[1] for c in chart_opts}

    with st.expander("5) Widgets (charts / tables / metrics)", expanded=True):
        st.caption("Widgets control how this dataset is presented on the Stock Analysis page.")

        viz_count_default = len(viz_existing) if viz_existing else 1
        viz_count = int(
            st.number_input(
                "Number of widgets",
                min_value=1,
                max_value=20,
                value=viz_count_default,
                step=1,
                key=f"{key_prefix}_viz_count",
            )
        )

        visualizations: List[Dict[str, Any]] = []
        for vidx in range(viz_count):
            v_existing = viz_existing[vidx] if vidx < len(viz_existing) else {}
            st.markdown(f"**Widget {vidx + 1}**")

            v_title = st.text_input(
                "Widget title",
                value=str(v_existing.get("title") or ""),
                key=f"{key_prefix}_viz_{vidx}_title",
            )
            v_type = st.selectbox(
                "Chart type",
                options=chart_values,
                format_func=lambda v: chart_labels.get(v, v),
                index=(chart_values.index(v_existing.get("type")) if v_existing.get("type") in chart_values else 0),
                key=f"{key_prefix}_viz_{vidx}_type",
            )

            x_field = st.selectbox(
                "X axis / Category field (optional)",
                options=[""] + output_names,
                index=([""] + output_names).index(v_existing.get("x_field")) if v_existing.get("x_field") in output_names else 0,
                key=f"{key_prefix}_viz_{vidx}_x",
            )
            y_field = st.selectbox(
                "Metric / Value field (optional)",
                options=[""] + output_names,
                index=([""] + output_names).index(v_existing.get("y_field")) if v_existing.get("y_field") in output_names else 0,
                key=f"{key_prefix}_viz_{vidx}_y",
            )
            series_field = st.selectbox(
                "Series / Color field (optional)",
                options=[""] + output_names,
                index=([""] + output_names).index(v_existing.get("series_field")) if v_existing.get("series_field") in output_names else 0,
                key=f"{key_prefix}_viz_{vidx}_series",
            )

            visualizations.append(
                {
                    "title": (v_title or "").strip(),
                    "type": v_type,
                    "x_field": (x_field or "").strip(),
                    "y_field": (y_field or "").strip(),
                    "series_field": (series_field or "").strip(),
                }
            )
            st.markdown("---")

    # -------------------- 6) Save / Preview / Materialize / Delete --------------------
    with st.expander("6) Save / Preview / Materialize", expanded=True):
        preview_days = st.number_input(
            "Preview window (days)",
            min_value=1,
            max_value=365,
            value=30,
            step=1,
            key=f"{key_prefix}_preview_days",
        )

        today = date.today()
        preview_from = today - timedelta(days=int(preview_days))
        preview_to = today

        username = (user or {}).get("username", "system")

        material_table_default = str(tab_config.get("table_name") or _slugify_identifier(f"sa_{tab_name}", fallback=f"sa_{loc.id}"))
        material_table_name = st.text_input(
            "Optional materialized table name",
            value=material_table_default,
            key=f"{key_prefix}_mat_table",
            help="If set, you can write the query results into this table.",
        ).strip()

        if_exists = st.selectbox(
            "When saving, if table exists...",
            options=["append", "replace", "fail"],
            index=(["append", "replace", "fail"].index(str(tab_config.get("if_exists") or "append")) if str(tab_config.get("if_exists") or "append") in ["append", "replace", "fail"] else 0),
            key=f"{key_prefix}_if_exists",
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            do_preview = st.button("Preview query", key=f"{key_prefix}_preview_btn")
        with c2:
            do_save = st.button("Save tab configuration", type="primary", key=f"{key_prefix}_save_btn")
        with c3:
            do_materialize = st.button("Run & write to table", key=f"{key_prefix}_mat_btn", disabled=not bool(material_table_name))

        # Build final payload
        payload: Dict[str, Any] = {
            "id": str(selected_id or tab_config.get("id") or ""),
            "name": (tab_name or "").strip(),
            "description": (tab_desc or "").strip(),
            "active": bool(tab_active),
            "table_name": material_table_name or None,
            "if_exists": if_exists,
            "source_tables": [{"name": primary_table, "alias": primary_alias}],
            "joins": joins_out,
            "columns": output_cols,
            "group_by": group_by,
            "order_by": order_by,
            "limit": (int(limit_val) if int(limit_val) > 0 else None),
            "runtime_filters": {
                "location_field": (loc_field or "").strip() or None,
                "date_field": (date_field or None),
            },
            "visualizations": visualizations,
        }

        payload_errors = _validate_analysis_tab_payload(payload)

        if do_preview or do_materialize:
            if payload_errors:
                for err in payload_errors:
                    st.error(err)
                _audit(
                    user,
                    action="PREVIEW" if do_preview else "MATERIALIZE",
                    resource_type="StockAnalysisTab",
                    resource_id=str(selected_id or "unsaved"),
                    details=f"Validation failed for tab '{payload.get('name') or ''}': {payload_errors[0]}",
                    location_id=loc.id,
                    success=False,
                )
                st.stop()

            # Preview/materialize runtime filters (location + last N days) if date filter enabled
            user_filters: Dict[str, Any] = {"location_id": loc.id}
            if date_field:
                user_filters["date_from"] = preview_from
                user_filters["date_to"] = preview_to

            query_ok = True
            try:
                qb = AnalyticsQueryBuilder(payload)
                sql = qb.build_sql(user_filters)
                st.code(sql, language="sql")
                df = qb.execute(user_filters)
            except Exception as ex:
                query_ok = False
                st.error(f"Failed to execute query: {ex}")
                df = pd.DataFrame()
                _audit(
                    user,
                    action="PREVIEW" if do_preview else "MATERIALIZE",
                    resource_type="StockAnalysisTab",
                    resource_id=str(selected_id or "unsaved"),
                    details=f"Query execution failed for tab '{payload.get('name') or ''}': {ex}",
                    location_id=loc.id,
                    success=False,
                )

            if not df.empty:
                TableDisplay.display_data_table(df, title="Preview (first rows)", searchable=True)
            else:
                st.info("No rows returned (or query failed).")

            if do_preview and query_ok:
                _audit(
                    user,
                    action="PREVIEW",
                    resource_type="StockAnalysisTab",
                    resource_id=str(selected_id or "unsaved"),
                    details=(
                        f"Previewed tab '{payload.get('name') or ''}' "
                        f"(primary={primary_table}, joins={len(joins_out)}, cols={len(output_cols)}; rows={len(df)})"
                    ),
                    location_id=loc.id,
                    success=True,
                )

            if do_materialize and query_ok and df.empty and material_table_name:
                _audit(
                    user,
                    action="MATERIALIZE",
                    resource_type="StockAnalysisTable",
                    resource_id=str(material_table_name),
                    details=(
                        f"Materialize requested for tab '{payload.get('name') or ''}' "
                        f"to table '{material_table_name}' but query returned 0 rows"
                    ),
                    location_id=loc.id,
                    success=True,
                )

            if do_materialize and not df.empty and material_table_name:
                ok, msg, _rows = AnalysisResultWriter.save_to_table(
                    df=df,
                    table_name=material_table_name,
                    location_id=loc.id,
                    username=username,
                    if_exists=if_exists,
                )
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

                _audit(
                    user,
                    action="MATERIALIZE",
                    resource_type="StockAnalysisTable",
                    resource_id=str(material_table_name),
                    details=(
                        f"Materialize tab '{payload.get('name') or ''}' to table '{material_table_name}' "
                        f"(if_exists={if_exists}; rows={len(df)}): {msg}"
                    ),
                    location_id=loc.id,
                    success=bool(ok),
                )

        if do_save:
            if payload_errors:
                for err in payload_errors:
                    st.error(err)
                _audit(
                    user,
                    action="UPDATE" if selected_id else "CREATE",
                    resource_type="StockAnalysisTab",
                    resource_id=str(selected_id or "unsaved"),
                    details=f"Validation failed saving tab '{payload.get('name') or ''}': {payload_errors[0]}",
                    location_id=loc.id,
                    success=False,
                )
            else:
                with get_session() as session:
                    ok, msg, tab_id = AnalysisConfigManager.save_analysis_tab(session, loc.id, payload)
                if ok:
                    st.success(msg)
                    _audit(
                        user,
                        action="UPDATE" if selected_id else "CREATE",
                        resource_type="StockAnalysisTab",
                        resource_id=str(tab_id or selected_id or "unknown"),
                        details=f"{'Updated' if selected_id else 'Created'} stock analysis tab '{payload.get('name') or ''}'",
                        location_id=loc.id,
                        success=True,
                    )
                    st.rerun()
                else:
                    st.error(msg)
                    _audit(
                        user,
                        action="UPDATE" if selected_id else "CREATE",
                        resource_type="StockAnalysisTab",
                        resource_id=str(selected_id or payload.get("name") or "unknown"),
                        details=f"Failed to save stock analysis tab '{payload.get('name') or ''}': {msg}",
                        location_id=loc.id,
                        success=False,
                    )

        st.markdown("---")
        st.subheader("Delete tab")
        if selected_id:
            drop_table = st.checkbox(
                "Also drop materialized table (if exists)",
                value=False,
                key=f"{key_prefix}_drop_table",
                help="If checked, the saved DB table will be dropped too (based on the table name above).",
            )
            confirm = st.text_input(
                "Type DELETE to confirm",
                value="",
                key=f"{key_prefix}_delete_confirm",
            )
            if st.button("Delete tab", type="secondary", key=f"{key_prefix}_delete_btn", disabled=(confirm.strip().upper() != "DELETE")):
                with get_session() as session:
                    ok, msg = AnalysisConfigManager.delete_analysis_tab(session, loc.id, str(selected_id), drop_table=bool(drop_table))
                if ok:
                    st.success(msg)
                    _audit(
                        user,
                        action="DELETE",
                        resource_type="StockAnalysisTab",
                        resource_id=str(selected_id),
                        details=f"Deleted stock analysis tab '{tab_config.get('name') or ''}' (drop_table={bool(drop_table)})",
                        location_id=loc.id,
                        success=True,
                    )
                    st.rerun()
                else:
                    st.error(msg)
                    _audit(
                        user,
                        action="DELETE",
                        resource_type="StockAnalysisTab",
                        resource_id=str(selected_id),
                        details=f"Failed to delete stock analysis tab '{tab_config.get('name') or ''}': {msg}",
                        location_id=loc.id,
                        success=False,
                    )
        else:
            st.caption("Select an existing tab to delete it.")
