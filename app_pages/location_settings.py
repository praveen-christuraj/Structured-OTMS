# app_pages/location_settings.py
import streamlit as st

from db import get_session
from models import Location
from security import SecurityManager

from location_config import (
    get_location_page_visibility,
    LocationConfig,
    get_tank_transactions_tab_visibility,
    save_tank_transactions_tab_visibility,
)

# ---------- defaults ----------
DEFAULT_FLAGS = {
    "show_tank_transactions": True,
    "show_tanker_transactions": True,
    "show_tanker_tracking": False,
    "show_yade_transactions": True,
    "show_yade_vessel_mapping": True,
    "show_yade_tracking": True,
    "show_view_transactions": True,
    "show_vessel_operations": True,
    "show_fso_operations": True,
    "show_export_operations": True,
    "show_otr": True,
    "show_reporting": True,
    "show_reports": True,
    "show_material_balance": True,
    "show_bccr": True,
    "show_convoy_status": True,
    "show_sharing": True,
}


def _is_admin(user) -> bool:
    role = (user or {}).get("role", "").lower()
    return role in ("admin-operations", "admin-it")


def _load_locations():
    with get_session() as session:
        return session.query(Location).order_by(Location.name).all()


def render_location_settings_page(active_location_id, user):
    """PUBLIC ENTRY — imported by main_app.py"""
    st.markdown("### 🧭 Location Settings")

    # Guard
    if not _is_admin(user):
        st.warning("You don’t have permission to view this page.")
        return

    # Pick location
    locations = _load_locations()
    if not locations:
        st.info("No locations found. Create one in **Manage Locations** first.")
        return

    labels = [f"{loc.name} ({loc.code})" for loc in locations]
    id_by_label = {label: loc.id for label, loc in zip(labels, locations)}

    if active_location_id and any(loc.id == active_location_id for loc in locations):
        default_label = next(l for l, loc in zip(labels, locations) if loc.id == active_location_id)
    else:
        default_label = labels[0]

    st.markdown("#### Select Location to Configure")
    sel_label = st.selectbox(
        "Location",
        labels,
        index=labels.index(default_label),
        key="ls_location_selector",
    )
    sel_location_id = id_by_label[sel_label]

    # -------- section switcher --------
    section = st.radio(
        "Configure Section",
        ["Page Access", "Tank Tx Tabs", "Reporting Tabs", "Convoy Status", "Service Types", "Tanker Tracking", "Yade Tracking", "Operations"],
        horizontal=True,
        key="ls_section_switch",
    )

    if section == "Page Access":
        _render_page_access(sel_location_id, user)

    elif section == "Tank Tx Tabs":
        _render_tank_tx_tabs(sel_location_id, user)

    elif section == "Reporting Tabs":
        _render_reporting_tabs(sel_location_id, user)
    elif section == "Convoy Status":
        _render_convoy_status_settings(sel_location_id, user)
    elif section == "Service Types":
        _render_service_types(sel_location_id, user)
    elif section == "Tanker Tracking":
        _render_tanker_tracking_settings(sel_location_id, user)
    elif section == "Yade Tracking":
        _render_yade_tracking_settings(sel_location_id, user)

    else:  # "Operations" (this is where you also add Cargo Type / Destination / Loading Berth via categories)
        _render_operations_config(sel_location_id, user)


