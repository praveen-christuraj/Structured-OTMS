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
        ["Page Access", "Tank Tx Tabs", "Operations"],
        horizontal=True,
        key="ls_section_switch",
    )

    if section == "Page Access":
        _render_page_access(sel_location_id, user)

    elif section == "Tank Tx Tabs":
        _render_tank_tx_tabs(sel_location_id, user)

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
        show_fso = st.toggle(
            "⚓ FSO Operations",
            value=cfg.get("show_fso_operations", True),
            key="ls_flag_fso",
        )
    with col2:
        show_yade = st.toggle(
            "⛴️ YADE Transactions",
            value=cfg.get("show_yade_transactions", True),
            key="ls_flag_yade",
        )
        show_rpts = st.toggle(
            "📄 Reports",
            value=cfg.get("show_reports", True),
            key="ls_flag_reports",
        )

    st.caption("These switches control which operational pages this location can access.")

    if st.button("💾 Save Settings", type="primary", key="ls_save_page_flags"):
        new_flags = {
            "show_tank_transactions": bool(show_tank),
            "show_tanker_transactions": bool(show_tanker),
            "show_yade_transactions": bool(show_yade),
            "show_fso_operations": bool(show_fso),
            "show_reports": bool(show_rpts),
        }
        try:
            with get_session() as session:
                full_cfg = LocationConfig.get_config(session, sel_location_id)
                pv = full_cfg.get("page_visibility", {}).copy()
                pv.update(new_flags)
                full_cfg["page_visibility"] = pv
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
        if st.button("➕ Add Operation", type="primary", key="ops_add_btn"):
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
            if st.button("💾 Save", key=f"ops_save_{row_key}", help="Save the active/inactive status"):
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
            if st.button("🗑️ Delete", key=f"ops_del_{row_key}", help="Permanently delete this operation"):
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
