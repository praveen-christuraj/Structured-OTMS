# reporting.py
"""
Reporting Page - User interface for viewing and exporting reports
Users can select from available reports, apply filters, and download in multiple formats
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import json

from db import get_session
from models import ReportDefinition, ReportAccess, Location, Tank
from report_engine import ReportEngine
from permission_manager import PermissionManager
from security import SecurityManager

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
    
    st.markdown("### 🔍 Filters")
    
    # Always include date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Start Date",
            value=date.today() - timedelta(days=30),
            key="filter_start_date"
        )
    with col2:
        end_date = st.date_input(
            "End Date",
            value=date.today(),
            key="filter_end_date"
        )
    
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
            filters[field] = st.date_input(label, key=f"filter_{field}")
        
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
    
    # Render filters
    filter_configs = config.get('filters', [])
    user_filters = render_filter_inputs(filter_configs, active_location_id)
    
    st.markdown("---")
    
    # Generate report button
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        generate_btn = st.button("🔍 Generate Report", type="primary", use_container_width=True)
    
    # Initialize session state for report data
    if 'report_data' not in st.session_state:
        st.session_state.report_data = None
    if 'report_name' not in st.session_state:
        st.session_state.report_name = None
    
    # Generate report
        # Generate report
    if generate_btn:
        with st.spinner("Generating report..."):
            try:
                # Create report engine
                engine = ReportEngine(config)
                
                # Execute report
                df = engine.execute_report(user_filters)
                
                # Store in session state
                st.session_state.report_data = df
                st.session_state.report_name = selected_report['name']
                
                if df.empty:
                    st.warning("⚠️ No data found for the selected filters.")
                    # Log report generation (no data)
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
                else:
                    st.success(f"✅ Report generated successfully! Found {len(df)} records.")
                    # Log successful report generation
                    SecurityManager.log_audit(
                        None,
                        user['username'],
                        "REPORT_GENERATE",
                        resource_type="Report",
                        resource_id=str(selected_report['id']),
                        details=f"Generated report '{selected_report['name']}' - {len(df)} records",
                        user_id=user['id'],
                        location_id=active_location_id,
                        success=True
                    )
            
            except Exception as e:
                st.error(f"❌ Error generating report: {str(e)}")
                st.session_state.report_data = None
                # Log error
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
    
    # Display report results
    if st.session_state.report_data is not None and not st.session_state.report_data.empty:
        df = st.session_state.report_data
        report_name = st.session_state.report_name or "Report"
        
        # Sanitize report_name to ensure it's a valid string
        if not isinstance(report_name, str) or not report_name:
            report_name = "Report"
        
        st.markdown("---")
        st.markdown(f"### 📊 Report Results ({len(df)} records)")
        
        # Export buttons
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # CSV Export
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
            # Excel Export
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
            # PDF Export
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
            # PDF Preview
            if st.button("👁️ Preview PDF", use_container_width=True):
                st.session_state.show_pdf_preview = True
                # Log PDF preview
                SecurityManager.log_audit(
                    None, user['username'], "REPORT_VIEW",
                    resource_type="Report", resource_id=str(selected_report['id']),
                    details=f"Viewed PDF preview of '{report_name}' ({len(df)} records)",
                    user_id=user['id'], location_id=active_location_id, success=True
                )
        
        # Show PDF preview in iframe if requested
        if st.session_state.get('show_pdf_preview', False):
            try:
                engine = ReportEngine(config)
                pdf_base64 = engine.get_pdf_base64(df, report_name)
                st.markdown("### 📄 PDF Preview")
                st.markdown(
                    f'<iframe src="data:application/pdf;base64,{pdf_base64}" '
                    f'width="100%" height="800px" style="border: 1px solid #ddd;"></iframe>',
                    unsafe_allow_html=True
                )
                if st.button("✖️ Close Preview"):
                    st.session_state.show_pdf_preview = False
                    st.rerun()
            except Exception as e:
                st.error(f"PDF preview error: {e}")
        
        # Display data table with pagination
        st.markdown("---")
        st.markdown("### 📋 Data Preview")
        
        # Pagination controls
        rows_per_page = st.selectbox("Rows per page", [10, 25, 50, 100], index=1)
        rows_per_page = int(rows_per_page)  # Ensure it's an integer
        
        total_pages = max(1, (len(df) - 1) // rows_per_page + 1)
        
        # Initialize or validate current_page with proper error handling
        if 'current_page' not in st.session_state:
            st.session_state.current_page = 1
        else:
            # Safely convert to integer, reset to 1 if invalid
            try:
                st.session_state.current_page = int(st.session_state.current_page)
            except (ValueError, TypeError):
                st.session_state.current_page = 1
        
        # Ensure current_page is within valid range
        if st.session_state.current_page < 1:
            st.session_state.current_page = 1
        elif st.session_state.current_page > total_pages:
            st.session_state.current_page = total_pages
        
        # Page navigation
        col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
        
        with col1:
            if st.button("⏮️ First"):
                st.session_state.current_page = 1
        
        with col2:
            if st.button("◀️ Previous"):
                current = int(st.session_state.current_page)
                if current > 1:
                    st.session_state.current_page = current - 1
        
        with col3:
            st.markdown(f"<div style='text-align: center; padding: 8px;'>Page {st.session_state.current_page} of {total_pages}</div>", 
                       unsafe_allow_html=True)
        
        with col4:
            if st.button("Next ▶️"):
                current = int(st.session_state.current_page)
                if current < total_pages:
                    st.session_state.current_page = current + 1
        
        with col5:
            if st.button("Last ⏭️"):
                st.session_state.current_page = total_pages
        
        # Display paginated data
        current_page = int(st.session_state.current_page)
        start_idx = (current_page - 1) * rows_per_page
        end_idx = start_idx + rows_per_page
        
        st.dataframe(
            df.iloc[start_idx:end_idx],
            use_container_width=True,
            height=400
        )
        
        # Show summary statistics for numeric columns
        numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
        if len(numeric_cols) > 0:
            st.markdown("---")
            st.markdown("### 📈 Summary Statistics")
            
            summary_data = {}
            for col in numeric_cols:
                summary_data[col] = {
                    'Total': f"{df[col].sum():,.2f}",
                    'Average': f"{df[col].mean():,.2f}",
                    'Min': f"{df[col].min():,.2f}",
                    'Max': f"{df[col].max():,.2f}",
                }
            
            summary_df = pd.DataFrame(summary_data).T
            st.dataframe(summary_df, use_container_width=True)
    
    elif st.session_state.report_data is not None and st.session_state.report_data.empty:
        st.info("ℹ️ No data available for the selected filters. Try adjusting your filter criteria.")