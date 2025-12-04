# app_pages/report_customization.py
"""
Report Customization Page

Admins can compose reports that pull columns from multiple tables (across locations)
and map how those tables relate using explicit join keys directly in the UI.
"""

from datetime import datetime
import json
import re
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from db import get_session
from models import Location, ReportAccess, ReportDefinition
from report_engine import get_available_data_sources, get_columns_for_source


# -----------------------------------------------------------------------------
# Helper utilities
# -----------------------------------------------------------------------------

def _slugify(value: str, fallback: str = "field") -> str:
    """Convert labels into safe, lowercase keys for storage/output."""
    if not value:
        return fallback
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or fallback


def _table_display_name(table: str) -> str:
    """Human-friendly names for common tables."""
    mapping = {
        "otr_records": "OTR Records",
        "tank_transactions": "Tank Transactions",
        "tanker_transactions": "Tanker Dispatch Records",
        "yade_voyages": "YADE Voyages",
        "fso_operations": "FSO Operations",
        "gpp_production": "GPP Production",
        "river_draft": "River Draft",
        "produced_water": "Produced Water",
        "ofs_production": "OFS Production & Evacuation",
        "tanks": "Tank Master",
        "vessels": "Vessel Master",
        "locations": "Locations",
        "users": "Users",
        "audit_log": "Audit Log",
        "tasks": "Tasks",
        "recycle_bin": "Recycle Bin",
        "report_definitions": "Report Definitions",
        "report_access": "Report Access Rules",
    }
    if table in mapping:
        return mapping[table]
    if table and table.startswith("flex_"):
        parts = table.split("_")
        if len(parts) >= 3:
            section = parts[1].replace("_", " ").title()
            loc_id = parts[-1]
            return f"{section} (Custom - Location {loc_id})"
    return table.replace("_", " ").title() if table else "Unknown"


def _table_option(table: str) -> str:
    """Show display + technical name in selects."""
    return f"{_table_display_name(table)} ({table})"


def _parse_table(option_value: str) -> Optional[str]:
    if not option_value:
        return None
    if "(" in option_value and option_value.endswith(")"):
        return option_value.split("(")[-1][:-1]
    return option_value


def _load_locations() -> Tuple[List[str], Dict[str, int]]:
    """Return label list and label->id mapping for locations."""
    with get_session() as session:
        locs = session.query(Location).order_by(Location.name.asc()).all()
    labels = [f"{loc.name} (ID: {loc.id})" for loc in locs]
    mapping = {label: loc.id for label, loc in zip(labels, locs)}
    return labels, mapping


def _default_join_keys(base_cols: List[Dict[str, Any]], src_cols: List[Dict[str, Any]], mode: str) -> List[Dict[str, str]]:
    """
    Build default join keys based on a selected mode.
    Supported modes: auto, date_location, tank_date, location_only.
    """
    base_fields = {c["field"] for c in base_cols}
    src_fields = {c["field"] for c in src_cols}

    def _first_match(options: List[str], field_set: set) -> Optional[str]:
        for opt in options:
            if opt in field_set:
                return opt
        return None

    join_keys: List[Dict[str, str]] = []
    if mode == "date_location":
        left_date = _first_match(["tx_date", "date", "record_date"], base_fields)
        right_date = _first_match(["tx_date", "date", "record_date"], src_fields)
        left_loc = _first_match(["location_id"], base_fields)
        right_loc = _first_match(["location_id"], src_fields)
        if left_date and right_date:
            join_keys.append({"primary": left_date, "source": right_date})
        if left_loc and right_loc:
            join_keys.append({"primary": left_loc, "source": right_loc})
    elif mode == "tank_date":
        left_tank = _first_match(["tank_id"], base_fields)
        right_tank = _first_match(["tank_id"], src_fields)
        left_date = _first_match(["tx_date", "date", "record_date"], base_fields)
        right_date = _first_match(["tx_date", "date", "record_date"], src_fields)
        if left_tank and right_tank:
            join_keys.append({"primary": left_tank, "source": right_tank})
        if left_date and right_date:
            join_keys.append({"primary": left_date, "source": right_date})
    elif mode == "location_only":
        left_loc = "location_id" if "location_id" in base_fields else None
        right_loc = "location_id" if "location_id" in src_fields else None
        if left_loc and right_loc:
            join_keys.append({"primary": left_loc, "source": right_loc})
    else:
        # auto: prefer date + location if both exist
        return _default_join_keys(base_cols, src_cols, "date_location")
    return join_keys


