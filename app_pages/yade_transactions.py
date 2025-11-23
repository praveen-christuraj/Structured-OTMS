# yade_transactions.py
from __future__ import annotations

from datetime import date, datetime, time as dt_time
from typing import Any, Dict, Optional, List

import re
import streamlit as st

from db import get_session
from ui import header
from security import SecurityManager
from logger import log_error
from models import (
    Location,
    YadeVoyage,
    YadeBarge,
    YadeDip,
    YadeSampleParam,
    TOAYadeStage,
    TOAYadeSummary,
    YadeSealDetail,
)
from location_config import LocationConfig

# Optional permissions
try:
    from permission_manager import PermissionManager
except Exception:  # pragma: no cover - optional module
    PermissionManager = None


# ========================= audit / guards =========================
def _audit_error(details: str, user: dict | None = None, location_id: int | None = None):
    """Log UI errors for YADE page (similar style as View Transactions)."""
    try:
        SecurityManager.log_audit(
            None,
            (user or {}).get("username", "system"),
            "ERROR",
            resource_type="UI",
            resource_id="YadeTransactions",
            details=str(details)[:900],
            user_id=(user or {}).get("id"),
            location_id=location_id,
            ip_address=str(st.session_state.get("client_ip") or "N/A"),
            success=False,
        )
    except Exception:
        pass


def _guard_location(active_location_id: Optional[int]):
    if not active_location_id:
        st.warning("No active location is selected. Go to **Home** and select a location first.")
        return None, None
    with get_session() as session:
        loc = session.query(Location).get(active_location_id)
        if not loc:
            st.warning("Selected location was not found. Please re-select from **Home**.")
            return None, None
        return loc, f"{loc.name} ({loc.code})"


def _guard_permissions(user: Optional[dict], active_location_id: Optional[int]) -> bool:
    role = (user or {}).get("role", "")
    if PermissionManager and user:
        try:
            if not PermissionManager.can_access_operational_pages(user):
                st.error(f"Your role **{role}** cannot access operational pages.")
                return False
        except Exception as ex:  # pragma: no cover - defensive
            _audit_error(f"Permission check failed: {ex}", user, active_location_id)
    return True


def _st_safe_rerun():
    """Streamlit rerun helper that works on older/newer versions."""
    try:
        import streamlit as _stmod

        _stmod.rerun()
    except Exception:
        import streamlit as _stmod

        _stmod.experimental_rerun()


# ========================= generic helpers =========================
TEMP_LIMITS = {
    "C": (0.0, 60.0),
    "F": (32.0, 120.0),
}
API_MIN, API_MAX = 15.0, 70.0
DENSITY_MIN, DENSITY_MAX = 600.0, 1000.0


def _normalize_temp_unit(unit: Optional[str]) -> str:
    label = (unit or "").strip().upper().replace("°", "")
    return "F" if label.startswith("F") else "C"


def _temperature_bounds(unit: Optional[str]) -> tuple[float, float]:
    norm = _normalize_temp_unit(unit)
    return TEMP_LIMITS.get(norm, TEMP_LIMITS["C"])


def _clamp_value(value: Optional[float], min_value: float, max_value: float) -> float:
    if value is None:
        return min_value
    try:
        numeric = float(value)
    except Exception:
        return min_value
    return max(min(numeric, max_value), min_value)


def _session_state_proxy():
    try:
        state = st.session_state
        if hasattr(state, "__contains__"):
            return state
    except Exception:
        return None
    return None


def _coerce_numeric_state(key: str, min_value: float, max_value: float):
    state_key = str(key)
    state = _session_state_proxy()
    if state is not None and state_key in state:
        state[state_key] = _clamp_value(state[state_key], min_value, max_value)


def _bounded_number_input(
    label: str,
    key: str,
    min_value: float,
    max_value: float,
    *,
    value: Optional[float] = None,
    **kwargs,
):
    state_key = str(key)
    state = _session_state_proxy()
    if state is not None:
        _coerce_numeric_state(state_key, min_value, max_value)
    params = dict(kwargs)
    params["min_value"] = min_value
    params["max_value"] = max_value
    params["key"] = state_key
    if "step" not in params:
        params["step"] = 0.1
    if value is not None:
        params["value"] = _clamp_value(value, min_value, max_value)
    return st.number_input(label, **params)


def _temperature_input(
    label: str,
    unit: Optional[str],
    key: str,
    *,
    value: Optional[float] = None,
    **kwargs,
):
    min_value, max_value = _temperature_bounds(unit)
    return _bounded_number_input(label, key, min_value, max_value, value=value, **kwargs)


def _observed_value_bounds(mode: str) -> tuple[float, float]:
    return (
        (DENSITY_MIN, DENSITY_MAX)
        if "density" in (mode or "").lower()
        else (API_MIN, API_MAX)
    )


