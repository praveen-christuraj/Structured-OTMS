# deletion_approval.py
"""
Comprehensive deletion approval system for OTMS
Handles both local (supervisor code) and remote (task request) approval workflows
Ensures operators and managers cannot delete without proper authorization
"""

import streamlit as st
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from db import get_session
from models import User, Task, TaskStatus, TaskType
from security import SecurityManager
from task_manager import TaskManager
from sqlalchemy import or_, func
from action_logger_utils import log_delete_action


class DeletionApprovalManager:
    """
    Manages deletion approval workflows for all resources in OTMS
    
    Approval Methods:
    1. No approval needed: admin-it, admin-operations, supervisor (can delete directly)
    2. Local approval: operator/manager + supervisor code verification
    3. Remote approval: operator/manager requests approval via task system
    """
    
    @staticmethod
    def can_delete_without_approval(user: Optional[Dict[str, Any]]) -> bool:
        """
        Check if user can delete without any approval
        
        Returns:
            True if user is admin-operations or supervisor (at their location)
            False if user is operator (needs approval) or manager (cannot delete)
            False if user is admin-it (no access to operational pages)
        """
        if not user:
            return False
        
        role = user.get("role", "")
        return role in ["admin-operations", "supervisor"]
    
    @staticmethod
    def get_location_supervisors(location_id: int) -> list[Dict[str, Any]]:
        """Get list of active supervisors for a specific location"""
        with get_session() as session:
            supervisors = (
                session.query(User)
                .filter(
                    User.role == "supervisor",
                    User.is_active == True,  # noqa: E712
                    User.location_id == location_id  # Only supervisors assigned to this location
                )
                .order_by(User.full_name, User.username)
                .all()
            )
            
            return [
                {
                    "id": sup.id,
                    "username": sup.username,
                    "full_name": sup.full_name or sup.username,
                    "location_id": sup.location_id,
                    "has_code": bool(sup.supervisor_code_hash),
                }
                for sup in supervisors
            ]
    
    @staticmethod
    def verify_local_approval(supervisor_username: str, supervisor_code: str) -> tuple[bool, str]:
        """
        Verify local approval with supervisor code
        
        Returns:
            (is_valid, error_message)
        """
        if not supervisor_username:
            return False, "Supervisor username is required"
        
        if not supervisor_code:
            return False, "Supervisor code is required"
        
        # Verify the code
        if SecurityManager.verify_supervisor_code(supervisor_code, supervisor_username):
            return True, ""
        else:
            return False, "Invalid supervisor code"
    
    @staticmethod
    def check_remote_approval_status(
        resource_type: str,
        resource_id: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Check if there's an approved remote deletion request for this resource
        
        Returns:
            Task dict if approved, None otherwise
        """
        return TaskManager.get_task_for_resource(
            resource_type=resource_type,
            resource_id=str(resource_id),
            statuses=[TaskStatus.APPROVED.value]
        )
    
    @staticmethod
    def check_pending_approval(
        resource_type: str,
        resource_id: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Check if there's a pending deletion request
        
        Returns:
            Task dict if pending, None otherwise
        """
        return TaskManager.get_task_for_resource(
            resource_type=resource_type,
            resource_id=str(resource_id),
            statuses=[TaskStatus.PENDING.value]
        )
    
    @staticmethod
    def request_remote_approval(
        resource_type: str,
        resource_id: Any,
        resource_label: str,
        user: Dict[str, Any],
        location_id: Optional[int],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a remote deletion approval request task
        
        Returns:
            Created or existing task dict
        """
        return TaskManager.create_delete_request(
            resource_type=resource_type,
            resource_id=resource_id,
            resource_label=resource_label,
            raised_by=user.get("username"),
            raised_by_role=user.get("role"),
            location_id=location_id,
            metadata=metadata
        )
    
    @staticmethod
    def execute_deletion_with_approval(
        resource_type: str,
        resource_id: Any,
        resource_label: str,
        approver_name: str,
        approval_method: str,
        delete_func: Callable,
        user: Dict[str, Any],
        location_id: Optional[int],
        session=None
    ) -> tuple[bool, Optional[str]]:
        """
        Execute deletion with proper logging and task completion
        
        Args:
            resource_type: Type of resource (TankTransaction, YadeVoyage, etc.)
            resource_id: ID of resource
            resource_label: Display label for resource
            approver_name: Name of approver
            approval_method: 'local', 'remote', or 'direct'
            delete_func: Function that performs the actual deletion
            user: User performing deletion
            location_id: Location ID
            session: Database session
        
        Returns:
            (success, error_message)
        """
        try:
            # Execute the deletion
            delete_func()
            
            # Log the deletion action
            log_delete_action(
                resource_type=resource_type,
                resource_id=resource_id,
                user=user,
                location_id=location_id,
                details=f"Deleted {resource_label} with {approval_method} approval by {approver_name}",
                session=session
            )
            
            # Complete any related tasks
            TaskManager.complete_tasks_for_resource(
                resource_type=resource_type,
                resource_id=resource_id,
                actor=user.get("username"),
                notes=f"Deletion completed with {approval_method} approval by {approver_name}",
                session=session
            )
            
            return True, None
            
        except Exception as e:
            error_msg = f"Failed to delete {resource_label}: {str(e)}"
            
            # Log error with task creation
            from logger import ActionLogger
            ActionLogger.log_error_with_task(
                error=e,
                context=f"Deleting {resource_type}",
                user=user,
                location_id=location_id,
                severity="HIGH",
                additional_info=f"Resource: {resource_label}\nApprover: {approver_name}\nMethod: {approval_method}"
            )
            
            return False, error_msg


def render_deletion_ui(
    resource_type: str,
    resource_id: Any,
    resource_label: str,
    delete_func: Callable,
    user: Dict[str, Any],
    location_id: Optional[int],
    on_success_message: str = "Deleted successfully",
    metadata: Optional[Dict[str, Any]] = None,
    button_key_prefix: Optional[str] = None
) -> bool:
    """
    Render comprehensive deletion UI with appropriate approval method
    
    This function handles all three deletion scenarios:
    1. Direct deletion for admins and supervisors
    2. Local approval with supervisor code for operators/managers
    3. Remote approval via task system for operators/managers
    
    Args:
        resource_type: Type of resource (TankTransaction, YadeVoyage, etc.)
        resource_id: ID of resource to delete
        resource_label: Display label (e.g., "Tank Transaction #123")
        delete_func: Function that performs actual deletion
        user: Current user dict
        location_id: Active location ID
        on_success_message: Message to show on successful deletion
        metadata: Additional metadata for task creation
        button_key_prefix: Prefix for button keys (auto-generated if None)
    
    Returns:
        True if deletion was completed, False otherwise
    """
    if not user:
        st.error("You must be logged in to delete records")
        return False
    
    # Generate unique key prefix if not provided
    if not button_key_prefix:
        import hashlib
        button_key_prefix = f"del_{hashlib.md5(f'{resource_type}_{resource_id}'.encode()).hexdigest()[:8]}"
    
    role = user.get("role", "")
    username = user.get("username", "")
    
    # CASE 1: Admin-Operations or Supervisor can delete directly
    if DeletionApprovalManager.can_delete_without_approval(user):
        st.warning(f"⚠️ Are you sure you want to delete **{resource_label}**?")
        st.caption("This action cannot be undone.")
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            if st.button("✅ Confirm Delete", key=f"{button_key_prefix}_confirm", type="primary"):
                success, error = DeletionApprovalManager.execute_deletion_with_approval(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    resource_label=resource_label,
                    approver_name=f"{username} ({role})",
                    approval_method="direct",
                    delete_func=delete_func,
                    user=user,
                    location_id=location_id
                )
                
                if success:
                    st.success(on_success_message)
                    return True
                else:
                    st.error(error)
                    return False
        
        with col2:
            if st.button("❌ Cancel", key=f"{button_key_prefix}_cancel"):
                st.info("Deletion cancelled")
                return False
    
    # CASE 2: Manager cannot delete (view-only access)
    elif role == "manager":
        st.error("❌ Managers have view-only access and cannot delete records")
        return False
    
    # CASE 3: Admin-IT cannot access operational pages
    elif role == "admin-it":
        st.error("❌ Admin-IT role does not have access to operational pages")
        return False
    
    # CASE 4: Operator needs supervisor approval from their location
    elif role == "operator":
        if not location_id:
            st.error("❌ Location is required for operator deletions")
            return False
        
        # Check for existing remote approval
        remote_approval = DeletionApprovalManager.check_remote_approval_status(
            resource_type, resource_id
        )
        
        # Check for pending approval request
        pending_approval = DeletionApprovalManager.check_pending_approval(
            resource_type, resource_id
        )
        
        # If remote approval exists, allow deletion
        if remote_approval:
            approved_by = remote_approval.get("approved_by", "Supervisor")
            approved_at = remote_approval.get("approved_at")
            
            st.success(
                f"✅ Remote approval granted by **{approved_by}** "
                f"on {approved_at.strftime('%Y-%m-%d %H:%M') if approved_at else 'N/A'}"
            )
            st.warning(f"⚠️ Delete **{resource_label}**?")
            
            col1, col2 = st.columns([1, 3])
            
            with col1:
                if st.button("✅ Delete", key=f"{button_key_prefix}_remote_del", type="primary"):
                    success, error = DeletionApprovalManager.execute_deletion_with_approval(
                        resource_type=resource_type,
                        resource_id=resource_id,
                        resource_label=resource_label,
                        approver_name=f"{approved_by} (remote)",
                        approval_method="remote",
                        delete_func=delete_func,
                        user=user,
                        location_id=location_id
                    )
                    
                    if success:
                        st.success(on_success_message)
                        return True
                    else:
                        st.error(error)
                        return False
            
            with col2:
                if st.button("❌ Cancel", key=f"{button_key_prefix}_remote_cancel"):
                    st.info("Deletion cancelled")
                    return False
            
            return False
        
        # Show pending status if exists
        if pending_approval:
            raised_at = pending_approval.get("raised_at")
            st.info(
                f"⏳ Deletion approval requested on "
                f"{raised_at.strftime('%Y-%m-%d %H:%M') if raised_at else 'N/A'}. "
                "Awaiting supervisor action. Check **My Tasks** for updates."
            )
            return False
        
        # Show both approval options
        st.warning(f"⚠️ Supervisor approval required to delete **{resource_label}**")
        
        tab1, tab2 = st.tabs(["📋 Local Approval (Supervisor Code)", "📤 Remote Approval (Task Request)"])
        
        # TAB 1: Local Approval with Supervisor Code
        with tab1:
            st.markdown("#### Enter supervisor credentials to approve deletion immediately")
            
            supervisors = DeletionApprovalManager.get_location_supervisors(location_id)
            
            if not supervisors:
                st.warning("No supervisors available for approval at this location")
            else:
                with st.form(f"{button_key_prefix}_local_approval"):
                    # Supervisor selection
                    sup_options = {
                        f"{sup['full_name']} ({sup['username']})": sup
                        for sup in supervisors
                        if sup["has_code"]
                    }
                    
                    if not sup_options:
                        st.warning("No supervisors with supervisor codes set. Use remote approval instead.")
                        st.form_submit_button("Submit", disabled=True)
                    else:
                        selected_label = st.selectbox(
                            "Select Supervisor",
                            list(sup_options.keys()),
                            key=f"{button_key_prefix}_sup_select"
                        )
                        
                        supervisor_code = st.text_input(
                            "Supervisor Code",
                            type="password",
                            key=f"{button_key_prefix}_sup_code",
                            help="Enter the supervisor's code to approve this deletion"
                        )
                        
                        submitted = st.form_submit_button("🔓 Approve & Delete", type="primary")
                        
                        if submitted:
                            selected_sup = sup_options[selected_label]
                            
                            valid, error = DeletionApprovalManager.verify_local_approval(
                                selected_sup["username"],
                                supervisor_code
                            )
                            
                            if valid:
                                success, del_error = DeletionApprovalManager.execute_deletion_with_approval(
                                    resource_type=resource_type,
                                    resource_id=resource_id,
                                    resource_label=resource_label,
                                    approver_name=f"{selected_sup['full_name']} (local)",
                                    approval_method="local",
                                    delete_func=delete_func,
                                    user=user,
                                    location_id=location_id
                                )
                                
                                if success:
                                    st.success(on_success_message)
                                    st.rerun()
                                else:
                                    st.error(del_error)
                            else:
                                st.error(f"❌ {error}")
        
        # TAB 2: Remote Approval Request
        with tab2:
            st.markdown("#### Request supervisor approval via task system")
            st.info(
                "A task will be created and assigned to supervisors at this location. "
                "They can approve from the **My Tasks** page."
            )
            
            if st.button(
                "📤 Send Approval Request",
                key=f"{button_key_prefix}_remote_request",
                type="primary"
            ):
                merged_metadata = metadata.copy() if metadata else {}
                merged_metadata.setdefault("requested_by", username)
                merged_metadata.setdefault("requested_at", datetime.utcnow().isoformat())
                
                task = DeletionApprovalManager.request_remote_approval(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    resource_label=resource_label,
                    user=user,
                    location_id=location_id,
                    metadata=merged_metadata
                )
                
                st.success(
                    f"✅ Approval request sent! Task ID: {task.get('id')}. "
                    "Supervisors will be notified. Check **My Tasks** for updates."
                )
                st.rerun()
    
    # CASE 5: Unknown role
    else:
        st.error(f"❌ Role '{role}' does not have delete permissions")
        return False
