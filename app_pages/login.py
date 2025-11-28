# login.py
import streamlit as st
from datetime import datetime
import platform

from db import get_session
from auth import AuthManager
from ip_service import IPService
from task_manager import TaskManager
from security import SecurityManager
from models import User
from logger import ActionLogger
from ui_components import FormBuilder, Notifications, apply_custom_css


def render_login_page():
    """
    Simple login form using AuthManager.authenticate.
    AuthManager already logs login attempts + audit entries.
    """
    apply_custom_css()
    
    # Modern header with gradient background
    st.markdown("""
    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 2.5rem; border-radius: 12px; margin-bottom: 2rem; text-align: center;'>
        <h1 style='color: white; margin: 0; font-size: 2.5rem;'>🔐 OTMS Login</h1>
        <p style='color: rgba(255,255,255,0.9); margin: 0.5rem 0 0 0; font-size: 1.1rem;'>
            Oil Tanker Management System
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<p style='text-align: center; color: #666; margin-bottom: 2rem;'>Enter your credentials to continue</p>", unsafe_allow_html=True)

    with st.form("login_form"):
        FormBuilder.section_header("", "")
        username = FormBuilder.input_field("Username", "login_username", "Enter your username", required=True)
        password = FormBuilder.input_field("Password", "login_password", "Enter your password", "password", required=True)
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            submitted = st.form_submit_button("🔐 Login", use_container_width=True, type="primary")

    if submitted:
        if not username or not password:
            Notifications.error_alert("Please enter both username and password.", "Login Failed")
            return

        # Build a Streamlit-flavoured user agent similar to legacy app
        st_version = getattr(st, "__version__", "unknown")
        system_info = f"{platform.system()} {platform.release()}"
        python_version = platform.python_version()
        user_agent = f"Streamlit/{st_version} ({system_info}; Python {python_version})"

        # Detect client IP (public if available, else localhost)
        client_ip = IPService.get_client_ip()

        with get_session() as session:
            user_dict = AuthManager.authenticate(
                session=session,
                username=username.strip(),
                password=password,
                ip_address=client_ip,
                user_agent=user_agent,
            )

        if not user_dict:
            Notifications.error_alert("Invalid username or password. Please try again.", "Authentication Failed")
            return

        # Check for forced password change or 2FA setup
        with get_session() as session:
            from models import User
            from datetime import timedelta
            
            user = session.query(User).filter(User.id == user_dict["id"]).first()
            
            # Check if password expired (30-day rule for non-admins)
            password_expired = False
            if not user.password_never_expires:
                if user.password_changed_at:
                    password_age = (datetime.utcnow() - user.password_changed_at).days
                    expiry_days = user.password_expiry_days or 30
                    if password_age >= expiry_days:
                        password_expired = True
                else:
                    # Password never changed
                    password_expired = True
            
            # Store flags in session for post-login checks
            if user.force_password_change or password_expired:
                st.session_state["must_change_password"] = True
                st.session_state["password_expired"] = password_expired
            
            if user.force_2fa and not user.totp_enabled:
                st.session_state["must_setup_2fa"] = True

        # Track last activity in session (for idle timeout)
        user_dict["last_activity"] = datetime.utcnow().isoformat()

        # Save user in session
        st.session_state["auth_user"] = user_dict
        st.session_state["active_location_id"] = user_dict.get("location_id")
        st.session_state["current_page"] = "Home"
        st.session_state["client_ip"] = client_ip
        
        # Persist last login IP and UA for downstream pages (e.g., 2FA Settings)
        st.session_state["last_login_ip"] = client_ip
        st.session_state["last_login_useragent"] = user_agent

        Notifications.success_alert(f"Welcome, {user_dict.get('full_name') or user_dict['username']}!", "Login Successful")
        st.rerun()

    st.markdown("---")
    
    # Forgot Password Section
    FormBuilder.section_header("Forgot Password?", "Request a password reset from your administrator")
    if not st.session_state.get("fp_open"):
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("🔑 Request Password Reset", key="fp_open_btn", use_container_width=True, type="secondary"):
                st.session_state["fp_open"] = True
                st.rerun()
    else:
        with st.form("forgot_password_form"):
            fp_username = FormBuilder.input_field("Username", "fp_username", "Enter your username", required=True)
            
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                fp_submit = st.form_submit_button("📩 Submit Request", use_container_width=True, type="primary")

        if fp_submit:
            uname = (fp_username or "").strip()
            if not uname:
                Notifications.error_alert("Please enter your username to request a password reset.", "Missing Information")
            else:
                try:
                    with get_session() as s:
                        target = s.query(User).filter(User.username == uname).one_or_none()
                        if not target or not target.is_active:
                            Notifications.error_alert("Username not found or account is inactive. Please contact your administrator.", "User Not Found")
                        else:
                            user_stub = {"id": target.id, "username": target.username, "role": target.role}
                            TaskManager.create_password_reset_request(user=user_stub, reason=None)
                            try:
                                SecurityManager.log_audit(
                                    s,
                                    target.username,
                                    "TASK_CREATE",
                                    resource_type="Task:PasswordReset",
                                    resource_id=str(target.id),
                                    details=f"Password reset requested via Login page",
                                    user_id=target.id,
                                    location_id=target.location_id,
                                )
                            except Exception:
                                pass
                            Notifications.success_alert("Your password reset request has been submitted to the administrator. You will be notified once approved.", "Request Submitted")
                            st.session_state["fp_open"] = False
                            st.rerun()
                except Exception as ex:
                    Notifications.error_alert(f"Failed to submit request: {str(ex)}", "System Error")
                    try:
                        ActionLogger.log_error_with_task(ex, context="Login Forgot Password", user=None, location_id=None, severity="HIGH", additional_info=f"username={uname}")
                    except Exception:
                        pass
