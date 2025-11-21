import streamlit as st

from db import get_session
from models import Location
from dashboard_utils import DashboardMetrics
from location_manager import LocationManager

# New imports for Step 3
try:
    from location_config import get_location_page_visibility
except Exception:
    # Fallback if the helper name ever changes
    get_location_page_visibility = None

try:
    from permission_manager import PermissionManager
except Exception:
    PermissionManager = None


def _load_locations():
    """Small helper to load all active locations."""
    with get_session() as session:
        locations = LocationManager.get_all_locations(session, active_only=True)
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
    show_fso  = bool(flags.get("show_fso_operations", True))
    show_rep  = bool(flags.get("show_reports", True))

    # Small helper to format a line
    def line(enabled: bool, label: str, emoji: str) -> str:
        if enabled:
            return f"{emoji} **{label}** — ✅ Enabled"
        return f"{emoji} **{label}** — ⛔ Disabled"

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(line(show_tank, "Tank Transactions", "🛢️"))
        st.markdown(line(show_fso,  "FSO Operations", "⚓"))
    with col2:
        st.markdown(line(show_yade, "YADE Transactions", "⛴️"))
        st.markdown(line(show_rep,  "Reports", "📄"))

    # Role hint
    role = (user or {}).get("role", "")
    if not role_ok:
        st.caption(
            f"Your role **{role}** does not have access to operational pages. "
            "Even if a page is enabled for this location, it won’t appear for you."
        )
    else:
        st.caption(
            "Pages shown here are controlled by **Location Settings**. "
            "Operational pages will appear in the sidebar when created and your role allows it."
        )


def render_home_page(active_location_id, user):
    """
    Home page:
    - If locations exist: choose/lock active location and show summary.
    - If no locations: ask user to go to Manage Locations.
    - Admins (admin-operations, admin-it) can switch locations.
      Non-admins are locked to their assigned location if present.
    """
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
    is_admin = role_lc in ("admin-operations", "admin-it")

    # 2) Build label -> id mapping for the dropdown
    labels = [f"{loc.name} ({loc.code})" for loc in locations]
    id_by_label = {label: loc.id for label, loc in zip(labels, locations)}
    id_set = {loc.id for loc in locations}

    # Helper to get label by id
    def _label_for_location_id(loc_id: int) -> str:
        for loc in locations:
            if loc.id == loc_id:
                return f"{loc.name} ({loc.code})"
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
        active_location_id = locations[0].id

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
                "Please contact an administrator. For now, select from available locations."
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
        selected_label = st.selectbox(
            "Location",
            labels,
            index=labels.index(default_label),
            help="This active location will be used across all other pages.",
        )
        selected_location_id = id_by_label[selected_label]
        st.session_state["active_location_id"] = selected_location_id

    # 4) Visibility preview for this location (new section for Step 3)
    _render_location_access_overview(selected_location_id, user)

    # 5) Fetch summary metrics for this location
    with get_session() as session:
        summary = DashboardMetrics.get_location_summary(session, selected_location_id)

    st.markdown("#### Location Summary (last 7 days)")

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

    st.caption(
        "Home dashboard is now only for viewing. "
        "All creation and maintenance of Locations & Users will be done via the dedicated pages."
    )
