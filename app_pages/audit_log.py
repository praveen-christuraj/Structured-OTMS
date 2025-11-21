# audit_log.py
import streamlit as st
from datetime import datetime, timedelta

from db import get_session
from security import SecurityManager
from models import Location, AuditLog


def render_audit_log_page(active_location_id, user):
    """Audit trail viewer."""
    st.markdown("### 🧾 Audit Log")

    if not user or user["role"] not in ["admin-operations", "admin-it", "manager"]:
        st.warning("You do not have permission to view the audit log.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        range_label = st.selectbox(
            "Date range",
            ["Last 24 hours", "Last 7 days", "Last 30 days", "All"],
        )
    with col2:
        only_me = st.checkbox("Show only my actions", value=False)
    with col3:
        limit = st.number_input(
            "Max rows",
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

    st.dataframe(rows, use_container_width=True)