# ========================= YADE-specific helpers =========================
def hhmm_ok(s: str) -> bool:
    if not s or len(s) not in (4, 5):
        return False
    s = s.strip()
    if ":" not in s:
        return False
    h, m = s.split(":", 1)
    if not (h.isdigit() and m.isdigit()):
        return False
    h_i, m_i = int(h), int(m)
    return 0 <= h_i <= 23 and 0 <= m_i <= 59


def only_digits_hyphen(s: str) -> bool:
    return bool(re.fullmatch(r"[0-9-]+", s)) and any(ch.isdigit() for ch in s)


WAT60_LOCAL = 999.012


def api_from_density(density_kgm3: float) -> float:
    if not density_kgm3 or density_kgm3 <= 0:
        return 0.0
    sg = float(density_kgm3) / WAT60_LOCAL
    if sg <= 0:
        return 0.0
    return round(141.5 / sg - 131.5, 2)


def density_from_api(api_val: float) -> float:
    if not api_val or api_val <= 0:
        return 0.0
    sg = 141.5 / (float(api_val) + 131.5)
    return round(sg * WAT60_LOCAL, 1)


def _get_yade_date_bounds(location_id: int) -> tuple[date, date]:
    """Return (min_date, max_date) for YADE voyages at this location, clamped to today."""
    today = date.today()
    try:
        from sqlalchemy import func

        with get_session() as s:
            q = (
                s.query(func.min(YadeVoyage.date), func.max(YadeVoyage.date))
                .filter(YadeVoyage.location_id == location_id)
            )
            dmin, dmax = q.first()
        if not dmin or not dmax:
            return today, today
        if dmax > today:
            dmax = today
        if dmin > dmax:
            dmin = dmax
        return dmin, dmax
    except Exception:
        return today, today


def _load_yade_barges() -> List[YadeBarge]:
    try:
        with get_session() as s:
            rows = s.query(YadeBarge).order_by(YadeBarge.name.asc()).all()
        return rows
    except Exception:
        return []


def _status_badge(v: YadeVoyage) -> str:
    if getattr(v, "is_cancelled", False):
        return "❌ Cancelled"
    if getattr(v, "is_closed", False):
        return "✅ Closed"
    return "⏳ Open"