# ===================== Page Access =====================
def _render_page_access(sel_location_id: int, user):
    with get_session() as session:
        flags = get_location_page_visibility(session, sel_location_id) or {}
    cfg = {**DEFAULT_FLAGS, **flags}

    st.markdown("#### Page Access Toggles")

    col1, col2 = st.columns(2)
    with col1:
        show_tank = st.toggle(
            "🛢️ Tank Transactions",
            value=cfg.get("show_tank_transactions", True),
            key="ls_flag_tank",
        )
        show_tanker = st.toggle(
            "🚚 Tanker Transactions",
            value=cfg.get("show_tanker_transactions", True),
            key="ls_flag_tanker",
        )
        show_tanker_tracking = st.toggle(
            "🚚 Tanker Tracking",
            value=cfg.get("show_tanker_tracking", False),
            key="ls_flag_tanker_tracking",
        )
        show_fso = st.toggle(
            "⚓ FSO Operations",
            value=cfg.get("show_fso_operations", True),
            key="ls_flag_fso",
        )
        show_vessel_ops = st.toggle(                           # ← add this block
            "⛴️ Vessel Operations",
            value=cfg.get("show_vessel_operations", True),
            key="ls_flag_vessel_ops",
        )
        show_export_ops = st.toggle(
            "📤 Export Operations",
            value=cfg.get("show_export_operations", True),
            key="ls_flag_export_ops",
        )
        show_otr = st.toggle(
            "📊 OTR",
            value=cfg.get("show_otr", True),
            key="ls_flag_otr",
        )
        show_reporting = st.toggle(
            "📊 Reporting",
            value=cfg.get("show_reporting", True),
            key="ls_flag_reporting",
        )
        show_material_balance = st.toggle(
            "🧮 Material Balance",
            value=cfg.get("show_material_balance", True),
            key="ls_flag_mb",
        )
    with col2:
        show_yade = st.toggle(
            "⛴️ YADE Transactions",
            value=cfg.get("show_yade_transactions", True),
            key="ls_flag_yade",
        )
        show_yvm = st.toggle(
            "🗺️ Yade-Vessel Mapping",
            value=cfg.get("show_yade_vessel_mapping", True),
            key="ls_flag_yvm",
        )
        show_rpts = st.toggle(
            "📄 Reports",
            value=cfg.get("show_reports", True),
            key="ls_flag_reports",
        )
        show_yade_tracking = st.toggle(
            "📍 Yade Tracking",
            value=cfg.get("show_yade_tracking", True),
            key="ls_flag_yade_tracking",
        )
        show_view_tx = st.toggle(
            "🗂️ View Transactions",
            value=cfg.get("show_view_transactions", True),
            key="ls_flag_view_tx",
        )
        show_convoy_status = st.toggle(
            "🧭 Convoy Status",
            value=cfg.get("show_convoy_status", True),
            key="ls_flag_convoy",
        )
        show_bccr = st.toggle(
            "📋 BCCR",
            value=cfg.get("show_bccr", True),
            key="ls_flag_bccr",
        )
        show_sharing = st.toggle(
            "🔗 Sharing",
            value=cfg.get("show_sharing", True),
            key="ls_flag_sharing",
        )

    st.caption("These switches control which operational pages this location can access.")

    if st.button("💾", type="primary", key="ls_save_page_flags", help="Save Settings"):
        new_flags = {
            "show_tank_transactions": bool(show_tank),
            "show_tanker_transactions": bool(show_tanker),
            "show_tanker_tracking": bool(show_tanker_tracking),
            "show_yade_transactions": bool(show_yade),
            "show_yade_vessel_mapping": bool(show_yvm),
            "show_yade_tracking": bool(show_yade_tracking),
            "show_view_transactions": bool(show_view_tx),
            "show_vessel_operations": bool(show_vessel_ops),
            "show_fso_operations": bool(show_fso),
            "show_export_operations": bool(show_export_ops),
            "show_otr": bool(show_otr),
            "show_reporting": bool(show_reporting),
            "show_reports": bool(show_rpts),
            "show_material_balance": bool(show_material_balance),
            "show_convoy_status": bool(show_convoy_status),
            "show_bccr": bool(show_bccr),
            "show_sharing": bool(show_sharing),
        }
        try:
            with get_session() as session:
                full_cfg = LocationConfig.get_config(session, sel_location_id)
                pv = full_cfg.get("page_visibility", {}).copy()
                pv.update(new_flags)
                full_cfg["page_visibility"] = pv
                
                # Sync permissions dictionary for PermissionManager compatibility
                perms = full_cfg.get("permissions", {}).copy()
                perms.update({
                    "tank_transactions": bool(show_tank),
                    "tanker_transactions": bool(show_tanker),
                    "tanker_tracking": bool(show_tanker_tracking),
                    "yade_transactions": bool(show_yade),
                    "otr_vessel": bool(show_vessel_ops),
                    "fso_operations": bool(show_fso),
                    "export_operations": bool(show_export_ops),
                })
                full_cfg["permissions"] = perms
                
                LocationConfig.save_config(session, sel_location_id, full_cfg)

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


