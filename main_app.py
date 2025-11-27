import streamlit as st
from datetime import datetime, timedelta
import importlib.util

from db import init_db, get_session
from ui import header
from security import SecurityManager
from auth import AuthManager
from models import User, Location
from app_pages.manage_users import ROLE_ICONS as USER_ROLE_ICONS
from permission_manager import PermissionManager
from location_config import get_location_page_visibility
from app_pages.page_customization import render_page_customization
from app_pages.tanker_transactions import render_tanker_transactions_page
from app_pages.vessel_operations import render_vessel_operations_page
from app_pages.yade_vessel_mapping import render_yade_vessel_mapping_page
from location_config import get_page_section_config  # (kept in case other pages use it)

# Session timeout (minutes)
SecurityManager.SESSION_TIMEOUT_MINUTES = 30

# Make sure DB is ready once at import
init_db()

# ---- Icons for pages ----
ICONS = {
    "Home": "🏠",
    "My Tasks": "✅",
    "Profile Settings": "👤",
    "Manage Locations": "📍",
    "Manage Users": "👥",
    "Audit Log": "🧾",
    "Error Monitoring": "🔍",
    "Location Settings": "📍⚙️",
    "Asset Management": "🧰",
    "Page Customization": "🛠️",
    "Dashboard Customization": "📊⚙️",
    "Tank Transactions": "🛢️",
    "Tanker Transactions": "🚚",
    "Yade Transactions": "⛴️",
    "Yade Tracking": "📍",
    "Yade-Vessel Mapping": "🚩",
    "Vessel Operations": "🛳️",
    "FSO-Operations": "⚓",
    "Reports": "📄",
    "Reporting": "📊",
    "Report Customization": "🛠️",
    "MB Customization": "🛠️",
    "Settings": "⚙️",
    "View Transactions": "🗂️",
    "OTR": "📊",
    "Deleted Records": "🗑️",
    "Material Balance": "🧮",
    "2FA Settings": "🔐",
    "Login History": "📜",
    "Convoy Status": "ℹ️",
    "BCCR": "🗃️",
    "Sharing": "🔗",
    "Services": "🛠️",
    "Backup & Recovery": "💾",
    }

ROLE_ICONS = USER_ROLE_ICONS


def role_with_icon_main(role: str) -> str:
    return f"{ROLE_ICONS.get(role, '👤')} {role}"


def ensure_default_admin_user():
    """
    If there are no users in the database, create a default admin-operations user.

    Default credentials:
        username: admin
        password: Admin@123
    """
    with get_session() as session:
        existing_count = session.query(User).count()
        if existing_count > 0:
            return

        admin_dict = AuthManager.create_user(
            session=session,
            username="admin",
            password="Admin@123",
            full_name="System Admin",
            role="admin-operations",
            location_id=None,
            supervisor_code=None,
        )

        # Optional: write an audit entry (system bootstrap)
        SecurityManager.log_audit(
            session,
            username="system",
            action="CREATE",
            resource_type="User",
            resource_id=str(admin_dict["id"]),
            details="Bootstrap: default admin-operations user created (username=admin).",
            user_id=None,
            location_id=None,
        )


def _module_exists(dotted_path: str) -> bool:
    """Return True if a module can be imported (module present)."""
    return importlib.util.find_spec(dotted_path) is not None