def _persist_toa_from_current_inputs(
    session,
    voyage_obj: YadeVoyage,
    yade_name: str,
    tank_ids: List[str],
    sample_block_key: str,
):
    """Persist TOA (Transfer of Account) data from current YADE voyage inputs.

    This recreates TOAYadeSummary and TOAYadeStage rows based on the dips and sample
    parameters already stored for this voyage.
    """
    try:
        try:
            from yade_toa_calculator import calculate_yade_toa
        except ImportError:
            # Fallback: create placeholder rows so reporting still works
            summary = TOAYadeSummary(
                voyage_id=voyage_obj.id,
                ticket_id=f"YADE-{voyage_obj.voyage_no}",
                date=voyage_obj.date,
                time=voyage_obj.time,
                yade_name=yade_name,
                convoy_no=voyage_obj.convoy_no,
                destination=voyage_obj.destination,
                loading_berth=voyage_obj.loading_berth,
                gsv_before_bbl=0.0,
                gsv_after_bbl=0.0,
                gsv_loaded_bbl=0.0,
            )
            session.add(summary)
            for stage_name in ("before", "after"):
                stage = TOAYadeStage(
                    voyage_id=voyage_obj.id,
                    stage=stage_name,
                    gov_bbl=0.0,
                    gsv_bbl=0.0,
                    bsw_pct=0.0,
                    bsw_bbl=0.0,
                    nsv_bbl=0.0,
                    lt=0.0,
                    mt=0.0,
                    fw_bbl=0.0,
                )
                session.add(stage)
            return

        # Clear existing stages/summary
        session.query(TOAYadeStage).filter(TOAYadeStage.voyage_id == voyage_obj.id).delete(
            synchronize_session=False
        )
        session.query(TOAYadeSummary).filter(
            TOAYadeSummary.voyage_id == voyage_obj.id
        ).delete(synchronize_session=False)
        session.flush()

        # Load dips
        before_dips_db = session.query(YadeDip).filter(
            YadeDip.voyage_id == voyage_obj.id, YadeDip.stage == "before"
        ).all()
        after_dips_db = session.query(YadeDip).filter(
            YadeDip.voyage_id == voyage_obj.id, YadeDip.stage == "after"
        ).all()

        dip_data = {"before": {}, "after": {}}
        for dip in before_dips_db:
            dip_data["before"][dip.tank_id] = {
                "total_cm": float(dip.total_cm or 0.0),
                "water_cm": float(dip.water_cm or 0.0),
            }
        for dip in after_dips_db:
            dip_data["after"][dip.tank_id] = {
                "total_cm": float(dip.total_cm or 0.0),
                "water_cm": float(dip.water_cm or 0.0),
            }

        # Load sample params
        before_params = session.query(YadeSampleParam).filter(
            YadeSampleParam.voyage_id == voyage_obj.id, YadeSampleParam.stage == "before"
        ).first()
        after_params = session.query(YadeSampleParam).filter(
            YadeSampleParam.voyage_id == voyage_obj.id, YadeSampleParam.stage == "after"
        ).first()

        def _safe_param(row, default_unit="°F"):
            if not row:
                return {
                    "obs_mode": "Observed API",
                    "obs_val": 0.0,
                    "sample_temp": 60.0,
                    "tank_temp": 60.0,
                    "bsw_pct": 0.0,
                    "ccf": 1.0,
                }
            return {
                "obs_mode": row.obs_mode or "Observed API",
                "obs_val": float(row.obs_val or 0.0),
                "sample_temp": float(row.sample_temp or 60.0),
                "tank_temp": float(row.tank_temp or 60.0),
                "bsw_pct": float(row.bsw_pct or 0.0),
                "ccf": float(row.ccf or 1.0),
            }

        sample_data = {
            "before": _safe_param(before_params),
            "after": _safe_param(after_params),
        }

        toa_result = calculate_yade_toa(
            yade_name=yade_name,
            dip_data=dip_data,
            sample_data=sample_data,
            session=session,
        )
        if not toa_result:
            return

        # Summary
        summary = TOAYadeSummary(
            voyage_id=voyage_obj.id,
            ticket_id=f"YADE-{voyage_obj.voyage_no}",
            date=voyage_obj.date,
            time=voyage_obj.time,
            yade_name=yade_name,
            convoy_no=voyage_obj.convoy_no,
            destination=voyage_obj.destination,
            loading_berth=voyage_obj.loading_berth,
            gsv_before_bbl=float(toa_result.get("before", {}).get("gsv_bbl", 0.0)),
            gsv_after_bbl=float(toa_result.get("after", {}).get("gsv_bbl", 0.0)),
            gsv_loaded_bbl=float(toa_result.get("loaded", {}).get("gsv_bbl", 0.0)),
        )
        session.add(summary)

        # Stage rows
        for stage_name in ("before", "after"):
            vals = toa_result.get(stage_name, {}) or {}
            stage = TOAYadeStage(
                voyage_id=voyage_obj.id,
                stage=stage_name,
                gov_bbl=float(vals.get("gov_bbl", 0.0)),
                gsv_bbl=float(vals.get("gsv_bbl", 0.0)),
                bsw_pct=float(vals.get("bsw_pct", 0.0)),
                bsw_bbl=float(vals.get("bsw_bbl", 0.0)),
                nsv_bbl=float(vals.get("nsv_bbl", 0.0)),
                lt=float(vals.get("lt", 0.0)),
                mt=float(vals.get("mt", 0.0)),
                fw_bbl=float(vals.get("fw_bbl", 0.0)),
            )
            session.add(stage)

    except Exception as ex:  # pragma: no cover - defensive
        log_error(f"Failed to persist YADE TOA: {ex}", exc_info=True)


