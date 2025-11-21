# app_pages/tank_transactions_view.py
import streamlit as st
from datetime import date, timedelta
import pandas as pd

from db import get_session
from models import Location
import models as db_models
from security import SecurityManager

# --- PDF imports ---
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

try:
    from permission_manager import PermissionManager
except Exception:
    PermissionManager = None

try:
    from location_config import get_location_page_visibility
except Exception:
    get_location_page_visibility = None


def _guard_location(active_location_id):
    if not active_location_id:
        st.warning("No active location is selected. Go to **Home** and select a location first.")
        return None, None
    with get_session() as session:
        loc = session.query(Location).get(active_location_id)
        if not loc:
            st.warning("Selected location was not found. Please re-select from **Home**.")
            return None, None
        return loc, f"{loc.name} ({loc.code})"


def _guard_permissions(user, active_location_id) -> bool:
    role = (user or {}).get("role", "")
    if PermissionManager and user:
        if not PermissionManager.can_access_operational_pages(user):
            st.error(f"Your role **{role}** cannot access operational pages.")
            return False
    if get_location_page_visibility and active_location_id:
        try:
            with get_session() as session:
                flags = get_location_page_visibility(session, active_location_id) or {}
            if not flags.get("show_tank_transactions", True):
                st.error("Tank Transactions are disabled for this location (see **Location Settings**).")
                return False
        except Exception:
            pass
    return True


def _get_tx_model():
    for name in ("TankTransaction", "TankTransactions", "TankTxn", "Tank_Transaction"):
        model = getattr(db_models, name, None)
        if model is not None:
            return model
    return None


def _fetch_transactions(session, location_id: int, d_from: date, d_to: date):
    Tx = _get_tx_model()
    if Tx is None:
        return [], "TankTransaction model not found in models.py."

    # find date field
    date_field = None
    for cand in ("tx_date", "date", "txn_date", "entry_date"):
        if hasattr(Tx, cand):
            date_field = getattr(Tx, cand)
            break
    if date_field is None:
        return [], "No date column on TankTransaction (expect tx_date/date/txn_date/entry_date)."

    loc_field = getattr(Tx, "location_id", None)
    if loc_field is None:
        return [], "No location_id on TankTransaction."

    q = (
        session.query(Tx)
        .filter(loc_field == location_id)
        .filter(date_field >= d_from)
        .filter(date_field <= d_to)
    )
    try:
        q = q.order_by(date_field.desc(), getattr(Tx, "id").desc())
    except Exception:
        pass
    return q.all(), None


def _rows_to_dataframe(rows):
    data = []
    for r in rows:
        get = lambda *names, default=None: next((getattr(r, n) for n in names if hasattr(r, n)), default)
        data.append(
            {
                "ID": get("id"),
                "Date": get("tx_date", "date", "txn_date", "entry_date"),
                "Tank": get("tank_name") or get("tank_code") or get("tank", "tank_id"),
                "Movement": get("movement_type", "movement", "type"),
                "Volume (bbl)": get("volume_bbl", "bbl", "volume", "qty_bbl", default=0.0),
                "Remarks": get("remarks", "note", "notes"),
                "Created By": get("created_by", "entered_by", "user"),
                "Created At": get("created_at", "timestamp"),
            }
        )
    df = pd.DataFrame(data)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    if "Created At" in df.columns:
        df["Created At"] = pd.to_datetime(df["Created At"], errors="coerce")
    return df


