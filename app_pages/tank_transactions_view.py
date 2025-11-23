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

    # Source filter
    src_col = st.columns([1])[0]
    with src_col:
        srcs = st.multiselect(
            "Sources",
            ["TankTx", "Meters", "Condensate", "Produced Water", "Production"],
            default=["TankTx", "Meters", "Condensate", "Produced Water", "Production"],
            key="vtv_sources"
        )

    # Free text search
    search = st.text_input("Search (ticket, tank name, remarks, etc.)", value="", key="vtv_search")

    # Load
    rows: List[Dict[str, Any]] = []
    with get_session() as s:
        if "TankTx" in srcs:
            rows += _load_tank_rows(s, active_location_id, d1, d2, created_by, search)

        # Map UI labels to flex sections
        flex_map = []
        if "Meters" in srcs:
            flex_map.append("meters")
        if "Condensate" in srcs:
            flex_map.append("condensate")
        if "Produced Water" in srcs:
            flex_map.append("produced_water")
        if "Production" in srcs:
            flex_map.append("production")

        rows += _load_flex_rows(s, active_location_id, flex_map, d1, d2, created_by, search)

    # If FlexibleRecord missing, hint
    if any(x in srcs for x in ["Meters","Condensate","Produced Water","Production"]) and _get_flexible_model() is None:
        st.info("`FlexibleRecord` model not found. Add it to `models.py` to see Meter/Condensate/PW/Production rows.")

    if not rows:
        st.warning("No records found for the selected filters.")
        return

    # DataFrame
    df = pd.DataFrame(rows, columns=[
        "Source","ID","Date","Time","Asset","Operation","GOV","GSV","NSV","MT","LT","Remarks","CreatedBy","CreatedAt"
    ])

    # Quick metrics summary
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1: st.metric("Count", len(df))
    with m2: st.metric("∑ GOV (bbl)", _sumfmt(df["GOV"]))
    with m3: st.metric("∑ GSV (bbl)", _sumfmt(df["GSV"]))
    with m4: st.metric("∑ NSV (bbl)", _sumfmt(df["NSV"]))
    with m5: st.metric("∑ MT", _sumfmt(df["MT"]))

    # Table + expanders
    st.markdown("#### Results")
    for r in rows:
        with st.expander(f"{r['Source']} • ID {r['ID']} • {r['Date']} {r['Time']} • {r['Asset']}"):
            _render_row_card(r)

    # Exports
    st.markdown("---")
    c1, c2 = st.columns([0.25, 0.75])
    with c1:
        st.markdown("#### Export")
    with c2:
        _export_bar(df)

    # audit view event (optional)
    try:
        SecurityManager.log_audit(
            None,
            (user or {}).get("username", "system"),
            "READ",
            resource_type="UnifiedView",
            resource_id=str(active_location_id),
            details=f"Viewed {len(df)} rows: filters src={srcs}, from={d1}, to={d2}, by={created_by}, q={search}",
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
