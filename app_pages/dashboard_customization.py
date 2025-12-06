# dashboard_customization.py
"""
Dashboard Customization Page
Allows admins to configure dashboard layout and widgets
"""

import streamlit as st
from sqlalchemy import inspect
from db import engine
import json
from datetime import date, datetime
from dashboard_config import DashboardConfigManager, DashboardConfig
from dashboard_widgets import WidgetRenderer
from db import get_session
from location_manager import LocationManager


def _ensure_hex_color(color: str, default: str = "#000000") -> str:
    """Ensure color is a valid hex code, convert common names if needed"""
    if not color:
        return default
    
    # If already hex, return as-is
    if color.startswith("#") and len(color) in [4, 7]:
        return color
    
    # Convert common color names to hex
    color_map = {
        "white": "#ffffff",
        "black": "#000000",
        "red": "#ff0000",
        "green": "#00ff00",
        "blue": "#0000ff",
        "gray": "#808080",
        "grey": "#808080",
    }
    
    return color_map.get(color.lower(), default)


def render_dashboard_customization():
    """Render dashboard customization page"""
    
    st.title("⚙️ Dashboard Customization")
    st.markdown("Configure dashboard layout, widgets, and data mappings")
    
    # Check permissions
    user = st.session_state.get("auth_user")
    if not user or user.get("role") not in ["admin", "super-admin", "admin-operations"]:
        st.error("🚫 Access Denied.  Only administrators can customize dashboards.")
        return
    
    with get_session() as session:
        locations = LocationManager.get_all_locations(session, active_only=True)
    if not locations:
        st.warning("⚠️ No active locations available")
        return

    labels = [f"{getattr(l, 'name', 'Location')} ({getattr(l, 'code', '')})" for l in locations]
    id_by_label = {labels[i]: locations[i].id for i in range(len(locations))}
    default_label = labels[0]

    current_location_id = st.session_state.get("active_location_id") or locations[0].id
    current_label = next((lbl for lbl, lid in id_by_label.items() if lid == current_location_id), default_label)

    st.markdown("#### Select Location for Customization")
    selected_label = st.selectbox(
        "Location",
        labels,
        index=labels.index(current_label) if current_label in labels else labels.index(default_label),
        help="Changes are saved per location and do not affect others.",
        key="dc_location_selector"
    )
    location_id = id_by_label[selected_label]

    prev_key = "__prev_active_location_id_dc"
    prev_id = st.session_state.get(prev_key)
    st.session_state["active_location_id"] = location_id
    if prev_id != location_id:
        st.session_state[prev_key] = location_id
        st.session_state.dashboard_config = DashboardConfigManager.load_config(location_id)
        st.rerun()
    
    # Tabs for different customization sections
    tabs = st.tabs([
        "📋 Overview",
        "📊 Summary Cards",
        "🛢️ Tank Visuals",
        "📅 Monthly Data",
        "📈 Charts & Trends",
        "🚢 Convoy Status",
        "🗂️ Sections Manager",
        "🎨 Styles",
        "💾 Save & Load",
        "🖨️ PDF Export",
        "📄 PDF Customization"
    ])
    
    # Load current configuration
    if "dashboard_config" not in st.session_state:
        st.session_state.dashboard_config = DashboardConfigManager.load_config(location_id)
    
    config = st.session_state.dashboard_config
    
    # Tab 0: Overview
    with tabs[0]:
        render_overview_tab(config, location_id)
    
    # Tab 1: Summary Cards
    with tabs[1]:
        render_summary_cards_tab(config)
        st.markdown("---")
        if st.button("💾", key="save_cards", type="primary", help="Save Configuration"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")
    
    # Tab 2: Tank Visuals
    with tabs[2]:
        render_tank_visuals_tab(config)
        st.markdown("---")
        if st.button("💾", key="save_tanks", type="primary", help="Save Configuration"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")
    
    # Tab 3: Monthly Data
    with tabs[3]:
        render_monthly_data_tab(config)
        st.markdown("---")
        if st.button("💾", key="save_monthly", type="primary", help="Save Configuration"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")

    # Tab 4: Charts & Trends
    with tabs[4]:
        render_charts_tab(config)
        st.markdown("---")
        if st.button("💾", key="save_charts", type="primary", help="Save Configuration"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")
    
    # Tab 5: Convoy Status
    with tabs[5]:
        render_convoy_status_tab(config, location_id)
        st.markdown("---")
        if st.button("💾", key="save_convoy", type="primary", help="Save Configuration"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")

    # Tab 6: Sections Manager
    with tabs[6]:
        render_sections_manager_tab(config)
        st.markdown("---")
        if st.button("💾", key="save_sections", type="primary", help="Save Configuration"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")
    
    # Tab 7: Styles
    with tabs[7]:
        render_styles_tab(config)
        st.markdown("---")
        if st.button("💾", key="save_styles", type="primary", help="Save Configuration"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")
    
    # Tab 8: Save & Load
    with tabs[8]:
        render_save_load_tab(config, location_id, user)

    # Tab 9: PDF Export
    with tabs[9]:
        st.markdown("### PDF Export Configuration")
        pdf_cfg = config.setdefault("pdf_export", {})
        enabled = pdf_cfg.setdefault("enabled_sections", {})
        sections = config.get("sections", [])
        for sec in sections:
            sid = sec.get("id")
            sname = sec.get("name") or sid
            cur = bool(enabled.get(sid, sec.get("enabled", True)))
            enabled[sid] = st.toggle(f"Include: {sname}", value=cur, key=f"pdf_inc_{sid}")
        st.markdown("---")
        if st.button("💾", key="save_pdf", type="primary", help="Save Configuration"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")
    
    # Tab 10: PDF Customization
    with tabs[10]:
        render_pdf_customization_tab(config, location_id, user)

def render_monthly_data_tab(config: dict):
    """Render monthly data configuration tab"""
    st.markdown("### Monthly Data Configuration")
    layout = config.setdefault("layout", {}).setdefault("monthly_data", {})
    section_list = config.setdefault("sections", [])
    # ensure section exists
    found = False
    for s in section_list:
        if s.get("id") == "monthly_data":
            found = True
            section = s
            break
    if not found:
        section = {
            "id": "monthly_data",
            "name": "Monthly Data",
            "type": "monthly_data",
            "enabled": True,
            "order": 3,
            "date_filter": {"enabled": True, "type": "month", "label": "Month"}
        }
        section_list.append(section)

    col1, col2 = st.columns(2)
    with col1:
        section["enabled"] = st.toggle("Enable Monthly Data Section", value=bool(section.get("enabled", True)))
        layout["enabled"] = section["enabled"]
        layout["columns"] = st.number_input("Number of Columns", min_value=1, max_value=6, value=int(layout.get("columns", 4) or 4))
    with col2:
        st.caption("Configure visuals like cards, line/area/bar charts, pie/doughnut charts")

    st.markdown("---")
    st.markdown("### Monthly Visuals")
    visuals = layout.setdefault("cards", [])

    if st.button("➕", help="Add Visual"):
        visuals.append({
            "name": "New Visual",
            "type": "card",
            "data_source": "material_balance",
            "field": "Receipt",
            "aggregation": "sum",
            "unit": "bbls",
            "color": "#667eea",
            "show_labels": True,
            "show_markers": True,
            "show_average": False
        })

    for idx, v in enumerate(visuals):
        with st.expander(f"Visual {idx + 1}: {v.get('name','Visual')}", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                v["name"] = st.text_input("Title", value=v.get("name", "Visual"), key=f"md_name_{idx}")
                vtype_options = ["card", "line", "area", "bar", "pie", "doughnut"]
                if v.get("type") not in vtype_options:
                    v["type"] = "card"
                v["type"] = st.selectbox("Visual Type", options=vtype_options, index=vtype_options.index(v.get("type", "card")), key=f"md_type_{idx}")
                ds_opts = ["material_balance", "fso_operations", "table", "manual"]
                try:
                    ds_idx = ds_opts.index(v.get("data_source", "material_balance"))
                except Exception:
                    ds_idx = 0
                v["data_source"] = st.selectbox("Data Source", options=ds_opts, index=ds_idx, key=f"md_ds_{idx}")
                v["aggregation"] = st.selectbox("Aggregation", options=["sum", "avg", "min", "max"], index=["sum", "avg", "min", "max"].index(v.get("aggregation", "sum")), key=f"md_agg_{idx}")
                v["unit"] = st.text_input("Unit", value=v.get("unit", ""), key=f"md_unit_{idx}")
                v["color"] = st.color_picker("Color", value=_ensure_hex_color(v.get("color", "#667eea"), "#667eea"), key=f"md_color_{idx}")
            with col2:
                if v.get("data_source") == "table":
                    insp = inspect(engine)
                    tables = sorted(insp.get_table_names())
                    v["table_name"] = st.selectbox("Table", options=tables or [""], index=max(0, (tables or [""]).index(v.get("table_name")) if v.get("table_name") in (tables or []) else 0), key=f"md_tbl_{idx}")
                    cols = [c.get("name") for c in insp.get_columns(v.get("table_name"))] if v.get("table_name") else []
                    v["field"] = st.selectbox("Value Field", options=cols or [""], index=max(0, (cols or [""]).index(v.get("field")) if v.get("field") in (cols or []) else 0), key=f"md_val_{idx}")
                    if v.get("type") in ("pie", "doughnut"):
                        v["group_field"] = st.selectbox("Group Field", options=cols or [""], index=max(0, (cols or [""]).index(v.get("group_field")) if v.get("group_field") in (cols or []) else 0), key=f"md_grp_{idx}")
                        default_palette = v.get("palette", ["#667eea","#06b6d4","#22c55e","#f59e0b","#ef4444","#8b5cf6"])
                        default_palette_str = ",".join(default_palette if isinstance(default_palette, list) else [str(default_palette)])
                        pal_str = st.text_input("Palette (comma colors)", value=default_palette_str, key=f"md_pal_{idx}")
                        v["palette"] = [c.strip() for c in pal_str.split(",") if c.strip()]
                    st.markdown("**Filters**")
                    criteria = v.setdefault("criteria", [])
                    if st.button("➕", key=f"md_add_filter_{idx}", help="Add Filter"):
                        criteria.append({"column": (cols or [""])[0] if cols else "", "operator": "equals", "value": ""})
                    for c_i, crit in enumerate(list(criteria)):
                        fc1, fc2, fc3, fc4 = st.columns([1.6, 1.2, 1.6, 0.6])
                        with fc1:
                            crit["column"] = st.selectbox("Column", options=cols or [""], index=max(0, (cols or [""]).index(crit.get("column")) if crit.get("column") in (cols or []) else 0), key=f"md_crit_col_{idx}_{c_i}")
                        with fc2:
                            crit["operator"] = st.selectbox("Operator", options=["equals", "not_equals", "contains", "starts_with", "ends_with", "greater_than", "less_than", "greater_equal", "less_equal"], index=["equals", "not_equals", "contains", "starts_with", "ends_with", "greater_than", "less_than", "greater_equal", "less_equal"].index(crit.get("operator", "equals")), key=f"md_crit_op_{idx}_{c_i}")
                        with fc3:
                            crit["value"] = st.text_input("Value", value=str(crit.get("value", "")), key=f"md_crit_val_{idx}_{c_i}")
                        with fc4:
                            if st.button("🗑️", key=f"md_crit_del_{idx}_{c_i}"):
                                criteria.pop(c_i)
                                st.rerun()
                else:
                    v["field"] = st.text_input("Field Name", value=v.get("field", "Receipt"), key=f"md_field_{idx}")
                v["show_labels"] = st.checkbox("Show Labels", value=bool(v.get("show_labels", True)), key=f"md_labels_{idx}")
                v["show_markers"] = st.checkbox("Show Markers (for line)", value=bool(v.get("show_markers", True)), key=f"md_markers_{idx}")
                if v.get("type", "card") == "card":
                    v["show_average"] = st.checkbox(
                        "Show average (selected month)",
                        value=bool(v.get("show_average", False)),
                        help="Displays the average for the selected month under the main value. For the current month, averages stop at today.",
                        key=f"md_avg_{idx}"
                    )
                if v.get("type") in ("doughnut", "pie"):
                    v["inner_radius"] = st.number_input("Inner Radius (donut)", min_value=0, max_value=120, value=int(v.get("inner_radius", 60)), key=f"md_inner_{idx}")
                v["height"] = st.number_input("Chart/Card Height", min_value=180, max_value=600, value=int(v.get("height", 280)), key=f"md_h_{idx}")
            if st.button(f"🗑️ Delete Visual {idx + 1}", key=f"md_del_{idx}"):
                visuals.pop(idx)
                st.rerun()

def render_convoy_status_tab(config: dict, location_id: int):
    st.markdown("### Convoy Status Display Settings")
    st.caption("Configure how saved Convoy Status entries appear on the dashboard for this location.")

    layout_cfg = config.setdefault("layout", {}).setdefault("convoy_status", {})
    section_list = config.setdefault("sections", [])
    # ensure section exists
    found = False
    for s in section_list:
        if s.get("id") == "convoy_status":
            found = True
            section = s
            break
    if not found:
        section = {
            "id": "convoy_status",
            "name": "Convoy Status",
            "type": "convoy_status",
            "enabled": True,
            "order": 5,
            "date_filter": {"enabled": True, "type": "single", "label": "Convoy Date"}
        }
        section_list.append(section)

    col1, col2 = st.columns(2)
    with col1:
        section["enabled"] = st.toggle("Enable Convoy Status Section", value=bool(section.get("enabled", True)))
        layout_cfg["enabled"] = section["enabled"]
        layout_cfg["show_yade"] = st.checkbox("Show YADE convoys", value=bool(layout_cfg.get("show_yade", True)))
        layout_cfg["show_vessel"] = st.checkbox("Show Vessel convoys", value=bool(layout_cfg.get("show_vessel", True)))
    with col2:
        layout_cfg["display_mode"] = st.selectbox("Display Mode", ["table", "cards"], index=(0 if layout_cfg.get("display_mode") != "cards" else 1))

    st.markdown("#### Status Filters")
    from db import get_session
    from models import ConvoyStatusYade, ConvoyStatusVessel
    with get_session() as s:
        y_statuses = [r[0] for r in s.query(ConvoyStatusYade.status).filter(ConvoyStatusYade.location_id == location_id).distinct().all()]
        v_statuses = [r[0] for r in s.query(ConvoyStatusVessel.status).filter(ConvoyStatusVessel.location_id == location_id).distinct().all()]
    options = sorted(set((y_statuses or []) + (v_statuses or [])))
    layout_cfg["status_filters"] = st.multiselect("Statuses to include", options=options, default=layout_cfg.get("status_filters", []))

    st.info("Saved Convoy Status entries (from Convoy Status page) will be displayed on the dashboard according to these settings.")


def render_overview_tab(config: dict, location_id: int):
    """Render overview tab"""
    st.markdown("### Dashboard Configuration Overview")
    
    # Page Header Customization
    st.markdown("#### 🏷️ Page Header Settings")
    
    if "page_header" not in config:
        config["page_header"] = {
            "title": "{location_name} Dashboard",
            "subtitle": "Management Information System",
            "show_welcome": True,
            "show_datetime": True,
            "background_gradient_start": "#667eea",
            "background_gradient_end": "#764ba2"
        }
    
    header_cfg = config["page_header"]
    
    col1, col2 = st.columns(2)
    
    with col1:
        header_cfg["title"] = st.text_input(
            "Page Title",
            value=header_cfg.get("title", "{location_name} Dashboard"),
            help="Use {location_name} to insert location name dynamically"
        )
        
        header_cfg["subtitle"] = st.text_input(
            "Subtitle",
            value=header_cfg.get("subtitle", "Management Information System")
        )
    
    with col2:
        header_cfg["show_welcome"] = st.toggle(
            "Show Welcome Message",
            value=header_cfg.get("show_welcome", True)
        )
        
        header_cfg["show_datetime"] = st.toggle(
            "Show Date & Time",
            value=header_cfg.get("show_datetime", True)
        )
    
    st.markdown("**Header Background Colors**")
    col1, col2 = st.columns(2)
    
    with col1:
        header_cfg["background_gradient_start"] = st.color_picker(
            "Gradient Start Color",
            value=_ensure_hex_color(header_cfg.get("background_gradient_start", "#667eea"), "#667eea")
        )
    
    with col2:
        header_cfg["background_gradient_end"] = st.color_picker(
            "Gradient End Color",
            value=_ensure_hex_color(header_cfg.get("background_gradient_end", "#764ba2"), "#764ba2")
        )
    
    st.markdown("---")
    
    # Configuration metrics
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Location ID", location_id)
        st.metric("Summary Cards", len(config["layout"]["summary_cards"]["cards"]))
        st.metric("Tank Visuals Enabled", "Yes" if config["layout"]["tank_visuals"]["enabled"] else "No")
    
    with col2:
        st.metric("Monthly Data Cards", len(config["layout"]["monthly_data"]["cards"]))
        st.metric("Trend Series", len(config["layout"]["trend_chart"]["series"]))
        st.metric("Chart Type", config["layout"]["trend_chart"]["chart_type"])
    
    st.markdown("---")
    
    # Quick toggles
    st.markdown("### Quick Settings")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        summary_enabled = st.checkbox(
            "Enable Summary Cards",
            value=config["layout"]["summary_cards"]["enabled"],
            key="quick_summary_enabled"
        )
        config["layout"]["summary_cards"]["enabled"] = summary_enabled
    
    with col2:
        tank_enabled = st.checkbox(
            "Enable Tank Visuals",
            value=config["layout"]["tank_visuals"]["enabled"],
            key="quick_tank_enabled"
        )
        config["layout"]["tank_visuals"]["enabled"] = tank_enabled
    
    with col3:
        trend_enabled = st.checkbox(
            "Enable Trend Chart",
            value=config["layout"]["trend_chart"]["enabled"],
            key="quick_trend_enabled"
        )
        config["layout"]["trend_chart"]["enabled"] = trend_enabled
    
    # Preview button
    if st.button("🔍", type="primary", help="Preview Dashboard"):
        st.info("Preview will be shown in the Home page")


def render_summary_cards_tab(config: dict):
    """Render summary cards configuration tab"""
    st.markdown("### Summary Cards Configuration")
    
    # Global settings
    col1, col2 = st. columns(2)
    
    with col1:
        enabled = st.checkbox(
            "Enable Summary Cards Section",
            value=config["layout"]["summary_cards"]["enabled"]
        )
        config["layout"]["summary_cards"]["enabled"] = enabled
    
    with col2:
        num_columns = st.number_input(
            "Number of Columns",
            min_value=1,
            max_value=12,
            value=config["layout"]["summary_cards"]["columns"]
        )
        config["layout"]["summary_cards"]["columns"] = num_columns
    
    st.markdown("---")
    
    # Card configuration
    st.markdown("### Configure Individual Cards")
    
    cards = config["layout"]["summary_cards"]["cards"]
    
    # Add new card button
    if st.button("➕", help="Add New Card"):
        cards.append({
            "name": "New Card",
            "data_source": "material_balance",
            "field": "Receipt",
            "unit": "bbls",
            "color": "#667eea",
            "show_delta": False
        })
    
    # Edit existing cards
    for idx, card in enumerate(cards):
        with st.expander(f"Card {idx + 1}: {card['name']}", expanded=False):
            col1, col2 = st. columns(2)
            
            with col1:
                card["name"] = st.text_input(
                    "Card Name",
                    value=card["name"],
                    key=f"card_name_{idx}"
                )
                
                ds_opts = ["material_balance", "fso_operations", "calculated", "manual", "table"]
                try:
                    ds_idx = ds_opts.index(card.get("data_source", "material_balance"))
                except Exception:
                    ds_idx = 0
                card["data_source"] = st.selectbox(
                    "Data Source",
                    options=ds_opts,
                    index=ds_idx,
                    key=f"card_source_{idx}"
                )
                
                if card["data_source"] == "material_balance":
                    opts = ["Receipt", "Dispatch", "Closing Stock", "Opening Stock"]
                    try:
                        cur_idx = opts.index(card.get("field", "Receipt"))
                    except Exception:
                        cur_idx = 0
                    card["field"] = st.selectbox(
                        "Field",
                        options=opts,
                        index=cur_idx,
                        key=f"card_field_{idx}"
                    )
                elif card["data_source"] == "calculated":
                    card["calculation"] = st.selectbox(
                        "Calculation",
                        options=["ullage", "pumpable"],
                        index=["ullage", "pumpable"].index(
                            card.get("calculation", "ullage")
                        ),
                        key=f"card_calc_{idx}"
                    )
                elif card["data_source"] == "table":
                    insp = inspect(engine)
                    tables = sorted(insp.get_table_names())
                    if tables:
                        card["table_name"] = st.selectbox(
                            "Table",
                            options=tables,
                            index=max(0, tables.index(card.get("table_name")) if card.get("table_name") in tables else 0),
                            key=f"card_table_{idx}"
                        )
                        cols = [c.get("name") for c in insp.get_columns(card["table_name"])]
                        card["field"] = st.selectbox(
                            "Field",
                            options=cols or [""],
                            index=max(0, (cols or [""]).index(card.get("field")) if card.get("field") in (cols or []) else 0),
                            key=f"card_field_{idx}"
                        )
                        st.markdown("**Filters**")
                        criteria = card.setdefault("criteria", [])
                        if st.button("➕", key=f"card_add_filter_{idx}", help="Add Filter"):
                            criteria.append({"column": (cols or [""])[0] if cols else "", "operator": "equals", "value": ""})
                        for c_i, crit in enumerate(list(criteria)):
                            fc1, fc2, fc3, fc4 = st.columns([1.6, 1.2, 1.6, 0.6])
                            with fc1:
                                crit["column"] = st.selectbox("Column", options=cols or [""], index=max(0, (cols or [""]).index(crit.get("column")) if crit.get("column") in (cols or []) else 0), key=f"card_crit_col_{idx}_{c_i}")
                            with fc2:
                                crit["operator"] = st.selectbox("Operator", options=["equals", "not_equals", "contains", "starts_with", "ends_with", "greater_than", "less_than", "greater_equal", "less_equal"], index=["equals", "not_equals", "contains", "starts_with", "ends_with", "greater_than", "less_than", "greater_equal", "less_equal"].index(crit.get("operator", "equals")), key=f"card_crit_op_{idx}_{c_i}")
                            with fc3:
                                crit["value"] = st.text_input("Value", value=str(crit.get("value", "")), key=f"card_crit_val_{idx}_{c_i}")
                            with fc4:
                                if st.button("🗑️", key=f"card_crit_del_{idx}_{c_i}"):
                                    criteria.pop(c_i)
                                    st.rerun()
            
            with col2:
                card["unit"] = st.text_input(
                    "Unit",
                    value=card.get("unit", "bbls"),
                    key=f"card_unit_{idx}"
                )
                
                card["color"] = st.color_picker(
                    "Color",
                    value=card.get("color", "#667eea"),
                    key=f"card_color_{idx}"
                )
                
                card["show_delta"] = st.checkbox(
                    "Show Change from Previous Day",
                    value=card. get("show_delta", False),
                    key=f"card_delta_{idx}"
                )

            st.markdown("**Sub-Data (optional)**")
            sub_enabled = bool(card.get("sub_enabled", False))
            card["sub_enabled"] = st.toggle(
                "Enable Sub-Data",
                value=sub_enabled,
                key=f"card_sub_enabled_{idx}"
            )
            if card["sub_enabled"]:
                sub_col1, sub_col2 = st.columns(2)
                with sub_col1:
                    sub_ds_opts = ["table"]
                    try:
                        sub_ds_idx = sub_ds_opts.index(card.get("sub_data_source", "table"))
                    except Exception:
                        sub_ds_idx = 0
                    card["sub_data_source"] = st.selectbox(
                        "Sub-Data Source",
                        options=sub_ds_opts,
                        index=sub_ds_idx,
                        key=f"card_sub_source_{idx}"
                    )
                    card["sub_label"] = st.text_input(
                        "Sub-Data Label",
                        value=card.get("sub_label", ""),
                        key=f"card_sub_label_{idx}"
                    )
                with sub_col2:
                    if card.get("sub_data_source") == "table":
                        insp = inspect(engine)
                        tables = sorted(insp.get_table_names())
                        card["sub_table_name"] = st.selectbox(
                            "Sub-Data Table",
                            options=tables or [""],
                            index=max(0, (tables or [""]).index(card.get("sub_table_name")) if card.get("sub_table_name") in (tables or []) else 0),
                            key=f"card_sub_table_{idx}"
                        )
                        cols = [c.get("name") for c in insp.get_columns(card.get("sub_table_name"))] if card.get("sub_table_name") else []
                        card["sub_field"] = st.selectbox(
                            "Sub-Data Field",
                            options=cols or [""],
                            index=max(0, (cols or [""]).index(card.get("sub_field")) if card.get("sub_field") in (cols or []) else 0),
                            key=f"card_sub_field_{idx}"
                        )
                        st.markdown("Sub-Data Filters")
                        sub_criteria = card.setdefault("sub_criteria", [])
                        if st.button("➕", key=f"card_add_sub_filter_{idx}", help="Add Sub-Filter"):
                            sub_criteria.append({"column": (cols or [""])[0] if cols else "", "operator": "equals", "value": ""})
                        for c_i, crit in enumerate(list(sub_criteria)):
                            fc1, fc2, fc3, fc4 = st.columns([1.6, 1.2, 1.6, 0.6])
                            with fc1:
                                crit["column"] = st.selectbox("Column", options=cols or [""], index=max(0, (cols or [""]).index(crit.get("column")) if crit.get("column") in (cols or []) else 0), key=f"card_sub_crit_col_{idx}_{c_i}")
                            with fc2:
                                crit["operator"] = st.selectbox("Operator", options=["equals", "not_equals", "contains", "starts_with", "ends_with", "greater_than", "less_than", "greater_equal", "less_equal"], index=["equals", "not_equals", "contains", "starts_with", "ends_with", "greater_than", "less_than", "greater_equal", "less_equal"].index(crit.get("operator", "equals")), key=f"card_sub_crit_op_{idx}_{c_i}")
                            with fc3:
                                crit["value"] = st.text_input("Value", value=str(crit.get("value", "")), key=f"card_sub_crit_val_{idx}_{c_i}")
                            with fc4:
                                if st.button("🗑️", key=f"card_sub_crit_del_{idx}_{c_i}"):
                                    sub_criteria.pop(c_i)
                                    st.rerun()
            
            # Delete button
            if st.button(f"🗑️ Delete Card {idx + 1}", key=f"delete_card_{idx}"):
                cards.pop(idx)
                st.rerun()


def render_tank_visuals_tab(config: dict):
    """Render tank visuals configuration tab"""
    st.markdown("### Tank Visuals Configuration")
    
    col1, col2 = st.columns(2)
    
    with col1:
        enabled = st.toggle(
            "Enable Tank Visuals Section",
            value=config["layout"]["tank_visuals"]["enabled"]
        )
        config["layout"]["tank_visuals"]["enabled"] = enabled
        
        num_columns = st.number_input(
            "Tanks Per Row",
            min_value=1,
            max_value=10,
            value=config["layout"]["tank_visuals"]["columns"]
        )
        config["layout"]["tank_visuals"]["columns"] = num_columns
    
    with col2:
        style = config["layout"]["tank_visuals"]["style"]
        
        style["height"] = st.number_input(
            "Tank Visual Height (px)",
            min_value=100,
            max_value=400,
            value=style.get("height", 200)
        )
        
        style["border_radius"] = st.number_input(
            "Border Radius (px)",
            min_value=0,
            max_value=50,
            value=style.get("border_radius", 10)
        )
    
    st.markdown("### Display Options")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        style["show_status"] = st.checkbox(
            "Show Tank Status",
            value=style.get("show_status", True)
        )
    
    with col2:
        style["show_percentage"] = st.checkbox(
            "Show Fill Percentage",
            value=style.get("show_percentage", True)
        )
    
    with col3:
        style["color_scheme"] = st.selectbox(
            "Color Scheme",
            options=["dynamic", "static"],
            index=["dynamic", "static"].index(style.get("color_scheme", "dynamic"))
        )
    
    st.markdown("---")
    st.markdown("### 🎛️ Tank Status Dropdown")
    
    status_dropdown_enabled = config["layout"]["tank_visuals"].get("status_dropdown_enabled", False)
    config["layout"]["tank_visuals"]["status_dropdown_enabled"] = st.toggle(
        "Enable Tank Status Dropdown",
        value=status_dropdown_enabled,
        help="Allow operators to change tank status directly from the dashboard",
        key="status_dropdown_toggle"
    )
    
    st.caption("When enabled, operators can select tank status from: Idle, Receiving, Dispatching, Maintenance, Settling, Draining")
    
    st.markdown("---")
    st.markdown("### 🚦 Pumpable Stock Configuration")
    
    if "pumpable_config" not in config["layout"]["tank_visuals"]:
        config["layout"]["tank_visuals"]["pumpable_config"] = {
            "enabled": True,
            "pumpable_statuses": ["IDLE", "READY", "DISPATCHING"],
            "pumpable_factor": 0.85
        }
    
    pumpable_cfg = config["layout"]["tank_visuals"]["pumpable_config"]
    
    col1, col2 = st.columns(2)
    
    with col1:
        pumpable_cfg["enabled"] = st.toggle(
            "Enable Pumpable Stock Calculation",
            value=pumpable_cfg.get("enabled", True)
        )
        
        pumpable_cfg["pumpable_factor"] = st.number_input(
            "Pumpable Factor (multiply by)",
            min_value=0.0,
            max_value=1.0,
            value=pumpable_cfg.get("pumpable_factor", 0.85),
            step=0.05,
            help="Multiply tank stock by this factor for pumpable calculation (e.g., 0.85 = 85%)"
        )
    
    with col2:
        st.markdown("**Pumpable Tank Statuses**")
        st.caption("Select which tank statuses should be considered as pumpable")
        
        all_statuses = ["IDLE", "READY", "DISPATCHING", "RECEIVING", "SETTLING", "MAINTENANCE", "DRAINING"]
        current_pumpable = pumpable_cfg.get("pumpable_statuses", ["IDLE", "READY", "DISPATCHING"])
        
        selected_statuses = st.multiselect(
            "Pumpable Statuses",
            options=all_statuses,
            default=current_pumpable,
            help="Tanks with these statuses will be included in pumpable stock calculation"
        )
        pumpable_cfg["pumpable_statuses"] = selected_statuses
    
    st.markdown("---")
    st.markdown("### 🛢️ Tank Visuals Mapping")
    st.markdown("Configure which tanks to display and their order on the dashboard")
    
    # Get location tanks
    location_id = st.session_state.get("active_location_id")
    if location_id:
        with get_session() as s:
            from models import Tank
            all_tanks = s.query(Tank).filter(
                Tank.location_id == location_id
            ).order_by(Tank.name).all()
            
            if all_tanks:
                # Initialize tanks list if not exists
                if "tanks" not in config["layout"]["tank_visuals"]:
                    config["layout"]["tank_visuals"]["tanks"] = []
                
                tank_list = config["layout"]["tank_visuals"]["tanks"]
                
                # Clean up tank_list - ensure all items are dicts, not strings
                tank_list = [t for t in tank_list if isinstance(t, dict)]
                config["layout"]["tank_visuals"]["tanks"] = tank_list
                
                # Display configured tanks
                st.markdown("#### Configured Tanks")
                
                for idx, tank_cfg in enumerate(tank_list):
                    with st.container(border=True):
                        col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
                        
                        # Find tank object
                        tank_obj = next((t for t in all_tanks if t.id == tank_cfg.get("tank_id")), None)
                        
                        with col1:
                            tank_options = {t.id: f"{t.name} ({t.product})" for t in all_tanks}
                            selected_tank_id = st.selectbox(
                                "Tank",
                                options=list(tank_options.keys()),
                                format_func=lambda x: tank_options[x],
                                index=list(tank_options.keys()).index(tank_cfg.get("tank_id")) if tank_cfg.get("tank_id") in tank_options else 0,
                                key=f"tank_select_{idx}"
                            )
                            tank_cfg["tank_id"] = selected_tank_id
                        
                        with col2:
                            tank_cfg["display_name"] = st.text_input(
                                "Display Name",
                                value=tank_cfg.get("display_name", tank_obj.name if tank_obj else ""),
                                key=f"tank_name_{idx}"
                            )
                        
                        with col3:
                            data_source_options = [
                                "tank_transaction",
                                "otr",
                                "material_balance",
                                "manual"
                            ]
                            tank_cfg["data_source"] = st.selectbox(
                                "Data Source",
                                options=data_source_options,
                                index=data_source_options.index(tank_cfg.get("data_source", "otr")),
                                key=f"tank_datasource_{idx}"
                            )
                        
                        with col4:
                            # Field options based on data source
                            if tank_cfg["data_source"] == "otr":
                                field_options = ["nsv_bbl", "gsv_bbl", "volume_bbl"]
                            elif tank_cfg["data_source"] == "tank_transaction":
                                field_options = ["closing_stock", "opening_stock", "received", "dispatched"]
                            elif tank_cfg["data_source"] == "material_balance":
                                field_options = ["closing_stock", "opening_stock", "receipt", "dispatch"]
                            else:
                                field_options = ["manual_value"]
                            
                            current_field = tank_cfg.get("field", field_options[0])
                            if current_field not in field_options:
                                current_field = field_options[0]
                            
                            tank_cfg["field"] = st.selectbox(
                                "Field",
                                options=field_options,
                                index=field_options.index(current_field),
                                key=f"tank_field_{idx}"
                            )
                        
                        with col5:
                            tank_cfg["enabled"] = st.toggle(
                                "Show",
                                value=tank_cfg.get("enabled", True),
                                key=f"tank_enabled_{idx}"
                            )
                            if st.button("🗑️", key=f"delete_tank_{idx}"):
                                tank_list.pop(idx)
                                st.rerun()
                
                # Add new tank button
                if st.button("➕", type="secondary", help="Add Tank Visual"):
                    tank_list.append({
                        "tank_id": all_tanks[0].id if all_tanks else None,
                        "display_name": all_tanks[0].name if all_tanks else "",
                        "enabled": True,
                        "data_source": "otr",
                        "field": "nsv_bbl"
                    })
                    st.rerun()
            else:
                st.info("ℹ️ No tanks found for this location. Add tanks in Asset Management.")
    else:
        st.warning("⚠️ Please select a location first")


def render_sections_manager_tab(config: dict):
    """Render sections manager tab"""
    st.markdown("### 🗂️ Dashboard Sections Manager")
    st.markdown("Add, remove, reorder, and configure dashboard sections")
    
    # Initialize sections if not exists
    if "sections" not in config:
        config["sections"] = [
            {
                "id": "summary_cards",
                "name": "Summary Statistics",
                "type": "summary_cards",
                "enabled": True,
                "order": 1,
                "date_filter": {
                    "enabled": True,
                    "type": "single",
                    "label": "Dashboard Date"
                }
            },
            {
                "id": "tank_visuals",
                "name": "Tank Stock Levels",
                "type": "tank_visuals",
                "enabled": True,
                "order": 2,
                "date_filter": {
                    "enabled": True,
                    "type": "single",
                    "label": "As of Date"
                }
            },
            {
                "id": "monthly_data",
                "name": "Monthly Data",
                "type": "monthly_data",
                "enabled": True,
                "order": 3,
                "date_filter": {
                    "enabled": True,
                    "type": "month",
                    "label": "Month"
                }
            },
            {
                "id": "trend_chart",
                "name": "Production & Evacuation Trend",
                "type": "trend_chart",
                "enabled": True,
                "order": 4,
                "date_filter": {
                    "enabled": True,
                    "type": "range",
                    "label": "Date Range",
                    "default_days": 30
                }
            }
        ]
    
    sections = config["sections"]
    
    # Sort sections by order
    sections.sort(key=lambda x: x.get("order", 999))
    
    st.markdown("#### Configured Sections")
    
    for idx, section in enumerate(sections):
        with st.container(border=True):
            col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 1, 1, 1, 1])
            
            with col1:
                section["name"] = st.text_input(
                    "Section Name",
                    value=section.get("name", ""),
                    key=f"section_name_{idx}"
                )
            
            with col2:
                section_types = ["summary_cards", "tank_visuals", "monthly_data", "trend_chart", "custom"]
                current_type = section.get("type", "custom")
                if current_type not in section_types:
                    section_types.append(current_type)
                
                section["type"] = st.selectbox(
                    "Section Type",
                    options=section_types,
                    index=section_types.index(current_type),
                    key=f"section_type_{idx}"
                )
            
            with col3:
                section["order"] = st.number_input(
                    "Order",
                    min_value=1,
                    max_value=20,
                    value=section.get("order", idx + 1),
                    key=f"section_order_{idx}"
                )
            
            with col4:
                section["enabled"] = st.toggle(
                    "Enabled",
                    value=section.get("enabled", True),
                    key=f"section_enabled_{idx}"
                )
            
            with col5:
                if st.button("⬆️", key=f"section_up_{idx}", disabled=(idx == 0)):
                    if idx > 0:
                        sections[idx]["order"], sections[idx-1]["order"] = sections[idx-1]["order"], sections[idx]["order"]
                        st.rerun()
            
            with col6:
                if st.button("🗑️", key=f"section_delete_{idx}"):
                    sections.pop(idx)
                    st.rerun()
            
            # Date Filter Configuration
            with st.expander("📅 Date Filter Settings"):
                if "date_filter" not in section:
                    section["date_filter"] = {
                        "enabled": True,
                        "type": "single",
                        "label": "Date"
                    }
                
                date_filter = section["date_filter"]
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    date_filter["enabled"] = st.toggle(
                        "Enable Date Filter",
                        value=date_filter.get("enabled", True),
                        key=f"date_filter_enabled_{idx}"
                    )
                
                with col2:
                    filter_types = ["single", "range", "month", "year", "none"]
                    date_filter["type"] = st.selectbox(
                        "Filter Type",
                        options=filter_types,
                        index=filter_types.index(date_filter.get("type", "single")),
                        key=f"date_filter_type_{idx}"
                    )
                
                with col3:
                    date_filter["label"] = st.text_input(
                        "Filter Label",
                        value=date_filter.get("label", "Date"),
                        key=f"date_filter_label_{idx}"
                    )
                
                if date_filter["type"] == "range":
                    date_filter["default_days"] = st.number_input(
                        "Default Days Range",
                        min_value=1,
                        max_value=365,
                        value=date_filter.get("default_days", 30),
                        key=f"date_filter_days_{idx}"
                    )
    
    st.markdown("---")
    
    # Add new section
    if st.button("➕", type="secondary", help="Add New Section"):
        new_order = max([s.get("order", 0) for s in sections]) + 1 if sections else 1
        sections.append({
            "id": f"custom_{len(sections)}",
            "name": "New Section",
            "type": "custom",
            "enabled": True,
            "order": new_order,
            "date_filter": {
                "enabled": True,
                "type": "single",
                "label": "Date"
            }
        })
        st.rerun()
    
    # Available section types info
    with st.expander("ℹ️ Section Types Info"):
        st.markdown("""
        **Available Section Types:**
        - **summary_cards**: Display summary statistics cards
        - **tank_visuals**: Show tank stock levels with 3D visuals
        - **monthly_data**: Monthly aggregated data cards
        - **trend_chart**: Line/bar charts for trends
        - **custom**: Custom section (requires manual implementation)
        
        **Date Filter Types:**
        - **single**: Single date picker
        - **range**: Date range picker (start and end date)
        - **month**: Month picker
        - **year**: Year picker
        - **none**: No date filter
        """)


def render_charts_tab(config: dict):
    """Render charts configuration tab"""
    st. markdown("### Charts & Trends Configuration")
    
    col1, col2 = st.columns(2)
    
    with col1:
        enabled = st. checkbox(
            "Enable Trend Chart",
            value=config["layout"]["trend_chart"]["enabled"]
        )
        config["layout"]["trend_chart"]["enabled"] = enabled
    
    with col2:
        chart_type = st.selectbox(
            "Chart Type",
            options=["line", "area", "bar"],
            index=["line", "area", "bar"].index(
                config["layout"]["trend_chart"]. get("chart_type", "line")
            )
        )
        config["layout"]["trend_chart"]["chart_type"] = chart_type
    
    st.markdown("---")
    st.markdown("### Chart Series")
    
    series_list = config["layout"]["trend_chart"]["series"]
    
    # Add series button
    if st.button("➕", help="Add Series"):
        series_list.append({
            "name": "New Series",
            "data_source": "material_balance",
            "field": "Receipt",
            "color": "#667eea"
        })
    
    # Edit series
    for idx, series in enumerate(series_list):
        with st.expander(f"Series {idx + 1}: {series['name']}", expanded=False):
            col1, col2 = st.columns(2)
            
            with col1:
                series["name"] = st. text_input(
                    "Series Name",
                    value=series["name"],
                    key=f"series_name_{idx}"
                )
                
                ds_opts = ["material_balance", "fso_operations", "table"]
                try:
                    ds_idx = ds_opts.index(series.get("data_source", "material_balance"))
                except Exception:
                    ds_idx = 0
                series["data_source"] = st.selectbox(
                    "Data Source",
                    options=ds_opts,
                    index=ds_idx,
                    key=f"series_source_{idx}"
                )
            
            with col2:
                if series.get("data_source") == "table":
                    insp = inspect(engine)
                    tables = sorted(insp.get_table_names())
                    series["table_name"] = st.selectbox(
                        "Table",
                        options=tables,
                        index=max(0, tables.index(series.get("table_name")) if series.get("table_name") in tables else 0),
                        key=f"series_table_{idx}"
                    )
                    cols = [c.get("name") for c in insp.get_columns(series["table_name"])]
                    series["field"] = st.selectbox(
                        "Field",
                        options=cols or [""],
                        index=max(0, (cols or [""]).index(series.get("field")) if series.get("field") in (cols or []) else 0),
                        key=f"series_field_{idx}"
                    )
                    st.markdown("**Filters**")
                    criteria = series.setdefault("criteria", [])
                    if st.button("➕", key=f"series_add_filter_{idx}", help="Add Filter"):
                        criteria.append({"column": (cols or [""])[0] if cols else "", "operator": "equals", "value": ""})
                    for c_i, crit in enumerate(list(criteria)):
                        fc1, fc2, fc3, fc4 = st.columns([1.6, 1.2, 1.6, 0.6])
                        with fc1:
                            crit["column"] = st.selectbox("Column", options=cols or [""], index=max(0, (cols or [""]).index(crit.get("column")) if crit.get("column") in (cols or []) else 0), key=f"series_crit_col_{idx}_{c_i}")
                        with fc2:
                            crit["operator"] = st.selectbox("Operator", options=["equals", "not_equals", "contains", "starts_with", "ends_with", "greater_than", "less_than", "greater_equal", "less_equal"], index=["equals", "not_equals", "contains", "starts_with", "ends_with", "greater_than", "less_than", "greater_equal", "less_equal"].index(crit.get("operator", "equals")), key=f"series_crit_op_{idx}_{c_i}")
                        with fc3:
                            crit["value"] = st.text_input("Value", value=str(crit.get("value", "")), key=f"series_crit_val_{idx}_{c_i}")
                        with fc4:
                            if st.button("🗑️", key=f"series_crit_del_{idx}_{c_i}"):
                                criteria.pop(c_i)
                                st.rerun()
                else:
                    series["field"] = st.text_input(
                        "Field Name",
                        value=series.get("field", "Receipt"),
                        key=f"series_field_{idx}"
                    )
                
                series["color"] = st.color_picker(
                    "Line Color",
                    value=series.get("color", "#667eea"),
                    key=f"series_color_{idx}"
                )
            
            if st.button(f"🗑️ Delete Series {idx + 1}", key=f"delete_series_{idx}"):
                series_list.pop(idx)
                st.rerun()
    
    st.markdown("---")
    st.markdown("### Chart Display Options")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        show_markers = st.checkbox(
            "Show Markers",
            value=config["layout"]["trend_chart"]. get("show_markers", True)
        )
        config["layout"]["trend_chart"]["show_markers"] = show_markers
    
    with col2:
        show_labels = st.checkbox(
            "Show Value Labels",
            value=config["layout"]["trend_chart"].get("show_labels", True)
        )
        config["layout"]["trend_chart"]["show_labels"] = show_labels
    
    with col3:
        show_totals = st.checkbox(
            "Show Totals Card",
            value=config["layout"]["trend_chart"].get("show_totals_card", True)
        )
        config["layout"]["trend_chart"]["show_totals_card"] = show_totals


def render_styles_tab(config: dict):
    """Render styles configuration tab"""
    st. markdown("### Global Styles Configuration")
    
    styles = config. get("styles", {})
    
    # Card styles
    st.markdown("#### Card Styles")
    
    card_style = styles.get("card", {})

    col1, col2, col3 = st.columns(3)
    
    with col1:
        card_style["background"] = st.color_picker(
            "Background Color",
            value=_ensure_hex_color(card_style.get("background", "#ffffff"), "#ffffff"),
            key="card_bg"
        )
        
        card_style["border_radius"] = st.number_input(
            "Border Radius (px)",
            min_value=0,
            max_value=50,
            value=card_style.get("border_radius", 10),
            key="card_radius"
        )
    
    with col2:
        card_style["border_color"] = st.color_picker(
            "Border Color",
            value=_ensure_hex_color(card_style.get("border_color", "#667eea"), "#667eea"),
            key="card_border"
        )
        
        card_style["border_width"] = st.number_input(
            "Border Width (px)",
            min_value=0,
            max_value=20,
            value=card_style.get("border_width", 4),
            key="card_border_width"
        )
    
    with col3:
        card_style["padding"] = st.text_input(
            "Padding",
            value=card_style. get("padding", "1rem"),
            key="card_padding"
        )
        
        card_style["shadow"] = st.text_input(
            "Box Shadow",
            value=card_style.get("shadow", "0 2px 8px rgba(0,0,0,0.1)"),
            key="card_shadow"
        )
    colw, colh = st.columns(2)
    with colw:
        card_style["width"] = st.number_input(
            "Width (px)",
            min_value=0,
            max_value=1200,
            value=card_style.get("width", 0),
            key="card_width"
        )
    with colh:
        card_style["height"] = st.number_input(
            "Height (px)",
            min_value=0,
            max_value=600,
            value=card_style.get("height", 0),
            key="card_height"
        )

    styles["card"] = card_style
    
    st.markdown("---")
    
    # Value styles
    st.markdown("#### Value Text Styles")
    
    value_style = styles.get("value", {})
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Convert rem to simple number for user input
        current_size = value_style.get("font_size", "1.6rem")
        size_num = float(current_size.replace("rem", "")) if "rem" in current_size else 1.6
        
        font_size_input = st.number_input(
            "Font Size",
            min_value=0.5,
            max_value=5.0,
            value=size_num,
            step=0.1,
            help="Font size in relative units (1.0 = normal, 1.6 = large)",
            key="value_size"
        )
        value_style["font_size"] = f"{font_size_input}rem"
    
    with col2:
        value_style["font_weight"] = st.selectbox(
            "Font Weight",
            options=["normal", "bold", "bolder", "lighter"],
            index=["normal", "bold", "bolder", "lighter"]. index(
                value_style. get("font_weight", "bold")
            ),
            key="value_weight"
        )
    
    with col3:
        value_style["color"] = st.color_picker(
            "Color",
            value=_ensure_hex_color(value_style.get("color", "#667eea"), "#667eea"),
            key="value_color"
        )
    
    styles["value"] = value_style
    
    st.markdown("---")
    
    # Label styles
    st.markdown("#### Label Text Styles")
    
    label_style = styles.get("label", {})
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Convert rem to simple number for user input
        current_label_size = label_style.get("font_size", "0.8rem")
        label_size_num = float(current_label_size.replace("rem", "")) if "rem" in current_label_size else 0.8
        
        label_font_size_input = st.number_input(
            "Font Size",
            min_value=0.5,
            max_value=3.0,
            value=label_size_num,
            step=0.1,
            help="Font size in relative units (0.8 = small, 1.0 = normal)",
            key="label_size"
        )
        label_style["font_size"] = f"{label_font_size_input}rem"
    
    with col2:
        label_style["font_weight"] = st.selectbox(
            "Font Weight",
            options=["normal", "bold", "bolder", "lighter"],
            index=["normal", "bold", "bolder", "lighter"].index(
                label_style.get("font_weight", "bold")
            ),
            key="label_weight"
        )
    
    with col3:
        label_style["color"] = st.color_picker(
            "Color",
            value=_ensure_hex_color(label_style.get("color", "#666666"), "#666666"),
            key="label_color"
        )
    
    label_style["text_transform"] = st.selectbox(
        "Text Transform",
        options=["none", "uppercase", "lowercase", "capitalize"],
        index=["none", "uppercase", "lowercase", "capitalize"].index(
            label_style.get("text_transform", "uppercase")
        ),
        key="label_transform"
    )
    
    styles["label"] = label_style
    
    st.markdown("---")
    
    # Heading styles
    st.markdown("#### Section Heading Styles")
    
    heading_style = styles.get("heading", {})
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        current_heading_size = heading_style.get("font_size", "1.5rem")
        heading_size_num = float(current_heading_size.replace("rem", "")) if "rem" in current_heading_size else 1.5
        
        heading_font_size_input = st.number_input(
            "Font Size",
            min_value=0.8,
            max_value=3.0,
            value=heading_size_num,
            step=0.1,
            help="Font size for section headings (1.5 = default)",
            key="heading_size"
        )
        heading_style["font_size"] = f"{heading_font_size_input}rem"
    
    with col2:
        heading_style["font_weight"] = st.selectbox(
            "Font Weight",
            options=["normal", "bold", "bolder"],
            index=["normal", "bold", "bolder"].index(
                heading_style.get("font_weight", "bold")
            ),
            key="heading_weight"
        )
    
    with col3:
        heading_style["color"] = st.color_picker(
            "Color",
            value=_ensure_hex_color(heading_style.get("color", "#333333"), "#333333"),
            key="heading_color"
        )
    
    styles["heading"] = heading_style
    
    st.markdown("---")
    
    # Table/Dataframe styles
    st.markdown("#### Table & Dataframe Styles")
    
    table_style = styles.get("table", {})
    
    col1, col2 = st.columns(2)
    
    with col1:
        current_table_font = table_style.get("font_size", "0.9rem")
        table_font_num = float(current_table_font.replace("rem", "")) if "rem" in current_table_font else 0.9
        
        table_font_size_input = st.number_input(
            "Font Size",
            min_value=0.6,
            max_value=2.0,
            value=table_font_num,
            step=0.1,
            help="Font size for table text (0.9 = default)",
            key="table_size"
        )
        table_style["font_size"] = f"{table_font_size_input}rem"
    
    with col2:
        table_style["header_bg"] = st.color_picker(
            "Header Background",
            value=_ensure_hex_color(table_style.get("header_bg", "#f8f9fa"), "#f8f9fa"),
            key="table_header_bg"
        )
    
    styles["table"] = table_style
    
    config["styles"] = styles


def render_save_load_tab(config: dict, location_id: int, user: dict):
    """Render save & load configuration tab"""
    st. markdown("### Save & Load Configurations")
    
    # Save current configuration
    st.markdown("#### Save Current Configuration")
    
    col1, col2 = st. columns([2, 1])
    
    with col1:
        config_name = st.text_input(
            "Configuration Name",
            value="default",
            help="Enter a name for this configuration"
        )
    
    with col2:
        st.write("")  # Spacing
        st.write("")  # Spacing
        if st.button("💾", type="primary", help="Save Configuration"):
            success = DashboardConfigManager.save_config(
                location_id=location_id,
                config_name=config_name,
                config_data=config,
                user=user["username"]
            )
            
            if success:
                st.success(f"✅ Configuration '{config_name}' saved successfully!")
            else:
                st.error("❌ Failed to save configuration")
    
    st.markdown("---")
    
    # Load existing configurations
    st.markdown("#### Load Existing Configuration")
    
    configs = DashboardConfigManager.get_all_configs(location_id)
    
    if not configs:
        st.info("No saved configurations found for this location")
    else:
        for cfg in configs:
            with st. expander(
                f"📋 {cfg['name']} - "
                f"{'✅ Active' if cfg['is_active'] else '⏸️ Inactive'}",
                expanded=False
            ):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write(f"**Created By:** {cfg['created_by']}")
                    st.write(f"**Created:** {cfg['created_at']. strftime('%Y-%m-%d %H:%M')}")
                
                with col2:
                    st.write(f"**Updated:** {cfg['updated_at'].strftime('%Y-%m-%d %H:%M')}")
                
                with col3:
                    if st.button(f"📥 Load", key=f"load_{cfg['id']}"):
                        loaded_config = DashboardConfigManager.load_config(
                            location_id, cfg['name']
                        )
                        st.session_state.dashboard_config = loaded_config
                        st.success(f"✅ Configuration '{cfg['name']}' loaded!")
                        st.rerun()
                    
                    if st. button(f"🗑️ Delete", key=f"delete_{cfg['id']}"):
                        if DashboardConfigManager.delete_config(cfg['id']):
                            st.success(f"✅ Configuration deleted!")
                            st.rerun()
    
    st.markdown("---")
    
    # Export/Import JSON
    st.markdown("#### Export/Import Configuration (JSON)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Export Configuration**")
        config_json = json.dumps(config, indent=2)
        st.download_button(
            label="⬇️ Download JSON",
            data=config_json,
            file_name=f"dashboard_config_{location_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )
    
    with col2:
        st.markdown("**Import Configuration**")
        uploaded_file = st.file_uploader(
            "Upload JSON Configuration",
            type=["json"],
            help="Upload a previously exported configuration file"
        )
        
        if uploaded_file is not None:
            try:
                imported_config = json.load(uploaded_file)
                st.session_state.dashboard_config = imported_config
                st. success("✅ Configuration imported successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Failed to import configuration: {e}")


def render_pdf_customization_tab(config: dict, location_id: int, user: dict):
    """Render PDF customization tab with visual drag-and-drop layout designer"""
    st.markdown("### 📄 PDF Layout Designer")
    st.markdown("Design your PDF layout visually - drag, resize, and position widgets like Power BI")
    
    # Initialize PDF layout config
    pdf_layout_cfg = config.setdefault("pdf_layout", {})
    
    # Page Size Configuration
    st.markdown("#### 📏 Page Settings")
    page_col1, page_col2, page_col3 = st.columns(3)
    
    with page_col1:
        page_size = st.selectbox(
            "Page Size",
            ["A4", "A3", "Letter", "Legal"],
            index=["A4", "A3", "Letter", "Legal"].index(pdf_layout_cfg.get("page_size", "A4")),
            key="pdf_page_size"
        )
        pdf_layout_cfg["page_size"] = page_size
    
    with page_col2:
        orientation = st.selectbox(
            "Orientation",
            ["Portrait", "Landscape"],
            index=["Portrait", "Landscape"].index(pdf_layout_cfg.get("orientation", "Landscape")),
            key="pdf_orientation"
        )
        pdf_layout_cfg["orientation"] = orientation
    
    with page_col3:
        grid_cols = st.number_input(
            "Grid Columns",
            min_value=2,
            max_value=12,
            value=pdf_layout_cfg.get("grid_columns", 12),
            help="Number of columns in the grid (like Power BI)",
            key="pdf_grid_cols"
        )
        pdf_layout_cfg["grid_columns"] = grid_cols
    
    st.markdown("---")
    
    # Get available sections
    sections = config.get("sections", [])
    pdf_cfg = config.get("pdf_export", {})
    enabled_sections = pdf_cfg.get("enabled_sections", {})
    
    # Initialize widgets list with grid positions
    widgets = pdf_layout_cfg.setdefault("widgets", [])
    
    # Available widget types
    available_widget_types = []
    for sec in sections:
        sid = sec.get("id")
        if enabled_sections.get(sid, sec.get("enabled", True)):
            available_widget_types.append({
                "id": sid,
                "name": sec.get("name") or sid,
                "type": sec.get("type")
            })
    
    if not available_widget_types:
        st.info("ℹ️ No widgets enabled. Enable sections in the 'PDF Export' tab first.")
        return
    
    # Visual Canvas Layout Designer
    st.markdown("#### 🎨 Visual Layout Canvas")
    
    # Sidebar for adding widgets
    with st.expander("➕ Add Widget to Canvas", expanded=True):
        widget_options = [f"{w['name']} ({w['type']})" for w in available_widget_types]
        selected_widget = st.selectbox(
            "Select Widget",
            widget_options,
            key="new_widget_select"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ Add to Canvas", type="primary", key="add_widget_btn", use_container_width=True):
                selected_idx = widget_options.index(selected_widget)
                widget_data = available_widget_types[selected_idx]
                
                # Calculate next available position
                max_row = max([w.get("row", 0) + w.get("height", 1) for w in widgets]) if widgets else 0
                
                new_widget = {
                    "id": widget_data["id"],
                    "name": widget_data["name"],
                    "type": widget_data["type"],
                    "col": 0,  # Grid column position (0-based)
                    "row": max_row,  # Grid row position (0-based)
                    "width": 6,  # Width in grid columns
                    "height": 4,  # Height in grid rows
                    "display_type": "table",  # "table" or "visual"
                }
                widgets.append(new_widget)
                st.success(f"✅ Added {widget_data['name']} to canvas")
                st.rerun()
        
        with col2:
            if st.button("🗑️ Clear All", key="clear_all_btn", use_container_width=True):
                widgets.clear()
                st.success("✅ Canvas cleared")
                st.rerun()
    
    # Display visual canvas with interactive widget controls
    if widgets:
        st.markdown("##### Canvas - Full Drag & Resize (Power BI Style):")
        st.caption("💡 Tip: Interactive canvas with real-time adjustments. Change values below to see live updates.")
        
        # Create visual representation using HTML/CSS with enhanced interactivity
        import streamlit.components.v1 as components
        
        # Generate widget data for JavaScript
        widgets_json = json.dumps(widgets)
        grid_cols_val = grid_cols
        
        # Enhanced interactive canvas HTML with 6-point drag handles
        canvas_html = f"""
        <style>
            .canvas-toolbar {{
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                padding: 10px 12px;
                background: #0f172a;
                color: white;
                border: 1px solid #1f2937;
                border-radius: 10px;
                box-shadow: 0 6px 18px rgba(0,0,0,0.25);
                position: sticky;
                top: 0;
                z-index: 50;
            }}
            .canvas-toolbar .group-title {{
                font-weight: 700;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #cbd5e1;
                margin-right: 6px;
            }}
            .canvas-toolbar button {{
                background: #1d4ed8;
                color: white;
                border: 1px solid #1d4ed8;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                cursor: pointer;
                transition: all 0.15s ease;
            }}
            .canvas-toolbar button:hover {{
                background: #2563eb;
                border-color: #2563eb;
                transform: translateY(-1px);
            }}
            .canvas-toolbar button:active {{
                transform: translateY(0);
            }}
            .pdf-canvas {{
                background: linear-gradient(90deg, #f0f0f0 1px, transparent 1px),
                            linear-gradient(#f0f0f0 1px, transparent 1px);
                background-size: calc(100% / {grid_cols_val}) 30px;
                border: 3px solid #1e3a8a;
                border-radius: 12px;
                min-height: 720px;
                position: relative;
                padding: 10px;
                margin: 16px 0;
                background-color: #fafafa;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                overflow: hidden;
            }}
            .align-guides {{
                position: absolute;
                inset: 0;
                pointer-events: none;
                z-index: 5;
            }}
            .align-guides .guide-line {{
                position: absolute;
                background: rgba(14,165,233,0.6);
            }}
            .widget-box {{
                position: absolute;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-radius: 8px;
                padding: 15px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                transition: all 0.08s ease;
                cursor: move;
                border: 3px solid #4c63d2;
                font-family: Arial, sans-serif;
                user-select: none;
            }}
            .widget-box.selected {{
                box-shadow: 0 0 20px rgba(79, 172, 254, 0.8), inset 0 0 10px rgba(255,255,255,0.3);
                border: 3px solid #0ea5e9;
            }}
            .widget-name {{
                font-weight: bold;
                font-size: 14px;
                margin-bottom: 5px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .widget-info {{
                font-size: 11px;
                opacity: 0.95;
                margin: 3px 0;
            }}
            .resize-handle {{
                position: absolute;
                background: #0ea5e9;
                border: 2px solid white;
                border-radius: 50%;
                width: 12px;
                height: 12px;
                cursor: pointer;
                z-index: 1000;
                transition: all 0.2s ease;
            }}
            .resize-handle:hover {{
                width: 16px;
                height: 16px;
                background: #06b6d4;
            }}
            .resize-handle.tl {{ top: -6px; left: -6px; cursor: nwse-resize; }}
            .resize-handle.tr {{ top: -6px; right: -6px; cursor: nesw-resize; }}
            .resize-handle.bl {{ bottom: -6px; left: -6px; cursor: nesw-resize; }}
            .resize-handle.br {{ bottom: -6px; right: -6px; cursor: nwse-resize; }}
            .resize-handle.tm {{ top: -6px; left: 50%; transform: translateX(-50%); cursor: ns-resize; }}
            .resize-handle.bm {{ bottom: -6px; left: 50%; transform: translateX(-50%); cursor: ns-resize; }}
            .drag-handle {{
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 30px;
                background: linear-gradient(180deg, rgba(0,0,0,0.3), transparent);
                border-radius: 6px 6px 0 0;
                cursor: move;
                display: flex;
                align-items: center;
                padding-left: 8px;
            }}
            .drag-indicator {{
                color: rgba(255,255,255,0.8);
                font-size: 12px;
            }}
            .nudge-hint {{
                font-size: 11px;
                color: #475569;
                margin-left: 4px;
            }}
        </style>

        <div class="canvas-toolbar">
            <span class="group-title">Arrange</span>
            <button data-action="align-left">Align Left</button>
            <button data-action="align-center">Align Center</button>
            <button data-action="align-right">Align Right</button>
            <button data-action="align-top">Align Top</button>
            <button data-action="align-middle">Align Middle</button>
            <button data-action="align-bottom">Align Bottom</button>
            <span class="group-title" style="margin-left:10px;">Nudge</span>
            <button data-action="nudge-up">▲</button>
            <button data-action="nudge-left">◀</button>
            <button data-action="nudge-right">▶</button>
            <button data-action="nudge-down">▼</button>
            <span class="nudge-hint">Arrow keys also work (Shift=resize)</span>
        </div>

        <div class="pdf-canvas" id="pdfCanvas">
            <div class="align-guides" id="alignGuides"></div>
            <div style="text-align:center; padding:30px; color:#999;">
                <p style="font-size:18px; margin:0;">📊 Interactive PDF Layout Canvas</p>
                <p style="font-size:12px; margin:10px 0 0 0;">Drag widgets to move • Use handles to resize • Arrow keys to nudge • Shift + arrows to resize</p>
            </div>
        </div>
        <script>
            (function() {{
                var widgets = {widgets_json};
                var gridCols = {grid_cols_val};
                var canvas = document.getElementById('pdfCanvas');
                var guides = document.getElementById('alignGuides');
                var cellWidth = canvas.getBoundingClientRect().width / gridCols;
                var cellHeight = 30;
                function recalcGrid() {{
                    cellWidth = canvas.getBoundingClientRect().width / gridCols;
                    widgets.forEach(function(w, idx) {{ updateWidgetEl(idx, w); }});
                }}
                var selectedWidget = null;
                var dragStart = null;
                var resizeDir = null;
                var isDragging = false;
                var isResizing = false;

                function clamp(val, min, max) {{
                    return Math.max(min, Math.min(max, val));
                }}

                function snapCol(x) {{
                    return clamp(Math.round(x / cellWidth), 0, gridCols - 1);
                }}

                function snapRow(y) {{
                    return Math.max(0, Math.round(y / cellHeight));
                }}

                function renderGuides(col, row, w, h) {{
                    if (!guides) return;
                    guides.innerHTML = '';
                    var v = document.createElement('div');
                    v.className = 'guide-line';
                    v.style.width = '2px';
                    v.style.height = '100%';
                    v.style.left = (col * cellWidth) + 'px';
                    v.style.top = '0';
                    v.style.opacity = '0.35';
                    guides.appendChild(v);
                    var v2 = document.createElement('div');
                    v2.className = 'guide-line';
                    v2.style.width = '2px';
                    v2.style.height = '100%';
                    v2.style.left = ((col + w) * cellWidth) + 'px';
                    v2.style.top = '0';
                    v2.style.opacity = '0.2';
                    guides.appendChild(v2);
                    var hLine = document.createElement('div');
                    hLine.className = 'guide-line';
                    hLine.style.height = '2px';
                    hLine.style.width = '100%';
                    hLine.style.top = (row * cellHeight) + 'px';
                    hLine.style.left = '0';
                    hLine.style.opacity = '0.35';
                    guides.appendChild(hLine);
                    var h2 = document.createElement('div');
                    h2.className = 'guide-line';
                    h2.style.height = '2px';
                    h2.style.width = '100%';
                    h2.style.top = ((row + h) * cellHeight) + 'px';
                    h2.style.left = '0';
                    h2.style.opacity = '0.2';
                    guides.appendChild(h2);
                }}

                if (widgets.length > 0) {{
                    canvas.innerHTML = '<div class="align-guides" id="alignGuides"></div>';
                    guides = canvas.querySelector('#alignGuides');
                }}
                
                function updateWidgetEl(idx, w) {{
                    var widgetEl = document.getElementById('widget_' + idx);
                    if (!widgetEl) return;
                    widgetEl.style.left = (w.col * cellWidth) + 'px';
                    widgetEl.style.top = (w.row * cellHeight) + 'px';
                    widgetEl.style.width = (w.width * cellWidth - 6) + 'px';
                    widgetEl.style.height = (w.height * cellHeight - 6) + 'px';
                    var info = widgetEl.querySelectorAll('.widget-info');
                    if (info && info.length >= 2) {{
                        info[1].textContent = 'Position: Col ' + w.col + ', Row ' + w.row;
                        info[2].textContent = 'Size: ' + w.width + 'x' + w.height;
                    }}
                    renderGuides(w.col, w.row, w.width, w.height);
                }}
                
                function updateWidgetElPixels(idx, left, top, width, height) {{
                    var widgetEl = document.getElementById('widget_' + idx);
                    if (!widgetEl) return;
                    widgetEl.style.left = left + 'px';
                    widgetEl.style.top = top + 'px';
                    widgetEl.style.width = width + 'px';
                    widgetEl.style.height = height + 'px';
                }}
                
                widgets.forEach(function(widget, index) {{
                    var widgetDiv = document.createElement('div');
                    widgetDiv.className = 'widget-box';
                    widgetDiv.id = 'widget_' + index;
                    
                    var colorSchemes = [
                        'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                        'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
                        'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
                        'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
                        'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
                        'linear-gradient(135deg, #30cfd0 0%, #330867 100%)'
                    ];
                    widgetDiv.style.background = colorSchemes[index % colorSchemes.length];
                    
                    function updatePosition() {{
                        widgetDiv.style.left = (widget.col * cellWidth) + 'px';
                        widgetDiv.style.top = (widget.row * cellHeight) + 'px';
                        widgetDiv.style.width = (widget.width * cellWidth - 6) + 'px';
                        widgetDiv.style.height = (widget.height * cellHeight - 6) + 'px';
                    }}
                    updatePosition();
                    
                    var displayType = widget.display_type || 'table';
                    widgetDiv.innerHTML = '<div class="drag-handle"><span class="drag-indicator">⋮⋮</span></div>' +
                                         '<div class="widget-name">' + widget.name + '</div>' +
                                         '<div class="widget-info">📊 ' + widget.type + ' (' + displayType + ')</div>' +
                                         '<div class="widget-info">Position: Col ' + widget.col + ', Row ' + widget.row + '</div>' +
                                         '<div class="widget-info">Size: ' + widget.width + 'x' + widget.height + '</div>';
                    
                    var handles = ['tl', 'tr', 'bl', 'br', 'tm', 'bm'];
                    handles.forEach(function(handle) {{
                        var handleDiv = document.createElement('div');
                        handleDiv.className = 'resize-handle ' + handle;
                        handleDiv.data_direction = handle;
                        handleDiv.addEventListener('mousedown', function(e) {{
                            e.preventDefault();
                            e.stopPropagation();
                            selectedWidget = {{ index: index, widget: widget, element: widgetDiv }};
                            resizeDir = handle;
                            isResizing = true;
                            isDragging = false;
                            var rect = widgetDiv.getBoundingClientRect();
                            var canvasRect = canvas.getBoundingClientRect();
                            dragStart = {{ 
                                x: e.clientX, 
                                y: e.clientY, 
                                widget: {{...widget}},
                                left: rect.left - canvasRect.left,
                                top: rect.top - canvasRect.top,
                                width: rect.width,
                                height: rect.height
                            }};
                            widgetDiv.classList.add('selected');
                            document.body.style.cursor = getComputedStyle(handleDiv).cursor;
                        }});
                        widgetDiv.appendChild(handleDiv);
                    }});
                    
                    widgetDiv.addEventListener('mousedown', function(e) {{
                        if (e.target.classList.contains('resize-handle')) return;
                        e.preventDefault();
                        isDragging = true;
                        isResizing = false;
                        selectedWidget = {{ index: index, widget: widget, element: widgetDiv }};
                        var rect = widgetDiv.getBoundingClientRect();
                        var canvasRect = canvas.getBoundingClientRect();
                        dragStart = {{ 
                            x: e.clientX, 
                            y: e.clientY, 
                            widget: {{...widget}},
                            left: rect.left - canvasRect.left,
                            top: rect.top - canvasRect.top,
                            width: rect.width,
                            height: rect.height
                        }};
                        resizeDir = null;
                        widgetDiv.classList.add('selected');
                        document.body.style.cursor = 'move';
                        renderGuides(widget.col, widget.row, widget.width, widget.height);
                    }});
                    
                    canvas.appendChild(widgetDiv);
                }});
                
                function pushUpdate() {{
                    if (!selectedWidget) return;
                    window.parent.postMessage({{
                        type: 'streamlit:setComponentValue',
                        sessionID: 'widget_update',
                        value: selectedWidget.widget
                    }}, '*');
                }}
                
                document.addEventListener('mousemove', function(e) {{
                    if (!dragStart || !selectedWidget) return;
                    if (!isDragging && !isResizing) return;
                    
                    e.preventDefault();
                    var dx = e.clientX - dragStart.x;
                    var dy = e.clientY - dragStart.y;
                    
                    if (isResizing && resizeDir) {{
                        var newLeft = dragStart.left;
                        var newTop = dragStart.top;
                        var newWidth = dragStart.width;
                        var newHeight = dragStart.height;
                        
                        if (resizeDir.includes('l')) {{
                            newLeft = dragStart.left + dx;
                            newWidth = dragStart.width - dx;
                            if (newWidth < cellWidth) {{
                                newWidth = cellWidth;
                                newLeft = dragStart.left + dragStart.width - cellWidth;
                            }}
                        }}
                        if (resizeDir.includes('r')) {{
                            newWidth = dragStart.width + dx;
                            if (newWidth < cellWidth) newWidth = cellWidth;
                        }}
                        if (resizeDir.includes('t')) {{
                            newTop = dragStart.top + dy;
                            newHeight = dragStart.height - dy;
                            if (newHeight < cellHeight) {{
                                newHeight = cellHeight;
                                newTop = dragStart.top + dragStart.height - cellHeight;
                            }}
                        }}
                        if (resizeDir.includes('b')) {{
                            newHeight = dragStart.height + dy;
                            if (newHeight < cellHeight) newHeight = cellHeight;
                        }}
                        
                        updateWidgetElPixels(selectedWidget.index, newLeft, newTop, newWidth, newHeight);
                        
                    }} else if (isDragging) {{
                        var newLeft = dragStart.left + dx;
                        var newTop = dragStart.top + dy;
                        if (newLeft < 0) newLeft = 0;
                        if (newTop < 0) newTop = 0;
                        updateWidgetElPixels(selectedWidget.index, newLeft, newTop, dragStart.width, dragStart.height);
                    }}
                }});
                
                document.addEventListener('mouseup', function(e) {{
                    if (selectedWidget && (isDragging || isResizing)) {{
                        var widgetEl = document.getElementById('widget_' + selectedWidget.index);
                        if (widgetEl) {{
                            widgetEl.classList.remove('selected');
                            var rect = widgetEl.getBoundingClientRect();
                            var canvasRect = canvas.getBoundingClientRect();
                            var left = rect.left - canvasRect.left;
                            var top = rect.top - canvasRect.top;
                            var width = rect.width;
                            var height = rect.height;
                            
                            var newCol = Math.max(0, Math.min(Math.round(left / cellWidth), gridCols - 1));
                            var newRow = Math.max(0, Math.round(top / cellHeight));
                            var newWidth = Math.max(1, Math.min(Math.round(width / cellWidth), gridCols - newCol));
                            var newHeight = Math.max(1, Math.round(height / cellHeight));
                            
                            selectedWidget.widget.col = newCol;
                            selectedWidget.widget.row = newRow;
                            selectedWidget.widget.width = newWidth;
                            selectedWidget.widget.height = newHeight;
                            
                            updateWidgetEl(selectedWidget.index, selectedWidget.widget);
                            pushUpdate();
                        }}
                    }}
                    document.body.style.cursor = '';
                    dragStart = null;
                    resizeDir = null;
                    isDragging = false;
                    isResizing = false;
                    selectedWidget = null;
                    renderGuides(-1, -1, 0, 0);
                }});

                // Recalculate sizing on window resize for smoother drag/resize
                window.addEventListener('resize', function() {{
                    recalcGrid();
                }});

                // Keyboard nudging: arrows move, Shift+arrows resize
                document.addEventListener('keydown', function(e) {{
                    if (!selectedWidget) return;
                    var w = selectedWidget.widget;
                    var delta = e.ctrlKey || e.metaKey ? 2 : 1;
                    var changed = false;
                    if (e.key === 'ArrowLeft') {{
                        if (e.shiftKey) {{ w.width = Math.max(1, w.width - delta); changed = true; }}
                        else {{ w.col = clamp(w.col - delta, 0, gridCols - w.width); changed = true; }}
                    }} else if (e.key === 'ArrowRight') {{
                        if (e.shiftKey) {{ w.width = clamp(w.width + delta, 1, gridCols - w.col); changed = true; }}
                        else {{ w.col = clamp(w.col + delta, 0, gridCols - w.width); changed = true; }}
                    }} else if (e.key === 'ArrowUp') {{
                        if (e.shiftKey) {{ w.height = Math.max(1, w.height - delta); changed = true; }}
                        else {{ w.row = Math.max(0, w.row - delta); changed = true; }}
                    }} else if (e.key === 'ArrowDown') {{
                        if (e.shiftKey) {{ w.height = Math.max(1, w.height + delta); changed = true; }}
                        else {{ w.row = Math.max(0, w.row + delta); changed = true; }}
                    }}
                    if (changed) {{
                        updateWidgetEl(selectedWidget.index, w);
                        pushUpdate();
                        e.preventDefault();
                    }}
                }});

                // Toolbar actions for Excel/Power BI like alignment
                document.querySelectorAll('.canvas-toolbar button').forEach(function(btn) {{
                    btn.addEventListener('click', function() {{
                        if (!selectedWidget) return;
                        var w = selectedWidget.widget;
                        var action = btn.getAttribute('data-action');
                        if (action === 'align-left') w.col = 0;
                        if (action === 'align-center') w.col = Math.round((gridCols - w.width) / 2);
                        if (action === 'align-right') w.col = Math.max(0, gridCols - w.width);
                        if (action === 'align-top') w.row = 0;
                        if (action === 'align-middle') w.row = Math.max(0, Math.round(5 - (w.height / 2)));
                        if (action === 'align-bottom') w.row = Math.max(0, widgets.reduce(function(max, it) {{ return Math.max(max, (it.row || 0) + (it.height || 1)); }}, 0));
                        if (action === 'nudge-left') w.col = clamp(w.col - 1, 0, gridCols - w.width);
                        if (action === 'nudge-right') w.col = clamp(w.col + 1, 0, gridCols - w.width);
                        if (action === 'nudge-up') w.row = Math.max(0, w.row - 1);
                        if (action === 'nudge-down') w.row = Math.max(0, w.row + 1);
                        updateWidgetEl(selectedWidget.index, w);
                        pushUpdate();
                    }});
                }});
            }})();
        </script>
        """
        
        components.html(canvas_html, height=800, scrolling=False)
        
        # Widget controls section - removed old duplicated HTML
        st.markdown("---")
        st.markdown("##### ⚙️ Widget Configuration & Display Options:")
        
        for idx, widget in enumerate(widgets):
            with st.expander(f"📊 {widget.get('name', 'Widget')} - {widget.get('type', 'unknown')}", expanded=False):
                ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4, ctrl_col5 = st.columns([2, 2, 2, 2, 1])
                
                with ctrl_col1:
                    new_col = st.number_input(
                        "Column",
                        min_value=0,
                        max_value=grid_cols - 1,
                        value=widget.get("col", 0),
                        help=f"Starting column (0 to {grid_cols-1})",
                        key=f"widget_col_{idx}"
                    )
                    widget["col"] = new_col
                
                with ctrl_col2:
                    new_row = st.number_input(
                        "Row",
                        min_value=0,
                        max_value=100,
                        value=widget.get("row", 0),
                        help="Starting row position",
                        key=f"widget_row_{idx}"
                    )
                    widget["row"] = new_row
                
                with ctrl_col3:
                    # Clamp width to current grid columns
                    current_width = min(widget.get("width", 6), grid_cols)
                    new_width = st.number_input(
                        "Width (cols)",
                        min_value=1,
                        max_value=grid_cols,
                        value=current_width,
                        help=f"Widget width in grid columns (1-{grid_cols})",
                        key=f"widget_width_{idx}"
                    )
                    widget["width"] = new_width
                
                with ctrl_col4:
                    new_height = st.number_input(
                        "Height (rows)",
                        min_value=1,
                        max_value=20,
                        value=widget.get("height", 4),
                        help="Widget height in grid rows",
                        key=f"widget_height_{idx}"
                    )
                    widget["height"] = new_height
                
                with ctrl_col5:
                    if st.button("🗑️", key=f"delete_widget_{idx}", help="Delete this widget"):
                        widgets.pop(idx)
                        st.success("✅ Widget deleted")
                        st.rerun()
                
                # Display type selector (Table vs Visual)
                st.markdown("**Display Type:**")
                display_type_col1, display_type_col2 = st.columns(2)
                
                current_display_type = widget.get("display_type", "table")
                
                with display_type_col1:
                    if st.button("📋 Table", key=f"display_table_{idx}", 
                               use_container_width=True,
                               type="primary" if current_display_type == "table" else "secondary"):
                        widget["display_type"] = "table"
                        st.rerun()
                
                with display_type_col2:
                    if st.button("📊 Visual", key=f"display_visual_{idx}", 
                               use_container_width=True,
                               type="primary" if current_display_type == "visual" else "secondary"):
                        widget["display_type"] = "visual"
                        st.rerun()
                
                st.caption(f"Current: **{current_display_type.title()}** mode")
                
                # Quick position buttons
                st.markdown("**Quick Positions:**")
                quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
                
                with quick_col1:
                    if st.button("↖️ Top Left", key=f"pos_tl_{idx}"):
                        widget["col"] = 0
                        widget["row"] = 0
                        st.rerun()
                
                with quick_col2:
                    if st.button("↗️ Top Right", key=f"pos_tr_{idx}"):
                        widget["col"] = grid_cols - widget["width"]
                        widget["row"] = 0
                        st.rerun()
                
                with quick_col3:
                    if st.button("↙️ Bottom Left", key=f"pos_bl_{idx}"):
                        widget["col"] = 0
                        max_row = max([w.get("row", 0) + w.get("height", 1) for w in widgets])
                        widget["row"] = max_row
                        st.rerun()
                
                with quick_col4:
                    if st.button("↘️ Bottom Right", key=f"pos_br_{idx}"):
                        widget["col"] = grid_cols - widget["width"]
                        max_row = max([w.get("row", 0) + w.get("height", 1) for w in widgets])
                        widget["row"] = max_row
                        st.rerun()
    else:
        st.info("ℹ️ No widgets on canvas. Add widgets using the form above.")
        
        # Show empty canvas
        import streamlit.components.v1 as components
        empty_canvas = f"""
        <style>
            .pdf-canvas-empty {{
                background: linear-gradient(90deg, #f0f0f0 1px, transparent 1px),
                            linear-gradient(#f0f0f0 1px, transparent 1px);
                background-size: calc(100% / {grid_cols}) 30px;
                border: 2px dashed #ccc;
                border-radius: 8px;
                min-height: 400px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #999;
                font-size: 18px;
                margin: 20px 0;
            }}
        </style>
        <div class="pdf-canvas-empty">
            <div style="text-align:center;">
                <p style="font-size:24px; margin:0;">📄</p>
                <p style="margin:10px 0 0 0;">Empty Canvas - Add widgets to start designing</p>
            </div>
        </div>
        """
        components.html(empty_canvas, height=450, scrolling=False)
    
    # Save button
    st.markdown("---")
    if st.button("💾 Save PDF Layout Configuration", type="primary", key="save_pdf_layout"):
        if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
            st.success("✅ PDF layout configuration saved successfully!")
            st.session_state.dashboard_config = config
        else:
            st.error("❌ Failed to save configuration")


if __name__ == "__main__":
    render_dashboard_customization()
