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
from ui_components import Notifications, apply_custom_css


def render_login_page(notice: str | None = None):
    """
    Compact login form using AuthManager.authenticate.
    AuthManager already logs login attempts + audit entries.
    """
    apply_custom_css()

    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] { display: none !important; }
        header[data-testid="stHeader"] { display: none !important; }
        [data-testid="stAppViewContainer"] > .main {
            padding: 0 !important;
            display: flex;
            align-items: center;
            justify-content: center;
            background: radial-gradient(1000px 500px at 12% 15%, rgba(37,99,235,0.08), transparent 60%),
                        radial-gradient(900px 450px at 88% 10%, rgba(14,165,233,0.08), transparent 60%),
                        linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
        }
        [data-testid="stAppViewContainer"] .block-container {
            width: 100%;
            max-width: 1040px;
            padding: 1rem 1.25rem 1.25rem;
        }
        .login-brand-panel {
            display: grid;
            place-items: center;
            min-height: 300px;
            padding: 0.5rem;
            margin-top: -10.5rem;
        }
        .brand-tagline {
            margin: 0.5rem 0 0 0;
            color: #334155;
            font-weight: 700;
            letter-spacing: 0.01em;
        }
        div[data-testid="stForm"] {
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%) !important;
            border: 1px solid rgba(15, 23, 42, 0.08) !important;
            border-radius: 16px !important;
            padding: 1.05rem !important;
            box-shadow: 0 18px 55px rgba(15, 23, 42, 0.18) !important;
            margin-bottom: 0.6rem !important;
        }
        .login-form h3 { margin: 0 0 0.15rem 0; color: #0f172a; }
        .login-form .sub { margin: 0 0 0.7rem 0; color: #475569; }
        .compact-label { font-weight: 700; color: #0f172a; margin: 0.35rem 0 0.25rem 0; }
        .login-helper { margin-top: 0.25rem; font-size: 0.9rem; color: #475569; }
        .login-utility { margin-top: 0.4rem; }
        @media (max-width: 980px) {
            [data-testid="stAppViewContainer"] .block-container { padding: 0.8rem 1rem 1rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col_left, col_right = st.columns([0.9, 1], gap="large")

    with col_left:
        st.markdown('<div class="login-brand-panel">', unsafe_allow_html=True)
        logo_shown = False
        for logo_path in (
            "assets/app_logo.png",
            "assets/logo.png",
            "assets/logos/otms_logo.png",
        ):
            try:
                st.image(logo_path, width=190)
                logo_shown = True
                break
            except Exception:
                continue
        if not logo_shown:
            st.markdown("<h3 style='color:#0f172a; margin:0;'>OTMS</h3>", unsafe_allow_html=True)
        st.markdown("<p class='brand-tagline'>A Hydrocarbon Accounting Solution</p>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    fp_submit = False
    fp_username = ""

    with col_right:
        with st.form("login_form"):
            st.markdown(
                """
                <div class="login-form">
                    <h3>Sign in</h3>
                    <p class="sub">Enter your credentials to continue.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if notice:
                st.warning(notice)

            st.markdown("<div class='compact-label'>Username</div>", unsafe_allow_html=True)
            username = st.text_input(
                "Username", key="login_username", placeholder="Enter your username", label_visibility="collapsed"
            )

            st.markdown("<div class='compact-label'>Password</div>", unsafe_allow_html=True)
            password = st.text_input(
                "Password",
                key="login_password",
                type="password",
                placeholder="Enter your password",
                label_visibility="collapsed",
            )

            submitted = st.form_submit_button("Sign in", use_container_width=True, type="primary")

        with st.expander("Need a password reset?", expanded=False):
            st.caption("Send a quick request to your administrator.")
            with st.form("forgot_password_form"):
                st.markdown("<div class='compact-label'>Username</div>", unsafe_allow_html=True)
                fp_username = st.text_input(
                    "Forgot Username",
                    key="fp_username",
                    placeholder="Enter your username",
                    label_visibility="collapsed",
                )
                fp_submit = st.form_submit_button("Send request", use_container_width=True, type="secondary")

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

        Notifications.success_alert(
            f"Welcome, {user_dict.get('full_name') or user_dict['username']}!", "Login Successful"
        )
        st.rerun()

    if fp_submit:
        uname = (fp_username or "").strip()
        if not uname:
            Notifications.error_alert("Please enter your username to request a password reset.", "Missing Information")
        else:
            try:
                with get_session() as s:
                    target = s.query(User).filter(User.username == uname).one_or_none()
                    if not target or not target.is_active:
                        Notifications.error_alert(
                            "Username not found or account is inactive. Please contact your administrator.",
                            "User Not Found",
                        )
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
                                details="Password reset requested via Login page",
                                user_id=target.id,
                                location_id=target.location_id,
                            )
                        except Exception:
                            pass
                        Notifications.success_alert(
                            "Your password reset request has been submitted to the administrator. You will be notified once approved.",
                            "Request Submitted",
                        )
                        st.rerun()
            except Exception as ex:
                Notifications.error_alert(f"Failed to submit request: {str(ex)}", "System Error")
                try:
                    ActionLogger.log_error_with_task(
                        ex,
                        context="Login Forgot Password",
                        user=None,
                        location_id=None,
                        severity="HIGH",
                        additional_info=f"username={uname}",
                    )
                except Exception:
                    pass