def _inject_sidebar_css():
    """Apply light, professional theme + glass-style sidebar nav."""
    st.markdown(
        """
        <style>
        /* -------- Global Page Look (light, professional) -------- */
        .block-container { padding-top: 1.2rem; }
        header[data-testid="stHeader"] { background: transparent; }
        body {
            background: #f3f4f6; color: #111827;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                         Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif;
        }
        /* Global button polish */
        .stButton > button {
            border-radius: 14px !important; padding: .6rem 1.0rem !important;
            font-weight: 600 !important; box-shadow: 0 6px 16px rgba(0,0,0,.06) !important;
            border: 1px solid rgba(0,0,0,.06) !important;
            transition: transform .06s ease, box-shadow .2s ease, background .2s ease !important;
        }
        .stButton > button:hover { transform: translateY(-1px); box-shadow: 0 10px 24px rgba(0,0,0,.10) !important; }
        .stButton > button:active { transform: translateY(0); }
        /* Primary buttons look */
        div[data-testid="stButton"] button[kind="primary"],
        .stButton > button[kind="primary"] {
            background: linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%) !important;
            color: #ffffff !important; border: 0 !important;
        }
        div[data-testid="stButton"] button[kind="primary"]:hover,
        .stButton > button[kind="primary"]:hover {
            box-shadow: 0 10px 26px rgba(37,99,235,.35) !important;
        }
        /* -------- Sidebar (light glass style) -------- */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #f9fafb 0%, #e5e7eb 100%) !important;
            border-right: 1px solid #e5e7eb !important;
        }
        /* Sidebar nav buttons (glass cards) */
        section[data-testid="stSidebar"] .stButton > button {
            width: 100%; text-align: left; border-radius: 18px; padding: 0.45rem 0.8rem; margin-bottom: 0.3rem;
            background: rgba(255,255,255,0.85); backdrop-filter: blur(14px);
            border: 1px solid rgba(148,163,184,0.55);
            box-shadow: 0 8px 20px rgba(15,23,42,0.06);
            color: #111827; font-weight: 600; font-size: 0.9rem;
        }
        section[data-testid="stSidebar"] .stButton > button:hover {
            background: rgba(255,255,255,1.0); box-shadow: 0 12px 30px rgba(15,23,42,0.12);
        }
        /* Sidebar active button (disabled used as active) */
        section[data-testid="stSidebar"] .stButton > button:disabled {
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
            border-color: rgba(191,219,254,0.95) !important; color: #ffffff !important;
            box-shadow: 0 18px 40px rgba(37,99,235,0.45);
        }
        /* Inputs */
        input, textarea, select, .stNumberInput input, .stTextInput input { border-radius: 12px !important; }
        /* Alerts */
        div[data-testid="stAlert"] { border-radius: 16px !important; }
        img { border-radius: 14px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _ensure_session_defaults():
    ss = st.session_state
    ss.setdefault("auth_user", None)
    ss.setdefault("active_location_id", None)
    ss.setdefault("current_page", "Home")


def get_pages(user, active_location_id):
    """
    Pages depend on:
      - Role (PermissionManager)
      - Per-location page visibility (Location Settings)
      - Module presence (only show pages that actually exist)
    """
    pages = ["Home", "My Tasks", "Profile Settings", "2FA Settings", "Login History", "Sharing", "Services"]

    # ---- Management pages (admins only) ----
    if user and PermissionManager.can_access_management_pages(user):
        pages += [
            "Manage Locations",
            "Manage Users",
            "Audit Log",
            "Error Monitoring",
            "Location Settings",
            "Asset Management",
            "Page Customization",
            "Dashboard Customization",
            "MB Customization",
            "Report Customization",
            "Deleted Records",
            "Backup & Recovery",
        ]

    # ---- Operational pages (role + location flags + module present) ----
    role_ok = bool(user and PermissionManager.can_access_operational_pages(user))
    loc_flags = {}
    if active_location_id:
        try:
            with get_session() as session:
                loc_flags = get_location_page_visibility(session, active_location_id) or {}
        except Exception:
            loc_flags = {}

    # Mapping: flag -> (page title, module path)
    ops = [
        ("show_tank_transactions",   ("Tank Transactions",   "app_pages.tank_transactions")),
        ("show_tanker_transactions", ("Tanker Transactions", "app_pages.tanker_transactions")),
        ("show_tank_transactions",   ("View Transactions",   "app_pages.view_transactions")),
        ("show_yade_transactions",   ("Yade Transactions",   "app_pages.yade_transactions")),
        ("show_yade_tracking",       ("Yade Tracking",       "app_pages.yade_tracking")),
        ("show_yade_vessel_mapping", ("Yade-Vessel Mapping", "app_pages.yade_vessel_mapping")),
        ("show_otr",                 ("OTR",                 "app_pages.otr")),
        ("show_fso_operations",      ("FSO-Operations",      "app_pages.fso_operations")),
        ("show_vessel_operations",   ("Vessel Operations",   "app_pages.vessel_operations")),
        ("show_reports",             ("Reports",             "app_pages.reports")),
        ("show_reporting",           ("Reporting",           "app_pages.reporting")),
        ("show_material_balance",    ("Material Balance",    "app_pages.material_balance")),
        ("show_bccr",                ("BCCR",                "app_pages.bccr")),
        ("show_convoy_status",       ("Convoy Status",       "app_pages.convoy_status")),
        ("show_sharing",             ("Sharing",             "app_pages.sharing")),
    ]

    if role_ok:
        for flag, (title, mod) in ops:
            # Default-visible pages when location flag is missing
            default_true = {"show_otr", "show_reporting", "show_material_balance", "show_yade_vessel_mapping"}
            allow = loc_flags.get(flag, flag in default_true)

            if allow and _module_exists(mod):
                if title not in pages:
                    pages.append(title)

    return pages

def _render_sidebar_nav(pages, current_page, user, active_location_id):
    """User header (logo on top) + logout + glass-style icon nav in sidebar."""
    _inject_sidebar_css()

    # ---------- User header ----------
    with st.sidebar.container():
        # Logo at the very top
        logo_loaded = False
        for logo_path in (
            "assets/app_logo.png",
            "assets/logo.png",
            "assets/logos/otms_logo.png",
        ):
            try:
                st.image(logo_path, width=150)
                logo_loaded = True
                break
            except Exception:
                continue
        if not logo_loaded:
            st.markdown("### 🛢️ OTMS")

        st.markdown("---")

        # User info below the logo
        if user:
            username = user.get("username", "")
            role = user.get("role", "")
            # Assigned location of user (not active dashboard location)
            loc_label = "Not assigned"
            if user.get("location_id"):
                with get_session() as session:
                    loc = session.query(Location).get(user["location_id"])
                    if loc:
                        loc_label = loc.name

            st.markdown(f"🧑‍💼 **Username:** {username}")
            st.markdown(f"{ROLE_ICONS.get(role, '👤')} **Role:** {role}")
            st.markdown(f"📍 **Location:** {loc_label}")
        else:
            st.markdown("**Not logged in**")

    # ---------- Task Notifications ----------
    if user:
        from ui import render_task_notification_badge, render_error_summary_for_admin
        
        # Show pending task notifications
        render_task_notification_badge(user)
        
        # Show error summary for admin users
        render_error_summary_for_admin(user)

    # ---------- Logout with confirmation ----------
    if user:
        if "logout_confirm" not in st.session_state:
            st.session_state["logout_confirm"] = False

        if not st.session_state["logout_confirm"]:
            if st.sidebar.button("🚪 Logout", key="btn_logout"):
                st.session_state["logout_confirm"] = True
        else:
            st.sidebar.warning("Are you sure you want to logout?")
            c1, c2 = st.sidebar.columns(2)
            if c1.button("✅Yes", key="btn_logout_yes"):
                SecurityManager.log_audit(
                    None,
                    user["username"],
                    "LOGOUT",
                    resource_type="User",
                    resource_id=str(user["id"]),
                    details="User logged out from sidebar",
                    user_id=user["id"],
                    location_id=user.get("location_id"),
                )
                st.session_state["auth_user"] = None
                st.session_state["active_location_id"] = None
                st.session_state["current_page"] = "Home"
                st.session_state["logout_confirm"] = False
                st.rerun()

            if c2.button("❌ No", key="btn_logout_no"):
                st.session_state["logout_confirm"] = False
    else:
        st.sidebar.caption("Not logged in")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📋 Navigation")

    # ---------- Navigation buttons (single click) ----------
    for p in pages:
        label = f"{ICONS.get(p, '📄')}  {p}"
        is_active = (p == current_page)
        btn_label = f"{'• ' if is_active else ''}{label}"

        if st.sidebar.button(btn_label, key=f"nav_{p}"):
            st.session_state["current_page"] = p
            st.rerun()


def main():
    st.set_page_config(
        page_title="OTMS",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Ensure DB + default admin user
    init_db()
    ensure_default_admin_user()
    _ensure_session_defaults()

    user = st.session_state.get("auth_user")

    from app_pages.login import render_login_page  # local import to avoid circulars

    # ================= NOT LOGGED IN ================= #
    if not user:
        header("OTMS Login")
        render_login_page()
        return

    # ================= SESSION TIMEOUT CHECK ================= #
    # If session is already expired → log + clear + show login
    if SecurityManager.is_session_expired(user):
        try:
            SecurityManager.log_audit(
                None,
                user.get("username", "unknown"),
                "SESSION_EXPIRED",
                resource_type="User",
                resource_id=str(user.get("id")),
                details=f"Session expired after {SecurityManager.SESSION_TIMEOUT_MINUTES} minutes of inactivity.",
                user_id=user.get("id"),
                location_id=user.get("location_id"),
                success=False,
            )
        except Exception:
            pass

        # Clear session and go back to login
        st.session_state["auth_user"] = None
        st.session_state["active_location_id"] = None
        st.session_state["current_page"] = "Home"
        st.session_state["logout_confirm"] = False

        header("OTMS Login")
        st.warning(
            f"⏰ Your session has expired due to {SecurityManager.SESSION_TIMEOUT_MINUTES} minutes of inactivity. "
            "Please log in again."
        )
        render_login_page()
        return

    # ================= SESSION STILL VALID ================= #
    # Sliding timeout UI hint
    last_activity = user.get("last_activity")
    last_activity_dt = None
    if last_activity:
        if isinstance(last_activity, str):
            try:
                last_activity_dt = datetime.fromisoformat(last_activity)
            except ValueError:
                last_activity_dt = None
        else:
            last_activity_dt = last_activity

    if last_activity_dt:
        timeout = timedelta(minutes=SecurityManager.SESSION_TIMEOUT_MINUTES)
        expires_at = last_activity_dt + timeout
        remaining_seconds = (expires_at - datetime.utcnow()).total_seconds()

        if 0 < remaining_seconds <= 5 * 60:
            minutes_left = max(1, int(remaining_seconds // 60))
            st.sidebar.warning(
                f"⏰ Session expires in ~{minutes_left} minute(s). "
                "Any activity will keep you logged in."
            )

    # Refresh last activity both in DB and in session (sliding timeout)
    try:
        with get_session() as session:
            SecurityManager.update_last_activity(session, user["id"])
    except Exception:
        pass

    user["last_activity"] = datetime.utcnow().isoformat()
    st.session_state["auth_user"] = user

    # ================= ENFORCE PASSWORD/2FA REQUIREMENTS ================= #
    # Check if user must change password or setup 2FA
    must_change_password = st.session_state.get("must_change_password", False)
    must_setup_2fa = st.session_state.get("must_setup_2fa", False)
    password_expired = st.session_state.get("password_expired", False)
    
    if must_change_password or must_setup_2fa:
        # Force redirect to Profile Settings
        if st.session_state.get("current_page") != "Profile Settings":
            st.session_state["current_page"] = "Profile Settings"
        
        # Show warning
        if password_expired:
            st.error("🔐 Your password has expired. You must change it before accessing other pages.")
        elif must_change_password:
            st.warning("🔐 You must change your password before accessing other pages.")
        
        if must_setup_2fa:
            st.warning("🔒 2FA setup is mandatory. Please complete it before accessing other pages.")
        
        # Only allow access to Profile Settings
        from app_pages.profile_settings import render
        render()
        st.stop()

    # ================= NORMAL APP FLOW ================= #
    active_location_id = st.session_state.get("active_location_id")
    current_page = st.session_state.get("current_page", "Home")

    # Top header for the main app
    header("OTMS Dashboard")

    # Sidebar navigation (role-based pages)
    pages = get_pages(user, active_location_id)
    if current_page not in pages:
        current_page = "Home"
        st.session_state["current_page"] = current_page

    _render_sidebar_nav(pages, current_page, user, active_location_id)

    # ---- ROUTING ----
    if current_page == "Home":
        from app_pages.home import render_home_page
        render_home_page(active_location_id, user)

    elif current_page == "My Tasks":
        from app_pages.my_tasks import render_my_tasks_page
        render_my_tasks_page(active_location_id, user)
    
    elif current_page == "Profile Settings":
        from app_pages.profile_settings import render
        render()

    elif current_page == "Manage Locations":
        from app_pages.manage_locations import render_manage_locations_page
        render_manage_locations_page(active_location_id, user)

    elif current_page == "Manage Users":
        from app_pages.manage_users import render_manage_users_page
        render_manage_users_page(active_location_id, user)

    elif current_page == "Audit Log":
        from app_pages.audit_log import render_audit_log_page
        render_audit_log_page(active_location_id, user)
    
    elif current_page == "Error Monitoring":
        from error_monitoring import render_error_monitoring_dashboard
        render_error_monitoring_dashboard(user)

    elif current_page == "Location Settings":
        from app_pages.location_settings import render_location_settings_page
        render_location_settings_page(active_location_id, user)

    elif current_page == "Asset Management":
        from app_pages.asset_management import render_asset_management_page
        render_asset_management_page(active_location_id, user)

    elif current_page == "Page Customization":
        render_page_customization(user)

    elif current_page == "Dashboard Customization":
        from app_pages.dashboard_customization import render_dashboard_customization
        render_dashboard_customization()

    elif current_page == "MB Customization":
        from app_pages.mb_customization import render_mb_customization_page
        render_mb_customization_page(user)

    elif current_page == "Tank Transactions":
        from app_pages.tank_transactions import render_tank_transactions_page
        render_tank_transactions_page(active_location_id, user)

    elif current_page == "Tanker Transactions":
        # separate file: app_pages/tanker_transactions.py
        render_tanker_transactions_page(active_location_id, user)

    elif current_page == "Yade Transactions":
        from app_pages.yade_transactions import render_yade_transactions_page
        render_yade_transactions_page(active_location_id, user)

    elif current_page == "Yade Tracking":
        from app_pages.yade_tracking import render_yade_tracking_page
        render_yade_tracking_page(active_location_id, user)

    elif current_page == "Yade-Vessel Mapping":
        render_yade_vessel_mapping_page(active_location_id, user)

    elif current_page == "View Transactions":
        from app_pages.view_transactions import render_view_transactions_page
        render_view_transactions_page(active_location_id, user)

    elif current_page == "Vessel Operations":
        render_vessel_operations_page(active_location_id, user)

    elif current_page == "FSO-Operations":
        from app_pages.fso_operations import render_fso_operations_page
        render_fso_operations_page(active_location_id, user)
    elif current_page == "Deleted Records":
        from app_pages.recycle_bin_page import render_recycle_bin_page
        render_recycle_bin_page(active_location_id, user)
    elif current_page == "OTR":
        from app_pages.otr import render_otr_page
        render_otr_page(active_location_id, user)

    elif current_page == "Material Balance":
        from app_pages.material_balance import render_material_balance_page
        render_material_balance_page(active_location_id, user)
    
    elif current_page == "Reporting":
        from app_pages.reporting import render_reporting_page
        render_reporting_page(active_location_id, user)

    elif current_page == "Report Customization":
        from app_pages.report_customization import render_report_customization_page
        render_report_customization_page(user, active_location_id)
    elif current_page == "BCCR":
        from app_pages.bccr import render_bccr_page
        render_bccr_page(active_location_id, user)
    elif current_page == "Convoy Status":
        from app_pages.convoy_status import render_convoy_status_page
        render_convoy_status_page(active_location_id, user)
    elif current_page == "Sharing":
        from app_pages.sharing import render_sharing_page
        render_sharing_page(active_location_id, user)
        
    elif current_page == "2FA Settings":
        from app_pages.twofa_settings import render_twofa_settings_page
        render_twofa_settings_page(active_location_id, user)

    elif current_page == "Login History":
        from app_pages.login_history import render_login_history_page
        render_login_history_page(active_location_id, user)
    elif current_page == "Services":
        from app_pages.services import render_services_page
        render_services_page(active_location_id, user)
    elif current_page == "Backup & Recovery":
        from app_pages.backup_recovery import render_backup_recovery_page
        render_backup_recovery_page(active_location_id, user)
    # elif current_page == "FSO-Operations":
    #     from app_pages.fso_operations import render_fso_operations_page
    #     render_fso_operations_page(active_location_id, user)
    #
    # elif current_page == "Reports":
    #     from app_pages.reports import render_reports_page
    #     render_reports_page(active_location_id, user)


if __name__ == "__main__":
    main()
