"""
Home Page with Configurable Dashboard
Integrates location-based dashboard with customization support
"""

import streamlit as st
from datetime import date, datetime, timedelta
from db import get_session
from models import Location
from dashboard_utils import DashboardMetrics
from location_manager import LocationManager

# Dashboard imports
try:
    from dashboard_config import DashboardConfigManager
    from dashboard_widgets import DashboardRenderer
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False

# New imports for location visibility
try:
    from location_config import get_location_page_visibility
except Exception:
    get_location_page_visibility = None

try:
    from permission_manager import PermissionManager
except Exception:
    PermissionManager = None


def _load_locations():
    """Small helper to load all active locations."""
    with get_session() as session:
        locations = LocationManager. get_all_locations(session, active_only=True)
    return locations


def _render_location_access_overview(selected_location_id: int, user: dict):
    """Show a quick preview of which operational pages are enabled for this location."""
    st.markdown("#### 📋 Location Access Overview")

    if not get_location_page_visibility:
        st.info("Location visibility settings are not available in this build.")
        return

    # Role gate (can this role access operational pages at all?)
    role_ok = True
    if PermissionManager and user:
        role_ok = PermissionManager.can_access_operational_pages(user)

    # Load location flags
    flags = {}
    try:
        with get_session() as session:
            flags = get_location_page_visibility(session, selected_location_id) or {}
    except Exception:
        flags = {}

    # Defaults if not set yet
    show_tank = bool(flags.get("show_tank_transactions", True))
    show_yade = bool(flags.get("show_yade_transactions", True))
    show_fso = bool(flags.get("show_fso_operations", True))
    show_rep = bool(flags.get("show_reports", True))

    # Small helper to format a line
    def line(enabled: bool, label: str, emoji: str) -> str:
        if enabled:
            return f"{emoji} **{label}** — ✅ Enabled"
        return f"{emoji} **{label}** — ⛔ Disabled"

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(line(show_tank, "Tank Transactions", "🛢️"))
        st.markdown(line(show_fso, "FSO Operations", "⚓"))
    with col2:
        st.markdown(line(show_yade, "YADE Transactions", "⛴️"))
        st.markdown(line(show_rep, "Reports", "📄"))

    # Role hint
    role = (user or {}). get("role", "")
    if not role_ok:
        st.caption(
            f"Your role **{role}** does not have access to operational pages. "
            "Even if a page is enabled for this location, it won't appear for you."
        )
    else:
        st.caption(
            "Pages shown here are controlled by **Location Settings**. "
            "Operational pages will appear in the sidebar when created and your role allows it."
        )