# ===================== Tank Transactions tabs =====================
def _render_tank_tx_tabs(sel_location_id: int, user):
    st.markdown("### 🛢️ Tank Transactions (Tabs)")
    st.caption("Control which Tank Transactions sections are visible for this location.")

    page_enabled = bool(getattr(st.session_state, "ls_flag_tank", True))

    with get_session() as session:
        tab_flags = get_tank_transactions_tab_visibility(session, sel_location_id)

    d = st.columns(5)
    with d[0]:
        f_entry = st.toggle(
            "📝 Tank Entry",
            value=tab_flags["Tank Entry"],
            disabled=not page_enabled,
            key="ls_tt_entry",
        )
    with d[1]:
        f_meter = st.toggle(
            "🧮 Meter Records",
            value=tab_flags["Meter Records"],
            disabled=not page_enabled,
            key="ls_tt_meter",
        )
    with d[2]:
        f_cond = st.toggle(
            "🧪 Condensate Records",
            value=tab_flags["Condensate Records"],
            disabled=not page_enabled,
            key="ls_tt_cond",
        )
    with d[3]:
        f_pwater = st.toggle(
            "💧 Produced Water Records",
            value=tab_flags["Produced Water Records"],
            disabled=not page_enabled,
            key="ls_tt_pwater",
        )
    with d[4]:
        f_prod = st.toggle(
            "🏭 Production",
            value=tab_flags["Production"],
            disabled=not page_enabled,
            key="ls_tt_prod",
        )

    if not page_enabled:
        st.info(
            "Tank Transactions page access is OFF for this location, so these tabs are disabled. "
            "Turn on page access in Page Access."
        )

    if st.button(
        "💾 Save Tank Transactions Tabs",
        use_container_width=True,
        disabled=not page_enabled,
        key="ls_tt_save",
    ):
        try:
            with get_session() as session:
                save_tank_transactions_tab_visibility(
                    session,
                    sel_location_id,
                    {
                        "Tank Entry": bool(f_entry),
                        "Meter Records": bool(f_meter),
                        "Condensate Records": bool(f_cond),
                        "Produced Water Records": bool(f_pwater),
                        "Production": bool(f_prod),
                    },
                )
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


# ===================== Reporting tabs =====================
def _render_reporting_tabs(sel_location_id: int, user):
    st.markdown("### 📊 Reporting (Tabs)")
    st.caption("Control which reports are visible for this location. New reports appear automatically here.")

    from models import ReportDefinition
    with get_session() as s:
        reports = (
            s.query(ReportDefinition)
            .filter(ReportDefinition.is_active == True)
            .order_by(ReportDefinition.name.asc())
            .all()
        )

    if not reports:
        st.info("No active reports defined.")
        return

    with get_session() as s:
        cfg = LocationConfig.get_config(s, sel_location_id)
    tabs_access = cfg.setdefault("tabs_access", {})
    rep_map = tabs_access.setdefault("Reporting", {})

    cols = st.columns(2)
    toggles = {}
    for i, rep in enumerate(reports):
        col = cols[i % 2]
        slug = rep.slug or str(rep.id)
        label = rep.name or slug
        cur = bool(rep_map.get(slug, True))
        toggles[slug] = col.toggle(label, value=cur, key=f"ls_rep_tab_{slug}")

    if st.button("💾", type="primary", key="ls_rep_tabs_save", help="Save Reporting Tabs"):
        try:
            with get_session() as s:
                cfg = LocationConfig.get_config(s, sel_location_id)
                tabs_access = cfg.setdefault("tabs_access", {})
                rep_map = tabs_access.setdefault("Reporting", {})
                rep_map.update({k: bool(v) for k, v in toggles.items()})
                cfg["tabs_access"] = tabs_access
                LocationConfig.save_config(s, sel_location_id, cfg)
            SecurityManager.log_audit(
                None,
                (user or {}).get("username", "system"),
                "UPDATE",
                resource_type="LocationSettings.ReportingTabs",
                resource_id=str(sel_location_id),
                details=f"Updated Reporting tabs: {list(toggles.items())}",
                user_id=(user or {}).get("id"),
                location_id=sel_location_id,
            )
            st.success("Reporting tab visibility saved for this location.")
        except Exception as ex:
            st.error(f"Failed to save Reporting tabs: {ex}")


