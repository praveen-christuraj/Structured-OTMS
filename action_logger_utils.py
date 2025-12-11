# action_logger_utils.py
"""
Utility functions to easily integrate action logging and error handling
into existing OTMS pages and operations.
"""

from typing import Optional, Dict, Any, Callable
from logger import ActionLogger
from error_handler import handle_errors, ErrorContext
import streamlit as st


def log_create_action(
    resource_type: str,
    resource_id: Any,
    user: Optional[Dict[str, Any]] = None,
    location_id: Optional[int] = None,
    details: Optional[str] = None,
    session = None
):
    """Quick helper to log CREATE actions"""
    user = user or st.session_state.get("auth_user")
    location_id = location_id or st.session_state.get("active_location_id")
    
    ActionLogger.log_action(
        action="CREATE",
        resource_type=resource_type,
        resource_id=resource_id,
        username=user.get("username") if user else None,
        user_id=user.get("id") if user else None,
        location_id=location_id,
        details=details or f"Created {resource_type}",
        success=True,
        session=session
    )


def log_update_action(
    resource_type: str,
    resource_id: Any,
    user: Optional[Dict[str, Any]] = None,
    location_id: Optional[int] = None,
    details: Optional[str] = None,
    session = None
):
    """Quick helper to log UPDATE actions"""
    user = user or st.session_state.get("auth_user")
    location_id = location_id or st.session_state.get("active_location_id")
    
    ActionLogger.log_action(
        action="UPDATE",
        resource_type=resource_type,
        resource_id=resource_id,
        username=user.get("username") if user else None,
        user_id=user.get("id") if user else None,
        location_id=location_id,
        details=details or f"Updated {resource_type}",
        success=True,
        session=session
    )


def log_delete_action(
    resource_type: str,
    resource_id: Any,
    user: Optional[Dict[str, Any]] = None,
    location_id: Optional[int] = None,
    details: Optional[str] = None,
    session = None
):
    """Quick helper to log DELETE actions"""
    user = user or st.session_state.get("auth_user")
    location_id = location_id or st.session_state.get("active_location_id")
    
    ActionLogger.log_action(
        action="DELETE",
        resource_type=resource_type,
        resource_id=resource_id,
        username=user.get("username") if user else None,
        user_id=user.get("id") if user else None,
        location_id=location_id,
        details=details or f"Deleted {resource_type}",
        success=True,
        session=session
    )


def log_view_action(
    resource_type: str,
    user: Optional[Dict[str, Any]] = None,
    location_id: Optional[int] = None,
    details: Optional[str] = None,
    session = None
):
    """Quick helper to log VIEW actions"""
    user = user or st.session_state.get("auth_user")
    location_id = location_id or st.session_state.get("active_location_id")
    
    ActionLogger.log_action(
        action="VIEW",
        resource_type=resource_type,
        resource_id=None,
        username=user.get("username") if user else None,
        user_id=user.get("id") if user else None,
        location_id=location_id,
        details=details or f"Viewed {resource_type} page",
        success=True,
        session=session
    )


def log_export_action(
    resource_type: str,
    export_format: str,
    record_count: int,
    user: Optional[Dict[str, Any]] = None,
    location_id: Optional[int] = None,
    session = None
):
    """Quick helper to log EXPORT actions"""
    user = user or st.session_state.get("auth_user")
    location_id = location_id or st.session_state.get("active_location_id")
    
    ActionLogger.log_action(
        action="EXPORT",
        resource_type=resource_type,
        resource_id=None,
        username=user.get("username") if user else None,
        user_id=user.get("id") if user else None,
        location_id=location_id,
        details=f"Exported {record_count} {resource_type} records to {export_format}",
        success=True,
        session=session
    )


def log_filter_action(
    resource_type: str,
    filter_criteria: Dict[str, Any],
    record_count: int,
    user: Optional[Dict[str, Any]] = None,
    location_id: Optional[int] = None,
    session = None
):
    """Log when user applies filters to data"""
    user = user or st.session_state.get("auth_user")
    location_id = location_id or st.session_state.get("active_location_id")
    
    filter_summary = ", ".join([f"{k}={v}" for k, v in filter_criteria.items() if v])
    
    ActionLogger.log_action(
        action="FILTER",
        resource_type=resource_type,
        resource_id=None,
        username=user.get("username") if user else None,
        user_id=user.get("id") if user else None,
        location_id=location_id,
        details=f"Filtered {resource_type}: {filter_summary} - {record_count} results",
        success=True,
        session=session
    )


