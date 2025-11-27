# error_handler.py
"""
Centralized error handling decorators and utilities for OTMS
Automatically logs errors, creates admin tasks, and provides user feedback
"""

import functools
import streamlit as st
from typing import Callable, Optional, Dict, Any
from logger import ActionLogger, log_error
import traceback


def handle_errors(
    context: str,
    user_message: Optional[str] = None,
    severity: str = "HIGH",
    log_action: bool = True,
    create_task: bool = True,
    show_error: bool = True
):
    """
    Decorator to handle errors in any function with comprehensive logging
    
    Args:
        context: Description of the operation being performed
        user_message: Custom message to show to user (default: generic error message)
        severity: HIGH, MEDIUM, or LOW - determines task priority
        log_action: Whether to log the action
        create_task: Whether to create an admin task for the error
        show_error: Whether to show error message to user
    
    Usage:
        @handle_errors("Creating tank transaction", severity="HIGH")
        def create_transaction(data, user):
            # Your code here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                return result
                
            except Exception as e:
                # Extract user and location from args/kwargs or session state
                user = None
                location_id = None
                
                # Try to get user from function arguments
                if 'user' in kwargs:
                    user = kwargs['user']
                elif len(args) > 0:
                    # Check common patterns: (location_id, user) or (user)
                    for arg in args:
                        if isinstance(arg, dict) and 'username' in arg:
                            user = arg
                            break
                
                # Try to get location_id from arguments
                if 'location_id' in kwargs:
                    location_id = kwargs['location_id']
                elif 'active_location_id' in kwargs:
                    location_id = kwargs['active_location_id']
                elif len(args) > 0:
                    for arg in args:
                        if isinstance(arg, int):
                            location_id = arg
                            break
                
                # Fall back to session state
                if not user:
                    user = st.session_state.get("auth_user")
                if not location_id:
                    location_id = st.session_state.get("active_location_id")
                
                # Log the error comprehensively
                if create_task:
                    ActionLogger.log_error_with_task(
                        error=e,
                        context=context,
                        user=user,
                        location_id=location_id,
                        severity=severity,
                        additional_info=f"Function: {func.__name__}\nModule: {func.__module__}"
                    )
                else:
                    # Just log without creating task
                    log_error(
                        f"Error in {context} ({func.__name__}): {str(e)}\n"
                        f"User: {user.get('username') if user else 'Unknown'}\n"
                        f"Traceback: {traceback.format_exc()}",
                        exc_info=True
                    )
                
                # Show error to user
                if show_error:
                    if user_message:
                        st.error(user_message)
                    else:
                        st.error(
                            f"❌ An error occurred while {context.lower()}. "
                            f"The error has been logged and reported to administrators."
                        )
                    
                    # Show error details in expander for debugging
                    with st.expander("🔍 Error Details (for debugging)", expanded=False):
                        st.code(str(e))
                        st.caption(f"Error Type: {type(e).__name__}")
                
                # Re-raise if this is critical
                if severity == "CRITICAL":
                    raise
                
                return None
                
        return wrapper
    return decorator


def log_action_decorator(
    action: str,
    resource_type: str,
    get_resource_id: Optional[Callable] = None,
    success_message: Optional[str] = None
):
    """
    Decorator to automatically log actions to audit trail
    
    Args:
        action: Action type (CREATE, UPDATE, DELETE, VIEW, EXPORT, etc.)
        resource_type: Type of resource
        get_resource_id: Function to extract resource_id from function result or args
        success_message: Optional success message to show user
    
    Usage:
        @log_action_decorator("CREATE", "TankTransaction", get_resource_id=lambda r: r.id)
        def create_transaction(data, user):
            # Your code here
            return transaction
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract user and location
            user = kwargs.get('user') or st.session_state.get("auth_user")
            location_id = kwargs.get('location_id') or kwargs.get('active_location_id') or st.session_state.get("active_location_id")
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Extract resource_id
            resource_id = None
            if get_resource_id and result:
                try:
                    resource_id = get_resource_id(result)
                except Exception:
                    resource_id = None
            
            # Log the action
            ActionLogger.log_action(
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                username=user.get('username') if user else None,
                user_id=user.get('id') if user else None,
                location_id=location_id,
                details=f"{action} {resource_type} via {func.__name__}",
                success=True
            )
            
            # Show success message
            if success_message:
                st.success(success_message)
            
            return result
            
        return wrapper
    return decorator


class ErrorContext:
    """Context manager for handling errors in code blocks"""
    
    def __init__(
        self,
        context: str,
        user: Optional[Dict[str, Any]] = None,
        location_id: Optional[int] = None,
        severity: str = "HIGH",
        create_task: bool = True,
        show_error: bool = True
    ):
        self.context = context
        self.user = user or st.session_state.get("auth_user")
        self.location_id = location_id or st.session_state.get("active_location_id")
        self.severity = severity
        self.create_task = create_task
        self.show_error = show_error
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # An exception occurred
            if self.create_task:
                ActionLogger.log_error_with_task(
                    error=exc_val,
                    context=self.context,
                    user=self.user,
                    location_id=self.location_id,
                    severity=self.severity
                )
            else:
                log_error(
                    f"Error in {self.context}: {str(exc_val)}",
                    exc_info=True
                )
            
            if self.show_error:
                st.error(
                    f"❌ An error occurred while {self.context.lower()}. "
                    f"The error has been logged and reported to administrators."
                )
            
            # Suppress the exception (return True) or let it propagate (return False)
            return True if self.severity != "CRITICAL" else False
        
        return False


def safe_execute(func: Callable, context: str, *args, **kwargs) -> Optional[Any]:
    """
    Safely execute a function with error handling
    
    Args:
        func: Function to execute
        context: Description of operation
        *args, **kwargs: Arguments to pass to function
    
    Returns:
        Result of function or None if error occurred
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        user = st.session_state.get("auth_user")
        location_id = st.session_state.get("active_location_id")
        
        ActionLogger.log_error_with_task(
            error=e,
            context=context,
            user=user,
            location_id=location_id,
            severity="MEDIUM"
        )
        
        st.error(f"❌ Error: {str(e)}")
        return None
