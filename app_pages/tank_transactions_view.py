# app_pages/tank_transactions_view.py
import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from db import get_session
from models import Location  # always present in your project
from security import SecurityManager

# ---------- Helpers: safe imports ----------
def _get_flexible_model():
    """
    Returns FlexibleRecord model if present.
    We used this in Meter/Condensate/ProducedWater/Production saves.
    """
    try:
        import models as m
        return getattr(m, "FlexibleRecord", None)
    except Exception:
        return None

def _get_tank_tx_model():
    try:
        import models as m
        # Your project uses TankTransaction in multiple files
        return getattr(m, "TankTransaction", None)
    except Exception:
        return None

def _detect_operation_enum_info(model_cls):
    """
    Returns (op_col_name, is_enum, allowed_values) for TankTransaction.operation-like columns.
    If column missing, returns (None, False, []).
    """
    try:
        # Try to find a real Column named 'operation'
        table_col = model_cls.__table__.columns.get("operation")
        if not table_col:
            return (None, False, [])
        # SQLAlchemy Enum columns usually expose .enums (list of allowed strings)
        enums = getattr(table_col.type, "enums", None)
        if isinstance(enums, (list, tuple)):
            return ("operation", True, list(enums))
        return ("operation", False, [])
    except Exception:
        return (None, False, [])

def _map_friendly_to_enum(friendly: str, allowed: list[str]) -> str | None:
    """
    Map a human label (e.g., 'Opening Stock') to one of the allowed enum values.
    Heuristics: normalize, then match direct/contains like OPEN, CLOS, RECEIPT, DISPATCH, DRAIN, SETTL.
    """
    if not friendly or not allowed:
        return None
    ftxt = friendly.upper()

    # exact match on normalized “OPENING_STOCK” style if present
    import re as _re
    normalized = _re.sub(r"[^A-Z0-9]+", "_", ftxt).strip("_")
    for a in allowed:
        if a.upper() == normalized:
            return a

    # buckets / keywords
    buckets = ("OPEN", "CLOS", "RECEIPT", "DISPATCH", "DRAIN", "SETTL")
    for needle in buckets:
        if needle in ftxt:
            for a in allowed:
                if needle in a.upper():
                    return a

    # final fallback: soft prefix match on normalized
    for a in allowed:
        if a.upper().startswith(normalized[:6]):
            return a

    return None

# ---------- Adapters: normalize to a common row ----------
# Target columns:
# ["Source","ID","Date","Time","Asset","Operation","GOV","GSV","NSV","MT","LT","Remarks","CreatedBy","CreatedAt"]

def _adapt_tank_tx_row(r) -> Dict[str, Any]:
    """Map TankTransaction ORM row to unified dict."""
    # Safe getattr with defaults
    g = lambda n, d=None: getattr(r, n, d)

    # Coerce date/time
    dt_val = g("date")
    tm_val = g("time")
    dt_str = str(dt_val) if dt_val else ""
    tm_str = tm_val.strftime("%H:%M") if tm_val else ""

    return {
        "Source": "TankTx",
        "ID": g("id"),
        "Date": dt_str,
        "Time": tm_str,
        "Asset": g("tank_name") or "Tank",
        "Operation": str(g("operation") or "") or "",
        "GOV": _f(g("gov_bbl")),
        "GSV": _f(g("gsv_bbl")),
        "NSV": _f(g("qty_bbls")),
        "MT": _f(g("mt")),
        "LT": _f(g("lt")),
        "Remarks": g("remarks") or "",
        "CreatedBy": g("created_by") or "",
        "CreatedAt": _dtstr(g("created_at")),
        "_raw": r,   # keep original row for expanders/actions
        "_payload": None,
        "_section": None,
    }