# ========================= YADE form =========================
def _render_yade_form(
    location_id: int,
    loc_label: str,
    user: Dict[str, Any] | None,
    yade_cfg: Dict[str, Any],
):
    if "yade_edit_id" not in st.session_state:
        st.session_state["yade_edit_id"] = None

    edit_id = st.session_state.get("yade_edit_id")

    # Load choices from master data
    barges = _load_yade_barges()
    barge_names = [b.name for b in barges] if barges else []
    barge_design_by_name = {b.name: str(b.design) for b in barges}

    # Prefill if editing
    voy: Optional[YadeVoyage] = None
    if edit_id:
        try:
            with get_session() as s:
                voy = (
                    s.query(YadeVoyage)
                    .filter(YadeVoyage.id == edit_id, YadeVoyage.location_id == location_id)
                    .one_or_none()
                )
        except Exception as ex:
            _audit_error(f"Load voyage {edit_id} failed: {ex}", user, location_id)
            voy = None

    st.subheader("🆕 New YADE Voyage Entry")

    if voy:
        st.info(
            f"Editing voyage **#{voy.id}** — {voy.yade_name or 'N/A'} | "
            f"{voy.voyage_no or 'No'} on {voy.date or 'N/A'}"
        )

    # ---------- Form ----------
    with st.form("yade_voyage_form", clear_on_submit=False):
        # ---- Top metadata ----
        m1, m2, m3 = st.columns(3)
        with m1:
            if barge_names:
                default_idx = 0
                if voy and voy.yade_name in barge_names:
                    default_idx = barge_names.index(voy.yade_name)
                yade_no = st.selectbox("1) YADE No *", barge_names, index=default_idx, key="yt_yade_no")
            else:
                yade_no = st.selectbox(
                    "1) YADE No *",
                    ["(No YADE barges – add in Add Asset)"],
                    index=0,
                    key="yt_yade_no",
                )

            selected_design = barge_design_by_name.get(yade_no)
            design_choice = selected_design or st.selectbox(
                "Tank Design *",
                ["6", "4"],
                index=0,
                key="yt_design_fallback",
            )
        with m2:
            voyage_no = st.text_input(
                "2) Voyage number * (digits & '-' only)",
                placeholder="e.g., 12-3",
                key="yt_voyage_no",
                value=(voy.voyage_no or "") if voy else "",
            )
            convoy_no = st.text_input(
                "3) Convoy number * (digits & '-' only)",
                placeholder="e.g., 5-1",
                key="yt_convoy_no",
                value=(voy.convoy_no or "") if voy else "",
            )
        with m3:
            tx_date = st.date_input(
                "4) Date * (DD/MM/YYYY)",
                value=voy.date if (voy and voy.date) else date.today(),
                format="DD/MM/YYYY",
                key="yt_date",
            )
            default_time = (voy.time.strftime("%H:%M") if (voy and voy.time) else "08:00")
            tx_time = st.text_input(
                "5) Time * (HH:MM)",
                value=default_time,
                key="yt_time",
            )

        m4, m5, m6 = st.columns(3)
        with m4:
            # Cargo options from config if present, else simple defaults
            cargo_opts = yade_cfg.get("enabled_cargo_types") or ["Crude Oil"]
            default_idx = 0
            if voy and voy.cargo in cargo_opts:
                default_idx = cargo_opts.index(voy.cargo)
            cargo = st.selectbox("6) Cargo *", cargo_opts, index=default_idx, key="yt_cargo")
        with m5:
            dest_opts = yade_cfg.get("enabled_destinations") or ["Agge FSO"]
            dest_idx = 0
            if voy and voy.destination in dest_opts:
                dest_idx = dest_opts.index(voy.destination)
            destination = st.selectbox(
                "7) Destination *",
                dest_opts,
                index=dest_idx,
                key="yt_destination",
            )
        with m6:
            berth_opts = yade_cfg.get("enabled_loading_berths") or ["Asemoku Jetty"]
            berth_idx = 0
            if voy and voy.loading_berth in berth_opts:
                berth_idx = berth_opts.index(voy.loading_berth)
            loading_berth = st.selectbox(
                "8) Loading Berth *",
                berth_opts,
                index=berth_idx,
                key="yt_berth",
            )

        st.markdown("---")

        # ------------ Tank set by design ------------
        tank_ids_6 = ["C1", "C2", "P1", "P2", "S1", "S2"]
        tank_ids_4 = ["P1", "P2", "S1", "S2"]
        tank_ids = tank_ids_6 if str(design_choice) == "6" else tank_ids_4

        # ------------ Dip Entry Tables (Before / After) ------------
        st.markdown("#### Dip Entry Tables")
        left, right = st.columns(2)

        with left:
            st.markdown("##### Before Loading/Unloading")
            b_dcol, b_tcol = st.columns(2)
            with b_dcol:
                before_date = st.date_input(
                    "Gauging Date (Before)",
                    value=voy.before_gauge_date if (voy and voy.before_gauge_date) else tx_date,
                    format="DD/MM/YYYY",
                    key="before_date",
                )
            with b_tcol:
                default_before_time = (
                    voy.before_gauge_time.strftime("%H:%M") if (voy and voy.before_gauge_time) else "07:30"
                )
                before_time = st.text_input(
                    "Gauging Time (Before) (HH:MM)",
                    value=default_before_time,
                    key="before_time",
                )

            st.caption("Enter **Total Dip** and **Water Dip** (cm) for each tank")
            dip_before: Dict[str, Dict[str, float]] = {}
            for tid in tank_ids:
                r1, r2, r3 = st.columns([0.25, 0.375, 0.375])
                with r1:
                    st.text_input("Tank", value=tid, disabled=True, key=f"before_tank_{tid}")
                with r2:
                    tot = st.number_input(
                        "Total Dip (cm)",
                        min_value=0.0,
                        step=0.1,
                        key=f"before_total_{tid}",
                    )
                with r3:
                    wat = st.number_input(
                        "Water Dip (cm)",
                        min_value=0.0,
                        step=0.1,
                        key=f"before_water_{tid}",
                    )
                dip_before[tid] = {"total_cm": float(tot or 0.0), "water_cm": float(wat or 0.0)}

        with right:
            st.markdown("##### After Loading/Unloading")
            a_dcol, a_tcol = st.columns(2)
            with a_dcol:
                after_date = st.date_input(
                    "Gauging Date (After)",
                    value=voy.after_gauge_date if (voy and voy.after_gauge_date) else tx_date,
                    format="DD/MM/YYYY",
                    key="after_date",
                )
            with a_tcol:
                default_after_time = (
                    voy.after_gauge_time.strftime("%H:%M") if (voy and voy.after_gauge_time) else "17:30"
                )
                after_time = st.text_input(
                    "Gauging Time (After) (HH:MM)",
                    value=default_after_time,
                    key="after_time",
                )

            st.caption("Enter **Total Dip** and **Water Dip** (cm) for each tank")
            dip_after: Dict[str, Dict[str, float]] = {}
            for tid in tank_ids:
                r1, r2, r3 = st.columns([0.25, 0.375, 0.375])
                with r1:
                    st.text_input("Tank ", value=tid, disabled=True, key=f"after_tank_{tid}")
                with r2:
                    tot = st.number_input(
                        "Total Dip (cm) ",
                        min_value=0.0,
                        step=0.1,
                        key=f"after_total_{tid}",
                    )
                with r3:
                    wat = st.number_input(
                        "Water Dip (cm) ",
                        min_value=0.0,
                        step=0.1,
                        key=f"after_water_{tid}",
                    )
                dip_after[tid] = {"total_cm": float(tot or 0.0), "water_cm": float(wat or 0.0)}

        st.markdown("---")

        # ====================== SAMPLE PARAMETERS (Before / After) ======================
        st.markdown("### Sample Parameters")

        safe_yade = re.sub(r"[^A-Za-z0-9]", "_", str(yade_no))
        safe_voy = re.sub(r"[^A-Za-z0-9]", "_", str(voyage_no))
        ns_sp = f"ysp_{safe_yade}_{safe_voy}"

        if "yade_sample_params" not in st.session_state:
            st.session_state["yade_sample_params"] = {}
        if ns_sp not in st.session_state["yade_sample_params"]:
            st.session_state["yade_sample_params"][ns_sp] = {}

        def _sample_param_row(stage_key: str):
            st.markdown(f"#### {stage_key.title()}")
            c1, c2, c3, c4 = st.columns([0.28, 0.24, 0.24, 0.24])
            with c1:
                obs_mode = st.selectbox(
                    "Observed Input",
                    ["Observed API", "Observed Density (kg/m3)"],
                    index=0,
                    key=f"{ns_sp}_{stage_key}_obs_mode",
                )
            with c2:
                sample_unit = st.selectbox(
                    "Sample Temperature Unit",
                    ["°F", "°C"],
                    index=0,
                    key=f"{ns_sp}_{stage_key}_sample_unit",
                )
            with c3:
                sample_temp = _temperature_input(
                    "Sample Temperature",
                    sample_unit,
                    key=f"{ns_sp}_{stage_key}_sample_temp",
                )
            with c4:
                tank_temp = _temperature_input(
                    "Tank Temperature",
                    sample_unit,
                    key=f"{ns_sp}_{stage_key}_tank_temp",
                )

            d1, d2, d3 = st.columns([0.34, 0.33, 0.33])
            with d1:
                obs_min, obs_max = _observed_value_bounds(obs_mode)
                obs_val = _bounded_number_input(
                    "Observed Value",
                    key=f"{ns_sp}_{stage_key}_obs_val",
                    min_value=obs_min,
                    max_value=obs_max,
                    step=0.1,
                )
            with d2:
                ccf = st.number_input(
                    "Calibration Correction Factor",
                    min_value=0.000001,
                    value=1.0,
                    step=0.0001,
                    key=f"{ns_sp}_{stage_key}_ccf",
                    help="Default 1.0000. Cannot be 0.",
                )
            with d3:
                bsw_pct = st.number_input(
                    "BS&W %",
                    min_value=0.0,
                    max_value=100.0,
                    step=0.01,
                    key=f"{ns_sp}_{stage_key}_bsw_pct",
                    help="Basic Sediment & Water percentage (e.g., 0.25).",
                )

            st.session_state["yade_sample_params"][ns_sp][stage_key] = {
                "obs_mode": obs_mode,
                "obs_val": float(obs_val or 0.0),
                "sample_unit": sample_unit,
                "sample_temp": float(sample_temp or 0.0),
                "tank_temp": float(tank_temp or 0.0),
                "ccf": float(ccf or 1.0),
                "bsw_pct": float(bsw_pct or 0.0),
            }

        col_before, col_after = st.columns(2)
        with col_before:
            _sample_param_row("before")
        with col_after:
            _sample_param_row("after")

        # ===== SEAL DETAILS =====
        st.markdown("---")
        st.markdown("### Seal Details")

        tanks_seal = ["C1", "C2", "P1", "P2", "S1", "S2"] if str(design_choice) == "6" else ["P1", "P2", "S1", "S2"]

        _safe_yade = re.sub(r"[^A-Za-z0-9]", "_", str(yade_no))
        _safe_voy = re.sub(r"[^A-Za-z0-9]", "_", str(voyage_no))
        ns_seal = f"yseal_{_safe_yade}_{_safe_voy}"

        if "yade_seals" not in st.session_state:
            st.session_state["yade_seals"] = {}

        if ns_seal not in st.session_state["yade_seals"]:
            st.session_state["yade_seals"][ns_seal] = {
                t: {"mh1": "", "mh2": "", "lock": "", "diph": ""} for t in tanks_seal
            }

        hdr = st.columns([0.10, 0.225, 0.225, 0.225, 0.225])
        hdr[0].markdown("**Tank**")
        hdr[1].markdown("**Manhole-1 Seal No**")
        hdr[2].markdown("**Manhole-2 Seal No**")
        hdr[3].markdown("**Lock No**")
        hdr[4].markdown("**Dip Hatch Seal No**")

        for t in tanks_seal:
            row = st.columns([0.10, 0.225, 0.225, 0.225, 0.225])
            row[0].write(t)
            kbase = f"{ns_seal}_{t}"

            mh1 = row[1].text_input(
                "Manhole-1 Seal No",
                key=f"{kbase}_mh1",
                value=st.session_state["yade_seals"][ns_seal][t]["mh1"],
                label_visibility="collapsed",
            )
            mh2 = row[2].text_input(
                "Manhole-2 Seal No",
                key=f"{kbase}_mh2",
                value=st.session_state["yade_seals"][ns_seal][t]["mh2"],
                label_visibility="collapsed",
            )
            lk = row[3].text_input(
                "Lock No",
                key=f"{kbase}_lock",
                value=st.session_state["yade_seals"][ns_seal][t]["lock"],
                label_visibility="collapsed",
            )
            dh = row[4].text_input(
                "Dip Hatch Seal No",
                key=f"{kbase}_diph",
                value=st.session_state["yade_seals"][ns_seal][t]["diph"],
                label_visibility="collapsed",
            )

            st.session_state["yade_seals"][ns_seal][t]["mh1"] = mh1.strip()
            st.session_state["yade_seals"][ns_seal][t]["mh2"] = mh2.strip()
            st.session_state["yade_seals"][ns_seal][t]["lock"] = lk.strip()
            st.session_state["yade_seals"][ns_seal][t]["diph"] = dh.strip()

        st.markdown("---")

        # ---- FINAL Save / Reset buttons ----
        col_btn1, col_btn2 = st.columns([1, 1])
        safe_yade = re.sub(r"[^A-Za-z0-9]", "_", str(yade_no))
        safe_voy = re.sub(r"[^A-Za-z0-9]", "_", str(voyage_no))
        save_key = f"yade_save_btn_{safe_yade}_{safe_voy}"
        with col_btn1:
            save_clicked = st.form_submit_button(
                "💾 Save YADE Voyage", type="primary", key=save_key, use_container_width=True
            )
        with col_btn2:
            reset_clicked = st.form_submit_button("🔄 Reset Form", use_container_width=True)

    # ----- outside form: handle actions -----
    if reset_clicked:
        st.session_state["yade_edit_id"] = None
        st.success("Form reset to new-voyage mode.")
        _st_safe_rerun()

    if save_clicked:
        errs: List[str] = []
        if "(No YADE barges" in str(yade_no):
            errs.append("Please add YADE barges under **Add Asset** and select a valid YADE No.")
        if not only_digits_hyphen(voyage_no):
            errs.append("Voyage number: only digits and '-' allowed.")
        if convoy_no and not only_digits_hyphen(convoy_no):
            errs.append("Convoy number: only digits and '-' allowed.")
        if not hhmm_ok(tx_time) or not hhmm_ok(before_time) or not hhmm_ok(after_time):
            errs.append("All times must be HH:MM (24-hour).")

        if errs:
            for e in errs:
                st.error(e)
            return

        try:
            tx_time_obj = datetime.strptime(tx_time, "%H:%M").time()
            btime_obj = datetime.strptime(before_time, "%H:%M").time()
            atime_obj = datetime.strptime(after_time, "%H:%M").time()
        except Exception:
            st.error("Time parsing failed. Use HH:MM (24-hour).")
            return

        try:
            current_user = (st.session_state.get("auth_user") or {}).get("username", "unknown")
            current_user_id = (st.session_state.get("auth_user") or {}).get("id")

            with get_session() as s:
                if voy:
                    # ---- UPDATE header only (keep existing dips/sample/seals/TOA) ----
                    voy.yade_name = yade_no
                    voy.design = str(design_choice)
                    voy.voyage_no = voyage_no.strip()
                    voy.convoy_no = (convoy_no or "").strip()
                    voy.date = tx_date
                    voy.time = tx_time_obj
                    voy.cargo = cargo
                    voy.destination = destination
                    voy.loading_berth = loading_berth
                    voy.before_gauge_date = before_date
                    voy.before_gauge_time = btime_obj
                    voy.after_gauge_date = after_date
                    voy.after_gauge_time = atime_obj
                    voy.updated_by = current_user
                    voy.updated_at = datetime.utcnow()
                    voyage_id = voy.id
                    target_voy = voy
                    action = "UPDATE"
                else:
                    # ---- CREATE new voyage + all details ----
                    new_v = YadeVoyage(
                        location_id=location_id,
                        yade_name=yade_no,
                        design=str(design_choice),
                        voyage_no=voyage_no.strip(),
                        convoy_no=(convoy_no or "").strip(),
                        date=tx_date,
                        time=tx_time_obj,
                        cargo=cargo,
                        destination=destination,
                        loading_berth=loading_berth,
                        before_gauge_date=before_date,
                        before_gauge_time=btime_obj,
                        after_gauge_date=after_date,
                        after_gauge_time=atime_obj,
                        created_by=current_user,
                        created_at=datetime.utcnow(),
                    )
                    s.add(new_v)
                    s.flush()
                    voyage_id = new_v.id
                    target_voy = new_v
                    action = "CREATE"

                    # Dips (only for new voyages for now)
                    s.query(YadeDip).filter(YadeDip.voyage_id == voyage_id).delete()
                    for tid in tank_ids:
                        b_vals = dip_before.get(tid, {}) or {}
                        a_vals = dip_after.get(tid, {}) or {}
                        s.add(
                            YadeDip(
                                voyage_id=voyage_id,
                                tank_id=tid,
                                stage="before",
                                total_cm=float(b_vals.get("total_cm", 0.0)),
                                water_cm=float(b_vals.get("water_cm", 0.0)),
                            )
                        )
                        s.add(
                            YadeDip(
                                voyage_id=voyage_id,
                                tank_id=tid,
                                stage="after",
                                total_cm=float(a_vals.get("total_cm", 0.0)),
                                water_cm=float(a_vals.get("water_cm", 0.0)),
                            )
                        )

                    # Sample parameters from session
                    sp_store = st.session_state.get("yade_sample_params", {})
                    blk = sp_store.get(ns_sp, sp_store)

                    def _upsert_stage_params(stage_key: str):
                        data = blk.get(stage_key, {}) or {
                            "obs_mode": "Observed API",
                            "obs_val": 0.0,
                            "sample_unit": "°F",
                            "sample_temp": 0.0,
                            "tank_temp": 0.0,
                            "ccf": 1.0,
                            "bsw_pct": 0.0,
                        }
                        row = (
                            s.query(YadeSampleParam)
                            .filter(YadeSampleParam.voyage_id == voyage_id, YadeSampleParam.stage == stage_key)
                            .one_or_none()
                        )
                        if row is None:
                            row = YadeSampleParam(voyage_id=voyage_id, stage=stage_key)
                            s.add(row)
                        row.obs_mode = str(data.get("obs_mode") or "Observed API")
                        row.obs_val = float(data.get("obs_val") or 0.0)
                        row.sample_unit = str(data.get("sample_unit") or "°F")
                        row.sample_temp = float(data.get("sample_temp") or 0.0)
                        row.tank_temp = float(data.get("tank_temp") or 0.0)
                        row.ccf = max(float(data.get("ccf") or 1.0), 0.000001)
                        row.bsw_pct = float(data.get("bsw_pct") or 0.0)

                    _upsert_stage_params("before")
                    _upsert_stage_params("after")

                    # Seal details
                    seals_pack = st.session_state.get("yade_seals", {}).get(ns_seal, {}) or {}
                    for_save_tanks = ["C1", "C2", "P1", "P2", "S1", "S2"] if str(design_choice) == "6" else ["P1", "P2", "S1", "S2"]
                    row = (
                        s.query(YadeSealDetail)
                        .filter(YadeSealDetail.voyage_id == voyage_id)
                        .one_or_none()
                    )
                    if row is None:
                        row = YadeSealDetail(voyage_id=voyage_id)
                        s.add(row)

                    for t in for_save_tanks:
                        data = seals_pack.get(t, {})
                        k = t.lower()
                        setattr(row, f"{k}_mh1", (data.get("mh1", "") or "").strip() or None)
                        setattr(row, f"{k}_mh2", (data.get("mh2", "") or "").strip() or None)
                        setattr(row, f"{k}_lock", (data.get("lock", "") or "").strip() or None)
                        setattr(row, f"{k}_diphatch", (data.get("diph", "") or "").strip() or None)

                    # Persist TOA
                    _persist_toa_from_current_inputs(s, target_voy, yade_no, tank_ids, ns_sp)

                s.commit()

                # Audit log
                try:
                    SecurityManager.log_audit(
                        None,
                        username=current_user,
                        action=action,
                        resource_type="YadeVoyage",
                        resource_id=str(voyage_id),
                        details=f"{action} YADE voyage: {yade_no} - Voyage {voyage_no}",
                        user_id=current_user_id,
                        location_id=location_id,
                        ip_address=str(st.session_state.get("client_ip") or "N/A"),
                        success=True,
                    )
                except Exception:
                    pass

            st.session_state["yade_edit_id"] = None
            st.success(f"✅ YADE Voyage saved for {yade_no} — Voyage {voyage_no}")
            _st_safe_rerun()

        except Exception as ex:  # pragma: no cover - defensive
            log_error(f"Failed to save YADE voyage: {ex}", exc_info=True)
            st.error("Failed to save YADE Voyage. (Logged)")
            import traceback

            st.code(traceback.format_exc())


