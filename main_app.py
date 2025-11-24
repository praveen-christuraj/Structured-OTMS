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
from location_config import get_page_section_config  # (kept in case other pages use it)

# Session timeout (minutes)
SecurityManager.SESSION_TIMEOUT_MINUTES = 30

# Make sure DB is ready once at import
init_db()

# ---- Icons for pages ----
ICONS = {
    "Home": "🏠",
    "My Tasks": "✅",
    "Manage Locations": "🌍",
    "Manage Users": "👥",
    "Audit Log": "🧾",
    "Location Settings": "🧩",
    "Asset Management": "🧺",
    "Page Customization": "⚙️",
    "Tank Transactions": "🛢️",
    "Tanker Transactions": "🚚",
    "Yade Transactions": "⛴️",
    "Vessel Operations": "🛳️", 
    "FSO-Operations": "⚓",
    "Reports": "📄",
    "Settings": "⚙️",
    "View Transactions": "🗂️",
    "OTR": "📊",
    "Recycle Bin": "♻️",
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
    pages = ["Home", "My Tasks"]

    # ---- Management pages (admins only) ----
    if user and PermissionManager.can_access_management_pages(user):
        pages += [
            "Manage Locations",
            "Manage Users",
            "Audit Log",
            "Location Settings",
            "Asset Management",
            "Page Customization",
            "Recycle Bin",
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
        ("show_tank_transactions",   ("View Transactions",   "app_pages.view_transactions")),  # unified viewer
        ("show_yade_transactions",   ("Yade Transactions",   "app_pages.yade_transactions")),
        ("show_otr",                 ("OTR",                 "app_pages.otr")),               # ← NEW
        ("show_fso_operations",      ("FSO-Operations",      "app_pages.fso_operations")),
        ("show_vessel_operations",   ("Vessel Operations",   "app_pages.vessel_operations")),
        ("show_reports",             ("Reports",             "app_pages.reports")),
    ]

    if role_ok:
        for flag, (title, mod) in ops:
            # For OTR, default to True if flag is missing so it appears now,
            # but can still be controlled later from Location Settings.
            if flag == "show_otr":
                allow = loc_flags.get(flag, True)
            else:
                allow = loc_flags.get(flag, False)

            if allow and _module_exists(mod):
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

    elif current_page == "Manage Locations":
        from app_pages.manage_locations import render_manage_locations_page
        render_manage_locations_page(active_location_id, user)

    elif current_page == "Manage Users":
        from app_pages.manage_users import render_manage_users_page
        render_manage_users_page(active_location_id, user)

    elif current_page == "Audit Log":
        from app_pages.audit_log import render_audit_log_page
        render_audit_log_page(active_location_id, user)

    elif current_page == "Location Settings":
        from app_pages.location_settings import render_location_settings_page
        render_location_settings_page(active_location_id, user)

    elif current_page == "Asset Management":
        from app_pages.asset_management import render_asset_management_page
        render_asset_management_page(active_location_id, user)

    elif current_page == "Page Customization":
        render_page_customization(user)

    elif current_page == "Tank Transactions":
        from app_pages.tank_transactions import render_tank_transactions_page
        render_tank_transactions_page(active_location_id, user)

    elif current_page == "Tanker Transactions":
        # separate file: app_pages/tanker_transactions.py
        render_tanker_transactions_page(active_location_id, user)

    elif current_page == "Yade Transactions":
        from app_pages.yade_transactions import render_yade_transactions_page
        render_yade_transactions_page(active_location_id, user)

    elif current_page == "View Transactions":
        from app_pages.view_transactions import render_view_transactions_page
        render_view_transactions_page(active_location_id, user)

    elif current_page == "Vessel Operations":
        render_vessel_operations_page(active_location_id, user)

    elif current_page == "FSO-Operations":
        from app_pages.fso_operations import render_fso_operations_page
        render_fso_operations_page(active_location_id, user)
    elif current_page == "Recycle Bin":
        from app_pages.recycle_bin_page import render_recycle_bin_page
        render_recycle_bin_page(active_location_id, user)
    elif current_page == "OTR":
        from app_pages.otr import render_otr_page
        render_otr_page(active_location_id, user)
    # (keep YADE/FSO/Reports routes commented until those pages are ready)
    # elif current_page == "FSO-Operations":
    #     from app_pages.fso_operations import render_fso_operations_page
    #     render_fso_operations_page(active_location_id, user)
    #
    # elif current_page == "Reports":
    #     from app_pages.reports import render_reports_page
    #     render_reports_page(active_location_id, user)


if __name__ == "__main__":
    main()