def _adapt_flex_row(r) -> Dict[str, Any]:
    """
    Map FlexibleRecord row to unified dict.
    We’ll infer numbers from its data_json for known sections.
    """
    g = lambda n, d=None: getattr(r, n, d)
    section = g("section", "")
    payload = {}
    try:
        payload = json.loads(g("data_json") or "{}")
    except Exception:
        payload = {}

    # Common values
    dt_val = g("tx_date")
    dt_str = str(dt_val) if dt_val else str(payload.get("date") or "")
    tm_str = ""  # these flexible sections typically don’t have time

    # Derive metrics by section
    gov = gsv = nsv = mt = lt = None
    asset = ""
    op = ""

    if section == "meters":
        # Meter tab saved: {"date": "...", "meters":[{..,"net_bbl":..},...], "net_total_bbl": ...}
        asset = "Meter"
        gov = payload.get("net_total_bbl")  # Net used as the transactional qty; treat as GOV for viewing
        # No temperature/BSW here; keep others blank
    elif section == "condensate":
        asset = "Condensate"
        gov = payload.get("gov_bbl")
        gsv = payload.get("gsv_bbl")
        nsv = payload.get("nsv_bbl")
        mt = payload.get("mt")
        lt = payload.get("lt")
    elif section == "produced_water":
        asset = "Produced Water"
        # Arbitrary columns; we don’t force GOV/GSV. Leave empty.
    elif section == "production":
        asset = "Production"
        # Arbitrary columns; leave blank unless you later define derived sums.

    return {
        "Source": f"Flex:{section or 'unknown'}",
        "ID": g("id"),
        "Date": dt_str,
        "Time": tm_str,
        "Asset": asset,
        "Operation": op,
        "GOV": _f(gov),
        "GSV": _f(gsv),
        "NSV": _f(nsv),
        "MT": _f(mt),
        "LT": _f(lt),
        "Remarks": payload.get("remarks") or g("remarks") or "",
        "CreatedBy": g("created_by") or "",
        "CreatedAt": _dtstr(g("created_at")),
        "_raw": r,
        "_payload": payload,
        "_section": section,
    }

def _f(x) -> Optional[float]:
    try:
        if x is None: return None
        return float(x)
    except Exception:
        return None

def _dtstr(x) -> str:
    try:
        if not x: return ""
        if isinstance(x, (datetime, )):
            return x.strftime("%Y-%m-%d %H:%M:%S")
        return str(x)
    except Exception:
        return ""

# ---------- Loaders ----------
def _load_tank_rows(session, location_id: int, d1: Optional[date], d2: Optional[date], created_by: str, search: str) -> List[Dict[str, Any]]:
    Mt = _get_tank_tx_model()
    if Mt is None:
        return []

    q = session.query(Mt).filter(getattr(Mt, "location_id") == location_id)

    if d1:
        q = q.filter(getattr(Mt, "date") >= d1)
    if d2:
        q = q.filter(getattr(Mt, "date") <= d2)

    if created_by:
        q = q.filter(getattr(Mt, "created_by").ilike(f"%{created_by}%"))

    # basic search across a few fields
    if search:
        like = f"%{search}%"
        try:
            q = q.filter(
                (getattr(Mt, "tank_name").ilike(like)) |
                (getattr(Mt, "ticket_id").ilike(like)) |
                (getattr(Mt, "remarks").ilike(like))
            )
        except Exception:
            pass

    try:
        q = q.order_by(getattr(Mt, "date").desc(), getattr(Mt, "id").desc())
    except Exception:
        pass

    return [_adapt_tank_tx_row(r) for r in q.all()]

def _load_flex_rows(session, location_id: int, sections: List[str], d1: Optional[date], d2: Optional[date], created_by: str, search: str) -> List[Dict[str, Any]]:
    Flex = _get_flexible_model()
    if Flex is None:
        return []

    q = session.query(Flex).filter(getattr(Flex, "location_id") == location_id)

    # page & sections
    q = q.filter(getattr(Flex, "page") == "tank_transactions")
    if sections:
        q = q.filter(getattr(Flex, "section").in_(sections))

    # date filter: use tx_date; if null, skip
    if d1:
        q = q.filter((getattr(Flex, "tx_date") >= d1) | (getattr(Flex, "tx_date") == None))
    if d2:
        q = q.filter((getattr(Flex, "tx_date") <= d2) | (getattr(Flex, "tx_date") == None))

    if created_by:
        q = q.filter(getattr(Flex, "created_by").ilike(f"%{created_by}%"))

    if search:
        like = f"%{search}%"
        try:
            q = q.filter(
                (getattr(Flex, "section").ilike(like)) |
                (getattr(Flex, "data_json").ilike(like)) |
                (getattr(Flex, "remarks").ilike(like))
            )
        except Exception:
            pass

    try:
        q = q.order_by(getattr(Flex, "tx_date").desc(), getattr(Flex, "id").desc())
    except Exception:
        pass

    return [_adapt_flex_row(r) for r in q.all()]