# ===================== Convoy Status settings =====================
def _render_convoy_status_settings(sel_location_id: int, user):
    st.markdown("### 🧭 Convoy Status (Dropdowns)")
    st.caption("Define status options for YADE and Vessel on the Convoy Status page.")

    with get_session() as s:
        cfg = LocationConfig.get_config(s, sel_location_id)
    cs = cfg.setdefault("convoy_status", {})
    state_yade_key = f"ls_convoy_yade_statuses_{sel_location_id}"
    state_vessel_key = f"ls_convoy_vessel_statuses_{sel_location_id}"
    if state_yade_key not in st.session_state or st.session_state.get(state_yade_key) is None:
        st.session_state[state_yade_key] = list(cs.get("yade_statuses", []))
    if state_vessel_key not in st.session_state or st.session_state.get(state_vessel_key) is None:
        st.session_state[state_vessel_key] = list(cs.get("vessel_statuses", []))
    yade_statuses = list(st.session_state[state_yade_key])
    vessel_statuses = list(st.session_state[state_vessel_key])

    if not yade_statuses and not vessel_statuses:
        st.info("No status options configured. If none are added, the page will show 'N/A'.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**YADE Status Options**")
        new_yade = st.text_input("Add YADE status", key="ls_convoy_yade_new")
        if st.button("➕", key="ls_convoy_yade_add", help="Add YADE Status"):
            val = (new_yade or "").strip()
            if val:
                st.session_state[state_yade_key] = yade_statuses + [val]
                yade_statuses = list(st.session_state[state_yade_key])
                st.success(f"Added '{val}'")
            else:
                st.error("Enter a valid status name.")
        for i, name in enumerate(yade_statuses):
            c = st.columns([0.8, 0.2])
            c[0].write(name)
            if c[1].button("🗑️", key=f"ls_convoy_yade_del_{i}"):
                st.session_state[state_yade_key] = [n for n in yade_statuses if n != name]
                yade_statuses = list(st.session_state[state_yade_key])
                st.success(f"Removed '{name}'")
    with col2:
        st.markdown("**Vessel Status Options**")
        new_vessel = st.text_input("Add Vessel status", key="ls_convoy_vessel_new")
        if st.button("➕", key="ls_convoy_vessel_add", help="Add Vessel Status"):
            val = (new_vessel or "").strip()
            if val:
                st.session_state[state_vessel_key] = vessel_statuses + [val]
                vessel_statuses = list(st.session_state[state_vessel_key])
                st.success(f"Added '{val}'")
            else:
                st.error("Enter a valid status name.")
        for i, name in enumerate(vessel_statuses):
            c = st.columns([0.8, 0.2])
            c[0].write(name)
            if c[1].button("🗑️", key=f"ls_convoy_vessel_del_{i}"):
                st.session_state[state_vessel_key] = [n for n in vessel_statuses if n != name]
                vessel_statuses = list(st.session_state[state_vessel_key])
                st.success(f"Removed '{name}'")

    if st.button("💾", type="primary", key="ls_convoy_save", help="Save Convoy Status"):
        try:
            with get_session() as s:
                cfg = LocationConfig.get_config(s, sel_location_id)
                cs = cfg.setdefault("convoy_status", {})
                cs["yade_statuses"] = list(st.session_state.get(state_yade_key, []))
                cs["vessel_statuses"] = list(st.session_state.get(state_vessel_key, []))
                cfg["convoy_status"] = cs
                LocationConfig.save_config(s, sel_location_id, cfg)
            SecurityManager.log_audit(
                None,
                (user or {}).get("username", "system"),
                "UPDATE",
                resource_type="LocationSettings.ConvoyStatus",
                resource_id=str(sel_location_id),
                details=f"Updated Convoy Status options",
                user_id=(user or {}).get("id"),
                location_id=sel_location_id,
            )
            st.success("Convoy Status options saved.")
        except Exception as ex:
            st.error(f"Failed to save Convoy Status options: {ex}")


