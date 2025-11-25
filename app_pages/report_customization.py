# app_pages/report_customization.py
"""
Report Customization Page - Build custom reports with dynamic data source selection
"""

import streamlit as st
import json
from datetime import datetime
from db import get_session
from models import ReportDefinition, ReportAccess, Location
from report_engine import get_available_data_sources, get_columns_for_source
from permission_manager import PermissionManager


def render_report_customization_page(user: dict, active_location_id: int):
    """Main rendering function for Report Customization page"""
    
    st.title("📊 Report Customization")
    st.markdown("---")
    
    # Check admin permissions
    if user['role'] not in ['admin-operations', 'admin-it', 'manager']:
        st.warning("⚠️ You need admin or manager privileges to customize reports.")
        return
    
    # Tabs for Create New vs Manage Existing
    tab1, tab2 = st.tabs(["📝 Create New Report", "📋 Manage Existing Reports"])
    
    with tab1:
        render_create_report_form(user, active_location_id)
    
    with tab2:
        render_manage_reports(user, active_location_id)


def render_create_report_form(user: dict, active_location_id: int):
    """Form to create a new custom report"""
    
    st.markdown("### Create New Custom Report")
    
    # Basic Info
    with st.expander("📌 Basic Information", expanded=True):
        report_name = st.text_input("Report Name *", placeholder="e.g., Daily Tank Summary")
        report_slug = st.text_input("Report Slug *", placeholder="e.g., daily_tank_summary")
        st.caption("Slug must be unique and lowercase with underscores")
    
    # Data Source Selection
    st.markdown("---")
    st.markdown("### 🗃️ Data Source Selection")
    
    available_sources = get_available_data_sources()
    
    # Create friendly names for display
    source_display_names = {
        'otr_records': 'OTR Records (Tank Transactions)',
        'tank_transactions': 'Tank Transactions',
        'tanker_transactions': 'Tanker Dispatch Records',
        'yade_voyages': 'YADE Barge Voyages',
        'fso_operations': 'FSO Operations',
        'gpp_production': 'GPP Production Records',
        'river_draft': 'River Draft Records',
        'produced_water': 'Produced Water Records',
        'ofs_production': 'OFS Production & Evacuation',
        'tanks': 'Tank Master Data',
        'vessels': 'Vessel Master Data',
        'locations': 'Location Master Data'
    }
    
    source_options = [source_display_names.get(s, s) for s in available_sources]
    selected_source_display = st.selectbox("Select Data Source *", options=source_options)
    
    # Get actual source name from display name
    selected_source = None
    for key, value in source_display_names.items():
        if value == selected_source_display:
            selected_source = key
            break
    
    if not selected_source:
        selected_source = available_sources[0]
    
    st.info(f"📊 Selected Table: `{selected_source}`")
    
    # Column Selection
    st.markdown("---")
    st.markdown("### 📋 Select Columns for Report")
    
    if selected_source:
        available_columns = get_columns_for_source(selected_source)
        
        if available_columns:
            st.caption(f"Available columns from `{selected_source}` table:")
            
            # Multi-select for columns
            selected_columns = st.multiselect(
                "Choose Columns to Include *",
                options=[col['field'] for col in available_columns],
                format_func=lambda x: f"{x} ({next((c['type'] for c in available_columns if c['field'] == x), 'unknown')})"
            )
            
            # Show column details
            if selected_columns:
                st.markdown("#### Selected Column Configuration")
                
                column_configs = []
                for col_field in selected_columns:
                    col_info = next((c for c in available_columns if c['field'] == col_field), None)
                    if col_info:
                        with st.expander(f"⚙️ {col_info['label']}", expanded=False):
                            col1, col2 = st.columns(2)
                            with col1:
                                custom_label = st.text_input(
                                    "Custom Label",
                                    value=col_info['label'],
                                    key=f"label_{col_field}"
                                )
                            with col2:
                                col_type = st.selectbox(
                                    "Column Type",
                                    options=['string', 'numeric', 'date', 'datetime', 'boolean'],
                                    index=['string', 'numeric', 'date', 'datetime', 'boolean'].index(col_info['type']),
                                    key=f"type_{col_field}"
                                )
                            
                            column_configs.append({
                                'field': col_field,
                                'label': custom_label,
                                'type': col_type
                            })
        else:
            st.warning("No columns found for selected data source.")
            column_configs = []
    else:
        st.warning("Please select a data source.")
        column_configs = []
    
    # Filters Configuration
    st.markdown("---")
    st.markdown("### 🔍 Filter Configuration")
    
    with st.expander("Add Filters", expanded=False):
        st.caption("Define filters that users can apply when running this report")
        
        num_filters = st.number_input("Number of Filters", min_value=0, max_value=10, value=1)
        
        filter_configs = []
        for i in range(int(num_filters)):
            st.markdown(f"**Filter {i+1}**")
            fcol1, fcol2, fcol3 = st.columns(3)
            with fcol1:
                filter_field = st.selectbox(
                    "Field",
                    options=selected_columns if selected_columns else [],
                    key=f"filter_field_{i}"
                )
            with fcol2:
                filter_operator = st.selectbox(
                    "Operator",
                    options=['equals', 'not_equals', 'greater_than', 'less_than', 'contains', 'between'],
                    key=f"filter_op_{i}"
                )
            with fcol3:
                filter_value = st.text_input(
                    "Default Value (optional)",
                    placeholder="user_location",
                    key=f"filter_val_{i}"
                )
            
            filter_configs.append({
                'field': filter_field,
                'operator': filter_operator,
                'value': filter_value if filter_value else None
            })
    
    # Sorting Configuration
    st.markdown("---")
    st.markdown("### 🔢 Sorting Configuration")
    
    with st.expander("Add Sorting", expanded=False):
        num_sorts = st.number_input("Number of Sort Fields", min_value=0, max_value=5, value=1)
        
        sorting_configs = []
        for i in range(int(num_sorts)):
            scol1, scol2 = st.columns(2)
            with scol1:
                sort_field = st.selectbox(
                    f"Sort Field {i+1}",
                    options=selected_columns if selected_columns else [],
                    key=f"sort_field_{i}"
                )
            with scol2:
                sort_order = st.selectbox(
                    "Order",
                    options=['asc', 'desc'],
                    key=f"sort_order_{i}"
                )
            
            sorting_configs.append({
                'field': sort_field,
                'order': sort_order
            })
    
    # Access Control
    st.markdown("---")
    st.markdown("### 🔐 Access Control")
    
    allowed_roles = st.multiselect(
        "Grant Access to Roles",
        options=['admin-operations', 'admin-it', 'manager', 'supervisor', 'operator'],
        default=['manager', 'supervisor']
    )
    
    # Database Table Creation Toggle
    st.markdown("---")
    st.markdown("### 🗄️ Database Table Creation")
    st.info("💡 Enable this to create a new database table from this custom report structure. "
            "This allows you to store computed/aggregated data permanently.")
    
    create_db_table = st.checkbox(
        "Create as Database Table",
        value=False,
        help="When enabled, this will create a new table in the database with the selected columns"
    )
    
    if create_db_table:
        table_name_suggestion = report_slug if report_slug else "custom_report_table"
        custom_table_name = st.text_input(
            "Table Name *",
            value=table_name_suggestion,
            help="Enter the name for the new database table (lowercase, underscores only)"
        )
        st.caption("⚠️ Warning: Table creation requires database admin permissions and should be used carefully.")
    else:
        custom_table_name = None
    
    # Save Button
    st.markdown("---")
    if st.button("💾 Save Custom Report", type="primary", use_container_width=True):
        if not report_name or not report_slug or not selected_source or not column_configs:
            st.error("❌ Please fill all required fields: Report Name, Slug, Data Source, and at least one column.")
        else:
            # Build report configuration
            report_config = {
                'report_type': 'custom',
                'data_source': {
                    'table': selected_source,
                    'joins': []
                },
                'columns': column_configs,
                'filters': [f for f in filter_configs if f['field']],
                'sorting': [s for s in sorting_configs if s['field']],
                'grouping': [],
                'aggregations': {},
                'create_table': create_db_table,
                'custom_table_name': custom_table_name if create_db_table else None
            }
            
            # Save to database
            try:
                with get_session() as session:
                    # Create report definition
                    new_report = ReportDefinition(
                        location_id=active_location_id,
                        name=report_name,
                        slug=report_slug,
                        config_json=json.dumps(report_config),
                        is_active=True,
                        created_by=user['username'],
                        created_at=datetime.utcnow()
                    )
                    session.add(new_report)
                    session.flush()
                    
                    # Grant access to selected roles
                    for role in allowed_roles:
                        access = ReportAccess(
                            report_id=new_report.id,
                            role=role,
                            granted_by=user['username'],
                            granted_at=datetime.utcnow()
                        )
                        session.add(access)
                    
                    session.commit()
                    
                    success_msg = f"✅ Report '{report_name}' created successfully!"
                    
                    # Handle database table creation if enabled
                    if create_db_table and custom_table_name:
                        try:
                            from sqlalchemy import Table, Column, Integer, String, Float, Date, DateTime, Boolean, MetaData, Text
                            from db import engine
                            
                            metadata = MetaData()
                            
                            # Map column types to SQLAlchemy types
                            type_mapping = {
                                'numeric': Float,
                                'string': String(255),
                                'date': Date,
                                'datetime': DateTime,
                                'boolean': Boolean,
                            }
                            
                            # Build table columns
                            table_columns = [
                                Column('id', Integer, primary_key=True, autoincrement=True),
                                Column('location_id', Integer, nullable=True),
                                Column('created_at', DateTime, nullable=False),
                                Column('created_by', String(255), nullable=True),
                            ]
                            
                            for col_config in column_configs:
                                col_type = type_mapping.get(col_config['type'], String(255))
                                table_columns.append(
                                    Column(col_config['field'], col_type, nullable=True)
                                )
                            
                            # Create the table
                            new_table = Table(custom_table_name, metadata, *table_columns)
                            metadata.create_all(engine)
                            
                            success_msg += f"\n\n🗄️ Database table '{custom_table_name}' created successfully!"
                        except Exception as table_error:
                            st.warning(f"⚠️ Report created but table creation failed: {str(table_error)}")
                    
                    st.success(success_msg)
                    st.balloons()
            except Exception as e:
                st.error(f"❌ Error creating report: {str(e)}")