# ---------- UI ----------
def render_tank_transactions_view_page(active_location_id: Optional[int], user: Dict[str, Any]):
    st.markdown("### 🗂️ View Transactions")

    # Guard
    if not active_location_id:
        st.info("Select a location on **Home** to view records.")
        return

    # Show location label
    with get_session() as s:
        loc = s.query(Location).get(active_location_id)
    loc_label = f"{loc.name} ({loc.code})" if loc else f"ID={active_location_id}"
    st.caption(f"Active Location: **{loc_label}**")

    # Filters row
    col1, col2, col3 = st.columns([0.28, 0.28, 0.44])
    today = date.today()
    default_from = today - timedelta(days=30)
    with col1:
        d1 = st.date_input("From", value=default_from, key="vtv_from")
    with col2:
        d2 = st.date_input("To", value=today, key="vtv_to")
    with col3:
        created_by = st.text_input("Created By (contains)", value="", key="vtv_created_by")

    # Load custom tabs
    custom_tabs = []
    try:
        from location_config import get_custom_tabs
        with get_session() as s:
            custom_tabs = get_custom_tabs(s, active_location_id, "tank_transactions")
            custom_tabs = [t for t in custom_tabs if t.get("active", True)]
    except Exception:
        pass

    # Source filter - include custom tabs
    source_options = ["TankTx", "Meters", "Condensate", "Produced Water", "Production"]
    for ctab in custom_tabs:
        source_options.append(ctab.get("name", "Custom"))
    
    src_col = st.columns([1])[0]
    with src_col:
        srcs = st.multiselect(
            "Sources",
            source_options,
            default=source_options,  # Default all selected
            key="vtv_sources"
        )

    # Free text search
    search = st.text_input("Search (ticket, tank name, remarks, etc.)", value="", key="vtv_search")

    # Use tabs to organize different data sources
    tab_labels = []
    if "TankTx" in srcs:
        tab_labels.append("Tank Transactions")
    if "Meters" in srcs:
        tab_labels.append("Meters")
    if "Condensate" in srcs:
        tab_labels.append("Condensate")
    if "Produced Water" in srcs:
        tab_labels.append("Produced Water")
    if "Production" in srcs:
        tab_labels.append("Production")
    
    # Add custom tabs that are selected
    for ctab in custom_tabs:
        if ctab.get("name") in srcs:
            tab_labels.append(ctab.get("name"))
    
    if not tab_labels:
        st.warning("No sources selected. Please select at least one source from the filter above.")
        return
    
    tabs = st.tabs(tab_labels)
    
    tab_idx = 0
    
    # Tank Transactions Tab
    if "TankTx" in srcs:
        with tabs[tab_idx]:
            _render_tank_tx_tab(active_location_id, d1, d2, created_by, search, user)
        tab_idx += 1
    
    # Meters Tab
    if "Meters" in srcs:
        with tabs[tab_idx]:
            _render_flexible_tab(active_location_id, "meters", "Meter Records", d1, d2, created_by, search, user)
        tab_idx += 1
    
    # Condensate Tab
    if "Condensate" in srcs:
        with tabs[tab_idx]:
            _render_flexible_tab(active_location_id, "condensate", "Condensate Records", d1, d2, created_by, search, user)
        tab_idx += 1
    
    # Produced Water Tab
    if "Produced Water" in srcs:
        with tabs[tab_idx]:
            _render_flexible_tab(active_location_id, "produced_water", "Produced Water Records", d1, d2, created_by, search, user)
        tab_idx += 1
    
    # Production Tab
    if "Production" in srcs:
        with tabs[tab_idx]:
            _render_flexible_tab(active_location_id, "production", "Production Records", d1, d2, created_by, search, user)
        tab_idx += 1
    
    # Custom Tabs
    for ctab in custom_tabs:
        if ctab.get("name") in srcs:
            with tabs[tab_idx]:
                _render_custom_tab_data(active_location_id, ctab, d1, d2, created_by, search, user)
            tab_idx += 1
    
    # audit view event (optional)
    try:
        SecurityManager.log_audit(
            None,
            (user or {}).get("username", "system"),
            "READ",
            resource_type="UnifiedView",
            resource_id=str(active_location_id),
            details=f"Viewed transactions: filters src={srcs}, from={d1}, to={d2}, by={created_by}, q={search}",
            user_id=(user or {}).get("id"),
            location_id=active_location_id,
            ip_address=st.session_state.get("client_ip"),
            success=True,
        )
    except Exception:
        pass


