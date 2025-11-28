# audit_log.py
import streamlit as st
from datetime import datetime, timedelta

from db import get_session
from security import SecurityManager
from models import Location, AuditLog
from ui_components import FormBuilder, TableDisplay, DashboardCard, apply_custom_css


def render_audit_log_page(active_location_id, user):
    """Audit trail viewer."""
    apply_custom_css()
    
    # Modern header
    st.markdown("""
    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 2rem; border-radius: 12px; margin-bottom: 1.5rem;'>
        <h1 style='color: white; margin: 0; font-size: 2rem;'>🧾 Audit Log</h1>
        <p style='color: rgba(255,255,255,0.9); margin: 0.5rem 0 0 0;'>System Activity Trail</p>
    </div>
    """, unsafe_allow_html=True)

    if not user or user["role"] not in ["admin-operations", "admin-it", "manager"]:
        st.warning("You do not have permission to view the audit log.")
        return

    FormBuilder.section_header("Filter Options", "Customize your audit log view")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        range_label = st.selectbox(
            "📅 Date Range",
            ["Last 24 hours", "Last 7 days", "Last 30 days", "All"],
        )
    with col2:
        only_me = st.checkbox("👤 Show only my actions", value=False)
    with col3:
        limit = st.number_input(
            "📊 Max Rows",
            min_value=50,
            max_value=500,
            value=200,
            step=50,
        )

    now = datetime.utcnow()
    if range_label == "Last 24 hours":
        date_from = now - timedelta(days=1)
    elif range_label == "Last 7 days":
        date_from = now - timedelta(days=7)
    elif range_label == "Last 30 days":
        date_from = now - timedelta(days=30)
    else:
        date_from = None

    with get_session() as session:
        user_id_filter = user["id"] if only_me else None

        logs = SecurityManager.get_audit_trail(
            session=session,
            user_id=user_id_filter,
            location_id=None,
            action=None,
            date_from=date_from,
            date_to=None,
            limit=int(limit),
        )

        # Pre-load locations for IDs present in logs
        loc_ids = {log.location_id for log in logs if log.location_id}
        loc_by_id = {}
        if loc_ids:
            locs = (
                session.query(Location)
                .filter(Location.id.in_(loc_ids))
                .all()
            )
            loc_by_id = {loc.id: loc for loc in locs}

        rows = []
        for log in logs:
            loc = loc_by_id.get(log.location_id)
            loc_label = (
                f"{loc.name} ({loc.code})" if loc else ""
            )
            rows.append(
                {
                    "Time": log.timestamp,
                    "User": log.username,
                    "Action": log.action,
                    "Resource": log.resource_type or "",
                    "Resource ID": log.resource_id or "",
                    "Location": loc_label,
                    "Details": log.details or "",
                    "IP": log.ip_address or "",
                    "Success": "✅" if log.success else "⛔",
                }
            )

    st.markdown("---")
    
    # Display summary statistics
    if rows:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            DashboardCard.metric_card("Total Records", str(len(rows)), f"Last {range_label.lower()}", "📊", "blue")
        with col2:
            success_count = sum(1 for r in rows if r["Success"] == "✅")
            DashboardCard.metric_card("Successful", str(success_count), f"{success_count/len(rows)*100:.1f}% success rate", "✅", "green")
        with col3:
            failed_count = sum(1 for r in rows if r["Success"] == "⛔")
            DashboardCard.metric_card("Failed", str(failed_count), f"{failed_count/len(rows)*100:.1f}% failure rate", "⛔", "red")
        with col4:
            unique_users = len(set(r["User"] for r in rows))
            DashboardCard.metric_card("Unique Users", str(unique_users), "Active users", "👥", "purple")
    
    st.markdown("---")
    
    # Display the audit log table with search
    TableDisplay.display_data_table(
        st.session_state.get("audit_df") if "audit_df" not in locals() else __import__('pandas').DataFrame(rows),
        title="Audit Trail Records",
        searchable=True
    )
    
    # Store dataframe in session state for search functionality
    import pandas as pd
    st.session_state["audit_df"] = pd.DataFrame(rows)
