import streamlit as st

from db import get_session
from models import Location
from security import SecurityManager

# Import visibility reader + the class that can save config
from location_config import (
    get_location_page_visibility,
    LocationConfig,
    get_tank_transactions_tab_visibility,
    save_tank_transactions_tab_visibility,
)

# Default flags used if a location has no config yet
DEFAULT_FLAGS = {
    "show_tank_transactions": True,
    "show_yade_transactions": True,
    "show_fso_operations": True,
    "show_reports": True,
}

def _is_admin(user) -> bool:
    role = (user or {}).get("role", "").lower()
    return role in ("admin-operations", "admin-it")

def _load_locations():
    with get_session() as session:
        return session.query(Location).order_by(Location.name).all()

def render_location_settings_page(active_location_id, user):
    st.markdown("### 🧭 Location Settings")

    # ---- Guard rail: only admins can access ----
    if not _is_admin(user):
        st.warning("You don’t have permission to view this page.")
        return

    # ---- Choose location to configure ----
    locations = _load_locations()
    if not locations:
        st.info("No locations found. Create one in **Manage Locations** first.")
        return

    labels = [f"{loc.name} ({loc.code})" for loc in locations]
    id_by_label = {label: loc.id for label, loc in zip(labels, locations)}

    # Default to active_location_id if present
    if active_location_id and any(loc.id == active_location_id for loc in locations):
        default_label = next(l for l, loc in zip(labels, locations) if loc.id == active_location_id)
    else:
        default_label = labels[0]

    st.markdown("#### Select Location to Configure")
    sel_label = st.selectbox("Location", labels, index=labels.index(default_label))
    sel_location_id = id_by_label[sel_label]

    # ---- Load current flags ----
    with get_session() as session:
        flags = get_location_page_visibility(session, sel_location_id) or {}
    # merge defaults
    cfg = {**DEFAULT_FLAGS, **flags}

    st.markdown("#### Page Access Toggles")

    col1, col2 = st.columns(2)
    with col1:
        show_tank = st.toggle("🛢️ Tank Transactions", value=cfg.get("show_tank_transactions", True))
        show_fso  = st.toggle("⚓ FSO Operations", value=cfg.get("show_fso_operations", True))
    with col2:
        show_yade = st.toggle("⛴️ YADE Transactions", value=cfg.get("show_yade_transactions", True))
        show_rpts = st.toggle("📄 Reports", value=cfg.get("show_reports", True))

    st.caption("These switches control which operational pages this location can access.")

    # ---- Save button (page access) ----
    if st.button("💾 Save Settings", type="primary"):
        new_flags = {
            "show_tank_transactions": bool(show_tank),
            "show_yade_transactions": bool(show_yade),
            "show_fso_operations": bool(show_fso),
            "show_reports": bool(show_rpts),
        }
        try:
            with get_session() as session:
                # Load full config, update just the page_visibility, and save
                full_cfg = LocationConfig.get_config(session, sel_location_id)
                pv = full_cfg.get("page_visibility", {}).copy()
                pv.update(new_flags)
                full_cfg["page_visibility"] = pv
                LocationConfig.save_config(session, sel_location_id, full_cfg)

            # Audit log
            SecurityManager.log_audit(
                None,
                (user or {}).get("username", "system"),
                "UPDATE",
                resource_type="LocationSettings",
                resource_id=str(sel_location_id),
                details=f"Updated page visibility: {new_flags}",
                user_id=(user or {}).get("id"),
                location_id=sel_location_id,
            )

            st.success("Settings saved.")
        except Exception as ex:
            st.error(f"Failed to save settings: {ex}")

    st.markdown("---")

    # ===================== Tank Transactions (Tabs) =====================
    st.markdown("### 🛢️ Tank Transactions (Tabs)")
    st.caption("Control which Tank Transactions sections are visible for this location.")

    # Is page enabled? If not, disable the tab toggles
    page_enabled = bool(show_tank)

    # Load existing per-tab flags
    with get_session() as session:
        tab_flags = get_tank_transactions_tab_visibility(session, sel_location_id)

    d = st.columns(5)
    with d[0]:
        f_entry = st.toggle("📝 Tank Entry", value=tab_flags["Tank Entry"], disabled=not page_enabled)
    with d[1]:
        f_meter = st.toggle("🧮 Meter Records", value=tab_flags["Meter Records"], disabled=not page_enabled)
    with d[2]:
        f_cond  = st.toggle("🧪 Condensate Records", value=tab_flags["Condensate Records"], disabled=not page_enabled)
    with d[3]:
        f_pwater = st.toggle("💧 Produced Water Records", value=tab_flags["Produced Water Records"], disabled=not page_enabled)
    with d[4]:
        f_prod = st.toggle("🏭 Production", value=tab_flags["Production"], disabled=not page_enabled)

    if not page_enabled:
        st.info("Tank Transactions page access is OFF for this location, so these tabs are disabled. Turn on page access above to enable tab control.")

    if st.button("💾 Save Tank Transactions Tabs", use_container_width=True, disabled=not page_enabled):
        try:
            with get_session() as session:
                save_tank_transactions_tab_visibility(session, sel_location_id, {
                    "Tank Entry": bool(f_entry),
                    "Meter Records": bool(f_meter),
                    "Condensate Records": bool(f_cond),
                    "Produced Water Records": bool(f_pwater),
                    "Production": bool(f_prod),
                })
            # Audit
            SecurityManager.log_audit(
                None,
                (user or {}).get("username", "system"),
                "UPDATE",
                resource_type="LocationSettings.Tabs",
                resource_id=str(sel_location_id),
                details="Updated Tank Transactions tab visibility",
                user_id=(user or {}).get("id"),
                location_id=sel_location_id,
            )
            st.success("Tank Transactions tab visibility saved for this location.")
        except Exception as ex:
            st.error(f"Failed to save tab visibility: {ex}")