# ---------- Row card / summary ----------
def _render_row_card(r: Dict[str, Any]):
    cols = st.columns([0.20, 0.20, 0.20, 0.20, 0.20])
    with cols[0]: st.write(f"**Source:** {r['Source']}")
    with cols[1]: st.write(f"**Asset:** {r['Asset'] or ''}")
    with cols[2]: st.write(f"**Operation:** {r['Operation'] or ''}")
    with cols[3]: st.write(f"**GOV (bbl):** {nf(r['GOV'])}")
    with cols[4]: st.write(f"**NSV (bbl):** {nf(r['NSV'])}")

    cols2 = st.columns([0.20, 0.20, 0.20, 0.40])
    with cols2[0]: st.write(f"**GSV (bbl):** {nf(r['GSV'])}")
    with cols2[1]: st.write(f"**MT:** {nf(r['MT'])}")
    with cols2[2]: st.write(f"**LT:** {nf(r['LT'])}")
    with cols2[3]: st.write(f"**Remarks:** {r['Remarks'] or ''}")

    st.caption(f"Created By: **{r['CreatedBy'] or ''}**  •  Created At: **{r['CreatedAt'] or ''}**")

    # Show raw payload if flexible
    if r.get("Source","").startswith("Flex"):
        st.markdown("**Raw Payload**")
        st.code(json.dumps(r.get("_payload") or {}, indent=2, ensure_ascii=False))


# ---------- Exports ----------
def _export_bar(df: pd.DataFrame):
    # CSV
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ CSV", data=csv, file_name="transactions_view.csv", mime="text/csv")

    # Excel
    try:
        import io
        import xlsxwriter
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Transactions")
        st.download_button("⬇️ Excel", data=bio.getvalue(), file_name="transactions_view.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as ex:
        st.info(f"Excel export unavailable: {ex}")


# ---------- number helpers ----------
def nf(x: Any) -> str:
    try:
        if x is None: return ""
        return f"{float(x):,.2f}"
    except Exception:
        return ""

def _sumfmt(series: pd.Series) -> str:
    try:
        return f"{pd.to_numeric(series, errors='coerce').fillna(0).sum():,.2f}"
    except Exception:
        return "0.00"


# ---------- Tab Renderers ----------
def _render_tank_tx_tab(location_id: int, date_from, date_to, created_by_filter, search_text, user):
    """Render Tank Transactions tab with table view"""
    st.markdown("#### Tank Transactions")
    
    rows = []
    with get_session() as s:
        rows = _load_tank_rows(s, location_id, date_from, date_to, created_by_filter, search_text)
    
    if not rows:
        st.info("No tank transactions found for the selected filters.")
        return
    
    # Display metrics
    df = pd.DataFrame(rows)
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Records", len(df))
    with m2:
        if "GSV" in df.columns:
            st.metric("Total GSV (bbl)", _sumfmt(df["GSV"]))
    with m3:
        if "NSV" in df.columns:
            st.metric("Total NSV (bbl)", _sumfmt(df["NSV"]))
    with m4:
        if "MT" in df.columns:
            st.metric("Total MT", _sumfmt(df["MT"]))
    
    st.markdown("---")
    
    # Display as expandable cards with details
    for row in rows:
        with st.expander(f"ID {row['ID']} • {row['Date']} {row['Time']} • {row['Asset']}"):
            _render_row_card(row)


def _render_flexible_tab(location_id: int, section: str, title: str, date_from, date_to, created_by_filter, search_text, user):
    st.markdown(f"#### {title}")
    
    table_name = f"flex_{section}_{location_id}"
    try:
        from models import get_custom_table_model
        CustomModel = get_custom_table_model(table_name)
    except Exception:
        CustomModel = None
    
    if CustomModel:
        with get_session() as s:
            from sqlalchemy import or_
            query = s.query(CustomModel).filter(CustomModel.location_id == location_id)
            if date_from and hasattr(CustomModel, "tx_date"):
                query = query.filter(or_(CustomModel.tx_date >= date_from, CustomModel.tx_date == None))
            if date_to and hasattr(CustomModel, "tx_date"):
                query = query.filter(or_(CustomModel.tx_date <= date_to, CustomModel.tx_date == None))
            if created_by_filter and hasattr(CustomModel, "created_by"):
                query = query.filter(CustomModel.created_by.contains(created_by_filter))
            records = query.order_by(getattr(CustomModel, "id").desc()).all()
        if not records:
            st.info(f"No {title.lower()} found for the selected filters.")
            return
        st.metric("Total Records", len(records))
        st.markdown("---")
        cols = [c.name for c in CustomModel.__table__.columns]
        reserved = {"id","location_id","tx_date","created_by","created_at","updated_by","updated_at"}
        data_cols = [c for c in cols if c not in reserved]
        table_data = []
        for rec in records:
            row = {
                "ID": getattr(rec, "id", ""),
                "Date": str(getattr(rec, "tx_date", "")) if hasattr(rec, "tx_date") else "",
                "Created By": getattr(rec, "created_by", "") or "",
                "Created At": getattr(rec, "created_at").strftime("%Y-%m-%d %H:%M") if hasattr(rec, "created_at") and getattr(rec, "created_at") else "",
            }
            for c in data_cols:
                v = getattr(rec, c, None)
                if v is None:
                    row[c] = ""
                else:
                    try:
                        row[c] = f"{float(v):.2f}"
                    except Exception:
                        row[c] = str(v)
            table_data.append(row)
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True)
        st.markdown("---")
        st.markdown("##### Actions")
        for rec in records:
            col1, col2 = st.columns([0.7, 0.3])
            with col1:
                st.text(f"ID {getattr(rec,'id','')} • {getattr(rec,'tx_date', '') or 'No date'}")
            with col2:
                st.caption(f"By: {getattr(rec,'created_by','') or 'Unknown'}")
        return
    
    FlexModel = _get_flexible_model()
    if not FlexModel:
        st.info(f"`FlexibleRecord` model not found. Cannot display {title}.")
        return
    
    with get_session() as s:
        query = s.query(FlexModel).filter(
            FlexModel.location_id == location_id,
            FlexModel.page == "tank_transactions",
            FlexModel.section == section
        )
        if date_from:
            query = query.filter(FlexModel.tx_date >= date_from)
        if date_to:
            query = query.filter(FlexModel.tx_date <= date_to)
        if created_by_filter:
            query = query.filter(FlexModel.created_by.contains(created_by_filter))
        records = query.order_by(FlexModel.created_at.desc()).all()
    if not records:
        st.info(f"No {title.lower()} found for the selected filters.")
        return
    st.metric("Total Records", len(records))
    st.markdown("---")
    table_data = []
    for rec in records:
        try:
            data = json.loads(rec.data_json) if rec.data_json else {}
            row_dict = {
                "ID": rec.id,
                "Date": str(rec.tx_date) if rec.tx_date else "",
                "Created By": rec.created_by or "",
                "Created At": rec.created_at.strftime("%Y-%m-%d %H:%M") if rec.created_at else "",
                **data
            }
            table_data.append(row_dict)
        except Exception:
            continue
    if table_data:
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True)
        st.markdown("---")
        st.markdown("##### Actions")
        for i, rec in enumerate(records):
            col1, col2, col3, col4 = st.columns([0.5, 0.2, 0.15, 0.15])
            with col1:
                data = json.loads(rec.data_json) if rec.data_json else {}
                st.text(f"ID {rec.id} • {rec.tx_date or 'No date'}")
            with col2:
                st.caption(f"By: {rec.created_by or 'Unknown'}")
            with col3:
                if st.button("✏️ Edit", key=f"edit_flex_{section}_{rec.id}"):
                    st.session_state[f"editing_flex_{section}_{rec.id}"] = True
                    st.rerun()
            with col4:
                if st.button("🗑️", key=f"delete_flex_{section}_{rec.id}"):
                    st.session_state[f"deleting_flex_{section}_{rec.id}"] = True
                    st.rerun()
            if st.session_state.get(f"editing_flex_{section}_{rec.id}"):
                _render_flex_edit_modal(rec, section, title, user)
            if st.session_state.get(f"deleting_flex_{section}_{rec.id}"):
                _render_flex_delete_confirmation(rec, section, title, user)


