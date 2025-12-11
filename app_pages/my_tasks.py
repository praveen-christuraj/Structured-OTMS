# my_tasks.py
import streamlit as st

from task_manager import TaskManager


CLOSED_STATUSES = ["APPROVED", "REJECTED", "COMPLETED", "CANCELLED"]


def render_my_tasks_page(active_location_id, user):
    """Show tasks for the current user and allow actions on PENDING ones."""
    st.markdown("### ✅ My Tasks")

    if not user:
        st.warning("Please log in to see your tasks.")
        return

    view = st.radio(
        "Show",
        ["Pending", "All", "Closed"],
        horizontal=True,
        key="my_tasks_filter",
    )

    if view == "Pending":
        statuses = None
        include_history = False
    elif view == "All":
        statuses = None
        include_history = True
    else:  # Closed
        statuses = CLOSED_STATUSES
        include_history = True

    tasks = TaskManager.fetch_tasks_for_user(
        user=user,
        statuses=statuses,
        include_history=include_history,
    )

    if not tasks:
        st.info("No tasks found for this filter.")
        return

    for task in tasks:
        title = task.get("title") or f"Task #{task['id']}"
        status = task.get("status", "UNKNOWN")
        task_type = task.get("task_type", "UNKNOWN")
        
        # Build enhanced header with visual indicators
        header = f"[{status}] {title} (#{task['id']})"
        
        # For supervisors viewing deletion requests, add special indicators
        if task_type == "DELETE_REQUEST" and user.get("role") == "supervisor" and status == "PENDING":
            metadata = task.get("metadata", {})
            supervisor_count = metadata.get("supervisor_count", 0)
            if supervisor_count > 1:
                header += f" ⚠️ Shared with {supervisor_count} supervisors"

        with st.expander(header, expanded=False):
            st.write(f"**Type:** {task.get('task_type')} · **Priority:** {task.get('priority')}")
            st.write(
                f"**Raised by:** {task.get('raised_by')} "
                f"({task.get('raised_by_role')}) at {task.get('raised_at')}"
            )
            
            # Special message for deletion requests assigned to multiple supervisors
            if task_type == "DELETE_REQUEST" and user.get("role") == "supervisor" and status == "PENDING":
                metadata = task.get("metadata", {})
                supervisor_count = metadata.get("supervisor_count", 0)
                if supervisor_count > 1:
                    st.info(
                        f"💬 This deletion request has been sent to **{supervisor_count} supervisors** "
                        f"at this location. **Any ONE supervisor can approve** this request."
                    )
            
            if task.get("description"):
                st.markdown(f"**Description:** {task['description']}")
            if task.get("resolution_notes"):
                st.markdown(f"**Resolution Notes:** {task['resolution_notes']}")

            st.caption(
                f"Resource: {task.get('resource_type') or '—'} "
                f"(ID: {task.get('resource_id') or '—'}) · "
                f"Location ID: {task.get('location_id') or '—'}"
            )

            # Actions only for PENDING tasks where user is allowed
            can_act = (
                status == "PENDING"
                and TaskManager.user_can_act_on_task(task, user)
            )

            if not can_act:
                st.caption("No actions available for this task.")
                continue

            notes = st.text_input(
                "Notes (optional)",
                key=f"task_notes_{task['id']}",
            )

            col1, col2, col3 = st.columns(3)

            if col1.button("✅ Approve", key=f"approve_{task['id']}"):
                TaskManager.update_status(
                    task_id=task["id"],
                    new_status="APPROVED",
                    actor=user["username"],
                    notes=notes or None,
                )
                st.success("Task approved.")
                st.rerun()

            if col2.button("⛔ Reject", key=f"reject_{task['id']}"):
                TaskManager.update_status(
                    task_id=task["id"],
                    new_status="REJECTED",
                    actor=user["username"],
                    notes=notes or None,
                )
                st.success("Task rejected.")
                st.rerun()

            if col3.button("✔️ Mark Completed", key=f"complete_{task['id']}"):
                TaskManager.update_status(
                    task_id=task["id"],
                    new_status="COMPLETED",
                    actor=user["username"],
                    notes=notes or None,
                )
                st.success("Task marked as completed.")
                st.rerun()
