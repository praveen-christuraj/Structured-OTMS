# ui.py
import streamlit as st
from pathlib import Path

def header(title: str):
    """Simple top bar with title and user pill (no logo)."""
    # layout columns: title | right user pill
    mid, right = st.columns([0.76, 0.24])

    # Left/Middle: Title + subtitle
    with mid:
        st.markdown(f"<h2 style='margin:0'>{title}</h2>", unsafe_allow_html=True)
        st.caption("Oil Terminal Management System")

    # Right: User pill
    with right:
        user = st.session_state.get("auth_user")
        pill = f"{user['username']} · {user['role']}" if user else "Guest"
        st.markdown(
            f"<div style='text-align:right;border:1px solid #334155;"
            f"padding:6px 10px;border-radius:999px;display:inline-block'>{pill}</div>",
            unsafe_allow_html=True,
        )

    st.divider()


def render_task_notification_badge(user):
    """
    Render a notification badge showing pending/new task counts
    Returns the count of pending tasks for the user
    
    Enhanced: Shows breakdown by task type and provides clear notification
    """
    if not user:
        return 0
    
    try:
        from task_manager import TaskManager
        from db import get_session
        from models import Task, TaskStatus, TaskType
        
        # Get pending task count
        pending_count = TaskManager.count_pending_tasks_for_user(user)
        
        if pending_count > 0:
            # Get breakdown by task type
            role = user.get("role", "")
            location_id = user.get("location_id")
            
            with get_session() as session:
                # Count by type
                delete_count = session.query(Task).filter(
                    Task.status == TaskStatus.PENDING.value,
                    Task.task_type == TaskType.DELETE_REQUEST.value
                ).count() if role == "supervisor" and location_id else 0
                
                error_count = session.query(Task).filter(
                    Task.status == TaskStatus.PENDING.value,
                    Task.task_type == TaskType.ERROR_ALERT.value
                ).count() if role in ["admin-it", "admin-operations"] else 0
                
                password_count = session.query(Task).filter(
                    Task.status == TaskStatus.PENDING.value,
                    Task.task_type == TaskType.PASSWORD_RESET.value
                ).count() if role in ["admin-it", "admin-operations"] else 0
            
            # Compute overdue export stages for user's location
            overdue_count = 0
            try:
                from models import ExportProcess, ExportStageProgress
                from db import get_session
                from datetime import date as _date
                with get_session() as session:
                    loc_id = user.get("location_id")
                    if loc_id:
                        rows = (
                            session.query(ExportProcess, ExportStageProgress)
                            .filter(ExportProcess.location_id == int(loc_id))
                            .filter(ExportStageProgress.export_id == ExportProcess.id)
                            .filter(ExportStageProgress.due_date.isnot(None))
                            .filter(ExportStageProgress.due_date <= _date.today())
                            .all()
                        )
                        for exp, stg in rows:
                            try:
                                # Load pipeline config to check completion statuses and notify flag
                                from location_config import get_page_section_config
                                cfg = get_page_section_config(session, int(loc_id), "export_operations", f"pipeline_{(exp.terminal_label or '').strip().lower().replace(' ','_')}")
                                stages = list((cfg or {}).get("stages") or [])
                                sdef = next((sd for sd in stages if sd.get("code") == stg.stage_code), None)
                                completion = list((sdef or {}).get("completion_statuses") or ["Completed"])
                                notify = bool((sdef or {}).get("notify_on_due", True))
                                if notify and (stg.status not in completion):
                                    overdue_count += 1
                            except Exception:
                                # Fallback: count when not completed
                                if (getattr(stg, "status", "") or "").lower() not in ["completed", "approved"]:
                                    overdue_count += 1
            except Exception:
                overdue_count = overdue_count

            # Show notification badge with breakdown
            badge_color = "#ef4444" if pending_count > 5 else "#f59e0b"
            
            # Build breakdown text
            breakdown_parts = []
            if delete_count > 0:
                breakdown_parts.append(f"{delete_count} deletion request{'s' if delete_count != 1 else ''}")
            if error_count > 0:
                breakdown_parts.append(f"{error_count} error{'s' if error_count != 1 else ''}")
            if password_count > 0:
                breakdown_parts.append(f"{password_count} password reset{'s' if password_count != 1 else ''}")
            
            if overdue_count > 0:
                breakdown_parts.append(f"{overdue_count} export stage{'s' if overdue_count != 1 else ''} overdue")
            breakdown_text = "<br>".join(breakdown_parts) if breakdown_parts else "Pending tasks"
            
            st.sidebar.markdown(
                f"""
                <div style="
                    background: {badge_color};
                    color: white;
                    padding: 8px 12px;
                    border-radius: 8px;
                    text-align: center;
                    margin: 10px 0;
                    font-weight: bold;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
                ">
                    🔔 {pending_count} Pending Task{"s" if pending_count != 1 else ""}
                    <div style="font-size: 11px; margin-top: 4px; font-weight: normal; opacity: 0.9;">
                        {breakdown_text}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        return pending_count
        
    except Exception as e:
        # Silently fail - don't break UI if task counting fails
        return 0


def render_error_summary_for_admin(user):
    """
    Show error summary widget for admin users
    Displays recent error tasks and system health indicators
    """
    if not user:
        return
    
    role = user.get("role", "")
    if role not in ["admin-it", "admin-operations"]:
        return
    
    try:
        from task_manager import TaskManager
        from db import get_session
        from models import Task, TaskType, TaskStatus
        from datetime import datetime, timedelta
        
        with get_session() as session:
            # Get error tasks from last 24 hours
            yesterday = datetime.utcnow() - timedelta(days=1)
            error_tasks = session.query(Task).filter(
                Task.task_type == TaskType.ERROR_ALERT.value,
                Task.raised_at >= yesterday,
                Task.status == TaskStatus.PENDING.value
            ).order_by(Task.raised_at.desc()).limit(10).all()
            
            error_count = len(error_tasks)
            
            if error_count > 0:
                # Show error summary
                severity_color = "#dc2626" if error_count >= 5 else "#f59e0b" if error_count >= 2 else "#3b82f6"
                
                st.sidebar.markdown(
                    f"""
                    <div style="
                        background: {severity_color};
                        color: white;
                        padding: 10px;
                        border-radius: 8px;
                        margin: 10px 0;
                    ">
                        <div style="font-weight: bold; font-size: 14px;">
                            ⚠️ System Errors (24h)
                        </div>
                        <div style="font-size: 24px; margin: 5px 0;">
                            {error_count}
                        </div>
                        <div style="font-size: 11px; opacity: 0.9;">
                            Requires attention
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
    
    except Exception:
        # Silently fail - don't break UI
        pass

