# reporting.py
"""
Reporting Page - User interface for viewing and exporting reports
Users can select from available reports, apply filters, and download in multiple formats
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, date, timedelta
import json

from db import get_session
from models import ReportDefinition, ReportAccess, Location, Tank
from report_engine import ReportEngine
from permission_manager import PermissionManager
from security import SecurityManager
from location_config import LocationConfig
from ui_components import FormBuilder, Notifications, DashboardCard, TableDisplay, apply_custom_css

def get_user_reports(user: dict, location_id: int = None):
    """
    Get all reports accessible to the current user.
    
    Args:
        user: Current user dict
        location_id: Active location ID
    
    Returns:
        List of ReportDefinition objects
    """
    with get_session() as session:
        query = session.query(ReportDefinition).filter(
            ReportDefinition.is_active == True
        )
        
        # Admins see all reports
        if PermissionManager.can_access_management_pages(user):
            reports = query.all()
        else:
            # Regular users see only reports they have access to
            query = query.join(ReportAccess, ReportDefinition.id == ReportAccess.report_id)
            
            # Filter by role, user_id, or location
            query = query.filter(
                (ReportAccess.role == user['role']) |
                (ReportAccess.user_id == user['id']) |
                (ReportAccess.location_id == location_id)
            )
            
            reports = query.distinct().all()
        
        # Convert to list of dicts for easier handling
        result = []
        for r in reports:
            # Safely parse config_json
            config = {}
            if r.config_json:
                try:
                    config = json.loads(r.config_json)
                except (json.JSONDecodeError, TypeError) as e:
                    # Log error and skip invalid report
                    print(f"Warning: Invalid config_json for report {r.id}: {e}")
                    continue
            
            result.append({
                'id': r.id,
                'name': r.name,
                'slug': r.slug,
                'config': config,
                'location_id': r.location_id,
                'created_by': r.created_by,
                'created_at': r.created_at
            })
        
        return result


def render_filter_inputs(filter_configs: list, location_id: int) -> dict:
    """
    Render filter input widgets based on report configuration.
    
    Args:
        filter_configs: List of filter configurations from report config
        location_id: Active location ID
    
    Returns:
        Dictionary of filter values
    """
    filters = {}
    
    FormBuilder.section_header("🔍 Report Filters", "Customize your report parameters")
    
    # Always include date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = FormBuilder.date_field("Start Date", "filter_start_date", required=True)
        if start_date is None:
            start_date = date.today() - timedelta(days=30)
    with col2:
        end_date = FormBuilder.date_field("End Date", "filter_end_date", required=True)
        if end_date is None:
            end_date = date.today()
    
    filters['date_range'] = [start_date, end_date]
    filters['location_id'] = location_id
    
    # Render additional filters from config
    for filter_config in filter_configs:
        field = filter_config.get('field')
        if not field:
            continue  # Skip filters without a field
        
        # Safely handle label generation
        if isinstance(field, str):
            label = filter_config.get('label', field.replace('_', ' ').title())
        else:
            label = filter_config.get('label', 'Filter')
        
        filter_type = filter_config.get('type', 'string')
        operator = filter_config.get('operator', 'equals')
        
        # Skip auto-filled filters
        if filter_config.get('value') in ['user_location', 'auto']:
            continue
        
        # Render appropriate input widget
        if filter_type == 'date':
            filters[field] = st.date_input(label, key=f"filter_{field}", max_value=date.today())
        
        elif filter_type == 'numeric':
            if operator == 'between':
                col1, col2 = st.columns(2)
                with col1:
                    min_val = st.number_input(f"{label} (Min)", key=f"filter_{field}_min")
                with col2:
                    max_val = st.number_input(f"{label} (Max)", key=f"filter_{field}_max")
                filters[field] = [min_val, max_val]
            else:
                filters[field] = st.number_input(label, key=f"filter_{field}")
        
        elif filter_type == 'select':
            options = filter_config.get('options', [])
            filters[field] = st.selectbox(label, options, key=f"filter_{field}")
        
        elif filter_type == 'multiselect':
            options = filter_config.get('options', [])
            filters[field] = st.multiselect(label, options, key=f"filter_{field}")
        
        elif filter_type == 'tank':
            # Load tanks for the location
            with get_session() as session:
                tanks = session.query(Tank).filter(Tank.location_id == location_id).all()
                tank_names = [t.name for t in tanks]
                selected_tank = st.selectbox(label, ['All'] + tank_names, key=f"filter_{field}")
                if selected_tank != 'All':
                    filters[field] = selected_tank
        
        else:
            filters[field] = st.text_input(label, key=f"filter_{field}")
    
    return filters


def render_reporting_page(active_location_id: int, user: dict):
    """
    Main rendering function for the Reporting page.
    
    Args:
        active_location_id: Currently active location ID
        user: Current user dictionary
    """
    st.title("📊 Reporting")
    st.markdown("---")
    
    # Check if user has access to any reports
    available_reports = get_user_reports(user, active_location_id)

    # Apply per-location Reporting tab visibility from Location Settings
    try:
        with get_session() as s:
            cfg = LocationConfig.get_config(s, active_location_id) if active_location_id else None
        if cfg:
            tabs_access = cfg.get("tabs_access", {})
            rep_map = tabs_access.get("Reporting", {})
            if rep_map:
                def _is_enabled(r):
                    slug = r.get('slug') or str(r.get('id'))
                    val = rep_map.get(slug)
                    return True if val is None else bool(val)
                available_reports = [r for r in available_reports if _is_enabled(r)]
    except Exception:
        pass
    
    if not available_reports:
        st.info("📭 No reports are available for you at this time. Please contact your administrator.")
        return
    
    # Show location info
    location_name = "Unknown"
    if active_location_id:
        with get_session() as session:
            loc = session.query(Location).get(active_location_id)
            if loc:
                location_name = loc.name
    
    st.info(f"📍 **Current Location:** {location_name}")
    
    # Report selection
    st.markdown("### 📋 Select Report")
    
    report_options = {r['name']: r for r in available_reports}
    selected_report_name = st.selectbox(
        "Choose a report",
        options=list(report_options.keys()),
        key="selected_report"
    )
    
    if not selected_report_name:
        return
    
    selected_report = report_options[selected_report_name]
    
    st.markdown("---")
    
    # Display report info
    with st.expander("ℹ️ Report Information", expanded=False):
        st.write(f"**Report Name:** {selected_report['name']}")
        st.write(f"**Created By:** {selected_report['created_by']}")
        if selected_report.get('created_at') and hasattr(selected_report['created_at'], 'strftime'):
            st.write(f"**Created On:** {selected_report['created_at'].strftime('%Y-%m-%d')}")
    
    # Get report configuration
    config = selected_report['config']
    
    # Render filters directly above table
    filter_configs = config.get('filters', [])
    user_filters = render_filter_inputs(filter_configs, active_location_id)
    
    # Auto-generate and display report
    try:
        engine = ReportEngine(config)
        df = engine.execute_report(user_filters)
        report_name = selected_report['name'] or "Report"
        if df.empty:
            st.info("No data found for the selected filters.")
            SecurityManager.log_audit(
                None,
                user['username'],
                "REPORT_GENERATE",
                resource_type="Report",
                resource_id=str(selected_report['id']),
                details=f"Generated report '{selected_report['name']}' - No data found",
                user_id=user['id'],
                location_id=active_location_id,
                success=True
            )
            return
    except Exception as e:
        st.error(f"Error generating report: {str(e)}")
        SecurityManager.log_audit(
            None,
            user['username'],
            "REPORT_GENERATE",
            resource_type="Report",
            resource_id=str(selected_report['id']),
            details=f"Failed to generate report '{selected_report['name']}': {str(e)}",
            user_id=user['id'],
            location_id=active_location_id,
            success=False
        )
        return
    
    # Sanitize report_name to ensure it's a valid string
    if not isinstance(report_name, str) or not report_name:
        report_name = "Report"

    st.markdown("---")
    st.markdown(f"### 📋 Data Preview ({len(df)} records)")

    rows_per_page = st.selectbox("Rows per page", [10, 25, 50, 100], index=1)
    rows_per_page = int(rows_per_page)
    total_pages = max(1, (len(df) - 1) // rows_per_page + 1)

    page_key = f"report_page_{selected_report.get('id', 'default')}"
    if page_key not in st.session_state:
        st.session_state[page_key] = 1
    else:
        try:
            st.session_state[page_key] = int(st.session_state[page_key])
        except (ValueError, TypeError):
            st.session_state[page_key] = 1

    if st.session_state[page_key] < 1:
        st.session_state[page_key] = 1
    elif st.session_state[page_key] > total_pages:
        st.session_state[page_key] = total_pages

    nav1, nav2, nav3, nav4, nav5 = st.columns([1, 1, 2, 1, 1])
    with nav1:
        if st.button("⏮️ First"):
            st.session_state[page_key] = 1
    with nav2:
        if st.button("◀️ Previous"):
            current = int(st.session_state[page_key])
            if current > 1:
                st.session_state[page_key] = current - 1
    with nav3:
        st.markdown(
            f"<div style='text-align: center; padding: 8px;'>Page {st.session_state[page_key]} of {total_pages}</div>",
            unsafe_allow_html=True
        )
    with nav4:
        if st.button("Next ▶️"):
            current = int(st.session_state[page_key])
            if current < total_pages:
                st.session_state[page_key] = current + 1
    with nav5:
        if st.button("Last ⏭️"):
            st.session_state[page_key] = total_pages

    current_page_num = int(st.session_state[page_key])
    start_idx = (current_page_num - 1) * rows_per_page
    end_idx = start_idx + rows_per_page

    st.dataframe(
        df.iloc[start_idx:end_idx],
        use_container_width=True,
        height=400
    )

    # Export buttons below the table
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        try:
            engine = ReportEngine(config)
            csv_data = engine.export_csv(df)
            st.download_button(
                label="📥 Download CSV",
                data=csv_data,
                file_name=f"{report_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
                on_click=lambda: SecurityManager.log_audit(
                    None, user['username'], "REPORT_EXPORT",
                    resource_type="Report", resource_id=str(selected_report['id']),
                    details=f"Exported '{report_name}' as CSV ({len(df)} records)",
                    user_id=user['id'], location_id=active_location_id, success=True
                )
            )
        except Exception as e:
            st.error(f"CSV export error: {e}")

    with col2:
        try:
            engine = ReportEngine(config)
            xlsx_data = engine.export_xlsx(df)
            st.download_button(
                label="📊 Download Excel",
                data=xlsx_data,
                file_name=f"{report_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                on_click=lambda: SecurityManager.log_audit(
                    None, user['username'], "REPORT_EXPORT",
                    resource_type="Report", resource_id=str(selected_report['id']),
                    details=f"Exported '{report_name}' as Excel ({len(df)} records)",
                    user_id=user['id'], location_id=active_location_id, success=True
                )
            )
        except Exception as e:
            st.error(f"Excel export error: {e}")

    with col3:
        try:
            engine = ReportEngine(config)
            pdf_data = engine.export_pdf(df, report_name)
            st.download_button(
                label="📄 Download PDF",
                data=pdf_data,
                file_name=f"{report_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                use_container_width=True,
                on_click=lambda: SecurityManager.log_audit(
                    None, user['username'], "REPORT_EXPORT",
                    resource_type="Report", resource_id=str(selected_report['id']),
                    details=f"Exported '{report_name}' as PDF ({len(df)} records)",
                    user_id=user['id'], location_id=active_location_id, success=True
                )
            )
        except Exception as e:
            st.error(f"PDF export error: {e}")

    with col4:
        if st.button("👁️ View PDF", use_container_width=True):
            try:
                engine = ReportEngine(config)
                pdf_base64 = engine.get_pdf_base64(df, report_name)
                components.html(
                    f"""
                    <script>
                    (function(){{
                        const b64 = "{pdf_base64}";
                        const bytes = atob(b64);
                        const len = bytes.length;
                        const out = new Uint8Array(len);
                        for (let i = 0; i < len; i++) {{
                            out[i] = bytes.charCodeAt(i);
                        }}
                        const blob = new Blob([out], {{ type: "application/pdf" }});
                        const url = URL.createObjectURL(blob);
                        const w = window.open(url, "_blank");
                        if (!w) {{
                            alert("Please allow pop-ups to view the PDF.");
                        }}
                        setTimeout(() => URL.revokeObjectURL(url), 60000);
                    }})();
                    </script>
                    """,
                    height=0,
                )
                SecurityManager.log_audit(
                    None, user['username'], "REPORT_VIEW",
                    resource_type="Report", resource_id=str(selected_report['id']),
                    details=f"Viewed PDF of '{report_name}' ({len(df)} records)",
                    user_id=user['id'], location_id=active_location_id, success=True
                )
            except Exception as e:
                st.error(f"PDF open error: {e}")

    numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
    show_totals = bool(config.get('show_totals', True))
    if show_totals and len(numeric_cols) > 0:
        st.markdown("---")
        st.markdown("### 📈 Summary Statistics")
        summary_data = {}
        for col in numeric_cols:
            summary_data[col] = {
                'Total': f"{df[col].sum():,.2f}",
                'Average': f"{df[col].mean():,.2f}",
            }
        summary_df = pd.DataFrame(summary_data).T
        st.dataframe(summary_df, use_container_width=True)
    
    