def _render_custom_tab_data(location_id: int, tab_def: dict, date_from, date_to, created_by_filter, search_text, user):
    """Render custom tab data with full table, edit, and delete functionality"""
    from models import get_custom_table_model
    
    tab_name = tab_def.get("name", "Custom Tab")
    table_name = tab_def.get("table_name")
    columns = tab_def.get("columns", [])
    
    st.markdown(f"#### {tab_name}")
    
    if not table_name:
        st.error("No table name defined for this custom tab.")
        return
    
    CustomModel = get_custom_table_model(table_name)
    if not CustomModel:
        st.error(f"Database table `{table_name}` not found.")
        return
    
    # Load data
    with get_session() as s:
        query = s.query(CustomModel).filter(CustomModel.location_id == location_id)
        
        if date_from and hasattr(CustomModel, 'tx_date'):
            query = query.filter(CustomModel.tx_date >= date_from)
        if date_to and hasattr(CustomModel, 'tx_date'):
            query = query.filter(CustomModel.tx_date <= date_to)
        if created_by_filter and hasattr(CustomModel, 'created_by'):
            query = query.filter(CustomModel.created_by.contains(created_by_filter))
        
        # Apply search filter across all text columns
        if search_text:
            search_filters = []
            for col in columns:
                col_name = col.get("name")
                if col_name and hasattr(CustomModel, col_name):
                    col_obj = getattr(CustomModel, col_name)
                    if col.get("type") == "text":
                        search_filters.append(col_obj.contains(search_text))
            if search_filters:
                from sqlalchemy import or_
                query = query.filter(or_(*search_filters))
        
        records = query.order_by(CustomModel.id.desc()).all()
    
    if not records:
        st.info(f"No records found for {tab_name}.")
        return
    
    st.metric("Total Records", len(records))
    st.markdown("---")
    
    # Prepare table data
    table_data = []
    for rec in records:
        row_dict = {
            "ID": getattr(rec, "id", ""),
            "Date": str(getattr(rec, "tx_date", "")) if hasattr(rec, "tx_date") else "",
            "Created By": getattr(rec, "created_by", "") or "",
            "Created At": getattr(rec, "created_at").strftime("%Y-%m-%d %H:%M") if hasattr(rec, "created_at") and getattr(rec, "created_at") else "",
        }
        
        # Add custom columns
        for col in columns:
            col_name = col.get("name")
            col_label = col.get("label", col_name)
            if col_name and hasattr(rec, col_name):
                value = getattr(rec, col_name)
                if col.get("type") == "number" and value is not None:
                    row_dict[col_label] = f"{float(value):.2f}"
                elif col.get("type") == "date" and value:
                    row_dict[col_label] = str(value)
                else:
                    row_dict[col_label] = value or ""
            else:
                row_dict[col_label] = ""
        
        table_data.append(row_dict)
    
    # Display table with action buttons
    if table_data:
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, height=400)
        
        # Export buttons
        st.markdown("---")
        col1, col2 = st.columns([0.2, 0.8])
        with col1:
            st.markdown("**Export:**")
        with col2:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download CSV",
                data=csv,
                file_name=f"{tab_name.lower().replace(' ', '_')}_data.csv",
                mime="text/csv"
            )
        
        st.markdown("---")
        st.markdown("##### 📝 Actions")
        st.markdown("Select a record to edit or delete:")
        st.markdown("")
        
        # Create a cleaner table view with action buttons
        for idx, rec in enumerate(records):
            rec_id = getattr(rec, "id")
            tx_date = getattr(rec, "tx_date", None) if hasattr(rec, "tx_date") else None
            created_by = getattr(rec, "created_by", "") if hasattr(rec, "created_by") else ""
            created_at = getattr(rec, "created_at", None) if hasattr(rec, "created_at") else None
            updated_at = getattr(rec, "updated_at", None) if hasattr(rec, "updated_at") else None
            
            # Show summary data from custom columns
            summary_parts = [f"ID {rec_id}"]
            if tx_date:
                summary_parts.append(str(tx_date))
            
            # Add first 2 custom column values as preview
            preview_count = 0
            for col in columns[:3]:
                col_name = col.get("name")
                col_label = col.get("label", col_name)
                if col_name and hasattr(rec, col_name) and preview_count < 2:
                    value = getattr(rec, col_name)
                    if value is not None:
                        if col.get("type") == "number":
                            summary_parts.append(f"{col_label}: {float(value):.2f}")
                        else:
                            summary_parts.append(f"{col_label}: {value}")
                        preview_count += 1
            
            summary = " • ".join(summary_parts)
            
            col1, col2, col3, col4 = st.columns([0.50, 0.25, 0.125, 0.125])
            
            with col1:
                edit_indicator = " ⚠️" if updated_at else ""
                st.text(f"{summary}{edit_indicator}")
            
            with col2:
                created_str = created_at.strftime("%Y-%m-%d %H:%M") if created_at else "Unknown"
                st.caption(f"By: {created_by or 'Unknown'} • {created_str}")
            
            with col3:
                if st.button("✏️ Edit", key=f"edit_custom_{table_name}_{rec_id}"):
                    st.session_state[f"editing_custom_{table_name}_{rec_id}"] = True
                    st.rerun()
            
            with col4:
                if st.button("🗑️ Delete", key=f"delete_custom_{table_name}_{rec_id}"):
                    st.session_state[f"deleting_custom_{table_name}_{rec_id}"] = True
                    st.rerun()
            
            # Edit modal
            if st.session_state.get(f"editing_custom_{table_name}_{rec_id}"):
                _render_custom_edit_modal(rec, tab_def, user)
            
            # Delete confirmation
            if st.session_state.get(f"deleting_custom_{table_name}_{rec_id}"):
                _render_custom_delete_confirmation(rec, tab_def, user)
            
            st.markdown("---")