def _render_service_types(sel_location_id: int, user):
    st.markdown("### 🛠️ Service Types")
    st.caption("Manage global service types shown to all users at all locations.")

    from location_config import get_service_types, add_service_type, delete_service_type

    with get_session() as s:
        types = get_service_types(s, 0)

    if not types:
        st.info("No service types configured. If none are added, dropdown will show 'N/A'.")

    new_type = st.text_input("Add Service Type", key="ls_service_type_new")
    colA, colB = st.columns([0.25, 0.75])
    with colA:
        if st.button("➕", key="ls_service_type_add", type="primary", help="Add"):
            val = (new_type or "").strip()
            if not val:
                st.error("Enter a valid service type name.")
            else:
                try:
                    with get_session() as s:
                        add_service_type(s, 0, val)
                        SecurityManager.log_audit(
                            s,
                            (user or {}).get("username", "system"),
                            "CREATE",
                            resource_type="LocationSettings.ServiceType",
                            resource_id=val,
                            details="Added service type",
                            user_id=(user or {}).get("id"),
                                    location_id=None,
                                    ip_address=st.session_state.get("client_ip"),
                                    success=True,
                                )
                        s.commit()
                    st.success(f"Added '{val}'")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Failed to add: {ex}")

    st.markdown("#### Existing Service Types")
    for i, name in enumerate(types):
        c = st.columns([0.8, 0.2])
        c[0].write(name)
        if c[1].button("🗑️ Delete", key=f"ls_service_type_del_{i}"):
            try:
                with get_session() as s:
                    delete_service_type(s, 0, name)
                    SecurityManager.log_audit(
                        s,
                        (user or {}).get("username", "system"),
                        "DELETE",
                        resource_type="LocationSettings.ServiceType",
                        resource_id=name,
                        details="Deleted service type",
                        user_id=(user or {}).get("id"),
                        location_id=None,
                        ip_address=st.session_state.get("client_ip"),
                        success=True,
                    )
                    s.commit()
                st.success(f"Deleted '{name}'")
                st.rerun()
            except Exception as ex:
                st.error(f"Delete failed: {ex}")
# ===================== Tanker Tracking =====================
def _render_tanker_tracking_settings(sel_location_id: int, user):
    st.markdown("### 🚚 Tanker Tracking")
    st.caption("Configure sender/receiver roles and routing for tanker tracking.")

    with get_session() as session:
        cfg = LocationConfig.get_config(session, sel_location_id)
        all_locations = session.query(Location).order_by(Location.name).all()

    page_enabled = bool(cfg.get("page_visibility", {}).get("show_tanker_tracking", False))
    tt_cfg = cfg.get("tanker_tracking", {}) or {}

    loc_lookup = {loc.id: loc for loc in all_locations}
    selected_loc = loc_lookup.get(sel_location_id)
    options = {loc.id: f"{loc.name} ({loc.code})" for loc in all_locations if loc.id != sel_location_id}

    sender_default = [lid for lid in tt_cfg.get("sender_targets", []) if lid in options]
    receiver_default = [lid for lid in tt_cfg.get("receiver_sources", []) if lid in options]
    aliases = tt_cfg.get("receiver_aliases", []) or []
    alias_seed = ", ".join(aliases) if aliases else ", ".join(
        [v for v in [getattr(selected_loc, "name", ""), getattr(selected_loc, "code", "")] if v]
    )

    if not page_enabled:
        st.info("Enable Tanker Tracking for this location in Page Access to expose it in the sidebar.")

    col1, col2 = st.columns(2)
    with col1:
        is_sender = st.toggle(
            "Allow this location to dispatch tankers (Sender)",
            value=tt_cfg.get("is_sender", False),
            disabled=not page_enabled,
            key="ls_tt_sender",
        )
        sender_targets = st.multiselect(
            "Receivers this sender dispatches to",
            options=list(options.values()),
            default=[options[lid] for lid in sender_default],
            disabled=not (page_enabled and is_sender),
            key="ls_tt_sender_targets",
        )
    with col2:
        is_receiver = st.toggle(
            "Allow this location to receive/close tankers (Receiver)",
            value=tt_cfg.get("is_receiver", False),
            disabled=not page_enabled,
            key="ls_tt_receiver",
        )
        receiver_sources = st.multiselect(
            "This receiver expects tankers from",
            options=list(options.values()),
            default=[options[lid] for lid in receiver_default],
            disabled=not (page_enabled and is_receiver),
            key="ls_tt_receiver_sources",
        )

    alias_input = st.text_input(
        "Destination aliases that map to this receiver (comma separated)",
        value=alias_seed,
        disabled=not (page_enabled and is_receiver),
        key="ls_tt_aliases",
    )

    label_to_id = {label: lid for lid, label in options.items()}
    sender_ids = [label_to_id.get(label) for label in sender_targets if label in label_to_id]
    receiver_ids = [label_to_id.get(label) for label in receiver_sources if label in label_to_id]
    alias_list = [a.strip() for a in (alias_input or "").split(",") if a.strip()]

    if st.button("💾", type="primary", key="ls_tt_save", help="Save Tanker Tracking"):
        try:
            with get_session() as session:
                cfg = LocationConfig.get_config(session, sel_location_id)
                tt = cfg.get("tanker_tracking", {}) or {}
                tt.update(
                    {
                        "is_sender": bool(is_sender),
                        "is_receiver": bool(is_receiver),
                        "sender_targets": sender_ids,
                        "receiver_sources": receiver_ids,
                        "receiver_aliases": alias_list,
                    }
                )
                cfg["tanker_tracking"] = tt
                LocationConfig.save_config(session, sel_location_id, cfg)

            SecurityManager.log_audit(
                None,
                (user or {}).get("username", "system"),
                "UPDATE",
                resource_type="LocationSettings.TankerTracking",
                resource_id=str(sel_location_id),
                details=f"Tanker Tracking updated (sender={is_sender}, receiver={is_receiver})",
                user_id=(user or {}).get("id"),
                location_id=sel_location_id,
            )
            st.success("Tanker Tracking settings saved.")
        except Exception as ex:
            st.error(f"Failed to save Tanker Tracking settings: {ex}")

