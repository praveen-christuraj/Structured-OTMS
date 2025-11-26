# dashboard_customization.py
"""
Dashboard Customization Page
Allows admins to configure dashboard layout and widgets
"""

import streamlit as st
import json
from datetime import date, datetime
from dashboard_config import DashboardConfigManager, DashboardConfig
from dashboard_widgets import WidgetRenderer
from db import get_session


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
    
    location_id = st.session_state.get("active_location_id")
    if not location_id:
        st.warning("⚠️ Please select a location first")
        return
    
    # Tabs for different customization sections
    tabs = st.tabs([
        "📋 Overview",
        "📊 Summary Cards",
        "🛢️ Tank Visuals",
        "📈 Charts & Trends",
        "🗂️ Sections Manager",
        "🎨 Styles",
        "💾 Save & Load"
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
        if st.button("💾 Save Configuration", key="save_cards", type="primary"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")
    
    # Tab 2: Tank Visuals
    with tabs[2]:
        render_tank_visuals_tab(config)
        st.markdown("---")
        if st.button("💾 Save Configuration", key="save_tanks", type="primary"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")
    
    # Tab 3: Charts & Trends
    with tabs[3]:
        render_charts_tab(config)
        st.markdown("---")
        if st.button("💾 Save Configuration", key="save_charts", type="primary"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")
    
    # Tab 4: Sections Manager
    with tabs[4]:
        render_sections_manager_tab(config)
        st.markdown("---")
        if st.button("💾 Save Configuration", key="save_sections", type="primary"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")
    
    # Tab 5: Styles
    with tabs[5]:
        render_styles_tab(config)
        st.markdown("---")
        if st.button("💾 Save Configuration", key="save_styles", type="primary"):
            if DashboardConfigManager.save_config(location_id, "default", config, user["username"]):
                st.success("✅ Configuration saved successfully!")
                st.session_state.dashboard_config = config
            else:
                st.error("❌ Failed to save configuration")
    
    # Tab 6: Save & Load
    with tabs[6]:
        render_save_load_tab(config, location_id, user)


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
    if st.button("🔍 Preview Dashboard", type="primary"):
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
    if st.button("➕ Add New Card"):
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
                
                card["data_source"] = st. selectbox(
                    "Data Source",
                    options=["material_balance", "fso_operations", "calculated", "manual"],
                    index=["material_balance", "fso_operations", "calculated", "manual"]. index(
                        card. get("data_source", "material_balance")
                    ),
                    key=f"card_source_{idx}"
                )
                
                if card["data_source"] == "material_balance":
                    card["field"] = st.selectbox(
                        "Field",
                        options=["Receipt", "Dispatch", "Closing Stock", "Opening Stock"],
                        index=["Receipt", "Dispatch", "Closing Stock", "Opening Stock"].index(
                            card.get("field", "Receipt")
                        ),
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
                if st.button("➕ Add Tank Visual", type="secondary"):
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
                    "type": "single",
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
    if st.button("➕ Add New Section", type="secondary"):
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
    if st.button("➕ Add Series"):
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
                
                series["data_source"] = st.selectbox(
                    "Data Source",
                    options=["material_balance", "fso_operations"],
                    index=["material_balance", "fso_operations"]. index(
                        series.get("data_source", "material_balance")
                    ),
                    key=f"series_source_{idx}"
                )
            
            with col2:
                series["field"] = st.text_input(
                    "Field Name",
                    value=series. get("field", "Receipt"),
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
        if st.button("💾 Save Configuration", type="primary"):
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


if __name__ == "__main__":
    render_dashboard_customization()