# -----------------------------------------------------------------------------
# Page entrypoint
# -----------------------------------------------------------------------------

def render_report_customization_page(user: Dict[str, Any], active_location_id: int):
    st.title("Report Customization")
    st.caption("Create multi-table reports, map relationships with keys, and manage access.")
    st.markdown("---")

    role = (user or {}).get("role")
    if role not in ["admin-operations", "admin-it", "manager"]:
        st.warning("You need admin or manager privileges to customize reports.")
        return

    tab_create, tab_manage = st.tabs(["Create New Report", "Manage Existing Reports"])
    with tab_create:
        render_create_report_form(user, active_location_id)
    with tab_manage:
        render_manage_reports(user, active_location_id)


# -----------------------------------------------------------------------------
# Create flow
# -----------------------------------------------------------------------------

def render_create_report_form(user: Dict[str, Any], active_location_id: int):
    st.markdown("### Build a Custom Report")

    available_sources = get_available_data_sources()
    if not available_sources:
        st.error("No data sources available. Please check database connections.")
        return

    source_options = [_table_option(src) for src in available_sources]
    loc_labels, loc_map = _load_locations()

    # 1) Basic info
    with st.expander("1) Basic Information", expanded=True):
        report_name = st.text_input("Report Name *", placeholder="e.g., Daily Tank Summary")
        default_slug = _slugify(report_name) if report_name else ""
        report_slug = st.text_input("Report Slug *", value=default_slug, placeholder="e.g., daily_tank_summary")
        description = st.text_area("Description (optional)", placeholder="What this report is for")

    # 2) Base table & scope
    with st.expander("2) Choose Base Table & Scope", expanded=True):
        base_source_opt = st.selectbox(
            "Base table (drives primary rows)",
            options=source_options,
            key="base_source_opt",
        )
        base_source = _parse_table(base_source_opt)
        base_columns = get_columns_for_source(base_source) if base_source else []

        loc_scope = st.selectbox(
            "Base location scope",
            options=["Current location", "Specific location", "All locations"],
            help="Controls which location is used when pulling the base table rows.",
        )
        base_location_mode = "current" if loc_scope == "Current location" else ("specific" if loc_scope == "Specific location" else "all")
        base_location_id = None
        if base_location_mode == "specific":
            loc_labels, loc_map = _load_locations()
            sel_label = st.selectbox("Base location", options=loc_labels)
            base_location_id = loc_map.get(sel_label)

    # 3) Relationships between tables
    relationship_configs: List[Dict[str, Any]] = []
    with st.expander("3) Define Table Relationships (join keys)", expanded=True):
        st.caption("Tell the builder how other tables relate to the base table. These mappings are reused for columns from the same table.")
        rel_count = st.number_input("Number of relationships to define", min_value=0, max_value=10, value=1, step=1)
        for idx in range(int(rel_count)):
            st.markdown(f"**Relationship {idx + 1}**")
            c1, c2, c3 = st.columns([0.4, 0.3, 0.3])
            with c1:
                rel_table_opt = st.selectbox(
                    "Related table",
                    options=source_options,
                    key=f"rel_table_{idx}",
                )
                rel_table = _parse_table(rel_table_opt)
                rel_cols = get_columns_for_source(rel_table) if rel_table else []
            with c2:
                base_key = st.selectbox(
                    "Base key field",
                    options=[c["field"] for c in base_columns] if base_columns else [],
                    key=f"rel_base_key_{idx}",
                )
                target_key = st.selectbox(
                    "Related key field",
                    options=[c["field"] for c in rel_cols] if rel_cols else [],
                    key=f"rel_target_key_{idx}",
                )
            with c3:
                match_location = st.checkbox(
                    "Also match location_id",
                    value=True,
                    key=f"rel_loc_match_{idx}",
                    help="Useful when combining data across tables but keeping locations aligned.",
                )
                join_type = st.selectbox(
                    "Join type",
                    options=["left", "inner"],
                    key=f"rel_join_type_{idx}",
                )
            join_keys: List[Dict[str, str]] = []
            if base_key and target_key:
                join_keys.append({"primary": base_key, "source": target_key})
            if match_location:
                join_keys.append({"primary": "location_id", "source": "location_id"})
            if rel_table and join_keys:
                relationship_configs.append(
                    {
                        "table": rel_table,
                        "join_keys": join_keys,
                        "join_type": join_type,
                    }
                )

    relationship_lookup = {rel["table"]: rel.get("join_keys", []) for rel in relationship_configs if rel.get("table")}

    # 4) Columns
    column_configs: List[Dict[str, Any]] = []
    with st.expander("4) Columns & Mappings", expanded=True):
        st.caption("Add columns from one or more tables. Map how each column should join back to the base table.")
        col_count = st.number_input("Number of columns", min_value=1, max_value=60, value=4, step=1)
        for idx in range(int(col_count)):
            st.markdown(f"**Column {idx + 1}**")
            c1, c2, c3 = st.columns([0.35, 0.35, 0.30])
            with c1:
                label = st.text_input("Column label *", key=f"col_label_{idx}")
                output_field = st.text_input(
                    "Output key",
                    value=_slugify(label or f"col_{idx+1}"),
                    key=f"col_field_{idx}",
                    help="Used in exports and formulas. Lowercase + underscores only.",
                )
                dtype = st.selectbox(
                    "Type",
                    ["string", "numeric", "date", "datetime", "boolean"],
                    key=f"col_type_{idx}",
                )
                decimal_places = None
                if dtype == "numeric":
                    decimal_places = int(
                        st.number_input(
                            "Decimal places",
                            min_value=0,
                            max_value=6,
                            value=2,
                            step=1,
                            key=f"col_decimals_{idx}",
                            help="Number of decimal places to show for this numeric column in PDFs.",
                        )
                    )
            with c2:
                src_opt = st.selectbox(
                    "Data source (table) *",
                    options=source_options,
                    index=source_options.index(_table_option(base_source)) if base_source_opt in source_options and idx == 0 else 0,
                    key=f"col_src_{idx}",
                )
                source_table = _parse_table(src_opt)
                src_cols = get_columns_for_source(source_table) if source_table else []
                source_field = st.selectbox(
                    "Data field (column) *",
                    options=[c["field"] for c in src_cols] if src_cols else [],
                    key=f"col_field_select_{idx}",
                )
                agg = st.selectbox(
                    "Aggregation (optional)",
                    ["none", "sum", "avg", "max", "min"],
                    key=f"col_agg_{idx}",
                )
                aggregation = None if agg == "none" else agg
            with c3:
                loc_mode_label = st.selectbox(
                    "Location scope for this column",
                    options=["Use base location", "Specific location", "All locations", "Keep source location"],
                    key=f"col_loc_mode_{idx}",
                )
                source_location_mode = {
                    "Use base location": "current",
                    "Specific location": "specific",
                    "All locations": "all",
                    "Keep source location": "cross",
                }[loc_mode_label]
                source_location_id = None
                if source_location_mode == "specific":
                    loc_labels, loc_map = _load_locations()
                    sel_label = st.selectbox(
                        "Choose location",
                        options=loc_labels,
                        key=f"col_loc_select_{idx}",
                    )
                    source_location_id = loc_map.get(sel_label)

            # Join strategy
            jc1, jc2, jc3 = st.columns([0.34, 0.33, 0.33])
            with jc1:
                join_strategy = st.selectbox(
                    "Join strategy",
                    options=[
                        "Use defined relationship",
                        "Auto (date + location)",
                        "Date + Location",
                        "Tank + Date",
                        "Location only",
                        "Custom fields",
                    ],
                    key=f"col_join_strategy_{idx}",
                )
            manual_join_keys: List[Dict[str, str]] = []
            with jc2:
                if join_strategy == "Custom fields":
                    base_key_1 = st.selectbox(
                        "Base join field",
                        options=[c["field"] for c in base_columns] if base_columns else [],
                        key=f"col_join_base_{idx}",
                    )
                    source_key_1 = st.selectbox(
                        "Source join field",
                        options=[c["field"] for c in src_cols] if src_cols else [],
                        key=f"col_join_src_{idx}",
                    )
                    if base_key_1 and source_key_1:
                        manual_join_keys.append({"primary": base_key_1, "source": source_key_1})
            with jc3:
                if join_strategy == "Custom fields":
                    base_key_2 = st.selectbox(
                        "Additional base field (optional)",
                        options=[""] + ([c["field"] for c in base_columns] if base_columns else []),
                        key=f"col_join_base2_{idx}",
                    )
                    source_key_2 = st.selectbox(
                        "Additional source field (optional)",
                        options=[""] + ([c["field"] for c in src_cols] if src_cols else []),
                        key=f"col_join_src2_{idx}",
                    )
                    if base_key_2 and source_key_2:
                        manual_join_keys.append({"primary": base_key_2, "source": source_key_2})

            # Resolve join keys + link_by
            link_by = "auto"
            join_keys: List[Dict[str, str]] = []
            if join_strategy == "Use defined relationship":
                join_keys = relationship_lookup.get(source_table, [])
            elif join_strategy == "Auto (date + location)":
                join_keys = _default_join_keys(base_columns, src_cols, "date_location")
                link_by = "date+location"
            elif join_strategy == "Date + Location":
                join_keys = _default_join_keys(base_columns, src_cols, "date_location")
                link_by = "date+location"
            elif join_strategy == "Tank + Date":
                join_keys = _default_join_keys(base_columns, src_cols, "tank_date")
                link_by = "tank+date"
            elif join_strategy == "Location only":
                join_keys = _default_join_keys(base_columns, src_cols, "location_only")
                link_by = "location"
            elif join_strategy == "Custom fields":
                join_keys = manual_join_keys
                link_by = "custom"

            # Optional formula based on previously defined columns
            formula_cfg = None
            with st.expander(f"Add Calculation (optional) - Column {idx + 1}", expanded=False):
                use_formula = st.checkbox("Enable formula", key=f"col_use_formula_{idx}")
                if use_formula:
                    operation = st.selectbox(
                        "Operation",
                        ["sum", "subtract", "multiply", "divide", "percentage", "maximum", "minimum", "average"],
                        key=f"col_formula_op_{idx}",
                    )
                    available_labels = [c.get("label") for c in column_configs if c.get("label")]
                    selected_cols = st.multiselect(
                        "Columns to use",
                        options=available_labels,
                        key=f"col_formula_cols_{idx}",
                    )
                    if selected_cols:
                        formula_cfg = {"operation": operation, "columns": selected_cols}

            column_configs.append(
                {
                    "label": label or (source_field or f"Column {idx + 1}"),
                    "field": output_field or _slugify(label or source_field or f"col_{idx+1}"),
                    "type": dtype,
                    "source_table": source_table,
                    "source_field": source_field,
                    "aggregation": aggregation,
                    "join_keys": join_keys,
                    "source_location_mode": source_location_mode,
                    "source_location_id": source_location_id,
                    "link_by": link_by,
                    "formula": formula_cfg,
                    "decimal_places": decimal_places,
                }
            )

    # 5) Filters
    filter_configs: List[Dict[str, Any]] = []
    with st.expander("5) Filters", expanded=False):
        st.caption("Define filters end users can apply when running this report.")
        filter_count = st.number_input("Number of filters", min_value=0, max_value=15, value=1, step=1)
        for idx in range(int(filter_count)):
            st.markdown(f"**Filter {idx + 1}**")
            f1, f2, f3 = st.columns([0.4, 0.3, 0.3])
            with f1:
                field_options = [c.get("label") or c.get("field") for c in column_configs]
                filter_field = st.selectbox(
                    "Field",
                    options=field_options,
                    key=f"filter_field_{idx}",
                )
            with f2:
                filter_operator = st.selectbox(
                    "Operator",
                    options=["equals", "not_equals", "greater_than", "less_than", "contains", "between"],
                    key=f"filter_op_{idx}",
                )
            with f3:
                filter_value = st.text_input(
                    "Default value (optional)",
                    placeholder="user_location or leave blank",
                    key=f"filter_val_{idx}",
                )
            filter_configs.append(
                {
                    "field": filter_field,
                    "operator": filter_operator,
                    "value": filter_value if filter_value else None,
                }
            )

    # 6) Sorting
    sorting_configs: List[Dict[str, Any]] = []
    with st.expander("6) Sorting", expanded=False):
        sort_count = st.number_input("Number of sort fields", min_value=0, max_value=10, value=1, step=1)
        for idx in range(int(sort_count)):
            s1, s2 = st.columns(2)
            with s1:
                sort_field = st.selectbox(
                    f"Sort field {idx + 1}",
                    options=[c.get("label") or c.get("field") for c in column_configs],
                    key=f"sort_field_{idx}",
                )
            with s2:
                sort_order = st.selectbox(
                    "Order",
                    options=["asc", "desc"],
                    key=f"sort_order_{idx}",
                )
            sorting_configs.append({"field": sort_field, "order": sort_order})

    # 7) Totals & access control
    allowed_location_ids: List[int] = []
    with st.expander("7) Totals & Access Control", expanded=False):
        show_totals = st.checkbox("Include totals for numeric columns", value=True)
        allowed_roles = st.multiselect(
            "Grant access to roles",
            options=["admin-operations", "admin-it", "manager", "supervisor", "operator"],
            default=["manager", "supervisor"],
        )
        default_loc_labels = [lbl for lbl, lid in loc_map.items() if lid == active_location_id]
        allowed_location_labels = st.multiselect(
            "Enable for locations",
            options=loc_labels,
            default=default_loc_labels,
            help="Reports will only appear in Reporting for these locations until you add more.",
        )
        allowed_location_ids = [loc_map[label] for label in allowed_location_labels if label in loc_map]
        if not allowed_location_ids and active_location_id:
            allowed_location_ids = [active_location_id]

    with st.expander("8) Export Formats & Delivery Options", expanded=False):
        st.caption("Configure available export formats and delivery destinations.")

        col_fmt1, col_fmt2 = st.columns(2)

        with col_fmt1:
            st.markdown("**Available Export Formats**")
            export_csv = st.checkbox("CSV (Comma-Separated Values)", value=True, key="exp_csv")
            export_xlsx = st.checkbox("Excel (XLSX)", value=True, key="exp_xlsx")
            export_pdf = st.checkbox("PDF Document", value=True, key="exp_pdf")
            export_json = st.checkbox("JSON (For APIs)", value=False, key="exp_json")
            export_xml = st.checkbox("XML (For Integration)", value=False, key="exp_xml")
            export_html = st.checkbox("HTML (For Email/Web)", value=False, key="exp_html")

        selected_formats: List[str] = []
        if export_csv:
            selected_formats.append("csv")
        if export_xlsx:
            selected_formats.append("xlsx")
        if export_pdf:
            selected_formats.append("pdf")
        if export_json:
            selected_formats.append("json")
        if export_xml:
            selected_formats.append("xml")
        if export_html:
            selected_formats.append("html")

        with col_fmt2:
            st.markdown("**PDF Options**")
            pdf_orientation = st.selectbox(
                "PDF Orientation",
                ["Landscape", "Portrait"],
                key="pdf_orientation",
            )
            pdf_page_size = st.selectbox(
                "PDF Page Size",
                ["A4", "Letter", "Legal", "A3"],
                key="pdf_page_size",
            )
            include_logo = st.checkbox("Include company logo", value=True, key="pdf_logo")

        st.markdown("---")
        st.markdown("**Output Destinations**")
        st.caption("Configure where reports can be automatically delivered.")

        enable_destinations = st.checkbox(
            "Enable automatic delivery to destinations",
            value=False,
            key="enable_dest",
        )

        destination_configs: List[Dict[str, Any]] = []

        if enable_destinations:
            dest_count = st.number_input(
                "Number of destinations",
                min_value=1,
                max_value=5,
                value=1,
                step=1,
                key="dest_count",
            )

            for idx in range(int(dest_count)):
                st.markdown(f"**Destination {idx + 1}**")
                dest_cols = st.columns([0.3, 0.7])

                with dest_cols[0]:
                    dest_type = st.selectbox(
                        "Type",
                        ["Network Path", "Email", "SFTP", "AWS S3", "Azure Blob"],
                        key=f"dest_type_{idx}",
                    )

                with dest_cols[1]:
                    dest_config: Dict[str, Any] = {"type": dest_type.lower().replace(" ", "_")}

                    if dest_type == "Network Path":
                        dest_config["path"] = st.text_input(
                            "UNC Path or Directory",
                            placeholder="//server/share/reports/ or /mnt/reports/",
                            key=f"dest_path_{idx}",
                        )
                        dest_config["subfolder_pattern"] = st.text_input(
                            "Subfolder Pattern (optional)",
                            placeholder="{year}/{month}/ or {date}/",
                            key=f"dest_subfolder_{idx}",
                            help="Use {year}, {month}, {day}, {date}, {datetime}",
                        )

                    elif dest_type == "Email":
                        dest_config["recipients"] = st.text_input(
                            "Recipients (comma-separated)",
                            placeholder="user1@company.com, user2@company.com",
                            key=f"dest_email_{idx}",
                        )
                        dest_config["subject"] = st.text_input(
                            "Email Subject",
                            value=f"Report: {report_name or 'Report'} - {{date}}",
                            key=f"dest_subject_{idx}",
                        )

                    elif dest_type == "SFTP":
                        dest_config["host"] = st.text_input("Host", key=f"dest_sftp_host_{idx}")
                        dest_config["port"] = st.number_input("Port", min_value=1, max_value=65535, value=22, step=1, key=f"dest_sftp_port_{idx}")
                        dest_config["username"] = st.text_input("Username", key=f"dest_sftp_user_{idx}")
                        dest_config["password"] = st.text_input("Password", type="password", key=f"dest_sftp_pass_{idx}")
                        dest_config["remote_path"] = st.text_input("Remote Path", placeholder="/reports/", key=f"dest_sftp_path_{idx}")

                    elif dest_type == "AWS S3":
                        dest_config["bucket"] = st.text_input("Bucket Name", key=f"dest_s3_bucket_{idx}")
                        dest_config["folder"] = st.text_input("Folder (optional)", placeholder="reports/{year}/{month}", key=f"dest_s3_folder_{idx}")
                        dest_config["access_key_id"] = st.text_input("Access Key ID", key=f"dest_s3_key_{idx}")
                        dest_config["secret_access_key"] = st.text_input("Secret Access Key", type="password", key=f"dest_s3_secret_{idx}")

                    elif dest_type == "Azure Blob":
                        dest_config["connection_string"] = st.text_input("Connection String", key=f"dest_az_conn_{idx}")
                        dest_config["container"] = st.text_input("Container", key=f"dest_az_container_{idx}")
                        dest_config["folder"] = st.text_input("Folder (optional)", placeholder="reports/{year}/{month}", key=f"dest_az_folder_{idx}")

                    destination_configs.append(dest_config)

    # Optional table creation
    with st.expander("Optional: Persist as database table", expanded=False):
        create_db_table = st.checkbox(
            "Create a physical table from this report schema",
            value=False,
            help="Creates a table with the selected output columns. Use only if you need to store computed results.",
        )
        custom_table_name = None
        if create_db_table:
            custom_table_name = st.text_input(
                "Table name",
                value=report_slug or "custom_report_table",
                help="Lowercase with underscores only.",
            )

    st.markdown("---")
    if st.button("💾", type="primary", use_container_width=True, help="Save Custom Report"):
        errors = []
        if not report_name:
            errors.append("Report name is required.")
        if not report_slug:
            errors.append("Report slug is required.")
        if not base_source:
            errors.append("Select a base table.")
        if not column_configs:
            errors.append("Define at least one column.")
        missing_sources = [c for c in column_configs if not c.get("source_table") or not c.get("source_field")]
        if missing_sources:
            errors.append("Each column needs a source table and field.")
        if not allowed_location_ids:
            errors.append("Select at least one location to enable this report.")

        if errors:
            for err in errors:
                st.error(err)
            return

        # Ensure slug uniqueness
        with get_session() as session:
            existing = session.query(ReportDefinition).filter(ReportDefinition.slug == report_slug).first()
            if existing:
                st.error(f"Slug '{report_slug}' already exists. Please choose another.")
                return

        report_config = {
            "report_type": "custom",
            "description": description,
            "data_source": {
                "table": base_source,
                "base_location_mode": base_location_mode,
                "base_location_id": base_location_id,
                "joins": relationship_configs,
            },
            "columns": column_configs,
            "filters": [f for f in filter_configs if f.get("field")],
            "sorting": [s for s in sorting_configs if s.get("field")],
            "grouping": [],
            "aggregations": {},
            "show_totals": bool(show_totals),
            "export_formats": selected_formats,
            "pdf_options": {
                "orientation": pdf_orientation.lower() if "pdf_orientation" in st.session_state else "landscape",
                "page_size": pdf_page_size if "pdf_page_size" in st.session_state else "A4",
                "include_logo": bool(include_logo) if "pdf_logo" in st.session_state else True,
            },
            "enable_destinations": bool(enable_destinations),
            "destinations": destination_configs,
            "create_table": bool(create_db_table),
            "custom_table_name": custom_table_name if create_db_table else None,
        }

        try:
            with get_session() as session:
                primary_location_id = active_location_id if base_location_mode != "all" else None
                if base_location_mode != "all" and allowed_location_ids:
                    primary_location_id = allowed_location_ids[0]
                new_report = ReportDefinition(
                    location_id=primary_location_id,
                    name=report_name,
                    slug=report_slug,
                    config_json=json.dumps(report_config),
                    is_active=True,
                    created_by=user.get("username"),
                    created_at=datetime.utcnow(),
                )
                session.add(new_report)
                session.flush()

                for loc_id in allowed_location_ids:
                    for role in allowed_roles:
                        access = ReportAccess(
                            report_id=new_report.id,
                            role=role,
                            location_id=loc_id,
                            granted_by=user.get("username"),
                            granted_at=datetime.utcnow(),
                        )
                        session.add(access)

                # Optional: create table schema
                if create_db_table and custom_table_name:
                    from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, MetaData, String, Table
                    from db import engine

                    type_mapping = {
                        "numeric": Float,
                        "string": String(255),
                        "date": Date,
                        "datetime": DateTime,
                        "boolean": Boolean,
                    }

                    metadata = MetaData()
                    table_columns = [
                        Column("id", Integer, primary_key=True, autoincrement=True),
                        Column("location_id", Integer, nullable=True),
                        Column("created_at", DateTime, nullable=False),
                        Column("created_by", String(255), nullable=True),
                    ]
                    for col_cfg in column_configs:
                        col_type = type_mapping.get(col_cfg.get("type"), String(255))
                        table_columns.append(Column(col_cfg.get("field"), col_type, nullable=True))
                    Table(custom_table_name, metadata, *table_columns)
                    metadata.create_all(engine)

                session.commit()
                st.success(f"Report '{report_name}' created successfully.")
                st.balloons()
        except Exception as exc:  # pragma: no cover - surfaced in UI
            st.error(f"Error creating report: {exc}")


