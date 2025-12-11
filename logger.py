# logger.py
"""
Enhanced logging system for OTMS
Logs errors, warnings, and info to files with comprehensive action tracking
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import sys
import traceback

# Create logs directory
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# Configure logging
def setup_logger(name: str = "OTMS") -> logging.Logger:
    """Setup application logger with file and console handlers"""
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # File handler (daily rotation)
    today = datetime.now().strftime("%Y-%m-%d")
    file_handler = logging.FileHandler(
        LOGS_DIR / f"otms_{today}.log",
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Create default logger
logger = setup_logger()

# Convenience functions
def log_info(message: str):
    """Log info message"""
    logger.info(message)

def log_warning(message: str):
    """Log warning message"""
    logger.warning(message)

def log_error(message: str, exc_info=False):
    """Log error message"""
    logger.error(message, exc_info=exc_info)

def log_critical(message: str, exc_info=False):
    """Log critical error"""
    logger.critical(message, exc_info=exc_info)

def log_debug(message: str):
    """Log debug message"""
    logger.debug(message)


# ============================================================================
# COMPREHENSIVE ACTION LOGGING
# ============================================================================

class ActionLogger:
    """Centralized action logging with automatic audit trail and error handling"""
    
    @staticmethod
    def log_action(
        action: str,
        resource_type: str,
        resource_id: Optional[Any] = None,
        username: Optional[str] = None,
        user_id: Optional[int] = None,
        location_id: Optional[int] = None,
        details: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        success: bool = True,
        session=None
    ):
        """
        Log any action with comprehensive details and automatic audit trail
        
        Args:
            action: Action type (CREATE, UPDATE, DELETE, VIEW, EXPORT, LOGIN, etc.)
            resource_type: Type of resource being acted upon
            resource_id: ID of the resource
            username: Username performing the action
            user_id: User ID performing the action
            location_id: Location where action occurred
            details: Additional details about the action
            metadata: Dictionary of additional context
            success: Whether the action was successful
            session: Database session (optional)
        """
        try:
            from security import SecurityManager
            
            # Build detailed log message
            log_msg = f"[{action}] {resource_type}"
            if resource_id:
                log_msg += f" #{resource_id}"
            if username:
                log_msg += f" by {username}"
            if details:
                log_msg += f" - {details}"
            
            # Add metadata to log
            if metadata:
                log_msg += f" | Metadata: {metadata}"
            
            # Log to file
            if success:
                logger.info(log_msg)
            else:
                logger.error(log_msg)
            
            # Write to audit trail
            SecurityManager.log_audit(
                session=session,
                username=username or "system",
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                details=details,
                user_id=user_id,
                location_id=location_id,
                success=success
            )
            
        except Exception as e:
            logger.error(f"Failed to log action: {e}", exc_info=True)
    
    @staticmethod
    def log_error_with_task(
        error: Exception,
        context: str,
        user: Optional[Dict[str, Any]] = None,
        location_id: Optional[int] = None,
        severity: str = "HIGH",
        additional_info: Optional[str] = None
    ):
        """
        Log an error and automatically create a task for admin review
        
        Args:
            error: The exception that occurred
            context: Description of where/what was being done
            user: User dictionary with username, role, etc.
            location_id: Location where error occurred
            severity: HIGH, MEDIUM, or LOW
            additional_info: Any additional context about the error
        """
        try:
            from task_manager import TaskManager
            
            # Build comprehensive error message
            error_msg = f"Error in {context}: {str(error)}"
            if additional_info:
                error_msg += f"\n{additional_info}"
            
            # Get stack trace
            stack_trace = ''.join(traceback.format_exception(
                type(error), error, error.__traceback__
            ))
            
            # Log error to file with full traceback
            logger.error(
                f"[ERROR] {context}\n"
                f"Error: {str(error)}\n"
                f"User: {user.get('username') if user else 'system'}\n"
                f"Location: {location_id}\n"
                f"Stack trace:\n{stack_trace}"
            )
            
            # Create error task for admin
            TaskManager.create_error_task(
                error_message=error_msg,
                context=context,
                user=user,
                location_id=location_id,
                severity=severity,
                stack_trace=stack_trace,
                additional_info=additional_info
            )
            
        except Exception as e:
            logger.critical(f"Failed to log error with task: {e}", exc_info=True)
    
    @staticmethod
    def log_login(username: str, success: bool, ip_address: Optional[str] = None, 
                  failure_reason: Optional[str] = None):
        """Log user login attempt"""
        if success:
            logger.info(f"LOGIN SUCCESS: {username} from {ip_address or 'unknown IP'}")
        else:
            logger.warning(
                f"LOGIN FAILED: {username} from {ip_address or 'unknown IP'} - "
                f"Reason: {failure_reason or 'invalid credentials'}"
            )
    
    @staticmethod
    def log_logout(username: str, ip_address: Optional[str] = None):
        """Log user logout"""
        logger.info(f"LOGOUT: {username} from {ip_address or 'unknown IP'}")
    
    @staticmethod
    def log_session_timeout(username: str):
        """Log session timeout"""
        logger.info(f"SESSION TIMEOUT: {username}")
    
    @staticmethod
    def log_2fa_setup(username: str, success: bool):
        """Log 2FA setup attempt"""
        status = "SUCCESS" if success else "FAILED"
        logger.info(f"2FA SETUP {status}: {username}")
    
    @staticmethod
    def log_2fa_verification(username: str, success: bool):
        """Log 2FA verification attempt"""
        status = "SUCCESS" if success else "FAILED"
        logger.info(f"2FA VERIFY {status}: {username}")