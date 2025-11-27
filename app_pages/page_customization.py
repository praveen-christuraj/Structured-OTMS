# app_pages/page_customization.py
import streamlit as st
from typing import Dict, Any, List
from db import get_session
from models import Location
from permission_manager import PermissionManager
from security import SecurityManager

from location_config import (
    get_page_section_config,
    set_page_section_config,
    LocationConfig,
)
from location_config import (
    get_dynamic_table_def, set_dynamic_table_def,
)
def _guard_admin(user) -> bool:
    if not user or not PermissionManager.can_access_management_pages(user):
        st.error("You do not have permission to access Page Customization.")
        return False
    return True

def _pick_location(active_location_id: int):
    if not active_location_id:
        st.warning("No active location selected on Home. Pick a location here for customization.")
        with get_session() as s:
            locs = s.query(Location).order_by(Location.name.asc()).all()
        if not locs:
            st.error("No locations found. Create one in Manage Locations.")
            return None, None

        labels = [f"{l.name} ({l.code})" for l in locs]
        lab2id = {labels[i]: locs[i].id for i in range(len(locs))}
        sel = st.selectbox("Select location", labels, key="pc_loc_pick")
        lid = lab2id.get(sel)
        if not lid:
            return None, None
        with get_session() as s:
            loc = s.query(Location).get(lid)
        return loc, f"{loc.name} ({loc.code})"

    with get_session() as s:
        loc = s.query(Location).get(active_location_id)
    if not loc:
        st.error("Active location not found. Re-select on Home.")
        return None, None
    return loc, f"{loc.name} ({loc.code})"

def _ensure_len(labels, n, filler_prefix):
    labels = list(labels or [])
    if len(labels) < n:
        labels += [f"{filler_prefix} {i+1}" for i in range(len(labels), n)]
    elif len(labels) > n:
        labels = labels[:n]
    return labels