def render_admin_it_home(user: dict):
    """Render Admin-IT special home page"""
    st.markdown("""
    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 2rem; border-radius: 10px; margin-bottom: 2rem;'>
        <h1 style='color: white; margin: 0;'>🔧 System Administration</h1>
        <p style='color: rgba(255,255,255,0.9); margin: 0. 5rem 0 0 0;'>Admin-IT Dashboard</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"### Welcome, {user. get('full_name') or user.get('username')}!")
    st.caption("You have system administration access")
    
    st.markdown("---")
    st.markdown("### 🔐 Your Access")
    
    col1, col2 = st. columns(2)
    
    with col1:
        st.markdown("""
        **✅ You Can Access:**
        - 👥 Manage Users
        - 📜 Audit Log
        - 🕒 Login History
        - 💾 Backup & Recovery
        - ✅ My Tasks (Password Reset Requests)
        - 🔐 2FA Settings
        """)
    
    with col2:
        st. markdown("""
        **⛔ Restricted Access:**
        - All Operational Pages (Tank, Yade, Tanker Transactions)
        - All Reports (OTR, BCCR, Material Balance)
        - Location-specific Operations
        
        *Admin-IT is for system administration only*
        """)
    
    st.markdown("---")
    st.markdown("### 📌 Quick Links")
    
    quick_col1, quick_col2, quick_col3 = st. columns(3)
    
    with quick_col1:
        if st.button("👥 Manage Users", use_container_width=True):
            st. session_state.page = "Manage Users"
            st.rerun()
    
    with quick_col2:
        if st.button("📜 View Audit Log", use_container_width=True):
            st. session_state.page = "Audit Log"
            st.rerun()
    
    with quick_col3:
        if st. button("✅ My Tasks", use_container_width=True):
            st.session_state.page = "My Tasks"
            st.rerun()


def render_location_dashboard(selected_location_id: int, user: dict):
    """Render full operational dashboard for location"""
    
    if not DASHBOARD_AVAILABLE:
        st.error("Dashboard modules not available.  Please ensure dashboard_config.py and dashboard_widgets.py are installed.")
        return
    
    # Get location details
    with get_session() as s:
        loc = LocationManager.get_location_by_id(s, selected_location_id)
        if not loc:
            st.error("❌ Location not found.")
            return
        
        loc_name = getattr(loc, "name", "Location")
        loc_code = getattr(loc, "code", "")
    
    # Load dashboard config for header settings
    from dashboard_config import DashboardConfigManager
    config = DashboardConfigManager.load_config(selected_location_id)
    header_cfg = config.get("page_header", {
        "title": "{location_name} Dashboard",
        "subtitle": "Management Information System",
        "show_welcome": True,
        "show_datetime": True,
        "background_gradient_start": "#667eea",
        "background_gradient_end": "#764ba2"
    })
    
    # Replace {location_name} placeholder
    page_title = header_cfg.get("title", "{location_name} Dashboard").replace("{location_name}", loc_name)
    page_subtitle = header_cfg.get("subtitle", "Management Information System")
    
    # Build welcome and datetime sections
    additional_info = []
    if header_cfg.get("show_welcome", True):
        additional_info.append(f"Welcome back, <strong>{user['username']}</strong>")
    if header_cfg.get("show_datetime", True):
        additional_info.append(datetime.now().strftime('%A, %B %d, %Y - %I:%M %p'))
    
    info_text = " | ".join(additional_info) if additional_info else ""
    
    # Dashboard header - full width
    gradient_start = header_cfg.get("background_gradient_start", "#667eea")
    gradient_end = header_cfg.get("background_gradient_end", "#764ba2")
    
    st.markdown(
        f"""
        <div style='background: linear-gradient(135deg, {gradient_start} 0%, {gradient_end} 100%); 
                    padding: 2.5rem; border-radius: 10px; margin-bottom: 1rem; color: white;'>
            <h1 style='margin: 0; font-size: 2.5rem;'>{page_title}</h1>
            <p style='margin: 0.5rem 0 0 0; opacity: 0.9; font-size: 1.1rem;'>{page_subtitle}</p>
            {f"<p style='margin: 0.5rem 0 0 0; font-size: 0.95rem;'>{info_text}</p>" if info_text else ""}
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Load dashboard configuration
    try:
        config = DashboardConfigManager.load_config(selected_location_id)
        
        # Render dashboard with section-based filters
        DashboardRenderer.render_dashboard_with_sections(config, selected_location_id, user)
    except Exception as e:
        st.error(f"Error rendering dashboard: {e}")
        import traceback
        st.code(traceback.format_exc())
        st.info("Falling back to basic summary view...")
        render_basic_summary(selected_location_id)
    
    st.markdown("---")
    
    # Quick Actions
    st.markdown("### ⚡ Quick Actions")
    
    action_cols = st.columns(4)
    
    with action_cols[0]:
        if st.button("➕ New Tank Transaction", use_container_width=True, type="primary"):
            st. session_state.page = "Tank Transactions"
            st.rerun()
    
    with action_cols[1]:
        if st.button("➕ New YADE Voyage", use_container_width=True, type="primary"):
            st.session_state.page = "Yade Transactions"
            st.rerun()
    
    with action_cols[2]:
        if st. button("➕ New Tanker Dispatch", use_container_width=True, type="primary"):
            st.session_state. page = "Tanker Transactions"
            st.rerun()
    
    with action_cols[3]:
        if st. button("👁️ View Transactions", use_container_width=True, type="primary"):
            st.session_state.page = "View Transactions"
            st.rerun()


def render_basic_summary(selected_location_id: int):
    """Fallback basic summary if dashboard fails"""
    with get_session() as session:
        summary = DashboardMetrics.get_location_summary(session, selected_location_id)
    
    st.markdown("### 📊 Location Summary (last 7 days)")
    
    # Row 1 – tank counts
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Tanks", summary.get("total_tanks", 0))
    c2.metric("Active Tanks", summary.get("active_tanks", 0))
    c3.metric("Inactive Tanks", summary.get("inactive_tanks", 0))
    
    # Row 2 – activity
    c4, c5, c6 = st.columns(3)
    c4.metric("Tank Transactions", summary.get("recent_transactions", 0))
    c5.metric("YADE Voyages", summary.get("recent_voyages", 0))
    c6.metric("Tanker Dispatches", summary.get("recent_tanker_dispatches", 0))
    
    # Row 3 – stock
    c7, c8 = st.columns(2)
    c7.metric("Current Stock (bbl)", f"{summary.get('current_stock_bbl', 0):,}")
    c8.metric("Tanks with Stock", summary.get("tanks_with_stock", 0))


def render_home_page(active_location_id, user):
    """
    Main home page entry point:
    - Admin-IT gets special homepage
    - Other users get location selector and operational dashboard
    - If no locations exist, prompt to create one
    """
    
    # Special handling for Admin-IT
    if user and user.get("role") == "admin-it":
        render_admin_it_home(user)
        return
    
    st.markdown("### 🏠 Home")
    
    # 1) Load existing locations
    locations = _load_locations()
    
    if not locations:
        st.warning(
            "No locations found in the database. "
            "Please go to **Manage Locations** (left sidebar) to create your first location."
        )
        return
    
    # ===== Role / assignment logic =====
    role = (user or {}).get("role", "")
    role_lc = (role or "").lower()
    user_loc_id = (user or {}).get("location_id")
    is_admin = role_lc in ("admin-operations", "admin-it", "admin", "super-admin")
    
    # 2) Build label -> id mapping for the dropdown
    labels = [f"{loc.name} ({loc.code})" for loc in locations]
    id_by_label = {label: loc.id for label, loc in zip(labels, locations)}
    id_set = {loc.id for loc in locations}
    
    # Helper to get label by id
    def _label_for_location_id(loc_id: int) -> str:
        for loc in locations:
            if loc. id == loc_id:
                return f"{loc.name} ({loc. code})"
        return labels[0]  # fallback
    
    # Decide default selection
    if active_location_id and active_location_id in id_set:
        default_label = _label_for_location_id(active_location_id)
    elif user_loc_id and user_loc_id in id_set:
        # If user has assigned location and it's active, prefer that
        default_label = _label_for_location_id(user_loc_id)
        st.session_state["active_location_id"] = user_loc_id
        active_location_id = user_loc_id
    else:
        default_label = labels[0]
        st.session_state["active_location_id"] = locations[0].id
        active_location_id = locations[0]. id
    
    # 3) Render location selector (locked for non-admins with assignment)
    st.markdown("#### Select Active Location")
    
    if not is_admin and user_loc_id:
        # Non-admin tied to a location: lock the selector to their assigned location
        if user_loc_id in id_set:
            locked_label = _label_for_location_id(user_loc_id)
            st.info("You are assigned to a specific location by your administrator.")
            st.selectbox("Location", labels, index=labels.index(locked_label), disabled=True)
            selected_location_id = user_loc_id
            st.session_state["active_location_id"] = user_loc_id
        else:
            # Assigned location not active/visible → allow choosing, but inform
            st.warning(
                "Your assigned location is not currently active. "
                "Please contact an administrator.  For now, select from available locations."
            )
            selected_label = st.selectbox(
                "Location",
                labels,
                index=labels.index(default_label),
                help="This active location will be used across all other pages.",
            )
            selected_location_id = id_by_label[selected_label]
            st.session_state["active_location_id"] = selected_location_id
    else:
        # Admins (or users without an assigned location): free selection
        selected_label = st. selectbox(
            "Location",
            labels,
            index=labels.index(default_label),
            help="This active location will be used across all other pages.",
        )
        selected_location_id = id_by_label[selected_label]
        st. session_state["active_location_id"] = selected_location_id
    
    st.markdown("---")
    
    # 4) Visibility preview for this location
    _render_location_access_overview(selected_location_id, user)
    
    st.markdown("---")
    
    # 5) Render the full operational dashboard
    if DASHBOARD_AVAILABLE:
        render_location_dashboard(selected_location_id, user)
    else:
        # Fallback to basic summary
        st.info("Full dashboard not available. Showing basic summary.")
        render_basic_summary(selected_location_id)
    
    # Footer note
    st.markdown("---")
    st.caption(
        "💡 **Tip:** Use 'Dashboard Customization' (admin only) to configure widgets, "
        "charts, and data mappings for this location."
    )


# Main entry point (if this file is run directly for testing)
if __name__ == "__main__":
    # For testing purposes
    render_home_page(
        active_location_id=st.session_state.get("active_location_id"),
        user=st.session_state.get("auth_user")
    )