def _export_buttons(df: pd.DataFrame, filename_prefix: str = "tank_transactions"):
    if df.empty:
        return
    csv_data = df.to_csv(index=False).encode("utf-8")

    # Excel as bytes
    from io import BytesIO
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Transactions", index=False)
    xlsx_bytes = bio.getvalue()

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "📊 Download Excel",
            data=xlsx_bytes,
            file_name=f"{filename_prefix}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with c2:
        st.download_button(
            "📄 Download CSV",
            data=csv_data,
            file_name=f"{filename_prefix}.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ---------- PDF builder ----------

def _df_to_pdf_bytes(df: pd.DataFrame, loc_label: str, d_from: date, d_to: date, username: str = "") -> bytes:
    """
    Build an A4 portrait PDF with ~0.5 cm margins listing the transactions.
    Conventional header + zebra table.
    """
    # Trim/arrange columns
    want_cols = ["ID", "Date", "Tank", "Movement", "Volume (bbl)", "Remarks", "Created By", "Created At"]
    cols = [c for c in want_cols if c in df.columns]
    df2 = df[cols].copy()

    # Format values & trim long remarks
    def _fmt(v):
        if pd.isna(v):
            return ""
        return str(v)
    if "Remarks" in df2.columns:
        df2["Remarks"] = df2["Remarks"].apply(
            lambda x: (_fmt(x)[:120] + "…") if _fmt(x) and len(_fmt(x)) > 120 else _fmt(x)
        )

    title = "View Tank Transactions"
    sub = f"{loc_label} — {d_from.isoformat()} to {d_to.isoformat()}"
    gen = f"Generated by: {username or 'N/A'}"

    bio = BytesIO()
    doc = SimpleDocTemplate(
        bio,
        pagesize=A4,
        leftMargin=0.5 * cm,
        rightMargin=0.5 * cm,
        topMargin=0.5 * cm,
        bottomMargin=0.5 * cm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleC", parent=styles["Title"], alignment=TA_CENTER, spaceAfter=6))
    styles.add(ParagraphStyle(name="SubC", parent=styles["Normal"], alignment=TA_CENTER, textColor=colors.grey, spaceAfter=6))

    elems = [
        Paragraph(title, styles["TitleC"]),
        Paragraph(sub, styles["SubC"]),
        Paragraph(gen, styles["SubC"]),
        Spacer(0, 6),
    ]

    data = [cols] + df2.fillna("").astype(str).values.tolist()
    tbl = Table(data, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#eeeeee")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.black),
        ("ALIGN", (0,0), (-1,0), "CENTER"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 9),

        ("FONTSIZE", (0,1), (-1,-1), 8),
        ("ALIGN", (0,1), (-1,-1), "LEFT"),
        ("VALIGN", (0,0), (-1,-1), "TOP"),

        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#fafafa")]),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))

    elems.append(tbl)
    doc.build(elems)
    return bio.getvalue()


def render_tank_transactions_view_page(active_location_id, user):
    """Read-only viewer page for saved tank transactions."""
    st.markdown("### 🗂️ View Tank Transactions")

    loc, loc_label = _guard_location(active_location_id)
    if not loc:
        return
    if not _guard_permissions(user, active_location_id):
        return

    st.caption(f"Active Location: **{loc_label}**")

    # Date range
    today = date.today()
    default_from = today - timedelta(days=6)
    default_to = today

    col1, col2, col3 = st.columns([1, 1, 0.5])
    with col1:
        d_from = st.date_input("From", value=default_from, max_value=today)
    with col2:
        d_to = st.date_input("To", value=default_to, max_value=today)
    with col3:
        load_clicked = st.button("🔍 Load", use_container_width=True)

    if "tt_view_loaded_once" not in st.session_state:
        st.session_state["tt_view_loaded_once"] = True
        load_clicked = True

    df = pd.DataFrame()
    error_msg = None
    if load_clicked:
        with get_session() as session:
            rows, error_msg = _fetch_transactions(session, loc.id, d_from, d_to)
            if not error_msg:
                df = _rows_to_dataframe(rows)

            # Audit the view
            try:
                SecurityManager.log_audit(
                    None,
                    (user or {}).get("username", "system"),
                    "VIEW",
                    resource_type="TankTransaction",
                    resource_id="",
                    details=f"Viewed transactions for {loc_label} from {d_from} to {d_to}; rows={len(df)}",
                    user_id=(user or {}).get("id"),
                    location_id=loc.id,
                )
            except Exception:
                pass

    if error_msg:
        st.error(error_msg)
        return

    # Exports (Excel/CSV + PDF)
    if not df.empty:
        _export_buttons(df)

        pdf_bytes = _df_to_pdf_bytes(
            df=df,
            loc_label=loc_label,
            d_from=d_from,
            d_to=d_to,
            username=(user or {}).get("username", ""),
        )
        st.download_button(
            "📄 Download PDF",
            data=pdf_bytes,
            file_name=f"tank_transactions_{loc_label.replace(' ', '_')}_{d_from}_{d_to}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

        # Audit the export
        try:
            SecurityManager.log_audit(
                None,
                (user or {}).get("username", "system"),
                "EXPORT_PDF",
                resource_type="TankTransaction",
                resource_id="",
                details=f"Exported PDF for {loc_label} from {d_from} to {d_to}; rows={len(df)}",
                user_id=(user or {}).get("id"),
                location_id=loc.id,
            )
        except Exception:
            pass

    st.markdown("---")
    if df.empty:
        st.info("No transactions found for the selected date range.")
    else:
        st.dataframe(df, use_container_width=True, height=460)