def render_manage_reports(user: dict, active_location_id: int):
    """Display and manage existing reports"""
    
    st.markdown("### Manage Existing Reports")
    
    # Filter options
    filter_option = st.radio(
        "Show Reports:",
        options=["All Reports", "My Location Only", "System Reports", "Custom Reports"],
        horizontal=True
    )
    
    with get_session() as session:
        query = session.query(ReportDefinition)
        
        # Apply filters based on selection
        if filter_option == "My Location Only":
            query = query.filter(ReportDefinition.location_id == active_location_id)
        elif filter_option == "System Reports":
            query = query.filter(ReportDefinition.created_by == 'system')
        elif filter_option == "Custom Reports":
            query = query.filter(ReportDefinition.created_by != 'system')
        # "All Reports" - no additional filter
        
        reports = query.order_by(ReportDefinition.created_at.desc()).all()
        
        if not reports:
            st.info("📭 No reports found. Create one in the 'Create New Report' tab.")
            return
        
        st.caption(f"Found {len(reports)} report(s)")
        
        for report in reports:
            # Parse configuration
            try:
                config = json.loads(report.config_json)
            except:
                config = {}
            
            # Report header with status badge
            status_badge = "✅ Active" if report.is_active else "❌ Inactive"
            report_type_badge = "🔧 Custom" if report.created_by != 'system' else "⚙️ System"
            
            with st.expander(f"📊 {report.name} | {status_badge} | {report_type_badge}", expanded=False):
                # Report Information
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Slug:** `{report.slug}`")
                    st.write(f"**Created By:** {report.created_by}")
                with col2:
                    if report.created_at:
                        st.write(f"**Created:** {report.created_at.strftime('%Y-%m-%d %H:%M')}")
                    location_name = "All Locations" if not report.location_id else f"Location ID: {report.location_id}"
                    st.write(f"**Location:** {location_name}")
                with col3:
                    st.write(f"**Status:** {status_badge}")
                    data_source = config.get('data_source', {}).get('table', 'Unknown')
                    st.write(f"**Data Source:** `{data_source}`")
                
                st.markdown("---")
                
                # Configuration Details
                with st.expander("📋 View Configuration", expanded=False):
                    st.json(config)
                
                # Edit Report Section
                st.markdown("#### ✏️ Edit Report")
                
                new_name = st.text_input("Report Name", value=report.name, key=f"edit_name_{report.id}")
                
                # Show columns from config
                columns_list = config.get('columns', [])
                if columns_list:
                    st.write("**Current Columns:**")
                    cols_display = ", ".join([f"`{c.get('field', 'unknown')}`" for c in columns_list])
                    st.markdown(cols_display)
                
                # Action Buttons
                st.markdown("---")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    if st.button(f"💾 Save Changes", key=f"save_{report.id}"):
                        report.name = new_name
                        session.commit()
                        st.success("✅ Report updated!")
                        st.rerun()
                
                with col2:
                    toggle_status = "Deactivate" if report.is_active else "Activate"
                    if st.button(f"🔄 {toggle_status}", key=f"toggle_{report.id}"):
                        report.is_active = not report.is_active
                        session.commit()
                        st.success(f"✅ Report {toggle_status.lower()}d!")
                        st.rerun()
                
                with col3:
                    # Show access control
                    if st.button(f"👥 View Access", key=f"access_{report.id}"):
                        accesses = session.query(ReportAccess).filter(
                            ReportAccess.report_id == report.id
                        ).all()
                        if accesses:
                            roles = [a.role for a in accesses if a.role]
                            st.info(f"**Roles with access:** {', '.join(roles)}")
                        else:
                            st.warning("No access rules defined.")
                
                with col4:
                    # Delete with confirmation
                    if f"confirm_delete_{report.id}" not in st.session_state:
                        st.session_state[f"confirm_delete_{report.id}"] = False
                    
                    if not st.session_state[f"confirm_delete_{report.id}"]:
                        if st.button(f"🗑️ Delete", key=f"delete_{report.id}", type="secondary"):
                            st.session_state[f"confirm_delete_{report.id}"] = True
                            st.rerun()
                    else:
                        st.warning("⚠️ Confirm deletion?")
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✅ Yes", key=f"confirm_yes_{report.id}"):
                                # Delete associated access records first
                                session.query(ReportAccess).filter(
                                    ReportAccess.report_id == report.id
                                ).delete()
                                session.delete(report)
                                session.commit()
                                st.session_state[f"confirm_delete_{report.id}"] = False
                                st.success("✅ Report deleted!")
                                st.rerun()
                        with c2:
                            if st.button("❌ No", key=f"confirm_no_{report.id}"):
                                st.session_state[f"confirm_delete_{report.id}"] = False
                                st.rerun()