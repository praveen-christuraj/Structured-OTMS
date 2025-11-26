# login.py
import streamlit as st
from datetime import datetime
import platform

from db import get_session
from auth import AuthManager
from ip_service import IPService


def render_login_page():
    """
    Simple login form using AuthManager.authenticate.
    AuthManager already logs login attempts + audit entries.
    """
    st.markdown("### 🔐 Login")
    st.write("Enter your OTMS credentials to continue.")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("🔐 Login")

    if submitted:
        if not username or not password:
            st.error("Please enter both username and password.")
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
            st.error("Invalid username or password.")
            return

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

        st.success(f"Welcome, {user_dict.get('full_name') or user_dict['username']}!")
        st.rerun()