# --- Operations Configuration (per location / asset / category) ---
def _render_operations_config(active_location_id, user):
    import streamlit as st
    from db import get_session
    from location_config import (
        OP_ASSETS, OP_CATEGORIES,
        list_operations, add_operation,
        set_operation_active, delete_operation,
    )
    from security import SecurityManager

    st.markdown("### 🧩 Operations (per Location / Asset / Category)")

    if not active_location_id:
        st.info("Select a location on **Home** to configure operations.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        asset = st.selectbox("Asset", OP_ASSETS, format_func=lambda x: x.title())
    with col2:
        category = st.selectbox("Category", OP_CATEGORIES)
    with col3:
        st.write("")  # spacer

    op_name = st.text_input("Operation name (e.g., 'Receipt from Agu')", key="op_name_input")

    c1, c2 = st.columns([0.25, 0.75])
    with c1:
        if st.button("➕ Add Operation", type="primary"):
            try:
                with get_session() as s:
                    item = add_operation(s, active_location_id, asset=asset, category=category, name=op_name, active=True)
                    # audit
                    try:
                        SecurityManager.log_audit(
                            s,
                            (user or {}).get("username", "system"),
                            "CREATE",
                            resource_type="LocationOperation",
                            resource_id=item["id"],
                            details=f"Add op '{item['name']}' under {asset}/{category}",
                            user_id=(user or {}).get("id"),
                            location_id=active_location_id,
                            ip_address=st.session_state.get("client_ip"),
                            success=True,
                        )
                    except Exception:
                        pass
                st.success("Operation added.")
                st.rerun()
            except Exception as ex:
                st.error(f"Failed: {ex}")

    st.markdown("---")
    st.markdown("#### Existing Operations")

    with get_session() as s:
        ops = list_operations(s, active_location_id)

    if not ops:
        st.info("No operations configured yet.")
        return

    # Filter by current selection (optional UX)
    show_filtered = st.checkbox("Show only selected Asset/Category", value=True)
    if show_filtered:
        ops = [o for o in ops if o["asset"] == asset and o["category"] == category]

    for o in ops:
        colA, colB, colC, colD = st.columns([0.38, 0.22, 0.18, 0.22])
        with colA:
            st.write(f"**{o['name']}**")
            st.caption(f"{o['asset'].title()} · {o['category']}")
        with colB:
            on = st.toggle("Active", value=o.get("active", True), key=f"op_active_{o['id']}")
        with colC:
            if st.button("💾 Save", key=f"op_save_{o['id']}"):
                with get_session() as s:
                    set_operation_active(s, active_location_id, op_id=o["id"], active=on)
                    # audit
                    try:
                        SecurityManager.log_audit(
                            s, (user or {}).get("username", "system"),
                            "UPDATE",
                            resource_type="LocationOperation",
                            resource_id=o["id"],
                            details=f"Set active={on} for '{o['name']}'",
                            user_id=(user or {}).get("id"),
                            location_id=active_location_id,
                            ip_address=st.session_state.get("client_ip"),
                            success=True,
                        )
                    except Exception:
                        pass
                st.success("Saved")
        with colD:
            if st.button("🗑️ Delete", key=f"op_del_{o['id']}"):
                if st.session_state.get(f"confirm_del_{o['id']}", False) is False:
                    st.session_state[f"confirm_del_{o['id']}"] = True
                    st.warning("Click delete again to confirm.")
                else:
                    with get_session() as s:
                        delete_operation(s, active_location_id, op_id=o["id"])
                        # audit
                        try:
                            SecurityManager.log_audit(
                                s, (user or {}).get("username", "system"),
                                "DELETE",
                                resource_type="LocationOperation",
                                resource_id=o["id"],
                                details=f"Deleted '{o['name']}'",
                                user_id=(user or {}).get("id"),
                                location_id=active_location_id,
                                ip_address=st.session_state.get("client_ip"),
                                success=True,
                            )
                        except Exception:
                            pass
                    st.success("Deleted")
                    st.rerun()