# ========================= YADE list =========================
def _render_yade_list(location_id: int, user: Dict[str, Any] | None):
    st.subheader("📜 YADE Voyages List")

    min_d, max_d = _get_yade_date_bounds(location_id)
    col1, col2 = st.columns(2)
    with col1:
        from_date = st.date_input("From date", value=min_d, key="yade_list_from")
    with col2:
        to_date = st.date_input("To date", value=max_d, key="yade_list_to")

    if from_date > to_date:
        st.error("From date cannot be after To date.")
        return

    rows: List[YadeVoyage] = []
    try:
        with get_session() as s:
            q = (
                s.query(YadeVoyage)
                .filter(YadeVoyage.location_id == location_id)
                .filter(YadeVoyage.date >= from_date)
                .filter(YadeVoyage.date <= to_date)
                .order_by(YadeVoyage.date.desc(), YadeVoyage.id.desc())
            )
            rows = q.all()
    except Exception as ex:
        _audit_error(f"Load voyages failed: {ex}", user, location_id)
        st.error("Failed to load YADE voyages. (Logged)")
        return

    if not rows:
        st.info("No YADE voyages found in the selected date range.")
        return

    st.caption(f"Total voyages: **{len(rows)}**")

    for i, v in enumerate(rows, start=1):
        c1, c2, c3, c4, c5 = st.columns([0.6, 1.4, 1.0, 1.0, 0.6])
        with c1:
            st.markdown(f"**#{v.id}**")
            st.markdown(v.date.isoformat() if v.date else "—")
        with c2:
            st.markdown(f"**{v.yade_name or 'N/A'}**")
            st.caption(f"Design: {v.design or 'N/A'} | Voyage: {v.voyage_no or 'N/A'}")
        with c3:
            st.markdown(v.cargo or "—")
            st.caption(v.loading_berth or "—")
        with c4:
            st.markdown(v.destination or "—")
            st.caption(_status_badge(v))
        with c5:
            if st.button("✏️ Edit", key=f"yade_edit_{v.id}", use_container_width=True):
                st.session_state["yade_edit_id"] = v.id
                _st_safe_rerun()

        st.markdown("---")


# ========================= main page =========================
def render_yade_transactions_page(active_location_id: int | None, user: Dict[str, Any] | None):
    try:
        header("Yade Transactions")

        loc, loc_label = _guard_location(active_location_id)
        if not loc:
            return
        if not _guard_permissions(user, active_location_id):
            return

        # Check location config: is YADE enabled?
        with get_session() as s:
            cfg = LocationConfig.get_config(s, loc.id)
        page_vis = cfg.get("page_visibility", {})
        if not page_vis.get("show_yade_transactions", False):
            st.warning(f"YADE Transactions page is disabled for **{loc_label}**.")
            return

        yade_cfg = cfg.get("yade_transactions", {}) or {}
        st.caption(f"Active Location: **{loc_label}**")

        tab_entry, tab_list = st.tabs(["🆕 Entry / Edit", "📜 Voyages List"])

        with tab_entry:
            _render_yade_form(loc.id, loc_label, user, yade_cfg)

        with tab_list:
            _render_yade_list(loc.id, user)

    except Exception as ex:  # pragma: no cover - defensive
        _audit_error(f"Render YADE page failed: {ex}", user, active_location_id)
        st.error("Unexpected error while rendering YADE Transactions. (Logged)")