def render_page_customization(user: Dict[str, Any]):
    st.markdown("### ⚙️ Page Customization")

    if not _guard_admin(user):
        return

    active_location_id = st.session_state.get("active_location_id")
    loc, loc_label = _pick_location(active_location_id)
    if not loc:
        return

    st.caption(f"Configuring for **{loc_label}**")
    st.markdown("---")

    loc_key = f"{loc.id}"

    # ==============================
    # 🧪 Condensate — Flow Meters (per location)
    # ==============================
    with st.expander("🧪 Condensate — Flow Meters (per location)", expanded=False):
        # load existing
        with get_session() as s:
            cfg = get_page_section_config(s, loc.id, page="tank_transactions", section="condensate_meters") or {}
        c_meters = list(cfg.get("meters") or [])

        st.caption(
            "Configure flow meters used in **Condensate Records**. "
            "Each meter has a Label, Meter Factor, and Unit (bbls or m³). "
            "If the unit is m³, net quantity will be converted to bbls with 6.289811."
        )

        # row builder
        def _row(m=None):
            m = m or {"label": "", "factor": 1.0, "unit": "bbls", "active": True}
            return {
                "label": str(m.get("label") or "").strip(),
                "factor": float(m.get("factor") or 1.0),
                "unit": (m.get("unit") or "bbls").lower(),  # "bbls" | "m3"
                "active": bool(m.get("active", True)),
            }

        # editable list
        st.markdown("#### Add / Edit Meters")
        add_cols = st.columns([0.40, 0.22, 0.20, 0.18])
        with add_cols[0]:
            new_label = st.text_input("Meter Label", key=f"pc_cond_label_{loc_key}")
        with add_cols[1]:
            new_factor = st.number_input("Meter Factor", min_value=0.0001, max_value=999999.0, step=0.0001, format="%.4f", key=f"pc_cond_factor_{loc_key}")
        with add_cols[2]:
            new_unit = st.selectbox("Unit", ["bbls", "m3"], index=0, key=f"pc_cond_unit_{loc_key}")
        with add_cols[3]:
            add_btn = st.button("➕ Add", key=f"pc_cond_add_{loc_key}", use_container_width=True)

        if add_btn:
            if not new_label.strip():
                st.error("Please enter a Meter Label.")
            else:
                c_meters.append(_row({"label": new_label, "factor": new_factor, "unit": new_unit, "active": True}))
                try:
                    with get_session() as s:
                        set_page_section_config(s, loc.id, "tank_transactions", "condensate_meters", {"meters": c_meters})
                        # audit
                        try:
                            SecurityManager.log_audit(
                                s, (user or {}).get("username", "system"), "CREATE",
                                resource_type="PageCustomization:CondensateMeter",
                                resource_id=str(loc.id),
                                details=f"Added condensate meter: {new_label} (factor={new_factor}, unit={new_unit})",
                                user_id=(user or {}).get("id"),
                                location_id=loc.id,
                                ip_address=st.session_state.get("client_ip"),
                                success=True,
                            )
                        except Exception:
                            pass
                    st.success("Meter added.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Save failed: {ex}")

        st.markdown("#### Saved Meters")
        if not c_meters:
            st.info("No condensate meters configured yet.")
        else:
            for idx, m in enumerate(c_meters):
                row_key = f"pc_cond_row_{loc_key}_{idx}"
                st.write(f"**{idx+1}.** {m.get('label','')}  —  factor: {m.get('factor',1.0)}  —  unit: {m.get('unit','bbls')}  —  {'active' if m.get('active',True) else 'inactive'}")
                ecols = st.columns([0.22, 0.22, 0.22, 0.18, 0.16])
                with ecols[0]:
                    new_label_i = st.text_input("Label", value=m.get("label",""), key=f"{row_key}_lbl")
                with ecols[1]:
                    new_factor_i = st.number_input("Factor", value=float(m.get("factor",1.0)), step=0.0001, format="%.4f", key=f"{row_key}_fac")
                with ecols[2]:
                    new_unit_i = st.selectbox("Unit", ["bbls","m3"], index=(0 if (m.get("unit","bbls")=="bbls") else 1), key=f"{row_key}_unit")
                with ecols[3]:
                    new_active_i = st.checkbox("Active", value=bool(m.get("active",True)), key=f"{row_key}_act")
                with ecols[4]:
                    save_i = st.button("💾 Save", key=f"{row_key}_save", use_container_width=True)

                if save_i:
                    c_meters[idx] = _row({"label": new_label_i, "factor": new_factor_i, "unit": new_unit_i, "active": new_active_i})
                    try:
                        with get_session() as s:
                            set_page_section_config(s, loc.id, "tank_transactions", "condensate_meters", {"meters": c_meters})
                            # audit
                            try:
                                SecurityManager.log_audit(
                                    s, (user or {}).get("username","system"), "UPDATE",
                                    resource_type="PageCustomization:CondensateMeter",
                                    resource_id=f"{loc.id}:{idx}",
                                    details=f"Edited condensate meter idx={idx}: {c_meters[idx]}",
                                    user_id=(user or {}).get("id"),
                                    location_id=loc.id,
                                    ip_address=st.session_state.get("client_ip"),
                                    success=True,
                                )
                            except Exception:
                                pass
                        st.success("Updated.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Save failed: {ex}")

                # delete with confirm
                del_flag_key = f"{row_key}_delflag"
                if del_flag_key not in st.session_state:
                    st.session_state[del_flag_key] = False

                dcols = st.columns([0.84, 0.16])
                with dcols[1]:
                    if not st.session_state[del_flag_key]:
                        if st.button("🗑️ Delete", key=f"{row_key}_del", use_container_width=True):
                            st.session_state[del_flag_key] = True
                    else:
                        st.warning("Confirm delete?")
                        c1, c2 = st.columns(2)
                        if c1.button("✅ Yes", key=f"{row_key}_del_yes", use_container_width=True):
                            try:
                                new_list = [x for j, x in enumerate(c_meters) if j != idx]
                                with get_session() as s:
                                    set_page_section_config(s, loc.id, "tank_transactions", "condensate_meters", {"meters": new_list})
                                    # audit
                                    try:
                                        SecurityManager.log_audit(
                                            s, (user or {}).get("username","system"), "DELETE",
                                            resource_type="PageCustomization:CondensateMeter",
                                            resource_id=f"{loc.id}:{idx}",
                                            details=f"Deleted condensate meter idx={idx} ({m.get('label','')})",
                                            user_id=(user or {}).get("id"),
                                            location_id=loc.id,
                                            ip_address=st.session_state.get("client_ip"),
                                            success=True,
                                        )
                                    except Exception:
                                        pass
                                st.success("Deleted.")
                                st.session_state[del_flag_key] = False
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Delete failed: {ex}")
                        if c2.button("❌ No", key=f"{row_key}_del_no", use_container_width=True):
                            st.session_state[del_flag_key] = False

    # ============================
    # 💧 Produced Water — Table Builder (soft-coded)
    # ==============================
    with st.expander("💧 Produced Water — Table Definition (per location)", expanded=False):
        with get_session() as s:
            pw_def = get_dynamic_table_def(s, loc.id, page="tank_transactions", section="produced_water")
        pw_columns = list(pw_def.get("columns") or [])

        st.caption("Define the columns used in Produced Water data entry. Exactly one column can be 'date' (enforced as date picker). Others can be 'number' or 'text'.")
        st.info("💡 **Calculated Columns**: For columns with formulas, the value will be auto-calculated based on other columns.")
        n_cols = st.number_input("Number of columns", min_value=1, max_value=20, step=1, value=max(1, len(pw_columns) or 3), key=f"pc_pw_count_{loc_key}")

        # normalize length
        def _def_col(i):
            return {"name": f"col_{i+1}", "label": f"Column {i+1}", "type": "text", "required": False, "formula": None}
        if len(pw_columns) < n_cols:
            for i in range(len(pw_columns), n_cols):
                pw_columns.append(_def_col(i))
        elif len(pw_columns) > n_cols:
            pw_columns = pw_columns[:n_cols]

        date_seen = any(c.get("type") == "date" for c in pw_columns)
        for i in range(n_cols):
            st.markdown(f"**Column {i+1}**")
            c1, c2, c3, c4 = st.columns([0.28, 0.28, 0.24, 0.20])
            with c1:
                pw_columns[i]["name"] = st.text_input("Field name (no spaces)", value=pw_columns[i].get("name", f"col_{i+1}"), key=f"pc_pw_name_{loc_key}_{i}")
            with c2:
                pw_columns[i]["label"] = st.text_input("Label", value=pw_columns[i].get("label", f"Column {i+1}"), key=f"pc_pw_label_{loc_key}_{i}")
            with c3:
                current_type = pw_columns[i].get("type", "text")
                type_choice = st.selectbox("Type", ["text", "number", "date"], index=["text","number","date"].index(current_type), key=f"pc_pw_type_{loc_key}_{i}")
                # enforce single date column
                if type_choice == "date":
                    if not date_seen or current_type == "date":
                        pw_columns[i]["type"] = "date"
                        date_seen = True
                    else:
                        st.warning("Only one 'date' column allowed. Switching to 'text'.")
                        pw_columns[i]["type"] = "text"
                else:
                    pw_columns[i]["type"] = type_choice
            with c4:
                pw_columns[i]["required"] = st.checkbox("Required", value=bool(pw_columns[i].get("required", False)), key=f"pc_pw_req_{loc_key}_{i}")
            
            # Formula configuration (only for number type)
            if pw_columns[i].get("type") == "number":
                with st.expander(f"➕ Formula for {pw_columns[i].get('label', 'Column')} (Optional)", expanded=bool(pw_columns[i].get("formula"))):
                    st.caption("Configure automatic calculation for this column based on other columns.")
                    
                    current_formula = pw_columns[i].get("formula") or {}
                    use_formula = st.checkbox("Enable Formula", value=bool(current_formula), key=f"pc_pw_formula_enable_{loc_key}_{i}")
                    
                    if use_formula:
                        fc1, fc2 = st.columns([0.4, 0.6])
                        with fc1:
                            operation = st.selectbox(
                                "Operation",
                                ["sum", "subtract", "multiply", "divide", "percentage", "maximum", "minimum", "average"],
                                index=["sum", "subtract", "multiply", "divide", "percentage", "maximum", "minimum", "average"].index(current_formula.get("operation", "sum")),
                                key=f"pc_pw_formula_op_{loc_key}_{i}"
                            )
                        
                        with fc2:
                            available_cols = [(idx, c.get("name"), c.get("label")) 
                                            for idx, c in enumerate(pw_columns) 
                                            if idx != i and c.get("type") != "date"]
                            
                            if not available_cols:
                                st.warning("No other numeric columns available for formula.")
                            else:
                                col_options = [f"{label} ({name})" for _, name, label in available_cols]
                                col_name_map = {f"{label} ({name})": name for _, name, label in available_cols}
                                
                                current_cols = current_formula.get("columns", [])
                                default_selection = [f"{pw_columns[idx].get('label')} ({pw_columns[idx].get('name')})" 
                                                   for idx, c in enumerate(pw_columns) 
                                                   if c.get("name") in current_cols]
                                
                                selected_cols = st.multiselect(
                                    "Select Columns",
                                    col_options,
                                    default=default_selection,
                                    key=f"pc_pw_formula_cols_{loc_key}_{i}",
                                    help="Select columns to use in the calculation"
                                )
                                
                                selected_col_names = [col_name_map[sc] for sc in selected_cols]
                                
                                if selected_col_names:
                                    if operation == "sum":
                                        formula_preview = " + ".join(selected_col_names)
                                    elif operation == "subtract":
                                        formula_preview = " - ".join(selected_col_names)
                                    elif operation == "multiply":
                                        formula_preview = " × ".join(selected_col_names)
                                    elif operation == "divide":
                                        formula_preview = " ÷ ".join(selected_col_names)
                                    elif operation == "percentage":
                                        formula_preview = f"({selected_col_names[0]} ÷ {selected_col_names[1] if len(selected_col_names) > 1 else '?'}) × 100" if len(selected_col_names) >= 2 else "Need 2 columns"
                                    elif operation == "maximum":
                                        formula_preview = f"MAX({', '.join(selected_col_names)})"
                                    elif operation == "minimum":
                                        formula_preview = f"MIN({', '.join(selected_col_names)})"
                                    elif operation == "average":
                                        formula_preview = f"AVG({', '.join(selected_col_names)})"
                                    
                                    st.code(f"Formula: {formula_preview}", language="text")
                                    
                                    pw_columns[i]["formula"] = {
                                        "operation": operation,
                                        "columns": selected_col_names
                                    }
                                else:
                                    st.info("Select at least one column for the formula.")
                                    pw_columns[i]["formula"] = None
                    else:
                        pw_columns[i]["formula"] = None
            
            st.markdown("---")

        if st.button("💾 Save Produced Water Table", type="primary", key=f"pc_pw_save_{loc_key}"):
            try:
                with get_session() as s:
                    set_dynamic_table_def(s, loc.id, "tank_transactions", "produced_water", {"columns": pw_columns})
                    # audit
                    try:
                        SecurityManager.log_audit(
                            s, (user or {}).get("username","system"), "UPDATE",
                            resource_type="PageCustomization:PWDef", resource_id=str(loc.id),
                            details=f"Produced Water columns saved: {pw_columns}",
                            user_id=(user or {}).get("id"), location_id=loc.id, success=True,
                            ip_address=st.session_state.get("client_ip")
                        )
                    except Exception:
                        pass
                st.success("Produced Water definition saved.")
                st.rerun()
            except Exception as ex:
                st.error(f"Save failed: {ex}")

        st.markdown("##### Saved definition")
        if not pw_columns:
            st.info("No columns defined yet.")
        else:
            for j, c in enumerate(pw_columns, start=1):
                formula_info = ""
                if c.get("formula"):
                    f = c["formula"]
                    op = f.get("operation", "N/A")
                    cols = ", ".join(f.get("columns", []))
                    formula_info = f" — **Formula**: {op.upper()}({cols})"
                st.write(f"**{j}.** `{c['name']}` — {c['label']} — *{c['type']}* — {'required' if c.get('required') else 'optional'}{formula_info}")


    # ==============================
    # 🏭 Production — Table Builder (soft-coded)
    # ==============================
    with st.expander("🏭 Production — Table Definition (per location)", expanded=False):
        with get_session() as s:
            prod_def = get_dynamic_table_def(s, loc.id, page="tank_transactions", section="production")
        prod_columns = list(prod_def.get("columns") or [])

        st.caption("Define the columns used in Production data entry. Exactly one 'date' column. Others can be 'number' or 'text'.")
        st.info("💡 **Calculated Columns**: For columns with formulas, the value will be auto-calculated based on other columns.")
        n_cols = st.number_input("Number of columns", min_value=1, max_value=30, step=1, value=max(1, len(prod_columns) or 4), key=f"pc_prod_count_{loc_key}")

        def _def_col2(i):
            return {"name": f"col_{i+1}", "label": f"Column {i+1}", "type": "number", "required": False, "formula": None}
        if len(prod_columns) < n_cols:
            for i in range(len(prod_columns), n_cols):
                prod_columns.append(_def_col2(i))
        elif len(prod_columns) > n_cols:
            prod_columns = prod_columns[:n_cols]

        date_seen = any(c.get("type") == "date" for c in prod_columns)
        
        # Get all column names for formula reference
        all_col_names = [c.get("name", f"col_{i+1}") for i, c in enumerate(prod_columns)]
        
        for i in range(n_cols):
            st.markdown(f"**Column {i+1}**")
            c1, c2, c3, c4 = st.columns([0.28, 0.28, 0.24, 0.20])
            with c1:
                prod_columns[i]["name"] = st.text_input("Field name (no spaces)", value=prod_columns[i].get("name", f"col_{i+1}"), key=f"pc_prod_name_{loc_key}_{i}")
            with c2:
                prod_columns[i]["label"] = st.text_input("Label", value=prod_columns[i].get("label", f"Column {i+1}"), key=f"pc_prod_label_{loc_key}_{i}")
            with c3:
                current_type = prod_columns[i].get("type", "number")
                type_choice = st.selectbox("Type", ["text", "number", "date"], index=["text","number","date"].index(current_type), key=f"pc_prod_type_{loc_key}_{i}")
                if type_choice == "date":
                    if not date_seen or current_type == "date":
                        prod_columns[i]["type"] = "date"
                        date_seen = True
                    else:
                        st.warning("Only one 'date' column allowed. Switching to 'number'.")
                        prod_columns[i]["type"] = "number"
                else:
                    prod_columns[i]["type"] = type_choice
            with c4:
                prod_columns[i]["required"] = st.checkbox("Required", value=bool(prod_columns[i].get("required", False)), key=f"pc_prod_req_{loc_key}_{i}")
            
            # Formula configuration (only for number type)
            if prod_columns[i].get("type") == "number":
                with st.expander(f"➕ Formula for {prod_columns[i].get('label', 'Column')} (Optional)", expanded=bool(prod_columns[i].get("formula"))):
                    st.caption("Configure automatic calculation for this column based on other columns.")
                    
                    # Get current formula or create default
                    current_formula = prod_columns[i].get("formula") or {}
                    
                    use_formula = st.checkbox("Enable Formula", value=bool(current_formula), key=f"pc_prod_formula_enable_{loc_key}_{i}")
                    
                    if use_formula:
                        fc1, fc2 = st.columns([0.4, 0.6])
                        with fc1:
                            operation = st.selectbox(
                                "Operation",
                                ["sum", "subtract", "multiply", "divide", "percentage", "maximum", "minimum", "average"],
                                index=["sum", "subtract", "multiply", "divide", "percentage", "maximum", "minimum", "average"].index(current_formula.get("operation", "sum")),
                                key=f"pc_prod_formula_op_{loc_key}_{i}"
                            )
                        
                        with fc2:
                            # Get available columns (exclude current column and date columns)
                            available_cols = [(idx, c.get("name"), c.get("label")) 
                                            for idx, c in enumerate(prod_columns) 
                                            if idx != i and c.get("type") != "date"]
                            
                            if not available_cols:
                                st.warning("No other numeric columns available for formula.")
                            else:
                                col_options = [f"{label} ({name})" for _, name, label in available_cols]
                                col_name_map = {f"{label} ({name})": name for _, name, label in available_cols}
                                
                                # Get currently selected columns
                                current_cols = current_formula.get("columns", [])
                                default_selection = [f"{prod_columns[idx].get('label')} ({prod_columns[idx].get('name')})" 
                                                   for idx, c in enumerate(prod_columns) 
                                                   if c.get("name") in current_cols]
                                
                                selected_cols = st.multiselect(
                                    "Select Columns",
                                    col_options,
                                    default=default_selection,
                                    key=f"pc_prod_formula_cols_{loc_key}_{i}",
                                    help="Select columns to use in the calculation"
                                )
                                
                                # Convert back to column names
                                selected_col_names = [col_name_map[sc] for sc in selected_cols]
                                
                                # Show formula preview
                                if selected_col_names:
                                    if operation == "sum":
                                        formula_preview = " + ".join(selected_col_names)
                                    elif operation == "subtract":
                                        formula_preview = " - ".join(selected_col_names)
                                    elif operation == "multiply":
                                        formula_preview = " × ".join(selected_col_names)
                                    elif operation == "divide":
                                        formula_preview = " ÷ ".join(selected_col_names)
                                    elif operation == "percentage":
                                        formula_preview = f"({selected_col_names[0]} ÷ {selected_col_names[1] if len(selected_col_names) > 1 else '?'}) × 100" if len(selected_col_names) >= 2 else "Need 2 columns"
                                    elif operation == "maximum":
                                        formula_preview = f"MAX({', '.join(selected_col_names)})"
                                    elif operation == "minimum":
                                        formula_preview = f"MIN({', '.join(selected_col_names)})"
                                    elif operation == "average":
                                        formula_preview = f"AVG({', '.join(selected_col_names)})"
                                    
                                    st.code(f"Formula: {formula_preview}", language="text")
                                    
                                    # Save formula to column definition
                                    prod_columns[i]["formula"] = {
                                        "operation": operation,
                                        "columns": selected_col_names
                                    }
                                else:
                                    st.info("Select at least one column for the formula.")
                                    prod_columns[i]["formula"] = None
                    else:
                        # Clear formula if disabled
                        prod_columns[i]["formula"] = None
            
            st.markdown("---")  # Separator between columns

        if st.button("💾 Save Production Table", type="primary", key=f"pc_prod_save_{loc_key}"):
            try:
                with get_session() as s:
                    set_dynamic_table_def(s, loc.id, "tank_transactions", "production", {"columns": prod_columns})
                    try:
                        SecurityManager.log_audit(
                            s, (user or {}).get("username","system"), "UPDATE",
                            resource_type="PageCustomization:ProductionDef", resource_id=str(loc.id),
                            details=f"Production columns saved: {prod_columns}",
                            user_id=(user or {}).get("id"), location_id=loc.id, success=True,
                            ip_address=st.session_state.get("client_ip")
                        )
                    except Exception:
                        pass
                st.success("Production definition saved.")
                st.rerun()
            except Exception as ex:
                st.error(f"Save failed: {ex}")

        st.markdown("##### Saved definition")
        if not prod_columns:
            st.info("No columns defined yet.")
        else:
            for j, c in enumerate(prod_columns, start=1):
                formula_info = ""
                if c.get("formula"):
                    f = c["formula"]
                    op = f.get("operation", "N/A")
                    cols = ", ".join(f.get("columns", []))
                    formula_info = f" — **Formula**: {op.upper()}({cols})"
                st.write(f"**{j}.** `{c['name']}` — {c['label']} — *{c['type']}* — {'required' if c.get('required') else 'optional'}{formula_info}")

    # ==============================================
    # 🧮 Meter Records (Meters & Factors)  <-- FULL CRUD + AUDIT
    # ==============================================
    with st.expander("🧮 Meter Records (Meters & Factors)", expanded=True):
        with get_session() as s:
            meters_cfg = get_page_section_config(s, loc.id, page="tank_transactions", section="meters")

        # structure: {"meters": [{"label": "...", "factor": 1.0000, "unit": "bbls"|"m3"}, ...]}
        meters = list(meters_cfg.get("meters") or [])
        count_default = len(meters) if len(meters) > 0 else 1

        nm = st.number_input(
            "Number of meters",
            min_value=1, max_value=24, value=count_default, step=1,
            key=f"pc_meters_count_{loc_key}"
        )

        # normalize list to size nm
        def _default_meter(i):
            return {"label": f"Meter {i+1}", "factor": 1.0000, "unit": "bbls"}

        if len(meters) < int(nm):
            for i in range(len(meters), int(nm)):
                meters.append(_default_meter(i))
        elif len(meters) > int(nm):
            meters = meters[: int(nm)]

        # --- Create/Update block (top) ---
        for i in range(int(nm)):
            st.markdown(f"**New/Update Slot {i+1}**")
            c1, c2, c3 = st.columns([0.45, 0.30, 0.25])

            with c1:
                meters[i]["label"] = st.text_input(
                    "Label",
                    value=str(meters[i].get("label", f"Meter {i+1}")),
                    key=f"pc_meter_label_{loc_key}_{i}"
                )
            with c2:
                meters[i]["factor"] = st.number_input(
                    "Meter factor",
                    min_value=0.0001, max_value=10.0,
                    step=0.0001, format="%.4f",
                    value=float(meters[i].get("factor", 1.0)),
                    key=f"pc_meter_factor_{loc_key}_{i}"
                )
            with c3:
                current_unit = (meters[i].get("unit") or "bbls").lower()
                meters[i]["unit"] = st.selectbox(
                    "Unit",
                    ["bbls", "m3"],
                    index=(0 if current_unit == "bbls" else 1),
                    key=f"pc_meter_unit_{loc_key}_{i}"
                )

            st.caption("Update factor here after each Meter Proving. Unit defines how readings are interpreted in Meter Records.")
            st.markdown("---")

        if st.button("💾 Save Meters & Factors", type="primary", key=f"pc_meters_save_{loc_key}"):
            try:
                payload = {"meters": meters}
                with get_session() as s:
                    set_page_section_config(s, loc.id, "tank_transactions", "meters", payload)
                    # ---- AUDIT (pass real session) ----
                    try:
                        ip = st.session_state.get("client_ip")  # set this elsewhere if you capture it
                        SecurityManager.log_audit(
                            s,
                            (user or {}).get("username", "system"),
                            "UPDATE",
                            resource_type="PageCustomization:MeterConfig",
                            resource_id=str(loc.id),
                            details=f"Saved {len(meters)} meter(s): {payload}",
                            user_id=(user or {}).get("id"),
                            location_id=loc.id,
                            ip_address=ip,
                            success=True,
                        )
                    except Exception:
                        pass
                st.success("Meter configuration saved.")
                st.rerun()
            except Exception as ex:
                st.error(f"Save failed: {ex}")


        # --- Saved meters table with Edit/Delete ---
        st.markdown("##### Saved meters")
        with get_session() as s:
            meters_cfg_live = get_page_section_config(s, loc.id, page="tank_transactions", section="meters")
        meters_live = list(meters_cfg_live.get("meters") or [])

        if not meters_live:
            st.info("No meters configured yet.")
        else:
            for idx, m in enumerate(meters_live):
                row_key = f"{loc_key}_{idx}"
                label = m.get("label") or f"Meter {idx+1}"
                factor = float(m.get("factor") or 1.0)
                unit = (m.get("unit") or "bbls").lower()

                st.write(
                    f"**{idx+1}. {label}** — Factor: `{factor:.4f}` — Unit: `{unit}`"
                )
                c1, c2, c3, c4, c5 = st.columns([0.36, 0.18, 0.16, 0.15, 0.15])

                # Edit mode toggle in session
                edit_flag_key = f"pc_meter_edit_flag_{row_key}"
                del_flag_key = f"pc_meter_del_flag_{row_key}"
                st.session_state.setdefault(edit_flag_key, False)
                st.session_state.setdefault(del_flag_key, False)

                if not st.session_state[edit_flag_key]:
                    # View row
                    with c4:
                        if st.button("✏️ Edit", key=f"pc_meter_edit_btn_{row_key}"):
                            st.session_state[edit_flag_key] = True
                            st.session_state[f"pc_edit_label_{row_key}"] = label
                            st.session_state[f"pc_edit_factor_{row_key}"] = factor
                            st.session_state[f"pc_edit_unit_{row_key}"] = unit
                    with c5:
                        if not st.session_state[del_flag_key]:
                            if st.button("🗑️ Delete", key=f"pc_meter_del_btn_{row_key}"):
                                st.session_state[del_flag_key] = True
                        else:
                            st.warning("Confirm delete?")
                            d1, d2 = st.columns(2)
                            with d1:
                                if st.button("✅ Yes", key=f"pc_meter_del_yes_{row_key}"):
                                    try:
                                        new_list = [x for j, x in enumerate(meters_live) if j != idx]
                                        payload = {"meters": new_list}
                                        with get_session() as s:
                                            set_page_section_config(s, loc.id, "tank_transactions", "meters", payload)
                                            # ---- AUDIT (pass real session) ----
                                            try:
                                                ip = st.session_state.get("client_ip")
                                                SecurityManager.log_audit(
                                                    s,
                                                    (user or {}).get("username", "system"),
                                                    "DELETE",
                                                    resource_type="PageCustomization:Meter",
                                                    resource_id=f"{loc.id}:{idx}",
                                                    details=f"Deleted meter #{idx+1} ({label})",
                                                    user_id=(user or {}).get("id"),
                                                    location_id=loc.id,
                                                    ip_address=ip,
                                                    success=True,
                                                )
                                            except Exception:
                                                pass
                                        st.success(f"Deleted meter: {label}")
                                        st.session_state[del_flag_key] = False
                                        st.rerun()
                                    except Exception as ex:
                                        st.error(f"Delete failed: {ex}")

                            with d2:
                                if st.button("❌ No", key=f"pc_meter_del_no_{row_key}"):
                                    st.session_state[del_flag_key] = False
                else:
                    # Edit row UI
                    with c1:
                        new_label = st.text_input(
                            "Label",
                            value=st.session_state.get(f"pc_edit_label_{row_key}", label),
                            key=f"pc_meter_edit_label_{row_key}"
                        )
                    with c2:
                        new_factor = st.number_input(
                            "Factor",
                            min_value=0.0001, max_value=10.0, step=0.0001, format="%.4f",
                            value=float(st.session_state.get(f"pc_edit_factor_{row_key}", factor)),
                            key=f"pc_meter_edit_factor_{row_key}"
                        )
                    with c3:
                        new_unit = st.selectbox(
                            "Unit",
                            ["bbls", "m3"],
                            index=(0 if (st.session_state.get(f"pc_edit_unit_{row_key}", unit) == "bbls") else 1),
                            key=f"pc_meter_edit_unit_{row_key}"
                        )
                    with c4:
                        if st.button("💾 Save", key=f"pc_meter_edit_save_{row_key}"):
                            try:
                                meters_live[idx] = {
                                    "label": (new_label or f"Meter {idx+1}").strip(),
                                    "factor": float(new_factor),
                                    "unit": new_unit.lower(),
                                }
                                payload = {"meters": meters_live}
                                with get_session() as s:
                                    set_page_section_config(s, loc.id, "tank_transactions", "meters", payload)
                                    # ---- AUDIT (pass real session) ----
                                    try:
                                        ip = st.session_state.get("client_ip")
                                        SecurityManager.log_audit(
                                            s,
                                            (user or {}).get("username", "system"),
                                            "UPDATE",
                                            resource_type="PageCustomization:Meter",
                                            resource_id=f"{loc.id}:{idx}",
                                            details=f"Edited meter #{idx+1} → {meters_live[idx]}",
                                            user_id=(user or {}).get("id"),
                                            location_id=loc.id,
                                            ip_address=ip,
                                            success=True,
                                        )
                                    except Exception:
                                        pass
                                st.success("Meter updated.")
                                st.session_state[edit_flag_key] = False
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Update failed: {ex}")

                    with c5:
                        if st.button("↩️ Cancel", key=f"pc_meter_edit_cancel_{row_key}"):
                            st.session_state[edit_flag_key] = False

                st.markdown("---")

    st.info("All changes take effect immediately on the corresponding pages.")

    # ==============================
    # 📑 Custom Tabs Management
    # ==============================
    st.markdown("---")
    st.markdown("## 📑 Custom Tabs Management")
    st.caption("Create custom tabs with dynamic columns for Tank Transactions and Tanker Transactions pages. Each tab gets its own database table and can be used in reports.")
    
    with st.expander("➕ Create New Custom Tab", expanded=False):
        st.markdown("### Add New Custom Tab")
        
        # Select target page
        target_page = st.selectbox(
            "Target Page",
            ["tank_transactions", "tanker_transactions"],
            format_func=lambda x: "Tank Transactions" if x == "tank_transactions" else "Tanker Transactions",
            key=f"pc_custom_tab_page_{loc_key}"
        )
        
        # Tab name
        new_tab_name = st.text_input(
            "Tab Name *",
            placeholder="e.g., Daily Production, Chemical Injection",
            key=f"pc_custom_tab_name_{loc_key}"
        )
        
        st.markdown("#### Define Columns")
        st.caption("Configure the columns for this custom tab. At least one column is required.")
        
        num_cols = st.number_input(
            "Number of Columns",
            min_value=1,
            max_value=20,
            value=3,
            step=1,
            key=f"pc_custom_tab_cols_count_{loc_key}"
        )
        
        # Store column definitions in session state
        if f"pc_custom_tab_columns_{loc_key}" not in st.session_state:
            st.session_state[f"pc_custom_tab_columns_{loc_key}"] = [
                {"name": f"col_{i+1}", "label": f"Column {i+1}", "type": "number", "required": False, "formula": None}
                for i in range(num_cols)
            ]
        
        # Adjust list size if num_cols changed
        current_cols = st.session_state[f"pc_custom_tab_columns_{loc_key}"]
        if len(current_cols) < num_cols:
            for i in range(len(current_cols), num_cols):
                current_cols.append({"name": f"col_{i+1}", "label": f"Column {i+1}", "type": "number", "required": False, "formula": None})
        elif len(current_cols) > num_cols:
            current_cols = current_cols[:num_cols]
            st.session_state[f"pc_custom_tab_columns_{loc_key}"] = current_cols
        
        date_seen = any(c.get("type") == "date" for c in current_cols)
        
        for i in range(num_cols):
            st.markdown(f"**Column {i+1}**")
            c1, c2, c3, c4 = st.columns([0.28, 0.28, 0.24, 0.20])
            
            with c1:
                current_cols[i]["name"] = st.text_input(
                    "Field name (no spaces)",
                    value=current_cols[i].get("name", f"col_{i+1}"),
                    key=f"pc_custom_new_col_name_{loc_key}_{i}"
                )
            
            with c2:
                current_cols[i]["label"] = st.text_input(
                    "Label",
                    value=current_cols[i].get("label", f"Column {i+1}"),
                    key=f"pc_custom_new_col_label_{loc_key}_{i}"
                )
            
            with c3:
                current_type = current_cols[i].get("type", "number")
                type_choice = st.selectbox(
                    "Type",
                    ["text", "number", "date"],
                    index=["text", "number", "date"].index(current_type),
                    key=f"pc_custom_new_col_type_{loc_key}_{i}"
                )
                
                if type_choice == "date":
                    if not date_seen or current_type == "date":
                        current_cols[i]["type"] = "date"
                        date_seen = True
                    else:
                        st.warning("Only one 'date' column allowed. Switching to 'number'.")
                        current_cols[i]["type"] = "number"
                else:
                    current_cols[i]["type"] = type_choice
            
            with c4:
                current_cols[i]["required"] = st.checkbox(
                    "Required",
                    value=bool(current_cols[i].get("required", False)),
                    key=f"pc_custom_new_col_req_{loc_key}_{i}"
                )
            
            # Formula configuration for number columns
            if current_cols[i].get("type") == "number":
                with st.expander(f"➕ Formula for {current_cols[i].get('label', 'Column')} (Optional)", expanded=bool(current_cols[i].get("formula"))):
                    st.caption("Configure automatic calculation for this column based on other columns.")
                    
                    current_formula = current_cols[i].get("formula") or {}
                    use_formula = st.checkbox(
                        "Enable Formula",
                        value=bool(current_formula),
                        key=f"pc_custom_new_formula_enable_{loc_key}_{i}"
                    )
                    
                    if use_formula:
                        fc1, fc2 = st.columns([0.4, 0.6])
                        with fc1:
                            operation = st.selectbox(
                                "Operation",
                                ["sum", "subtract", "multiply", "divide", "percentage", "maximum", "minimum", "average"],
                                index=["sum", "subtract", "multiply", "divide", "percentage", "maximum", "minimum", "average"].index(current_formula.get("operation", "sum")),
                                key=f"pc_custom_new_formula_op_{loc_key}_{i}"
                            )
                        
                        with fc2:
                            available_cols = [(idx, c.get("name"), c.get("label"))
                                            for idx, c in enumerate(current_cols)
                                            if idx != i and c.get("type") != "date"]
                            
                            if not available_cols:
                                st.warning("No other numeric columns available for formula.")
                            else:
                                col_options = [f"{label} ({name})" for _, name, label in available_cols]
                                col_name_map = {f"{label} ({name})": name for _, name, label in available_cols}
                                
                                current_sel = current_formula.get("columns", [])
                                default_selection = [f"{current_cols[idx].get('label')} ({current_cols[idx].get('name')})"
                                                   for idx, c in enumerate(current_cols)
                                                   if c.get("name") in current_sel]
                                
                                selected_cols = st.multiselect(
                                    "Select Columns",
                                    col_options,
                                    default=default_selection,
                                    key=f"pc_custom_new_formula_cols_{loc_key}_{i}",
                                    help="Select columns to use in the calculation"
                                )
                                
                                selected_col_names = [col_name_map[sc] for sc in selected_cols]
                                
                                if selected_col_names:
                                    if operation == "sum":
                                        formula_preview = " + ".join(selected_col_names)
                                    elif operation == "subtract":
                                        formula_preview = " - ".join(selected_col_names)
                                    elif operation == "multiply":
                                        formula_preview = " × ".join(selected_col_names)
                                    elif operation == "divide":
                                        formula_preview = " ÷ ".join(selected_col_names)
                                    elif operation == "percentage":
                                        formula_preview = f"({selected_col_names[0]} ÷ {selected_col_names[1] if len(selected_col_names) > 1 else '?'}) × 100"
                                    elif operation == "maximum":
                                        formula_preview = f"MAX({', '.join(selected_col_names)})"
                                    elif operation == "minimum":
                                        formula_preview = f"MIN({', '.join(selected_col_names)})"
                                    elif operation == "average":
                                        formula_preview = f"AVG({', '.join(selected_col_names)})"
                                    
                                    st.code(f"Formula: {formula_preview}", language="text")
                                    
                                    current_cols[i]["formula"] = {
                                        "operation": operation,
                                        "columns": selected_col_names
                                    }
                                else:
                                    st.info("Select at least one column for the formula.")
                                    current_cols[i]["formula"] = None
                    else:
                        current_cols[i]["formula"] = None
            
            st.markdown("---")
        
        # Create button
        if st.button("✅ Create Custom Tab", type="primary", key=f"pc_custom_tab_create_{loc_key}"):
            if not new_tab_name or not new_tab_name.strip():
                st.error("Tab name is required.")
            elif not current_cols:
                st.error("At least one column is required.")
            else:
                try:
                    from location_config import add_custom_tab
                    from models import create_custom_tab_table
                    
                    with get_session() as s:
                        # Add tab configuration
                        new_tab = add_custom_tab(s, loc.id, target_page, new_tab_name, current_cols)
                        
                        # Create database table
                        table_created = create_custom_tab_table(
                            new_tab["table_name"],
                            current_cols,
                            loc.id
                        )
                        
                        if table_created:
                            try:
                                SecurityManager.log_audit(
                                    s, (user or {}).get("username", "system"), "CREATE",
                                    resource_type="PageCustomization:CustomTab",
                                    resource_id=new_tab["id"],
                                    details=f"Created custom tab '{new_tab_name}' with table '{new_tab['table_name']}'",
                                    user_id=(user or {}).get("id"),
                                    location_id=loc.id,
                                    success=True,
                                    ip_address=st.session_state.get("client_ip")
                                )
                            except Exception:
                                pass
                            
                            st.success(f"✅ Custom tab '{new_tab_name}' created successfully!")
                            st.info(f"📊 Database table: `{new_tab['table_name']}`")
                            
                            # Clear session state
                            if f"pc_custom_tab_columns_{loc_key}" in st.session_state:
                                del st.session_state[f"pc_custom_tab_columns_{loc_key}"]
                            
                            st.rerun()
                        else:
                            st.error("Failed to create database table for custom tab.")
                except ValueError as ve:
                    st.error(f"❌ {str(ve)}")
                except Exception as ex:
                    st.error(f"❌ Failed to create custom tab: {ex}")
    
    # ============================
    # 📍 YADE Tracking — Custom Tables & Filters (per location)
    # ==============================
    with st.expander("📍 YADE Tracking — Custom Tables & Filters (per location)", expanded=False):
        st.caption("Define tables, map columns to YADE data sources, and add filters.")
        _SRC_FIELDS = {
            "voyage.date": "Voyage Date",
            "voyage.convoy_no": "Convoy No",
            "voyage.yade_name": "Yade No",
            "voyage.loading_berth": "Loading Berth",
            "toa.before.nsv_bbl": "TOA Before NSV (bbl)",
            "toa.after.nsv_bbl": "TOA After NSV (bbl)",
        }
        _TARGET_KEYS = ["ASEMOKU", "NDONI", "AGGE"]

        with get_session() as s:
            yt_cfg = get_page_section_config(s, loc.id, page="yade_tracking", section="customization") or {}
        tables = list(yt_cfg.get("tables") or [])

        n_tables = st.number_input("Number of tables", min_value=1, max_value=6, value=max(2, len(tables) or 2), step=1, key=f"pc_yt_count_{loc_key}")
        if len(tables) < n_tables:
            for i in range(len(tables), n_tables):
                tables.append({
                    "id": f"t{i+1}",
                    "title": f"Table {i+1}",
                    "sources": ["ASEMOKU", "NDONI"] if i == 0 else ["AGGE"],
                    "columns": [
                        {"label": "Date", "source": "voyage.date"},
                        {"label": "Convoy No", "source": "voyage.convoy_no"},
                        {"label": "Yade No", "source": "voyage.yade_name"},
                        {"label": "ROB qty", "source": "toa.before.nsv_bbl"},
                        {"label": "TOB qty", "source": "toa.after.nsv_bbl"},
                        {"label": "Loading berth", "source": "voyage.loading_berth"},
                    ],
                    "filters": [
                        {"label": "Date", "source": "voyage.date"},
                        {"label": "Convoy No", "source": "voyage.convoy_no"},
                        {"label": "Yade No", "source": "voyage.yade_name"},
                        {"label": "Loading berth", "source": "voyage.loading_berth"},
                    ],
                })
        elif len(tables) > n_tables:
            tables = tables[:n_tables]

        for i in range(n_tables):
            t = tables[i]
            st.markdown(f"#### Table {i+1}")
            c1, c2 = st.columns([0.5, 0.5])
            with c1:
                t["title"] = st.text_input("Table Title", value=t.get("title", f"Table {i+1}"), key=f"pc_yt_title_{loc_key}_{i}")
            with c2:
                t["sources"] = st.multiselect("Data Sources (locations)", options=_TARGET_KEYS, default=[x for x in t.get("sources", []) if x in _TARGET_KEYS], key=f"pc_yt_src_{loc_key}_{i}")

            st.markdown("##### Columns")
            cols = list(t.get("columns") or [])
            n_cols = st.number_input("Columns", min_value=1, max_value=20, value=max(1, len(cols) or 6), step=1, key=f"pc_yt_cols_{loc_key}_{i}")
            if len(cols) < n_cols:
                for j in range(len(cols), n_cols):
                    cols.append({"label": f"Column {j+1}", "source": "voyage.date"})
            elif len(cols) > n_cols:
                cols = cols[:n_cols]
            for j in range(n_cols):
                cj = cols[j]
                e = st.columns([0.6, 0.4])
                with e[0]:
                    cj["label"] = st.text_input("Label", value=cj.get("label", f"Column {j+1}"), key=f"pc_yt_col_lbl_{loc_key}_{i}_{j}")
                with e[1]:
                    cj["source"] = st.selectbox("Source Field", options=list(_SRC_FIELDS.keys()), index=list(_SRC_FIELDS.keys()).index(cj.get("source", "voyage.date")), format_func=lambda k: _SRC_FIELDS[k], key=f"pc_yt_col_src_{loc_key}_{i}_{j}")
            t["columns"] = cols

            st.markdown("##### Filters")
            fltrs = list(t.get("filters") or [])
            n_fltrs = st.number_input("Filters", min_value=0, max_value=10, value=len(fltrs or []), step=1, key=f"pc_yt_fltrs_{loc_key}_{i}")
            if len(fltrs) < n_fltrs:
                for j in range(len(fltrs), n_fltrs):
                    fltrs.append({"label": f"Filter {j+1}", "source": "voyage.date"})
            elif len(fltrs) > n_fltrs:
                fltrs = fltrs[:n_fltrs]
            for j in range(n_fltrs):
                fj = fltrs[j]
                e = st.columns([0.6, 0.4])
                with e[0]:
                    fj["label"] = st.text_input("Label", value=fj.get("label", f"Filter {j+1}"), key=f"pc_yt_f_lbl_{loc_key}_{i}_{j}")
                with e[1]:
                    fj["source"] = st.selectbox("Source Field", options=list(_SRC_FIELDS.keys()), index=list(_SRC_FIELDS.keys()).index(fj.get("source", "voyage.date")), format_func=lambda k: _SRC_FIELDS[k], key=f"pc_yt_f_src_{loc_key}_{i}_{j}")
            t["filters"] = fltrs

            tables[i] = t

        if st.button("💾 Save YADE Tracking Customization", key=f"pc_yt_save_{loc_key}"):
            try:
                with get_session() as s:
                    set_page_section_config(s, loc.id, page="yade_tracking", section="customization", cfg={"tables": tables})
                st.success("YADE Tracking customization saved.")
                st.rerun()
            except Exception as ex:
                st.error(f"Save failed: {ex}")

    with st.expander("🗺️ Yade-Vessel Mapping — Tab Visibility", expanded=False):
        st.caption("Enable or disable the Mapping and Comparison tabs for this location.")
        with get_session() as s:
            cfg = LocationConfig.get_config(s, loc.id)
        tabs_access = (cfg.get("tabs_access", {}) or {}).get("Yade-Vessel Mapping", {}) or {}
        show_mapping = st.toggle(
            "Show Mapping tab",
            value=tabs_access.get("Mapping", True),
            key=f"pc_yvm_tab_map_{loc_key}",
        )
        show_comparison = st.toggle(
            "Show Comparison tab",
            value=tabs_access.get("Comparison", True),
            key=f"pc_yvm_tab_comp_{loc_key}",
        )
        if st.button("💾 Save Yade-Vessel Tabs", key=f"pc_yvm_tab_save_{loc_key}"):
            try:
                with get_session() as s:
                    fresh_cfg = LocationConfig.get_config(s, loc.id)
                    tabs = fresh_cfg.get("tabs_access", {}).copy()
                    yvm_tabs = tabs.get("Yade-Vessel Mapping", {}).copy()
                    yvm_tabs["Mapping"] = bool(show_mapping)
                    yvm_tabs["Comparison"] = bool(show_comparison)
                    tabs["Yade-Vessel Mapping"] = yvm_tabs
                    fresh_cfg["tabs_access"] = tabs
                    LocationConfig.save_config(s, loc.id, fresh_cfg)
                    try:
                        SecurityManager.log_audit(
                            s,
                            (user or {}).get("username", "system"),
                            "UPDATE",
                            resource_type="PageCustomization:YadeVesselTabs",
                            resource_id=str(loc.id),
                            details=f"Mapping={show_mapping}, Comparison={show_comparison}",
                            user_id=(user or {}).get("id"),
                            location_id=loc.id,
                            success=True,
                            ip_address=st.session_state.get("client_ip"),
                        )
                    except Exception:
                        pass
                st.success("Yade-Vessel Mapping tabs updated for this location.")
                st.rerun()
            except Exception as ex:
                st.error(f"Failed to update Yade-Vessel Mapping tabs: {ex}")

    # Manage existing custom tabs
    with st.expander("📋 Manage Existing Custom Tabs", expanded=True):
        st.markdown("### Existing Custom Tabs")
        
        from location_config import get_custom_tabs, delete_custom_tab, update_custom_tab
        
        # Show tabs for each page
        for page in ["tank_transactions", "tanker_transactions"]:
            page_display = "Tank Transactions" if page == "tank_transactions" else "Tanker Transactions"
            
            with get_session() as s:
                tabs = get_custom_tabs(s, loc.id, page)
            
            if tabs:
                st.markdown(f"#### {page_display}")
                
                for tab in tabs:
                    tab_id = tab.get("id")
                    tab_name = tab.get("name")
                    table_name = tab.get("table_name")
                    columns = tab.get("columns", [])
                    active = tab.get("active", True)
                    
                    with st.container():
                        col1, col2, col3 = st.columns([0.5, 0.3, 0.2])
                        
                        with col1:
                            status_icon = "✅" if active else "⏸️"
                            st.markdown(f"**{status_icon} {tab_name}**")
                            st.caption(f"Table: `{table_name}` | {len(columns)} columns")
                        
                        with col2:
                            # Toggle active status
                            if st.button(
                                "⏸️ Deactivate" if active else "▶️ Activate",
                                key=f"pc_custom_tab_toggle_{tab_id}"
                            ):
                                try:
                                    with get_session() as s:
                                        update_custom_tab(s, loc.id, page, tab_id, active=not active)
                                    st.success(f"Tab {'deactivated' if active else 'activated'}.")
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"Failed to update: {ex}")
                        
                        with col3:
                            # Delete tab
                            if st.button("🗑️ Delete", key=f"pc_custom_tab_delete_{tab_id}"):
                                try:
                                    from models import drop_custom_tab_table
                                    
                                    with get_session() as s:
                                        # Delete from config
                                        delete_custom_tab(s, loc.id, page, tab_id)
                                        
                                        # Try to drop table (optional - may want to keep data)
                                        # drop_custom_tab_table(table_name)
                                        
                                        try:
                                            SecurityManager.log_audit(
                                                s, (user or {}).get("username", "system"), "DELETE",
                                                resource_type="PageCustomization:CustomTab",
                                                resource_id=tab_id,
                                                details=f"Deleted custom tab '{tab_name}' (table: {table_name})",
                                                user_id=(user or {}).get("id"),
                                                location_id=loc.id,
                                                success=True,
                                                ip_address=st.session_state.get("client_ip")
                                            )
                                        except Exception:
                                            pass
                                    
                                    st.success(f"Tab '{tab_name}' deleted.")
                                    st.info("Note: Database table was preserved. Contact IT to drop the table if needed.")
                                    st.rerun()
                                except Exception as ex:
                                    st.error(f"Failed to delete: {ex}")
                        
                        # Show column details
                        with st.expander(f"View Columns for {tab_name}"):
                            for idx, col in enumerate(columns, 1):
                                formula_info = ""
                                if col.get("formula"):
                                    f = col["formula"]
                                    op = f.get("operation", "N/A")
                                    cols = ", ".join(f.get("columns", []))
                                    formula_info = f" — **Formula**: {op.upper()}({cols})"
                                
                                st.write(f"{idx}. `{col['name']}` — {col['label']} — *{col['type']}* — {'required' if col.get('required') else 'optional'}{formula_info}")
                        
                        st.markdown("---")
            else:
                st.info(f"No custom tabs defined for {page_display} yet.")
            
            st.markdown("---")

