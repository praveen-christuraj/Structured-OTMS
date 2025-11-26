"""
Dashboard Widget Renderers
Handles rendering of various dashboard widgets
"""

import streamlit as st
import pandas as pd
import altair as alt
from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional, List
import streamlit.components.v1 as components


class WidgetRenderer:
    """Base class for widget renderers"""
    
    @staticmethod
    def render_stat_card(
        label: str,
        value: Any,
        unit: str = "",
        prev_value: Optional[float] = None,
        style: Dict = None,
        show_delta: bool = False,
        display_date: Optional[date] = None
    ):
        """Render a statistics card"""
        if style is None:
            style = {
                "background": "white",
                "border_radius": 10,
                "border_color": "#667eea",
                "border_width": 4,
                "padding": "1rem",
                "value_color": "#667eea",
                "label_color": "#666",
                "value_size": "1.6rem",
                "label_size": "0.8rem"
            }
        
        def _fmt(v):
            if v is None:
                return "-"
            try:
                return f"{float(v):,.0f}"
            except:
                return str(v)
        
        value_html = _fmt(value)
        if unit:
            value_html += f" {unit}"
        
        delta_html = ""
        if show_delta and prev_value is not None and value is not None:
            try:
                diff = float(value) - float(prev_value)
                if abs(diff) < 1e-6:
                    delta_html = f"<span style='color:#6c757d;margin-left:6px;font-size:0.95rem;'>&harr; 0</span>"
                else:
                    arrow = "&uarr;" if diff > 0 else "&darr;"
                    color = "#198754" if diff > 0 else "#dc3545"
                    delta_html = f"<span style='color:{color};margin-left:6px;font-size:0.95rem;'>{arrow} {abs(diff):,.0f}</span>"
            except:
                pass
        
        card_html = f"""
        <div style="
            background: {style. get('background', 'white')};
            padding: {style.get('padding', '1rem')};
            border-radius: {style.get('border_radius', 10)}px;
            box-shadow: {style.get('shadow', '0 2px 8px rgba(0,0,0,0.1)')};
            border-left: {style.get('border_width', 4)}px solid {style.get('border_color', '#667eea')};
        ">
            <div style="
                color: {style.get('label_color', '#666')};
                font-size: {style.get('label_size', '0.8rem')};
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 1px;
            ">{label}</div>
            <div style="
                font-size: {style.get('value_size', '1.6rem')};
                font-weight: bold;
                color: {style. get('value_color', '#667eea')};
                margin: 0.5rem 0;
            ">{value_html} {delta_html}</div>
            <div style="color:#6c757d;font-size:0.75rem;">{display_date.strftime('%d-%b-%Y') if display_date else datetime.now().strftime('%d-%b-%Y')}</div>
        </div>
        """
        
        st.markdown(card_html, unsafe_allow_html=True)
    
    @staticmethod
    def render_tank_visual(
        tank_name: str,
        tank_code: str,
        current_stock: float,
        capacity: float,
        product: str,
        status: str,
        style: Dict = None,
        tank_id: int = None,
        status_dropdown_enabled: bool = False
    ):
        """Render 3D cylindrical tank visual"""
        if style is None:
            style = {
                "height": 200,
                "border_radius": 10,
                "show_status": True,
                "show_percentage": True
            }
        
        fill_percentage = min((current_stock / max(capacity, 1) * 100), 100) if capacity > 0 else 0
        
        # Dynamic colors based on fill level
        if fill_percentage >= 80:
            liquid_color = "#28a745"
            liquid_dark = "#1e7e34"
            status_emoji = "🟢"
        elif fill_percentage >= 50:
            liquid_color = "#ffc107"
            liquid_dark = "#d39e00"
            status_emoji = "🟡"
        elif fill_percentage >= 20:
            liquid_color = "#fd7e14"
            liquid_dark = "#dc3545"
            status_emoji = "🟠"
        else:
            liquid_color = "#dc3545"
            liquid_dark = "#bd2130"
            status_emoji = "🔴"
        
        tank_height = style.get("height", 140)
        liquid_height = (fill_percentage / 100) * tank_height
        liquid_y = tank_height - liquid_height
        
        svg_code = f'''
        <svg width="100%" height="{tank_height + 60}" viewBox="0 0 140 {tank_height + 60}" xmlns="http://www.w3. org/2000/svg">
            <defs>
                <linearGradient id="tankGrad_{tank_code}" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" style="stop-color:#c0c0c0;stop-opacity:1" />
                    <stop offset="50%" style="stop-color:#e8e8e8;stop-opacity:1" />
                    <stop offset="100%" style="stop-color:#c0c0c0;stop-opacity:1" />
                </linearGradient>
                <linearGradient id="liquidGrad_{tank_code}" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" style="stop-color:{liquid_dark};stop-opacity:0.9" />
                    <stop offset="50%" style="stop-color:{liquid_color};stop-opacity:1" />
                    <stop offset="100%" style="stop-color:{liquid_dark};stop-opacity:0.9" />
                </linearGradient>
                <radialGradient id="topGrad_{tank_code}" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" style="stop-color:#ffffff;stop-opacity:1" />
                    <stop offset="100%" style="stop-color:#d0d0d0;stop-opacity:1" />
                </radialGradient>
                <radialGradient id="bottomGrad_{tank_code}" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" style="stop-color:#a0a0a0;stop-opacity:1" />
                    <stop offset="100%" style="stop-color:#707070;stop-opacity:1" />
                </radialGradient>
            </defs>
            
            <rect x="85" y="5" width="50" height="18" rx="9" fill="{liquid_color}" opacity="0.9"/>
            <text x="110" y="17" text-anchor="middle" fill="white" font-size="10" font-weight="bold">
                {current_stock/1000:.1f}K
            </text>
            
            <ellipse cx="70" cy="30" rx="40" ry="12" fill="url(#topGrad_{tank_code})" stroke="#999" stroke-width="1.5"/>
            <rect x="30" y="30" width="80" height="{tank_height}" fill="url(#tankGrad_{tank_code})" stroke="#999" stroke-width="1.5"/>
            <rect x="30" y="{30 + liquid_y}" width="80" height="{liquid_height}" fill="url(#liquidGrad_{tank_code})"/>
            <ellipse cx="70" cy="{30 + liquid_y}" rx="40" ry="12" fill="{liquid_color}" opacity="0.8"/>
            
            <text x="70" y="{30 + tank_height/2 + 6}" text-anchor="middle" fill="white" font-size="24" font-weight="bold" 
                style="text-shadow: 2px 2px 4px rgba(0,0,0,0.7);">
                {fill_percentage:.0f}%
            </text>
            
            <ellipse cx="70" cy="{30 + tank_height}" rx="40" ry="12" fill="url(#bottomGrad_{tank_code})" stroke="#666" stroke-width="1.5"/>
            <ellipse cx="70" cy="{33 + tank_height}" rx="42" ry="6" fill="black" opacity="0.2"/>
        </svg>
        '''
        
        with st.container(border=True):
            st.markdown(
                f"<div style='text-align: center; font-weight: bold; font-size: 0.9rem; margin-bottom: 0.2rem;'>{tank_name}</div>",
                unsafe_allow_html=True
            )
            
            # Show current status below tank name
            if style.get("show_status", True):
                st.markdown(
                    f"<div style='text-align: center; font-size: 0.75rem; color:#666; margin-bottom: 0.5rem;'>Status: <b>{status.title()}</b></div>",
                    unsafe_allow_html=True
                )
            
            components.html(svg_code, height=tank_height + 60)
            
            st.markdown(f"""
                <div style='font-size: 0.75rem; line-height: 1.3; color: #666;'>
                    <div style='display: flex; justify-content: space-between; margin-bottom: 0.2rem;'>
                        <span>Stock:</span>
                        <strong style='color: {liquid_color};'>{current_stock:,.0f}</strong>
                    </div>
                    <div style='display: flex; justify-content: space-between; margin-bottom: 0.2rem;'>
                        <span>Capacity:</span>
                        <strong>{capacity:,.0f}</strong>
                    </div>
                    <div style='display: flex; justify-content: space-between; margin-bottom: 0.2rem;'>
                        <span>Available:</span>
                        <strong>{(capacity - current_stock):,.0f}</strong>
                    </div>
                    <div style='display: flex; justify-content: space-between; margin-bottom: 0.2rem;'>
                        <span>Level:</span>
                        <strong style='color: {liquid_color};'>{status_emoji} {fill_percentage:.1f}%</strong>
                    </div>
                    <div style='text-align: center; padding-top: 0.3rem; border-top: 1px solid #dee2e6; margin-top: 0.3rem;'>
                        <div style='font-size: 0.7rem;'>{product}</div>
                        <div style='font-size: 0.65rem; color: #999;'>{tank_code}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Status dropdown at the bottom
            if status_dropdown_enabled and tank_id:
                from db import get_session
                from models import TankOpStatus, TankDailyStatus
                from datetime import date as dt_date
                
                status_options = ["IDLE", "RECEIVING", "DISPATCHING", "MAINTENANCE", "SETTLING", "DRAINING"]
                current_status = status.upper() if status else "IDLE"
                if current_status not in status_options:
                    current_status = "IDLE"
                
                new_status = st.selectbox(
                    "Update Status",
                    options=status_options,
                    index=status_options.index(current_status),
                    key=f"tank_status_{tank_id}"
                )
                
                if new_status != current_status:
                    with get_session() as s:
                        today = dt_date.today()
                        daily_status = s.query(TankDailyStatus).filter(
                            TankDailyStatus.tank_id == tank_id,
                            TankDailyStatus.date == today
                        ).first()
                        
                        if daily_status:
                            daily_status.op_status = TankOpStatus[new_status]
                        else:
                            daily_status = TankDailyStatus(
                                tank_id=tank_id,
                                date=today,
                                op_status=TankOpStatus[new_status]
                            )
                            s.add(daily_status)
                        
                        s.commit()
                        st.success(f"Status updated to {new_status}")
                        st.rerun()
    
    @staticmethod
    def render_trend_chart(
        df: pd.DataFrame,
        series_config: List[Dict],
        style: Dict = None
    ):
        """Render trend chart"""
        if df is None or df.empty:
            st.info("No data available for trend chart")
            return
        
        if style is None:
            style = {
                "height": 360,
                "show_markers": True,
                "show_labels": True,
                "show_totals_card": True
            }
        
        # Ensure DateTS column
        if "DateTS" not in df.columns and "Date" in df.columns:
            df["DateTS"] = pd. to_datetime(df["Date"])
        
        # Build long-form dataframe for altair
        frames = []
        for series in series_config:
            if series["field"] in df.columns:
                sub = df[["DateTS", series["field"]]].copy()
                sub = sub.rename(columns={series["field"]: "Value"})
                sub["Series"] = series["name"]
                sub["Color"] = series. get("color", "#667eea")
                frames.append(sub)
        
        if not frames:
            st.info("No series data available")
            return
        
        plot_df = pd.concat(frames, ignore_index=True)
        
        # Calculate domain
        max_val = plot_df["Value"].max()
        y_max = float(max_val if pd.notna(max_val) else 1.0) * 1.25
        
        base = alt.Chart(plot_df). properties(height=style.get("height", 360))
        
        # Lines
        lines = base.mark_line(strokeWidth=2).encode(
            x=alt.X("DateTS:T", axis=alt.Axis(title="Date", format="%d-%b", labelAngle=0)),
            y=alt.Y("Value:Q", axis=alt.Axis(title="Quantity in bbls"), scale=alt.Scale(domain=[0, y_max])),
            color=alt.Color("Series:N", legend=alt.Legend(title=None, orient="top"))
        )
        
        # Points
        if style.get("show_markers", True):
            points = base.mark_point(shape="triangle-up", filled=False, size=60).encode(
                x="DateTS:T",
                y="Value:Q",
                color=alt.Color("Series:N", legend=None)
            )
        else:
            points = alt.Chart(pd.DataFrame())
        
        # Labels
        if style.get("show_labels", True):
            labels = base. mark_text(dy=-12, color="black", fontSize=11).encode(
                x="DateTS:T",
                y="Value:Q",
                text=alt.Text("Value:Q", format=",.0f"),
                color=alt.Color("Series:N", legend=None)
            )
        else:
            labels = alt.Chart(pd.DataFrame())
        
        chart = (lines + points + labels).configure_view(strokeOpacity=0)
        
        st.altair_chart(chart, use_container_width=True)


class DashboardRenderer:
    """Main dashboard renderer"""
    
    @staticmethod
    def render_dashboard_with_sections(config: Dict, location_id: int, user: dict):
        """Render dashboard with section-based date filters"""
        from db import get_session
        from models import Tank, TankTransaction, OTRRecord
        
        # Get sections configuration
        sections = config.get("sections", [])
        
        # If no sections, fall back to old method
        if not sections:
            selected_date = st.date_input(
                "Dashboard Date",
                value=st.session_state.get("dash_date", date.today()),
                key="dash_date"
            )
            return DashboardRenderer.render_dashboard(config, location_id, selected_date)
        
        # Sort sections by order
        sections = sorted([s for s in sections if s.get("enabled", True)], key=lambda x: x.get("order", 999))
        
        # Render each section with its own date filter
        for section in sections:
            section_id = section.get("id", "unknown")
            section_name = section.get("name", "Section")
            section_type = section.get("type", "custom")
            date_filter_cfg = section.get("date_filter", {})
            
            # Render section header
            st.markdown(f"### {section_name}")
            
            # Render date filter for this section
            section_date_value = None
            if date_filter_cfg.get("enabled", True):
                filter_type = date_filter_cfg.get("type", "single")
                filter_label = date_filter_cfg.get("label", "Date")
                
                col1, col2 = st.columns([1, 3])
                
                with col1:
                    if filter_type == "single":
                        section_date_value = st.date_input(
                            filter_label,
                            value=st.session_state.get(f"section_date_{section_id}", date.today()),
                            key=f"section_date_{section_id}"
                        )
                    elif filter_type == "range":
                        default_days = date_filter_cfg.get("default_days", 30)
                        default_start = date.today() - timedelta(days=default_days)
                        start_date = st.date_input(
                            f"{filter_label} - Start",
                            value=st.session_state.get(f"section_start_{section_id}", default_start),
                            key=f"section_start_{section_id}"
                        )
                        end_date = st.date_input(
                            f"{filter_label} - End",
                            value=st.session_state.get(f"section_end_{section_id}", date.today()),
                            key=f"section_end_{section_id}"
                        )
                        section_date_value = (start_date, end_date)
                    elif filter_type == "month":
                        month_col, year_col = st.columns(2)
                        with month_col:
                            month = st.selectbox(
                                "Month",
                                options=list(range(1, 13)),
                                format_func=lambda x: datetime(2000, x, 1).strftime("%B"),
                                index=date.today().month - 1,
                                key=f"section_month_{section_id}"
                            )
                        with year_col:
                            year = st.number_input(
                                "Year",
                                min_value=2020,
                                max_value=2050,
                                value=date.today().year,
                                key=f"section_year_{section_id}"
                            )
                        section_date_value = (month, year)
                    elif filter_type == "year":
                        year = st.number_input(
                            filter_label,
                            min_value=2020,
                            max_value=2050,
                            value=st.session_state.get(f"section_year_{section_id}", date.today().year),
                            key=f"section_year_input_{section_id}"
                        )
                        section_date_value = year
                    else:  # none
                        section_date_value = date.today()
                
                with col2:
                    if filter_type == "single":
                        st.write(f"Showing data for **{section_date_value.strftime('%d-%b-%Y')}**")
                    elif filter_type == "range":
                        st.write(f"Showing data from **{section_date_value[0].strftime('%d-%b-%Y')}** to **{section_date_value[1].strftime('%d-%b-%Y')}**")
                    elif filter_type == "month":
                        st.write(f"Showing data for **{datetime(section_date_value[1], section_date_value[0], 1).strftime('%B %Y')}**")
                    elif filter_type == "year":
                        st.write(f"Showing data for year **{section_date_value}**")
            else:
                section_date_value = date.today()
            
            # Render section content based on type
            try:
                if section_type == "summary_cards":
                    DashboardRenderer._render_summary_cards_section(config, location_id, section_date_value)
                elif section_type == "tank_visuals":
                    DashboardRenderer._render_tank_visuals_section(config, location_id, section_date_value)
                elif section_type == "monthly_data":
                    DashboardRenderer._render_monthly_data_section(config, location_id, section_date_value)
                elif section_type == "trend_chart":
                    DashboardRenderer._render_trend_chart_section(config, location_id, section_date_value)
                else:
                    st.info(f"Custom section '{section_name}' - implementation pending")
            except Exception as e:
                st.error(f"Error rendering section '{section_name}': {e}")
            
            st.markdown("---")
    
    @staticmethod
    def _render_summary_cards_section(config: Dict, location_id: int, section_date):
        """Render summary cards section"""
        if isinstance(section_date, tuple):
            selected_date = section_date[0]  # Use start date for cards
        else:
            selected_date = section_date if isinstance(section_date, date) else date.today()
        
        cards = config["layout"]["summary_cards"]["cards"]
        num_cols = config["layout"]["summary_cards"]["columns"]
        
        cols = st.columns(num_cols)
        for idx, card in enumerate(cards[:num_cols]):
            with cols[idx]:
                value = DashboardRenderer._fetch_card_data(card, location_id, selected_date, config)
                prev_value = None
                if card.get("show_delta", False):
                    prev_value = DashboardRenderer._fetch_card_data(
                        card, location_id, selected_date - timedelta(days=1), config
                    )
                
                WidgetRenderer.render_stat_card(
                    label=card["name"],
                    value=value,
                    unit=card.get("unit", ""),
                    prev_value=prev_value,
                    style=config.get("styles", {}).get("card"),
                    show_delta=card.get("show_delta", False),
                    display_date=selected_date
                )
    
    @staticmethod
    def _render_tank_visuals_section(config: Dict, location_id: int, section_date):
        """Render tank visuals section"""
        from db import get_session
        from models import Tank, TankTransaction, OTRRecord, TankDailyStatus
        
        if isinstance(section_date, tuple):
            selected_date = section_date[0]
        else:
            selected_date = section_date if isinstance(section_date, date) else date.today()
        
        tank_style = config["layout"]["tank_visuals"]["style"]
        num_cols = config["layout"]["tank_visuals"]["columns"]
        
        with get_session() as s:
            tank_configs = config["layout"]["tank_visuals"].get("tanks", [])
            
            if tank_configs:
                enabled_tank_configs = [tc for tc in tank_configs if tc.get("enabled", True)]
                
                if enabled_tank_configs:
                    tank_ids = [tc["tank_id"] for tc in enabled_tank_configs]
                    tanks = s.query(Tank).filter(
                        Tank.location_id == location_id,
                        Tank.id.in_(tank_ids)
                    ).all()
                    
                    tank_lookup = {tank.id: tank for tank in tanks}
                    tank_rows = [enabled_tank_configs[i:i+num_cols] for i in range(0, len(enabled_tank_configs), num_cols)]
                    
                    for tank_row in tank_rows:
                        cols = st.columns(len(tank_row))
                        for idx, tank_cfg in enumerate(tank_row):
                            tank = tank_lookup.get(tank_cfg["tank_id"])
                            if tank:
                                with cols[idx]:
                                    current_stock = DashboardRenderer._fetch_tank_data(
                                        tank, tank_cfg, location_id, selected_date, s
                                    )
                                    
                                    display_name = tank_cfg.get("display_name") or tank.name
                                    
                                    # Fetch operational status from TankDailyStatus
                                    daily_status = s.query(TankDailyStatus).filter(
                                        TankDailyStatus.tank_id == tank.id,
                                        TankDailyStatus.date == selected_date
                                    ).first()
                                    
                                    if daily_status:
                                        tank_status = daily_status.op_status.value
                                    else:
                                        tank_status = "IDLE"
                                    
                                    status_dropdown_enabled = config["layout"]["tank_visuals"].get("status_dropdown_enabled", False)
                                    
                                    WidgetRenderer.render_tank_visual(
                                        tank_name=display_name,
                                        tank_code=f"T-{tank.id}",
                                        current_stock=current_stock,
                                        capacity=float(tank.capacity_bbl or 0.0),
                                        product=tank.product or "N/A",
                                        status=tank_status,
                                        style=tank_style,
                                        tank_id=tank.id,
                                        status_dropdown_enabled=status_dropdown_enabled
                                    )
                else:
                    st.info("No tanks enabled for display. Configure in Dashboard Customization.")
            else:
                st.info("No tanks configured. Go to Dashboard Customization to add tank visuals.")
    
    @staticmethod
    def _fetch_tank_data(tank, tank_cfg, location_id: int, selected_date: date, session) -> float:
        """Fetch tank data based on configured data source"""
        from models import TankTransaction, OTRRecord
        
        data_source = tank_cfg.get("data_source", "otr")
        field = tank_cfg.get("field", "nsv_bbl")
        
        if data_source == "otr":
            latest_txn = (
                session.query(TankTransaction.ticket_id)
                .filter(
                    TankTransaction.tank_id == tank.id,
                    TankTransaction.date <= selected_date
                )
                .order_by(
                    TankTransaction.date.desc(),
                    TankTransaction.time.desc()
                )
                .first()
            )
            
            if latest_txn and latest_txn.ticket_id:
                otr = session.query(OTRRecord).filter(
                    OTRRecord.ticket_id == latest_txn.ticket_id
                ).first()
                if otr:
                    return float(getattr(otr, field, 0) or 0.0)
        
        elif data_source == "tank_transaction":
            # Fetch from tank transactions
            latest_txn = (
                session.query(TankTransaction)
                .filter(
                    TankTransaction.tank_id == tank.id,
                    TankTransaction.date <= selected_date
                )
                .order_by(
                    TankTransaction.date.desc(),
                    TankTransaction.time.desc()
                )
                .first()
            )
            if latest_txn:
                return float(getattr(latest_txn, field, 0) or 0.0)
        
        return 0.0
    
    @staticmethod
    def _render_monthly_data_section(config: Dict, location_id: int, section_date):
        """Render monthly data section"""
        st.info("Monthly data section - implementation pending")
    
    @staticmethod
    def _render_trend_chart_section(config: Dict, location_id: int, section_date):
        """Render trend chart section"""
        st.info("Trend chart section - implementation pending")
    
    @staticmethod
    def render_dashboard(config: Dict, location_id: int, selected_date: date):
        """Render complete dashboard based on configuration"""
        from db import get_session
        from models import Tank, TankTransaction, OTRRecord
        
        # Summary Cards
        if config["layout"]["summary_cards"]["enabled"]:
            st.markdown("### 📊 Summary Statistics")
            cards = config["layout"]["summary_cards"]["cards"]
            num_cols = config["layout"]["summary_cards"]["columns"]
            
            cols = st.columns(num_cols)
            for idx, card in enumerate(cards[:num_cols]):
                with cols[idx]:
                    # Fetch data based on data_source
                    value = DashboardRenderer._fetch_card_data(
                        card, location_id, selected_date
                    )
                    prev_value = None
                    if card. get("show_delta", False):
                        prev_value = DashboardRenderer._fetch_card_data(
                            card, location_id, selected_date - timedelta(days=1)
                        )
                    
                    WidgetRenderer.render_stat_card(
                        label=card["name"],
                        value=value,
                        unit=card.get("unit", ""),
                        prev_value=prev_value,
                        style=config. get("styles", {}). get("card"),
                        show_delta=card.get("show_delta", False)
                    )
        
        # Tank Visuals
        if config["layout"]["tank_visuals"]["enabled"]:
            st.markdown("### 🛢️ Tank Stock Levels")
            tank_style = config["layout"]["tank_visuals"]["style"]
            num_cols = config["layout"]["tank_visuals"]["columns"]
            
            with get_session() as s:
                # Get configured tanks list
                tank_configs = config["layout"]["tank_visuals"].get("tanks", [])
                
                if tank_configs:
                    # Filter only enabled tanks
                    enabled_tank_configs = [tc for tc in tank_configs if tc.get("enabled", True)]
                    
                    if enabled_tank_configs:
                        # Get tank objects
                        tank_ids = [tc["tank_id"] for tc in enabled_tank_configs]
                        tanks = s.query(Tank).filter(
                            Tank.location_id == location_id,
                            Tank.id.in_(tank_ids)
                        ).all()
                        
                        # Create tank lookup
                        tank_lookup = {tank.id: tank for tank in tanks}
                        
                        # Display tanks in configured order
                        tank_rows = [enabled_tank_configs[i:i+num_cols] for i in range(0, len(enabled_tank_configs), num_cols)]
                        
                        for tank_row in tank_rows:
                            cols = st.columns(len(tank_row))
                            for idx, tank_cfg in enumerate(tank_row):
                                tank = tank_lookup.get(tank_cfg["tank_id"])
                                if tank:
                                    with cols[idx]:
                                        # Get current stock
                                        latest_txn = (
                                            s.query(TankTransaction.ticket_id)
                                            .filter(
                                                TankTransaction.tank_id == tank.id,
                                                TankTransaction.date <= selected_date
                                            )
                                            .order_by(
                                                TankTransaction.date.desc(),
                                                TankTransaction.time.desc()
                                            )
                                            .first()
                                        )
                                        
                                        current_stock = 0.0
                                        if latest_txn and latest_txn.ticket_id:
                                            otr = s.query(OTRRecord).filter(
                                                OTRRecord.ticket_id == latest_txn.ticket_id
                                            ).first()
                                            if otr:
                                                current_stock = float(otr.nsv_bbl or 0.0)
                                        
                                        # Use display name from config or tank name
                                        display_name = tank_cfg.get("display_name") or tank.name
                                        
                                        WidgetRenderer.render_tank_visual(
                                            tank_name=display_name,
                                            tank_code=f"T-{tank.id}",
                                            current_stock=current_stock,
                                            capacity=float(tank.capacity_bbl or 0.0),
                                            product=tank.product or "N/A",
                                            status=str(tank.status or "UNKNOWN"),
                                            style=tank_style
                                        )
                    else:
                        st.info("No tanks enabled for display. Configure in Dashboard Customization.")
                else:
                    st.info("No tanks configured. Go to Dashboard Customization to add tank visuals.")        # Monthly Data
        if config["layout"]["monthly_data"]["enabled"]:
            st.markdown("### 📊 Monthly Data")
            st.info("Monthly data section - configure in Dashboard Customization")
        
        # Trend Chart
        if config["layout"]["trend_chart"]["enabled"]:
            st.markdown("### 📈 Production & Evacuation Trend")
            st.info("Trend chart section - configure in Dashboard Customization")
    
    @staticmethod
    def _fetch_card_data(card_config: Dict, location_id: int, target_date: date, config: Dict = None) -> Optional[float]:
        """Fetch data for a card based on configuration"""
        data_source = card_config.get("data_source")
        
        if data_source == "calculated":
            calculation = card_config.get("calculation")
            if calculation == "ullage":
                return DashboardRenderer._calculate_ullage(location_id, target_date)
            elif calculation == "pumpable":
                return DashboardRenderer._calculate_pumpable(location_id, target_date, config)
        
        elif data_source == "material_balance":
            field = card_config.get("field")
            return DashboardRenderer._fetch_mb_data(location_id, target_date, field)
        
        elif data_source == "fso_operations":
            field = card_config.get("field")
            return DashboardRenderer._fetch_fso_data(location_id, target_date, field)
        
        return None
    
    @staticmethod
    def _calculate_ullage(location_id: int, target_date: date) -> float:
        """Calculate ullage available"""
        from db import get_session
        from models import Tank, TankTransaction, OTRRecord
        
        ullage = 0.0
        with get_session() as s:
            tanks = s.query(Tank).filter(Tank.location_id == location_id).all()
            for tank in tanks:
                capacity = float(tank.capacity_bbl or 0.0)
                
                latest = (
                    s.query(TankTransaction.ticket_id)
                    .filter(
                        TankTransaction.tank_id == tank.id,
                        TankTransaction.date <= target_date
                    )
                    .order_by(
                        TankTransaction.date.desc(),
                        TankTransaction.time.desc()
                    )
                    .first()
                )
                
                stock = 0.0
                if latest and latest.ticket_id:
                    otr = s.query(OTRRecord).filter(
                        OTRRecord.ticket_id == latest.ticket_id
                    ).first()
                    if otr:
                        stock = float(otr.nsv_bbl or 0.0)
                
                ullage += max(capacity - stock, 0.0)
    
        return ullage * 0.90
    
    @staticmethod
    def _calculate_pumpable(location_id: int, target_date: date, config: Dict = None) -> float:
        """Calculate pumpable stock based on configuration"""
        from db import get_session
        from models import Tank, TankTransaction, OTRRecord, TankDailyStatus
        
        # Get pumpable configuration
        if config and "pumpable_config" in config.get("layout", {}).get("tank_visuals", {}):
            pumpable_cfg = config["layout"]["tank_visuals"]["pumpable_config"]
        else:
            pumpable_cfg = {
                "enabled": True,
                "pumpable_statuses": ["IDLE", "READY", "DISPATCHING"],
                "pumpable_factor": 0.85
            }
        
        if not pumpable_cfg.get("enabled", True):
            return 0.0
        
        allowed_statuses = [s.upper() for s in pumpable_cfg.get("pumpable_statuses", ["IDLE", "READY", "DISPATCHING"])]
        pumpable_factor = pumpable_cfg.get("pumpable_factor", 0.85)
        
        pumpable = 0.0
        
        with get_session() as s:
            tanks = s.query(Tank).filter(Tank.location_id == location_id).all()
            for tank in tanks:
                latest = (
                    s.query(TankTransaction.ticket_id)
                    .filter(
                        TankTransaction.tank_id == tank.id,
                        TankTransaction.date <= target_date
                    )
                    .order_by(
                        TankTransaction.date.desc(),
                        TankTransaction.time.desc()
                    )
                    .first()
                )
                
                stock = 0.0
                if latest and latest.ticket_id:
                    otr = s.query(OTRRecord).filter(
                        OTRRecord.ticket_id == latest.ticket_id
                    ).first()
                    if otr:
                        stock = float(otr.nsv_bbl or 0.0)
                
                # Get operational status from TankDailyStatus
                daily_status = s.query(TankDailyStatus).filter(
                    TankDailyStatus.tank_id == tank.id,
                    TankDailyStatus.date == target_date
                ).first()
                
                if daily_status:
                    status = daily_status.op_status.value.upper()
                else:
                    status = "IDLE"
                
                if status in allowed_statuses:
                    pumpable += stock
        
        return pumpable * pumpable_factor
    
    @staticmethod
    def _fetch_mb_data(location_id: int, target_date: date, field: str) -> Optional[float]:
        """Fetch material balance data"""
        try:
            from material_balance_calculator import MaterialBalanceCalculator
            from location_manager import LocationManager
            from db import get_session
            
            with get_session() as s:
                loc = LocationManager.get_location_by_id(s, location_id)
                if not loc:
                    return None
                
                rows = MaterialBalanceCalculator.calculate_material_balance(
                    entries=None,
                    location_code=loc.code. upper(),
                    date_from=target_date,
                    date_to=target_date,
                    location_id=location_id,
                    debug=False
                )
                
                if rows:
                    df = pd.DataFrame(rows)
                    if field in df.columns:
                        return float(pd.to_numeric(df[field], errors="coerce"). fillna(0). sum())
        except Exception:
            pass
        
        return None
    
    @staticmethod
    def _fetch_fso_data(location_id: int, target_date: date, field: str) -> Optional[float]:
        """Fetch FSO operations data"""
        # Implementation for FSO data fetching
        return None
