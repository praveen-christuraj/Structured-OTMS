import streamlit as st
from security import SecurityManager
from db import get_session
from models import User, Location
from auth import AuthManager
from location_manager import LocationManager
from twofa import TwoFactorAuth

# Fixed role list
ROLES = [
    "operator",
    "supervisor",
    "manager",
    "admin-it",
    "admin-operations",
]

ROLE_ICONS = {
    "operator": "👷",
    "supervisor": "👤",
    "manager": "👔",
    "admin-it": "💻",
    "admin-operations": "🏢",
}


def role_with_icon(role: str) -> str:
    """Return role label with emoji icon."""
    return f"{ROLE_ICONS.get(role, '👤')} {role}"


def _load_locations():
    with get_session() as session:
        return LocationManager.get_all_locations(session, active_only=True)


# -------------------------------------------------------------------------
# CREATE USER
# -------------------------------------------------------------------------
def _create_user_form():
    st.markdown("#### ➕ Create New User")

    locations = _load_locations()

    with st.form("create_user_form"):
        username = st.text_input("Username *")
        full_name = st.text_input("Full Name *")
        password = st.text_input("Password *", type="password")
        confirm_password = st.text_input("Confirm Password *", type="password")

        role = st.selectbox(
            "Role *",
            [role_with_icon(r) for r in ROLES],
        )
        # Extract raw role from label
        raw_role = role.split(" ", 1)[1] if " " in role else role

        # Location selection (optional in UI, backend rules will enforce)
        location_options = ["— No specific location —"]
        loc_id_by_label = {}
        for loc in locations:
            label = f"{loc.name} ({loc.code})"
            location_options.append(label)
            loc_id_by_label[label] = loc.id

        selected_loc_label = st.selectbox("Assigned Location", location_options)
        location_id = loc_id_by_label.get(selected_loc_label)

        supervisor_code = st.text_input(
            "Supervisor Code (only if role = supervisor)",
            type="password",
            help="Supervisor code is required for supervisor accounts.",
        )
        
        st.markdown("---")
        st.markdown("**Password & 2FA Policy**")
        
        col1, col2 = st.columns(2)
        with col1:
            force_password_change = st.checkbox(
                "🔐 Mandatory Password Change on First Login",
                value=True,
                help="If enabled, user must change the default password on first login"
            )
        
        with col2:
            force_2fa = st.checkbox(
                "🔒 Mandatory 2FA",
                value=True,
                help="If enabled, user must setup 2FA on first login"
            )
        
        # Password expiry settings
        is_admin = raw_role in ["admin-it", "admin-operations"]
        if is_admin:
            password_never_expires = st.checkbox(
                "⏳ Password Never Expires (Admin Privilege)",
                value=True,
                help="Admins can be exempt from 30-day password expiry"
            )
        else:
            password_never_expires = False
            st.info("ℹ️ Non-admin users must change password every 30 days")

        submitted = st.form_submit_button("Create User")

    if submitted:
        if not username.strip() or not full_name.strip():
            st.error("Username and Full Name are required.")
            return

        if not password:
            st.error("Password is required.")
            return

        if password != confirm_password:
            st.error("Passwords do not match.")
            return

        try:
            with get_session() as session:
                user_dict = AuthManager.create_user(
                    session=session,
                    username=username.strip(),
                    password=password,
                    full_name=full_name.strip(),
                    role=raw_role,
                    location_id=location_id,
                    supervisor_code=supervisor_code or None,
                    force_password_change=force_password_change,
                    force_2fa=force_2fa,
                    password_never_expires=password_never_expires,
                )

            st.success(
                f"User '{user_dict['username']}' created successfully "
                f"with role '{role_with_icon(user_dict['role'])}'."
            )
            # Audit log – user created
            current_username = (st.session_state.get("auth_user") or {}).get("username", "system")
            current_user_id = (st.session_state.get("auth_user") or {}).get("id")

            SecurityManager.log_audit(
                None,
                current_username,
                "CREATE",
                resource_type="User",
                resource_id=str(user_dict["id"]),
                details=f"Created user {user_dict['username']} with role {user_dict['role']}.",
                user_id=current_user_id,
                location_id=user_dict.get("location_id"),
            )

        except ValueError as ex:
            st.error(str(ex))


