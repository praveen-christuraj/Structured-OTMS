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

    # Single structured table with action buttons
    hdr = st.columns([0.32, 0.18, 0.35, 0.15])
    hdr[0].markdown("**Name (Code)**")
    hdr[1].markdown("**Status**")
    hdr[2].markdown("**Address**")
    hdr[3].markdown("**Actions**")

    for loc in locations:
        row_id = f"ml_loc_{loc.id}"
        cols = st.columns([0.32, 0.18, 0.35, 0.15])
        with cols[0]:
            st.write(f"{loc.name} ({loc.code})")
        with cols[1]:
            st.write("Active" if loc.is_active else "Inactive")
        with cols[2]:
            st.write((loc.address or "")[:80])
        st.session_state.setdefault(f"{row_id}_edit_flag", False)
        st.session_state.setdefault(f"{row_id}_del_flag", False)
        with cols[3]:
            e1, e2 = st.columns(2)
            if e1.button("✏️", key=f"{row_id}_edit_btn", help="Edit"):
                st.session_state[f"{row_id}_edit_flag"] = True
            if not st.session_state[f"{row_id}_del_flag"]:
                if e2.button("🗑️", key=f"{row_id}_del_btn", help="Delete"):
                    st.session_state[f"{row_id}_del_flag"] = True
            else:
                c_yes, c_no = st.columns(2)
                with c_yes:
                    if st.button("✅", key=f"{row_id}_del_yes", help="Confirm delete"):
                        try:
                            with get_session() as session:
                                LocationManager.delete_location(session, int(loc.id))
                            u = st.session_state.get("auth_user", {})
                            SecurityManager.log_audit(
                                None,
                                u.get("username", "system"),
                                "DELETE",
                                resource_type="Location",
                                resource_id=str(loc.id),
                                details=f"Soft-deleted location {loc.name} ({loc.code})",
                                user_id=u.get("id"),
                                location_id=loc.id,
                            )
                            st.success("Location deleted (soft).")
                            st.session_state[f"{row_id}_del_flag"] = False
                            st.rerun()
                        except Exception as ex:
                            st.error(str(ex))
                with c_no:
                    if st.button("❌", key=f"{row_id}_del_no", help="Cancel"):
                        st.session_state[f"{row_id}_del_flag"] = False

        if st.session_state[f"{row_id}_edit_flag"]:
            with st.expander(f"Edit {loc.name} ({loc.code})", expanded=True):
                e_cols = st.columns([0.30, 0.20, 0.30, 0.20])
                with e_cols[0]:
                    new_name = st.text_input("Name", value=loc.name, key=f"{row_id}_edit_name")
                with e_cols[1]:
                    new_code = st.text_input("Code", value=loc.code, key=f"{row_id}_edit_code")
                with e_cols[2]:
                    new_addr = st.text_input("Address", value=(loc.address or ""), key=f"{row_id}_edit_addr")
                with e_cols[3]:
                    new_active = st.checkbox("Active", value=bool(loc.is_active), key=f"{row_id}_edit_active")
                a1, a2 = st.columns(2)
                if a1.button("💾 Save", key=f"{row_id}_edit_save"):
                    try:
                        with get_session() as session:
                            LocationManager.update_location(
                                session,
                                location_id=int(loc.id),
                                name=new_name.strip(),
                                code=new_code.strip(),
                                address=new_addr.strip(),
                                is_active=bool(new_active),
                            )
                        u = st.session_state.get("auth_user", {})
                        SecurityManager.log_audit(
                            None,
                            u.get("username", "system"),
                            "UPDATE",
                            resource_type="Location",
                            resource_id=str(loc.id),
                            details=f"Updated location to {new_name} ({new_code})",
                            user_id=u.get("id"),
                            location_id=loc.id,
                        )
                        st.success("Location updated.")
                        st.session_state[f"{row_id}_edit_flag"] = False
                        st.rerun()
                    except Exception as ex:
                        st.error(str(ex))
                if a2.button("Cancel", key=f"{row_id}_edit_cancel"):
                    st.session_state[f"{row_id}_edit_flag"] = False

def render_manage_locations_page(active_location_id, user):
    st.markdown("### 🗺️ Manage Locations")

    if user:
        st.caption(f"Current user: **{user['username']}** ({user['role']})")

    _create_location_form(user)

    st.markdown("---")

    _locations_table()