def _render_yade_tracking_settings(sel_location_id: int, user):
    st.markdown("### ⛴️ Yade Tracking")
    st.caption("Configure sender/receiver roles and routing for yade tracking.")

    with get_session() as session:
        cfg = LocationConfig.get_config(session, sel_location_id)
        all_locations = session.query(Location).order_by(Location.name).all()

    page_enabled = bool(cfg.get("page_visibility", {}).get("show_yade_tracking", True))
    yt_cfg = cfg.get("yade_tracking", {}) or {}

    loc_lookup = {loc.id: loc for loc in all_locations}
    selected_loc = loc_lookup.get(sel_location_id)
    options = {loc.id: f"{loc.name} ({loc.code})" for loc in all_locations if loc.id != sel_location_id}

    sender_default = [lid for lid in yt_cfg.get("sender_targets", []) if lid in options]
    receiver_default = [lid for lid in yt_cfg.get("receiver_sources", []) if lid in options]
    aliases = yt_cfg.get("receiver_aliases", []) or []
    alias_seed = ", ".join(aliases) if aliases else ", ".join(
        [v for v in [getattr(selected_loc, "name", ""), getattr(selected_loc, "code", "")] if v]
    )

    col1, col2 = st.columns(2)
    with col1:
        is_sender = st.toggle(
            "Allow this location to capture departures (Sender)",
            value=yt_cfg.get("is_sender", False),
            disabled=not page_enabled,
            key="ls_yt_sender",
        )
        sender_targets = st.multiselect(
            "Receivers this sender dispatches to",
            options=list(options.values()),
            default=[options[lid] for lid in sender_default],
            disabled=not (page_enabled and is_sender),
            key="ls_yt_sender_targets",
        )
    with col2:
        is_receiver = st.toggle(
            "Allow this location to capture arrivals (Receiver)",
            value=yt_cfg.get("is_receiver", False),
            disabled=not page_enabled,
            key="ls_yt_receiver",
        )
        receiver_sources = st.multiselect(
            "This receiver expects yades from",
            options=list(options.values()),
            default=[options[lid] for lid in receiver_default],
            disabled=not (page_enabled and is_receiver),
            key="ls_yt_receiver_sources",
        )

    alias_input = st.text_input(
        "Destination aliases that map to this receiver (comma separated)",
        value=alias_seed,
        disabled=not (page_enabled and is_receiver),
        key="ls_yt_aliases",
    )

    label_to_id = {label: lid for lid, label in options.items()}
    sender_ids = [label_to_id.get(label) for label in sender_targets if label in label_to_id]
    receiver_ids = [label_to_id.get(label) for label in receiver_sources if label in label_to_id]
    alias_list = [a.strip() for a in (alias_input or "").split(",") if a.strip()]

    if st.button("💾", type="primary", key="ls_yt_save", help="Save Yade Tracking"):
        try:
            with get_session() as session:
                cfg = LocationConfig.get_config(session, sel_location_id)
                yt = cfg.get("yade_tracking", {}) or {}
                yt.update(
                    {
                        "is_sender": bool(is_sender),
                        "is_receiver": bool(is_receiver),
                        "sender_targets": sender_ids,
                        "receiver_sources": receiver_ids,
                        "receiver_aliases": alias_list,
                    }
                )
                cfg["yade_tracking"] = yt
                LocationConfig.save_config(session, sel_location_id, cfg)

            SecurityManager.log_audit(
                None,
                (user or {}).get("username", "system"),
                "UPDATE",
                resource_type="LocationSettings.YadeTracking",
                resource_id=str(sel_location_id),
                details=f"Yade Tracking updated (sender={is_sender}, receiver={is_receiver})",
                user_id=(user or {}).get("id"),
                location_id=sel_location_id,
            )
            st.success("Yade Tracking settings saved.")
        except Exception as ex:
            st.error(f"Failed to save Yade Tracking settings: {ex}")

