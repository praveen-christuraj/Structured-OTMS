# error_monitoring.py
"""
Error Monitoring Dashboard for Admin Users
Provides comprehensive view of system errors, health metrics, and task summaries
"""

import streamlit as st
from datetime import datetime, timedelta
from typing import Dict, List, Any
import pandas as pd
from db import get_session
from models import Task, TaskType, TaskStatus, AuditLog


def render_error_monitoring_dashboard(user: Dict[str, Any]):
    """
    Render comprehensive error monitoring dashboard for admin users
    
    Shows:
    - Error summary and trends
    - Recent error tasks
    - System health metrics
    - Action logs
    """
    
    role = user.get("role", "")
    if role not in ["admin-it", "admin-operations"]:
        st.warning("This page is only accessible to Admin-IT and Admin-Operations users.")
        return
    
    st.markdown("## 🔍 Error Monitoring Dashboard")
    st.caption("Real-time system health and error tracking")
    
    # Time range selector
    time_range = st.selectbox(
        "Time Range",
        ["Last 24 Hours", "Last 7 Days", "Last 30 Days", "All Time"],
        index=0
    )
    
    time_delta = {
        "Last 24 Hours": timedelta(hours=24),
        "Last 7 Days": timedelta(days=7),
        "Last 30 Days": timedelta(days=30),
        "All Time": timedelta(days=36500)  # ~100 years
    }[time_range]
    
    cutoff_time = datetime.utcnow() - time_delta
    
    with get_session() as session:
        # ===== ERROR SUMMARY METRICS =====
        st.markdown("### 📊 Error Summary")
        
        # Get error tasks
        error_tasks = session.query(Task).filter(
            Task.task_type == TaskType.ERROR_ALERT.value,
            Task.raised_at >= cutoff_time
        ).all()
        
        total_errors = len(error_tasks)
        pending_errors = len([t for t in error_tasks if t.status == TaskStatus.PENDING.value])
        resolved_errors = len([t for t in error_tasks if t.status == TaskStatus.COMPLETED.value])
        
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Total Errors",
                total_errors,
                help="Total error tasks in selected time range"
            )
        
        with col2:
            st.metric(
                "Pending",
                pending_errors,
                delta=None,
                delta_color="inverse",
                help="Errors awaiting resolution"
            )
        
        with col3:
            st.metric(
                "Resolved",
                resolved_errors,
                help="Successfully resolved errors"
            )
        
        with col4:
            resolution_rate = (resolved_errors / total_errors * 100) if total_errors > 0 else 0
            st.metric(
                "Resolution Rate",
                f"{resolution_rate:.1f}%",
                help="Percentage of errors that have been resolved"
            )
        
        # ===== SEVERITY BREAKDOWN =====
        st.markdown("### ⚠️ Errors by Severity")
        
        severity_counts = {}
        for task in error_tasks:
            severity = task.priority or "MEDIUM"
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        if severity_counts:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                critical_count = severity_counts.get("CRITICAL", 0)
                st.markdown(
                    f"""
                    <div style="background: #dc2626; color: white; padding: 15px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 28px; font-weight: bold;">{critical_count}</div>
                        <div>CRITICAL</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            with col2:
                high_count = severity_counts.get("HIGH", 0)
                st.markdown(
                    f"""
                    <div style="background: #f59e0b; color: white; padding: 15px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 28px; font-weight: bold;">{high_count}</div>
                        <div>HIGH</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            with col3:
                medium_count = severity_counts.get("MEDIUM", 0)
                st.markdown(
                    f"""
                    <div style="background: #3b82f6; color: white; padding: 15px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 28px; font-weight: bold;">{medium_count}</div>
                        <div>MEDIUM</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.success("✅ No errors in selected time range!")
        
        # ===== ERROR TREND CHART =====
        if error_tasks:
            st.markdown("### 📈 Error Trend")
            
            # Group errors by date
            error_dates = {}
            for task in error_tasks:
                date_key = task.raised_at.date() if task.raised_at else datetime.utcnow().date()
                error_dates[date_key] = error_dates.get(date_key, 0) + 1
            
            # Create DataFrame for chart
            df_trend = pd.DataFrame([
                {"Date": date, "Errors": count}
                for date, count in sorted(error_dates.items())
            ])
            
            st.line_chart(df_trend.set_index("Date"))
        
        # ===== RECENT ERROR TASKS =====
        st.markdown("### 🚨 Recent Error Tasks")
        
        # Filter by role
        if role == "admin-it":
            display_tasks = [t for t in error_tasks if t.target_role == "admin-it"]
        elif role == "admin-operations":
            display_tasks = [t for t in error_tasks if t.target_role == "admin-operations"]
        else:
            display_tasks = error_tasks
        
        # Sort by raised date (newest first)
        display_tasks.sort(key=lambda t: t.raised_at or datetime.min, reverse=True)
        
        # Show only pending or recent errors
        show_all = st.checkbox("Show all errors (including resolved)", value=False)
        
        if not show_all:
            display_tasks = [t for t in display_tasks if t.status == TaskStatus.PENDING.value]
        
        # Display tasks
        if display_tasks:
            for task in display_tasks[:20]:  # Limit to 20 most recent
                severity_color = {
                    "CRITICAL": "🔴",
                    "HIGH": "🟠",
                    "MEDIUM": "🟡",
                    "LOW": "🟢"
                }.get(task.priority, "⚪")
                
                status_icon = {
                    "PENDING": "⏳",
                    "COMPLETED": "✅",
                    "RESOLVED": "✅",
                    "REJECTED": "❌"
                }.get(task.status, "❓")
                
                with st.expander(
                    f"{severity_color} {status_icon} {task.title} - {task.raised_at.strftime('%Y-%m-%d %H:%M') if task.raised_at else 'Unknown'}",
                    expanded=False
                ):
                    st.markdown(f"**Task ID:** {task.id}")
                    st.markdown(f"**Status:** {task.status}")
                    st.markdown(f"**Priority:** {task.priority}")
                    st.markdown(f"**Raised By:** {task.raised_by} ({task.raised_by_role})")
                    st.markdown(f"**Target Role:** {task.target_role}")
                    
                    if task.description:
                        st.markdown("**Description:**")
                        st.text(task.description)
                    
                    if task.resolution_notes:
                        st.markdown(f"**Resolution Notes:** {task.resolution_notes}")
                    
                    # Action buttons for pending tasks
                    if task.status == TaskStatus.PENDING.value:
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            if st.button(f"✅ Resolve Task #{task.id}", key=f"resolve_{task.id}"):
                                _resolve_error_task(task.id, user, session)
                                st.success("Task resolved!")
                                st.rerun()
                        
                        with col2:
                            if st.button(f"🔄 Mark In Progress #{task.id}", key=f"progress_{task.id}"):
                                _mark_task_in_progress(task.id, user, session)
                                st.info("Task marked in progress")
                                st.rerun()
        else:
            st.info("No error tasks found for your role in the selected time range.")
        
        # ===== SYSTEM HEALTH METRICS =====
        st.markdown("### 💚 System Health")
        
        # Get failed actions from audit log
        failed_actions = session.query(AuditLog).filter(
            AuditLog.timestamp >= cutoff_time,
            AuditLog.success == False
        ).count()
        
        total_actions = session.query(AuditLog).filter(
            AuditLog.timestamp >= cutoff_time
        ).count()
        
        success_rate = ((total_actions - failed_actions) / total_actions * 100) if total_actions > 0 else 100
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Actions", total_actions)
        
        with col2:
            st.metric("Failed Actions", failed_actions)
        
        with col3:
            color = "🟢" if success_rate >= 98 else "🟡" if success_rate >= 95 else "🔴"
            st.metric(f"{color} Success Rate", f"{success_rate:.2f}%")
        
        # ===== TOP ERROR CONTEXTS =====
        st.markdown("### 📍 Top Error Contexts")
        
        error_contexts = {}
        for task in error_tasks:
            try:
                import json
                metadata = json.loads(task.metadata_json) if task.metadata_json else {}
                context = metadata.get("context", "Unknown")
            except:
                context = "Unknown"
            
            error_contexts[context] = error_contexts.get(context, 0) + 1
        
        if error_contexts:
            df_contexts = pd.DataFrame([
                {"Context": ctx, "Count": cnt}
                for ctx, cnt in sorted(error_contexts.items(), key=lambda x: x[1], reverse=True)
            ][:10])  # Top 10
            
            st.dataframe(df_contexts, use_container_width=True)


def _resolve_error_task(task_id: int, user: Dict[str, Any], session):
    """Mark an error task as resolved"""
    from task_manager import TaskManager
    
    TaskManager.update_status(
        task_id=task_id,
        new_status="COMPLETED",
        actor=user.get("username"),
        notes="Reviewed and resolved by admin",
        session=session
    )


def _mark_task_in_progress(task_id: int, user: Dict[str, Any], session):
    """Mark task as in progress (custom status)"""
    from models import Task, TaskActivity
    
    task = session.query(Task).get(task_id)
    if task:
        # Add activity
        activity = TaskActivity(
            task_id=task_id,
            username=user.get("username"),
            action="IN_PROGRESS",
            notes="Admin is investigating this error"
        )
        session.add(activity)
        session.commit()


def render_error_summary_widget(user: Dict[str, Any]):
    """
    Compact error summary widget that can be embedded in other pages
    """
    role = user.get("role", "")
    if role not in ["admin-it", "admin-operations"]:
        return
    
    try:
        from db import get_session
        from models import Task, TaskType, TaskStatus
        from datetime import datetime, timedelta
        
        with get_session() as session:
            # Get errors from last 7 days
            cutoff = datetime.utcnow() - timedelta(days=7)
            
            error_count = session.query(Task).filter(
                Task.task_type == TaskType.ERROR_ALERT.value,
                Task.raised_at >= cutoff,
                Task.status == TaskStatus.PENDING.value
            ).count()
            
            if error_count > 0:
                st.warning(f"⚠️ {error_count} unresolved error(s) in the last 7 days. Check **My Tasks** for details.")
    
    except Exception:
        pass  # Silently fail