# -------------------------------------------------------------------------
# USER MAINTENANCE
# -------------------------------------------------------------------------
def _user_maintenance_section():
    st.markdown("#### 🛠️ User Maintenance")

    with get_session() as session:
        users = session.query(User).order_by(User.username).all()
        locations = session.query(Location).order_by(Location.name).all()
        loc_by_id = {loc.id: loc for loc in locations}

    if not users:
        st.info("No users found yet.")
        return

    user_labels = [
        f"{u.username} ({role_with_icon(u.role)})" for u in users
    ]
    user_by_label = {label: u for label, u in zip(user_labels, users)}

    selected_label = st.selectbox(
        "Select User",
        user_labels,
        key="selected_user_for_edit",
    )
    selected_user = user_by_label[selected_label]

    current_loc = loc_by_id.get(selected_user.location_id)
    if current_loc:
        st.markdown(
            f"**Current:** `{selected_user.username}` · "
            f"Role: **{role_with_icon(selected_user.role)}** · "
            f"Location: **{current_loc.name} ({current_loc.code})**"
        )
    else:
        st.markdown(
            f"**Current:** `{selected_user.username}` · "
            f"Role: **{role_with_icon(selected_user.role)}** · "
            f"Location: **—**"
        )

    st.markdown(
        f"Status: {'✅ Active' if selected_user.is_active else '⛔ Inactive'}"
    )

    st.markdown("---")

    # --- 1) Update details (full name, role, location) ---
    st.markdown("##### ✏️ Update Role / Location / Name")

    with st.form("update_user_details_form", clear_on_submit=False):
        new_full_name = st.text_input(
            "Full Name",
            value=selected_user.full_name or "",
        )

        role_labels = [role_with_icon(r) for r in ROLES]
        current_role_label = role_with_icon(selected_user.role) if selected_user.role in ROLES else role_labels[0]

        new_role_label = st.selectbox(
            "Role",
            role_labels,
            index=role_labels.index(current_role_label),
        )
        new_role = new_role_label.split(" ", 1)[1]

        # location options
        locations = _load_locations()
        loc_labels = ["— No specific location —"]
        loc_id_by_label2 = {}
        for loc in locations:
            label = f"{loc.name} ({loc.code})"
            loc_labels.append(label)
            loc_id_by_label2[label] = loc.id

        if selected_user.location_id:
            current_label = next(
                (f"{loc.name} ({loc.code})" for loc in locations if loc.id == selected_user.location_id),
                "— No specific location —",
            )
        else:
            current_label = "— No specific location —"

        new_loc_label = st.selectbox(
            "Assigned Location",
            loc_labels,
            index=loc_labels.index(current_label),
        )
        new_location_id = loc_id_by_label2.get(new_loc_label)

        submitted_update = st.form_submit_button("Update User Details")

    if submitted_update:
        try:
            with get_session() as session:
                AuthManager.update_user_details(
                    session=session,
                    user_id=selected_user.id,
                    full_name=new_full_name.strip() or None,
                    role=new_role,
                    location_id=new_location_id,
                )
            st.success("User details updated successfully.")
            actor = (st.session_state.get("auth_user") or {}).get("username", "system")
            actor_id = (st.session_state.get("auth_user") or {}).get("id")

            SecurityManager.log_audit(
                None,
                actor,
                "UPDATE",
                resource_type="User",
                resource_id=str(selected_user.id),
                details=f"Updated user details (role={new_role}, location_id={new_location_id}).",
                user_id=actor_id,
                location_id=new_location_id,
            )

        except ValueError as ex:
            st.error(str(ex))

    st.markdown("---")

    # --- 2) Password reset ---
    st.markdown("##### 🔐 Reset Password")

    with st.form("reset_password_form"):
        new_pwd = st.text_input("New Password *", type="password")
        new_pwd_confirm = st.text_input("Confirm New Password *", type="password")
        submit_pwd = st.form_submit_button("Reset Password")

    if submit_pwd:
        if not new_pwd:
            st.error("New password cannot be empty.")
        elif new_pwd != new_pwd_confirm:
            st.error("Passwords do not match.")
        else:
            try:
                with get_session() as session:
                    AuthManager.update_password(session, selected_user.id, new_pwd)
                st.success("Password reset successfully.")
                actor = (st.session_state.get("auth_user") or {}).get("username", "system")
                actor_id = (st.session_state.get("auth_user") or {}).get("id")
                SecurityManager.log_audit(
                    None,
                    actor,
                    "PASSWORD_RESET",
                    resource_type="User",
                    resource_id=str(selected_user.id),
                    details="Password reset from Manage Users page.",
                    user_id=actor_id,
                    location_id=selected_user.location_id,
                )

            except ValueError as ex:
                st.error(str(ex))

    st.markdown("---")

    # --- 3) Activation / Deactivation toggle ---
    st.markdown("##### ✅ / ⛔ Activate or Deactivate User")

    col_a1, col_a2 = st.columns(2)
    with col_a1:
        if selected_user.is_active:
            deactivate_clicked = st.button("⛔ Deactivate User")
            if deactivate_clicked:
                with get_session() as session:
                    u = session.query(User).get(selected_user.id)
                    if u:
                        u.is_active = False
                        session.commit()
                st.success("User deactivated.")
                actor = (st.session_state.get("auth_user") or {}).get("username", "system")
                actor_id = (st.session_state.get("auth_user") or {}).get("id")
                SecurityManager.log_audit(
                    None,
                    actor,
                    "DEACTIVATE",
                    resource_type="User",
                    resource_id=str(selected_user.id),
                    details="User deactivated",
                    user_id=actor_id,
                    location_id=selected_user.location_id,
                )
        else:
            activate_clicked = st.button("✅ Activate User")
            if activate_clicked:
                with get_session() as session:
                    u = session.query(User).get(selected_user.id)
                    if u:
                        u.is_active = True
                        session.commit()
                st.success("User activated.")
                actor = (st.session_state.get("auth_user") or {}).get("username", "system")
                actor_id = (st.session_state.get("auth_user") or {}).get("id")
                SecurityManager.log_audit(
                    None,
                    actor,
                    "ACTIVATE",
                    resource_type="User",
                    resource_id=str(selected_user.id),
                    details="User activated",
                    user_id=actor_id,
                    location_id=selected_user.location_id,
                )

    # --- 4) 2FA reset (disable 2FA) ---
    with col_a2:
        reset_2fa_clicked = st.button("🔁 Reset 2FA (Disable)")
        if reset_2fa_clicked:
            try:
                with get_session() as session:
                    TwoFactorAuth.disable_2fa(session, selected_user.id)
                st.success("2FA disabled for this user. They can re-enroll from login next time.")
                actor = (st.session_state.get("auth_user") or {}).get("username", "system")
                actor_id = (st.session_state.get("auth_user") or {}).get("id")
                SecurityManager.log_audit(
                    None,
                    actor,
                    "2FA_RESET",
                    resource_type="User",
                    resource_id=str(selected_user.id),
                    details="2FA disabled for this user.",
                    user_id=actor_id,
                    location_id=selected_user.location_id,
                )
            except ValueError as ex:
                st.error(str(ex))

    st.markdown("---")

    # --- 5) Delete user (moves to Deleted Records; purge from Deleted Records only) ---
    st.markdown("##### 🗑️ Delete User (Moves to Deleted Records)")

    col_d1, col_d2 = st.columns([2, 1])
    with col_d1:
        confirm_text = st.text_input(
            "Type the username to confirm deletion",
            help="To prevent mistakes, type the exact username here.",
        )
    with col_d2:
        delete_clicked = st.button("Delete User")

    if delete_clicked:
        if confirm_text.strip() != selected_user.username:
            st.error("Confirmation text does not match the username.")
        else:
            try:
                with get_session() as session:
                    u = session.query(User).get(selected_user.id)
                    if u:
                        try:
                            from recycle_bin import RecycleBinManager
                            RecycleBinManager.archive_record(
                                session,
                                u,
                                "User",
                                username=(st.session_state.get("auth_user") or {}).get("username", "system"),
                                user_id=(st.session_state.get("auth_user") or {}).get("id"),
                                location_id=u.location_id,
                                reason="Deleted from Manage Users page",
                                label=str(u.id),
                            )
                            session.commit()
                            st.success(
                                f"User '{u.username}' ({role_with_icon(u.role)}) moved to Deleted Records."
                            )
                            SecurityManager.log_audit(
                                None,
                                (st.session_state.get("auth_user") or {}).get("username", "system"),
                                "DELETE",
                                resource_type="User",
                                resource_id=str(u.id),
                                details=f"Moved user {u.username} to deleted records.",
                                user_id=(st.session_state.get("auth_user") or {}).get("id"),
                                location_id=u.location_id,
                            )
                        except Exception as ex:
                            st.error(str(ex))
            except ValueError as ex:
                st.error(str(ex))