def _render_flex_edit_modal(record, section: str, title: str, user):
    """Modal for editing FlexibleRecord"""
    st.markdown(f"### ✏️ Edit {title} Record (ID: {record.id})")
    
    try:
        data = json.loads(record.data_json) if record.data_json else {}
    except Exception:
        data = {}
    
    with st.form(key=f"edit_flex_form_{section}_{record.id}"):
        st.caption(f"**Created by:** {record.created_by or 'Unknown'} on {record.created_at.strftime('%Y-%m-%d %H:%M') if record.created_at else 'Unknown'}")
        
        # Editable fields (simplified - show JSON editor)
        edited_json = st.text_area("Data (JSON)", value=json.dumps(data, indent=2), height=200)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("💾 Save Changes", type="primary"):
                try:
                    new_data = json.loads(edited_json)
                    with get_session() as s:
                        rec = s.query(_get_flexible_model()).get(record.id)
                        if rec:
                            rec.data_json = json.dumps(new_data)
                            s.commit()
                            
                            # Audit log
                            try:
                                SecurityManager.log_audit(
                                    s, user.get("username", "system"), "UPDATE",
                                    resource_type=f"FlexibleRecord:{section}",
                                    resource_id=str(record.id),
                                    details=f"Edited {title} record",
                                    user_id=user.get("id"),
                                    location_id=record.location_id,
                                    ip_address=st.session_state.get("client_ip"),
                                    success=True
                                )
                            except Exception:
                                pass
                            
                            st.success("✅ Record updated successfully!")
                            del st.session_state[f"editing_flex_{section}_{record.id}"]
                            st.rerun()
                except Exception as ex:
                    st.error(f"Failed to update: {ex}")
        
        with col2:
            if st.form_submit_button("❌ Cancel"):
                del st.session_state[f"editing_flex_{section}_{record.id}"]
                st.rerun()


