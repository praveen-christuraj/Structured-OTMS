import streamlit as st
import json
from datetime import datetime, timedelta
from sqlalchemy import func

from ui import header
from db import get_session
from security import SecurityManager
from models import Task, TaskActivity, TaskType, TaskStatus, Location
from task_manager import TaskManager
from location_config import get_service_types
from logger import ActionLogger

SERVICE_TYPES = []

ASSIGNEES = [
    "admin-it",
    "admin-operations",
]

def _generate_service_id(session):
    today = datetime.utcnow().strftime("%Y%m%d")
    count_today = (
        session.query(func.count(Task.id))
        .filter(
            Task.task_type == TaskType.SERVICE_REQUEST.value,
            func.strftime("%Y%m%d", Task.raised_at) == today,
        )
        .scalar()
        or 0
    )
    seq = count_today + 1
    return f"SR-{today}-{seq:04d}"

def _list_locations():
    with get_session() as s:
        locs = s.query(Location).order_by(Location.name.asc()).all()
        return [(l.id, f"{l.name} ({l.code})") for l in locs]

def render_services_page(active_location_id, user):
    header("Services")

    if not user:
        st.error("Please login to access this page.")
        st.stop()

    tabs = st.tabs(["Service Request", "Status"])

    with tabs[0]:
        st.markdown("#### Raise Service Request")

        loc_options = _list_locations()
        loc_labels = [lbl for _, lbl in loc_options] or ["—"]
        loc_map = {lbl: idv for idv, lbl in loc_options}
        default_loc = None
        if active_location_id:
            for idv, lbl in loc_options:
                if idv == active_location_id:
                    default_loc = lbl
                    break

        with st.form("service_request_form"):
            loc_label = st.selectbox("Location", loc_labels, index=(loc_labels.index(default_loc) if default_loc in loc_labels else 0))
            with get_session() as s:
                types = []
                try:
                    types = get_service_types(s, 0)
                except Exception:
                    types = []
            service_type_options = types if types else ["N/A"]
            service_type = st.selectbox("Service Type", service_type_options)
            request_for_other = st.checkbox("Requesting for someone else", key="srv_req_other")
            other_username = st.text_input("Username", key="srv_req_other_username") if request_for_other else ""
            assign_to = st.selectbox("Assign To", ASSIGNEES, index=0)
            description = st.text_area("Description")
            contact_number = st.text_input("Contact Number")
            ip_number = st.text_input("IP Number")
            submitted = st.form_submit_button("Submit Request", type="primary")

        if submitted:
            if not description.strip() or not contact_number.strip():
                st.error("Description and Contact Number are required.")
            elif request_for_other and not (other_username or "").strip():
                st.error("Enter the username you are requesting for.")
            else:
                try:
                    with get_session() as s:
                        service_id = _generate_service_id(s)
                        meta = {
                            "service_type": service_type,
                            "contact_number": contact_number.strip(),
                            "ip_number": ip_number.strip(),
                            "assigned_to": assign_to,
                            "requesting_for_self": not request_for_other,
                            "for_username": (other_username or "").strip() if request_for_other else None,
                        }
                        task = Task(
                            title=f"Service Request • {service_type}",
                            description=description.strip(),
                            task_type=TaskType.SERVICE_REQUEST.value,
                            status=TaskStatus.PENDING.value,
                            priority="NORMAL",
                            resource_type="ServiceRequest",
                            resource_id=service_id,
                            location_id=loc_map.get(loc_label),
                            target_role=assign_to,
                            raised_by=user.get("username"),
                            raised_by_role=user.get("role"),
                            metadata_json=json.dumps(meta),
                        )
                        s.add(task)
                        s.flush()
                        act = TaskActivity(
                            task_id=task.id,
                            username=user.get("username"),
                            action="CREATED",
                            notes=f"Service request {service_id} created",
                        )
                        s.add(act)
                        SecurityManager.log_audit(
                            s,
                            user.get("username"),
                            "TASK_CREATE",
                            resource_type="Task",
                            resource_id=str(task.id),
                            details=f"Service request {service_id}",
                            user_id=user.get("id"),
                            location_id=loc_map.get(loc_label),
                            ip_address=st.session_state.get("client_ip"),
                            success=True,
                        )
                        s.commit()
                    st.success(f"Request submitted. Service ID: {service_id}")
                except Exception as ex:
                    st.error(f"Failed to submit request: {ex}")
                    try:
                        ActionLogger.log_error_with_task(
                            ex,
                            context="Service request submit",
                            user=user,
                            location_id=loc_map.get(loc_label),
                            severity="HIGH",
                            additional_info=f"service_type={service_type} assigned_to={assign_to}"
                        )
                    except Exception:
                        pass

    with tabs[1]:
        st.markdown("#### Request Status")
        role = (user or {}).get("role", "")
        is_admin = role in ["admin-it", "admin-operations"]
        view = "Mine" if not is_admin else st.radio("Show", ["Mine", "All"], horizontal=True)

        rows = []
        if view == "Mine":
            tasks = TaskManager.fetch_tasks_for_user(user=user, include_history=True)
            for t in tasks:
                if t.get("task_type") == TaskType.SERVICE_REQUEST.value:
                    rows.append(
                        {
                            "Service ID": t.get("resource_id"),
                            "Type": (t.get("metadata") or {}).get("service_type"),
                            "Assigned To": t.get("target_role"),
                            "Status": t.get("status"),
                            "Raised At": t.get("raised_at"),
                            "Resolved At": t.get("resolved_at"),
                        }
                    )
        else:
            with get_session() as s:
                q = s.query(Task).filter(Task.task_type == TaskType.SERVICE_REQUEST.value)
                q = q.order_by(Task.raised_at.desc()).limit(500)
                tasks = q.all()
                for t in tasks:
                    try:
                        meta = json.loads(t.metadata_json or "{}")
                    except Exception:
                        meta = {}
                    rows.append(
                        {
                            "Service ID": t.resource_id,
                            "Type": meta.get("service_type"),
                            "Assigned To": t.target_role,
                            "Status": t.status,
                            "Raised At": t.raised_at,
                            "Resolved At": t.resolved_at,
                        }
                    )

        if not rows:
            st.info("No service requests found.")
        else:
            st.dataframe(rows, use_container_width=True)

        try:
            recent_completed = []
            for r in rows:
                ra = r.get("Resolved At")
                if r.get("Status") == TaskStatus.COMPLETED.value and ra:
                    recent_completed.append(r)
            if recent_completed:
                st.success("Some requests have been marked completed.")
        except Exception:
            pass