def log_search_action(
    resource_type: str,
    search_term: str,
    record_count: int,
    user: Optional[Dict[str, Any]] = None,
    location_id: Optional[int] = None,
    session = None
):
    """Log when user performs a search"""
    user = user or st.session_state.get("auth_user")
    location_id = location_id or st.session_state.get("active_location_id")
    
    ActionLogger.log_action(
        action="SEARCH",
        resource_type=resource_type,
        resource_id=None,
        username=user.get("username") if user else None,
        user_id=user.get("id") if user else None,
        location_id=location_id,
        details=f"Searched {resource_type} for '{search_term}' - {record_count} results",
        success=True,
        session=session
    )


def log_select_action(
    resource_type: str,
    resource_id: Any,
    resource_label: str,
    user: Optional[Dict[str, Any]] = None,
    location_id: Optional[int] = None,
    session = None
):
    """Log when user selects a specific record for viewing/editing"""
    user = user or st.session_state.get("auth_user")
    location_id = location_id or st.session_state.get("active_location_id")
    
    ActionLogger.log_action(
        action="SELECT",
        resource_type=resource_type,
        resource_id=resource_id,
        username=user.get("username") if user else None,
        user_id=user.get("id") if user else None,
        location_id=location_id,
        details=f"Selected {resource_type}: {resource_label}",
        success=True,
        session=session
    )


def log_download_action(
    resource_type: str,
    file_name: str,
    file_format: str,
    user: Optional[Dict[str, Any]] = None,
    location_id: Optional[int] = None,
    session = None
):
    """Log when user downloads a file/report"""
    user = user or st.session_state.get("auth_user")
    location_id = location_id or st.session_state.get("active_location_id")
    
    ActionLogger.log_action(
        action="DOWNLOAD",
        resource_type=resource_type,
        resource_id=None,
        username=user.get("username") if user else None,
        user_id=user.get("id") if user else None,
        location_id=location_id,
        details=f"Downloaded {resource_type}: {file_name} ({file_format})",
        success=True,
        session=session
    )


def safe_transaction_operation(
    operation_func: Callable,
    operation_name: str,
    resource_type: str,
    user: Optional[Dict[str, Any]] = None,
    location_id: Optional[int] = None,
    severity: str = "HIGH"
) -> Optional[Any]:
    """
    Safely execute a transaction operation with automatic error handling and logging
    
    Usage:
        result = safe_transaction_operation(
            operation_func=lambda: create_transaction(data),
            operation_name="Creating Tank Transaction",
            resource_type="TankTransaction",
            user=user,
            location_id=location_id
        )
    """
    user = user or st.session_state.get("auth_user")
    location_id = location_id or st.session_state.get("active_location_id")
    
    with ErrorContext(
        context=operation_name,
        user=user,
        location_id=location_id,
        severity=severity,
        create_task=True,
        show_error=True
    ):
        result = operation_func()
        return result


# Example usage patterns as documentation
"""
USAGE EXAMPLES:

1. Logging a create operation:
   ```python
   # In your page after creating a record
   from action_logger_utils import log_create_action
   
   transaction = create_tank_transaction(data)
   log_create_action(
       resource_type="TankTransaction",
       resource_id=transaction.id,
       details=f"Created transaction for tank {tank_name}"
   )
   ```

2. Using the error handler decorator:
   ```python
   from error_handler import handle_errors
   
   @handle_errors("Creating tank transaction", severity="HIGH")
   def create_transaction_with_validation(data, user):
       # Your existing code here
       validate_data(data)
       transaction = TankTransaction(**data)
       session.add(transaction)
       session.commit()
       return transaction
   ```

3. Using safe_transaction_operation:
   ```python
   from action_logger_utils import safe_transaction_operation
   
   result = safe_transaction_operation(
       operation_func=lambda: create_transaction(form_data),
       operation_name="Creating Tank Transaction",
       resource_type="TankTransaction"
   )
   
   if result:
       st.success("Transaction created successfully!")
       log_create_action("TankTransaction", result.id)
   ```

4. Using ErrorContext for code blocks:
   ```python
   from error_handler import ErrorContext
   
   with ErrorContext("Processing bulk import", severity="HIGH"):
       for row in import_data:
           process_row(row)
   ```

5. Logging page views (at the start of render functions):
   ```python
   from action_logger_utils import log_view_action
   
   def render_tank_transactions_page(location_id, user):
       log_view_action("TankTransactions", user, location_id)
       # Rest of your page code
   ```
"""