def _render_flex_delete_confirmation(record, section: str, title: str, user):
    """Confirmation dialog for deleting FlexibleRecord"""
    st.warning(f"⚠️ Are you sure you want to delete {title} record ID {record.id}?")
    st.caption("This action cannot be undone.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Confirm Delete", key=f"confirm_delete_flex_{section}_{record.id}", type="primary"):
            try:
                with get_session() as s:
                    rec = s.query(_get_flexible_model()).get(record.id)
                    if rec:
                        # Audit log before deleting
                        try:
                            SecurityManager.log_audit(
                                s, user.get("username", "system"), "DELETE",
                                resource_type=f"FlexibleRecord:{section}",
                                resource_id=str(record.id),
                                details=f"Deleted {title} record",
                                user_id=user.get("id"),
                                location_id=record.location_id,
                                ip_address=st.session_state.get("client_ip"),
                                success=True
                            )
                        except Exception:
                            pass
                        
                        s.delete(rec)
                        s.commit()
                        
                        st.success("✅ Record deleted successfully!")
                        del st.session_state[f"deleting_flex_{section}_{record.id}"]
                        st.rerun()
            except Exception as ex:
                st.error(f"Failed to delete: {ex}")
    
    with col2:
        if st.button("❌ Cancel", key=f"cancel_delete_flex_{section}_{record.id}"):
            del st.session_state[f"deleting_flex_{section}_{record.id}"]
            st.rerun()