# -----------------------------------------------------------------------------
# Manage existing
# -----------------------------------------------------------------------------

def render_manage_reports(user: Dict[str, Any], active_location_id: int):
    st.markdown("### Manage Existing Reports")
    loc_labels, loc_map = _load_locations()

    filter_option = st.radio(
        "Show Reports:",
        options=["All Reports", "My Location Only", "System Reports", "Custom Reports"],
        horizontal=True,
    )

    with get_session() as session:
        query = session.query(ReportDefinition)

        if filter_option == "My Location Only":
            query = query.filter(ReportDefinition.location_id == active_location_id)
        elif filter_option == "System Reports":
            query = query.filter(ReportDefinition.created_by == "system")
        elif filter_option == "Custom Reports":
            query = query.filter(ReportDefinition.created_by != "system")

        reports = query.order_by(ReportDefinition.created_at.desc()).all()

        if filter_option == "My Location Only" and reports:
            scoped_reports = []
            for report in reports:
                include = report.location_id == active_location_id
                if not include:
                    try:
                        cfg = json.loads(report.config_json or "{}")
                    except Exception:
                        cfg = {}
                    cols = cfg.get("columns", []) or []
                    for col in cols:
                        mode = col.get("source_location_mode")
                        sid = col.get("source_location_id")
                        if mode in ["specific", "all"] and (sid == active_location_id or mode == "all"):
                            include = True
                            break
                if include:
                    scoped_reports.append(report)
            reports = scoped_reports

        if not reports:
            st.info("No reports found. Create one in the 'Create New Report' tab.")
            return

        st.caption(f"Found {len(reports)} report(s)")

        for report in reports:
            try:
                config = json.loads(report.config_json or "{}")
            except Exception:
                config = {}
            accesses = session.query(ReportAccess).filter(ReportAccess.report_id == report.id).all()

            status_badge = "Active" if report.is_active else "Inactive"
            report_type_badge = "Custom" if report.created_by != "system" else "System"

            with st.expander(f"{report.name} | {status_badge} | {report_type_badge}", expanded=False):
                info1, info2, info3 = st.columns(3)
                with info1:
                    st.write(f"**Slug:** `{report.slug}`")
                    st.write(f"**Created By:** {report.created_by}")
                with info2:
                    if report.created_at:
                        st.write(f"**Created:** {report.created_at.strftime('%Y-%m-%d %H:%M')}")
                    location_name = "All Locations" if not report.location_id else f"Location ID: {report.location_id}"
                    st.write(f"**Location:** {location_name}")
                with info3:
                    st.write(f"**Status:** {status_badge}")
                    data_source = config.get("data_source", {}).get("table", "Unknown")
                    st.write(f"**Base Table:** `{data_source}`")

                st.markdown("---")
                loc_ids_current = sorted({a.location_id for a in accesses if a.location_id})
                selected_loc_labels = [lbl for lbl, lid in loc_map.items() if lid in loc_ids_current]
                with st.expander("Location Access", expanded=False):
                    loc_selection = st.multiselect(
                        "Enabled locations",
                        options=loc_labels,
                        default=selected_loc_labels,
                        help="Reports stay hidden in Reporting unless the current location is enabled here.",
                        key=f"loc_access_{report.id}",
                    )
                    if st.button("💾", key=f"save_loc_access_{report.id}", help="Save Location Access"):
                        try:
                            new_loc_ids = {loc_map[lbl] for lbl in loc_selection if lbl in loc_map}
                            if not new_loc_ids:
                                st.warning("Select at least one location before saving.")
                                raise ValueError("No locations selected")
                            role_set = {a.role for a in accesses if a.role}
                            # Remove existing non user-specific entries, then recreate with new location scope
                            session.query(ReportAccess).filter(
                                ReportAccess.report_id == report.id,
                                ReportAccess.user_id == None  # noqa: E711
                            ).delete()
                            for loc_id in new_loc_ids:
                                if role_set:
                                    for role in role_set:
                                        session.add(
                                            ReportAccess(
                                                report_id=report.id,
                                                role=role,
                                                location_id=loc_id,
                                                granted_by=user.get("username"),
                                                granted_at=datetime.utcnow(),
                                            )
                                        )
                                else:
                                    session.add(
                                        ReportAccess(
                                            report_id=report.id,
                                            location_id=loc_id,
                                            granted_by=user.get("username"),
                                            granted_at=datetime.utcnow(),
                                        )
                                    )
                            session.commit()
                            st.success("Location access updated.")
                            st.rerun()
                        except Exception as exc:
                            session.rollback()
                            st.error(f"Could not update access: {exc}")

                st.markdown("---")
                with st.expander("View configuration JSON", expanded=False):
                    st.json(config)

                with st.expander("Edit configuration (advanced)", expanded=False):
                    cfg_text = st.text_area(
                        "Update report mapping/config JSON",
                        value=json.dumps(config, indent=2, default=str),
                        height=220,
                        key=f"cfg_edit_{report.id}",
                        help="Use this to correct mappings, joins, columns, or decimal places for this saved report.",
                    )
                    if st.button("💾", key=f"cfg_save_{report.id}", help="Save configuration"):
                        try:
                            new_cfg = json.loads(cfg_text)
                            report.config_json = json.dumps(new_cfg)
                            session.commit()
                            st.success("Configuration saved. Reload Reporting to apply changes.")
                            st.rerun()
                        except Exception as exc:
                            session.rollback()
                            st.error(f"Could not save configuration: {exc}")

                new_name = st.text_input("Rename report", value=report.name, key=f"edit_name_{report.id}")

                actions = st.columns(4)
                with actions[0]:
                    if st.button("💾", key=f"save_{report.id}", help="Save Name"):
                        report.name = new_name
                        session.commit()
                        st.success("Report updated.")
                        st.rerun()
                with actions[1]:
                    toggle_label = "Deactivate" if report.is_active else "Activate"
                    toggle_icon = "⛔" if report.is_active else "✅"
                    if st.button(toggle_icon, key=f"toggle_{report.id}", help=toggle_label):
                        report.is_active = not report.is_active
                        session.commit()
                        st.success(f"Report {toggle_label.lower()}d.")
                        st.rerun()
                with actions[2]:
                    if st.button("👁️", key=f"access_{report.id}", help="View Access"):
                        accesses = session.query(ReportAccess).filter(ReportAccess.report_id == report.id).all()
                        if accesses:
                            roles = [a.role for a in accesses if a.role]
                            st.info(f"Roles with access: {', '.join(roles)}")
                        else:
                            st.warning("No access rules defined.")
                with actions[3]:
                    delete_key = f"confirm_delete_{report.id}"
                    if delete_key not in st.session_state:
                        st.session_state[delete_key] = False
                    if not st.session_state[delete_key]:
                        if st.button("🗑️", key=f"delete_{report.id}", help="Delete"):
                            st.session_state[delete_key] = True
                            st.rerun()
                    else:
                        st.warning("Confirm deletion?")
                        d1, d2 = st.columns(2)
                        with d1:
                            if st.button("✅", key=f"confirm_yes_{report.id}", help="Yes, delete"):
                                session.query(ReportAccess).filter(ReportAccess.report_id == report.id).delete()
                                session.delete(report)
                                session.commit()
                                st.session_state[delete_key] = False
                                st.success("Report deleted.")
                                st.rerun()
                        with d2:
                            if st.button("❌", key=f"confirm_no_{report.id}", help="No, keep"):
                                st.session_state[delete_key] = False
                                st.rerun()
