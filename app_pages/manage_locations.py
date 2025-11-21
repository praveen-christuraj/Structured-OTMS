import streamlit as st
from security import SecurityManager
from db import get_session
from models import Location
from location_manager import LocationManager

def _create_location_form(user):
    """Form for creating a new location."""
    st.markdown("#### ➕ Create New Location")

    with st.form("create_location_form"):
        name = st.text_input("Location Name *", placeholder="e.g. Asemoku Jetty")
        code = st.text_input("Short Code *", placeholder="e.g. ASJ")
        address = st.text_area("Address (optional)")

        submitted = st.form_submit_button("Create Location")

    if submitted:
        if not name.strip() or not code.strip():
            st.error("Location Name and Short Code are required.")
            return

        try:
            from db import get_session

            with get_session() as session:
                loc_dict = LocationManager.create_location(
                    session=session,
                    name=name.strip(),
                    code=code.strip(),
                    address=address.strip() or None,
                )

            st.success(
                f"Location '{loc_dict['name']}' ({loc_dict['code']}) created successfully."
            )
            st.session_state["active_location_id"] = loc_dict["id"]

            # Audit log
            username = (user or {}).get("username", "system")
            user_id = (user or {}).get("id")
            SecurityManager.log_audit(
                None,
                username,
                "CREATE",
                resource_type="Location",
                resource_id=str(loc_dict["id"]),
                details=f"Created location {loc_dict['name']} ({loc_dict['code']}) via UI",
                user_id=user_id,
                location_id=loc_dict["id"],
            )

        except ValueError as ex:
            st.error(str(ex))

def _locations_table():
    """Show a simple table of all locations."""
    st.markdown("#### 📍 Existing Locations")

    with get_session() as session:
        locations = session.query(Location).order_by(Location.name).all()

    if not locations:
        st.info("No locations found yet.")
        return

    # Build a simple table
    data = []
    for loc in locations:
        data.append(
            {
                "ID": loc.id,
                "Name": loc.name,
                "Code": loc.code,
                "Address": (loc.address or "")[:80],
                "Active": "✅ Yes" if loc.is_active else "⛔ No",
            }
        )

    st.dataframe(data, use_container_width=True)

def render_manage_locations_page(active_location_id, user):
    st.markdown("### 🗺️ Manage Locations")

    if user:
        st.caption(f"Current user: **{user['username']}** ({user['role']})")

    _create_location_form(user)

    st.markdown("---")

    _locations_table()