# -------------------------------------------------------------------------
# LIST ALL USERS (read-only table)
# -------------------------------------------------------------------------
def _users_table():
    st.markdown("#### 👥 Users Overview")

    with get_session() as session:
        users = session.query(User).order_by(User.username).all()
        locations = session.query(Location).all()
        loc_by_id = {loc.id: loc for loc in locations}

    if not users:
        st.info("No users found yet.")
        return

    rows = []
    for u in users:
        loc = loc_by_id.get(u.location_id)
        rows.append(
            {
                "ID": u.id,
                "Username": u.username,
                "Full Name": u.full_name,
                "Role": role_with_icon(u.role),
                "Location": f"{loc.name} ({loc.code})" if loc else "—",
                "Active": "✅" if u.is_active else "⛔",
            }
        )

    st.dataframe(rows, use_container_width=True)


# -------------------------------------------------------------------------
# PAGE ENTRY
# -------------------------------------------------------------------------
def render_manage_users_page(active_location_id, user):
    """
    Manage Users page.
    - Create users
    - Edit role/location
    - Reset password
    - Activate / Deactivate
    - Reset 2FA
    - Delete user
    """
    st.markdown("### 👤 Manage Users")

    if user:
        st.caption(
            f"Current user: **{user['username']}** ({role_with_icon(user['role'])})"
        )

    _create_user_form()

    st.markdown("---")

    _user_maintenance_section()

    st.markdown("---")

    _users_table()