# ===================== Operations config =====================
def _render_operations_config(selected_location_id, user):
    """
    UNIFIED operations configurator for all assets and categories:
      - 'Operation' (generic ops)
      - 'Cargo Type'
      - 'Destination'
      - 'Loading Berth'
    and assets like 'tank', 'tanker', 'yade', 'fso' etc.
    
    All dropdowns in operational pages (Tank, Tanker, YADE, FSO) read from here (no hardcoding in pages).
    This allows dynamic configuration of Destination and Loading Berth dropdowns per location.
    
    NOTE: When you add items to 'Destination' category, they appear ONLY in Destination dropdown.
          When you add items to 'Loading Berth' category, they appear ONLY in Loading Bay/Berth dropdown.
          When you add items to 'Operation' category, they appear ONLY in Operation dropdown.
    """
    from location_config import (
        OP_ASSETS,
        OP_CATEGORIES,
        list_operations,
        add_operation,
        set_operation_active,
        delete_operation,
    )

    st.markdown("### 🧩 Operations (per Location / Asset / Category)")
    st.caption(
        "Configure operational dropdowns for all pages. "
        "Use **Category** selector to choose what type of item you're adding: "
        "Operations, Destinations, Loading Berths, or Cargo Types."
    )

    if not selected_location_id:
        st.info("Select a location above to configure operations.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        asset = st.selectbox("Asset", OP_ASSETS, format_func=lambda x: x.title(), key="ops_asset")
    with col2:
        category = st.selectbox("Category", OP_CATEGORIES, key="ops_category")
    with col3:
        st.write("")

    # Provide context-sensitive hints and explanation based on category
    hint_map = {
        "Operation": "e.g., 'Receipt from Aggu', 'Dispatch to GPP', 'Opening Stock'",
        "Cargo Type": "e.g., 'Crude Oil', 'Condensate', 'OKW', 'ANZ'",
        "Destination": "e.g., 'Aggu', 'OFS', 'Ogini', 'GPP', 'Ndoni', 'Bonny'",
        "Loading Berth": "e.g., 'Aggu', 'Ogini', 'OFS', 'Berth A', 'Loading Bay 1'",
    }
    hint = hint_map.get(category, "Enter a name for this operation/item")
    
    # Category-specific info messages
    category_info = {
        "Operation": "Items added here will appear in the **Operation** dropdown only.",
        "Destination": "Items added here will appear in the **Destination** dropdown only.",
        "Loading Berth": "Items added here will appear in the **Loading Bay/Berth** dropdown only.",
        "Cargo Type": "Items added here will appear in the **Cargo Type** dropdown only.",
    }
    
    info_msg = category_info.get(category, "")
    if info_msg:
        st.info(f"ℹ️ Currently configuring: **{asset.title()}** → **{category}**. {info_msg}")

    op_name = st.text_input(
        f"{category} name",
        placeholder=hint,
        help=f"Enter a {category.lower()} name for {asset}. {hint}",
        key="ops_name_input"
    )

    c1, c2 = st.columns([0.25, 0.75])
    with c1:
        if st.button("➕", type="primary", key="ops_add_btn", help="Add Operation"):
            if not op_name or not op_name.strip():
                st.error(f"Please enter a valid {category.lower()} name.")
            else:
                try:
                    with get_session() as s:
                        item = add_operation(
                            s,
                            selected_location_id,
                            asset=asset,
                            category=category,
                            name=op_name.strip(),
                            active=True,
                        )
                        try:
                            SecurityManager.log_audit(
                                s,
                                (user or {}).get("username", "system"),
                                "CREATE",
                                resource_type="LocationOperation",
                                resource_id=item["id"],
                                details=f"Add '{item['name']}' to {asset}/{category}",
                                user_id=(user or {}).get("id"),
                                location_id=selected_location_id,
                                ip_address=st.session_state.get("client_ip"),
                                success=True,
                            )
                        except Exception:
                            pass
                    st.success(f"✅ '{op_name.strip()}' added to {asset.title()} → {category}.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Failed to add operation: {ex}")
    with c2:
        # Quick guide for categories
        with st.expander("ℹ️ Category Guide"):
            st.markdown("""
            **Category Selector Guide:**
            - **Operation**: General operations like 'Receipt', 'Dispatch', 'Opening Stock'
            - **Destination**: Destinations like 'Aggu', 'OFS', 'GPP', 'Ndoni'
            - **Loading Berth**: Loading bays/berths like 'Berth A', 'Loading Bay 1', 'Aggu'
            - **Cargo Type**: Cargo types like 'Crude Oil', 'Condensate', 'OKW'
            
            **Important:** Each category populates a different dropdown in transaction pages.
            """)

    st.markdown("---")
    st.markdown("#### Existing Operations")

    with get_session() as s:
        ops = list_operations(s, selected_location_id)

    if not ops:
        st.info("No operations configured yet. Use the form above to add operations for different assets and categories.")
        return

    show_filtered = st.checkbox(
        "Show only selected Asset/Category",
        value=True,
        key="ops_only_filter",
        help="Filter the list to show only operations matching the selected asset and category above."
    )
    
    if show_filtered:
        ops = [o for o in ops if o["asset"] == asset and o["category"] == category]
        if not ops:
            st.info(f"No operations found for **{asset.title()}** → **{category}**. Add one using the form above.")
            return

    # Show count
    st.caption(f"📋 Showing {len(ops)} operation(s)" + (f" for **{asset.title()}** → **{category}**" if show_filtered else ""))

    for o in ops:
        row_key = o["id"]
        colA, colB, colC, colD = st.columns([0.38, 0.22, 0.18, 0.22])
        with colA:
            st.write(f"**{o['name']}**")
            st.caption(f"{o['asset'].title()} · {o['category']}")
        with colB:
            on = st.toggle(
                "Active", 
                value=o.get("active", True), 
                key=f"ops_active_{row_key}",
                help="Toggle to enable/disable this operation in dropdowns"
            )
        with colC:
            if st.button("💾", key=f"ops_save_{row_key}", help="Save the active/inactive status"):
                with get_session() as s:
                    set_operation_active(s, selected_location_id, op_id=o["id"], active=on)
                    try:
                        SecurityManager.log_audit(
                            s,
                            (user or {}).get("username", "system"),
                            "UPDATE",
                            resource_type="LocationOperation",
                            resource_id=o["id"],
                            details=f"Set active={on} for '{o['name']}'",
                            user_id=(user or {}).get("id"),
                            location_id=selected_location_id,
                            success=True,
                        )
                    except Exception:
                        pass
                st.success(f"✅ '{o['name']}' status updated.")
        with colD:
            if st.button("🗑️", key=f"ops_del_{row_key}", help="Permanently delete this operation"):
                with get_session() as s:
                    delete_operation(s, selected_location_id, op_id=o["id"])
                    try:
                        SecurityManager.log_audit(
                            s,
                            (user or {}).get("username", "system"),
                            "DELETE",
                            resource_type="LocationOperation",
                            resource_id=o["id"],
                            details=f"Delete '{o['name']}'",
                            user_id=(user or {}).get("id"),
                            location_id=selected_location_id,
                            success=True,
                        )
                    except Exception:
                        pass
                st.success(f"🗑️ '{o['name']}' deleted.")
                st.rerun()