def _render_custom_edit_modal(record, tab_def: dict, user):
    """Modal for editing custom tab record"""
    from models import get_custom_table_model
    from datetime import datetime as dt
    
    tab_name = tab_def.get("name", "Custom Tab")
    table_name = tab_def.get("table_name")
    columns = tab_def.get("columns", [])
    rec_id = getattr(record, "id")
    
    st.markdown(f"### ✏️ Edit {tab_name} Record (ID: {rec_id})")
    
    created_by = getattr(record, "created_by", "") if hasattr(record, "created_by") else ""
    created_at = getattr(record, "created_at", None) if hasattr(record, "created_at") else None
    updated_at = getattr(record, "updated_at", None) if hasattr(record, "updated_at") else None
    
    if updated_at:
        st.warning(f"⚠️ This record was last edited on {updated_at.strftime('%Y-%m-%d %H:%M')}")
    
    st.caption(f"**Created by:** {created_by or 'Unknown'} on {created_at.strftime('%Y-%m-%d %H:%M') if created_at else 'Unknown'}")
    
    with st.form(key=f"edit_custom_form_{table_name}_{rec_id}"):
        edited_values = {}
        
        # Separate manual and calculated columns
        manual_columns = [c for c in columns if not c.get("formula")]
        calculated_columns = [c for c in columns if c.get("formula")]
        
        # Render editable fields
        for col in manual_columns:
            col_name = col.get("name")
            col_label = col.get("label", col_name)
            col_type = col.get("type", "text")
            current_value = getattr(record, col_name, None) if hasattr(record, col_name) else None
            
            if col_type == "date":
                edited_values[col_name] = st.date_input(col_label, value=current_value, key=f"edit_{table_name}_{rec_id}_{col_name}")
            elif col_type == "number":
                edited_values[col_name] = st.number_input(col_label, value=float(current_value) if current_value is not None else 0.0, step=0.01, format="%.2f", key=f"edit_{table_name}_{rec_id}_{col_name}")
            else:
                edited_values[col_name] = st.text_input(col_label, value=str(current_value) if current_value else "", key=f"edit_{table_name}_{rec_id}_{col_name}")
        
        # Recalculate formulas
        if calculated_columns:
            st.markdown("##### 🧮 Calculated Columns (Auto-updated)")
            from tank_transactions import _evaluate_formula
            
            for calc_col in calculated_columns:
                formula = calc_col.get("formula")
                col_label = calc_col.get("label", calc_col.get("name"))
                col_name = calc_col.get("name")
                
                calculated_value = _evaluate_formula(formula, edited_values)
                if calculated_value is not None:
                    st.metric(col_label, f"{calculated_value:.2f}")
                    edited_values[col_name] = calculated_value
                else:
                    edited_values[col_name] = None
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("💾 Save Changes", type="primary"):
                try:
                    CustomModel = get_custom_table_model(table_name)
                    with get_session() as s:
                        rec = s.query(CustomModel).get(rec_id)
                        if rec:
                            # Update fields
                            for col_name, value in edited_values.items():
                                if hasattr(rec, col_name):
                                    setattr(rec, col_name, value)
                            
                            # Set updated_at timestamp
                            if hasattr(rec, "updated_at"):
                                setattr(rec, "updated_at", dt.now())
                            
                            s.commit()
                            
                            # Audit log
                            try:
                                SecurityManager.log_audit(
                                    s, user.get("username", "system"), "UPDATE",
                                    resource_type=f"CustomTab:{tab_name}",
                                    resource_id=str(rec_id),
                                    details=f"Edited {tab_name} record. Updated by {user.get('username')} at {dt.now().strftime('%Y-%m-%d %H:%M')}",
                                    user_id=user.get("id"),
                                    location_id=getattr(record, "location_id"),
                                    ip_address=st.session_state.get("client_ip"),
                                    success=True
                                )
                            except Exception:
                                pass
                            
                            st.success(f"✅ {tab_name} record updated successfully!")
                            del st.session_state[f"editing_custom_{table_name}_{rec_id}"]
                            st.rerun()
                except Exception as ex:
                    st.error(f"Failed to update: {ex}")
        
        with col2:
            if st.form_submit_button("❌ Cancel"):
                del st.session_state[f"editing_custom_{table_name}_{rec_id}"]
                st.rerun()


def _render_custom_delete_confirmation(record, tab_def: dict, user):
    """Confirmation dialog for deleting custom tab record"""
    from models import get_custom_table_model
    
    tab_name = tab_def.get("name", "Custom Tab")
    table_name = tab_def.get("table_name")
    rec_id = getattr(record, "id")
    
    st.warning(f"⚠️ Are you sure you want to delete {tab_name} record ID {rec_id}?")
    st.caption("This action cannot be undone.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Confirm Delete", key=f"confirm_delete_custom_{table_name}_{rec_id}", type="primary"):
            try:
                CustomModel = get_custom_table_model(table_name)
                with get_session() as s:
                    rec = s.query(CustomModel).get(rec_id)
                    if rec:
                        location_id = getattr(rec, "location_id")
                        
                        # Audit log before deleting
                        try:
                            SecurityManager.log_audit(
                                s, user.get("username", "system"), "DELETE",
                                resource_type=f"CustomTab:{tab_name}",
                                resource_id=str(rec_id),
                                details=f"Deleted {tab_name} record",
                                user_id=user.get("id"),
                                location_id=location_id,
                                ip_address=st.session_state.get("client_ip"),
                                success=True
                            )
                        except Exception:
                            pass
                        
                        s.delete(rec)
                        s.commit()
                        
                        st.success(f"✅ {tab_name} record deleted successfully!")
                        del st.session_state[f"deleting_custom_{table_name}_{rec_id}"]
                        st.rerun()
            except Exception as ex:
                st.error(f"Failed to delete: {ex}")
    
    with col2:
        if st.button("❌ Cancel", key=f"cancel_delete_custom_{table_name}_{rec_id}"):
            del st.session_state[f"deleting_custom_{table_name}_{rec_id}"]
            st.rerun()
