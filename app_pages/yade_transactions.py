# yade_transactions.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional, List, Tuple
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
    YadeCalibration,
    YadeDip,
)
from location_config import LocationConfig
from utils_calc import (
    density_from_api, api_from_density,
    api60_from_api_obs, api60_from_density_obs,
)
# Optional permissions
try:
    from permission_manager import PermissionManager
except Exception:
    PermissionManager = None


# ========================= audit / guards =========================
def _audit_error(details: str, user: dict | None = None, location_id: int | None = None):
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
            ip_address=str(st.session_state.get("client_ip", "N/A")),
            success=False,
        )
    except Exception:
        pass


def _guard_location(active_location_id: Optional[int]):
    if not active_location_id:
        st.warning("⚠️ No active location selected. Please select a location from **Home**.")
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
                st.error(f"🚫 Your role **{role}** cannot access operational pages.")
                return False
        except Exception as ex:
            _audit_error(f"Permission check failed: {ex}", user, active_location_id)
    return True


def _st_safe_rerun():
    try:
        import streamlit as _stmod
        _stmod.rerun()
    except Exception:
        import streamlit as _stmod
        _stmod.experimental_rerun()

# ==== Sample parameter helpers (dynamic validation & conversions) ====
WATER_DENS_60 = 999.012  # kg/m3 at 60°F reference

def _normalize_temp_unit(unit: Optional[str]) -> str:
    """Return 'F' or 'C' for any label like '°F'/'F'/'°C'/'C' (default 'F')."""
    if not unit:
        return "F"
    u = str(unit).upper().replace("°", "").strip()
    return "C" if u.startswith("C") else "F"

def _temp_bounds(unit_code: str) -> tuple[float, float]:
    """Unit-specific temperature bounds."""
    if unit_code == "C":
        return (0.0, 60.0)
    return (32.0, 140.0)  # F

def _to_fahrenheit(value: float, unit_code: str) -> float:
    """Convert given value to °F if needed."""
    if unit_code == "F":
        return float(value or 0.0)
    # C → F
    return float(value or 0.0) * 9.0 / 5.0 + 32.0

def _api_to_density60(api60: float) -> float:
    """Approx density at 60°F from API@60 formula (kg/m³)."""
    if api60 is None:
        return 0.0
    sg60 = 141.5 / (float(api60) + 131.5)
    return round(sg60 * WATER_DENS_60, 1)

def _density_to_api(density: float) -> float:
    """Approx instantaneous API (at same temp) from density (kg/m³)."""
    if not density or density <= 0:
        return 0.0
    sg = float(density) / WATER_DENS_60
    return round(141.5 / sg - 131.5, 2)

def _api_observed_to_api60(api_obs: float, temp_f: float) -> float:
    """
    Convert Observed API at (temp_f) to API@60°F.
    If you already have a refined function in utils_calc (api_observed_to_api60), swap this call.
    """
    try:
        # If your utils_calc has the refined correlation, prefer it:
        from utils_calc import api_observed_to_api60 as _api_to60
        return float(_api_to60(float(api_obs or 0.0), float(temp_f or 0.0)))
    except Exception:
        # Fallback: small linearized adjustment around 60°F (very rough)
        # Warmer sample → slightly lower API@60; Colder → slightly higher.
        # This is intentionally conservative until your full table routine is wired.
        k = 0.02  # rough slope per °F
        df = float(temp_f or 60.0) - 60.0
        return round(float(api_obs or 0.0) - k * df, 2)

def _density_observed_to_api60(density_obs: float, temp_f: float) -> tuple[float, float]:
    """
    Convert Observed density at (temp_f) to (API@60°F, density@60°F approx).
    If you have utils_calc.density_obs_to_api60, we defer to it. Else fallback.
    """
    try:
        from utils_calc import density_obs_to_api60 as _dens_to60
        api60, dens60 = _dens_to60(float(density_obs or 0.0), float(temp_f or 0.0))
        return float(api60 or 0.0), float(dens60 or 0.0)
    except Exception:
        # Fallback: treat observed density roughly equal to density@60 with small temp bias.
        # Warmer sample → slightly higher density@60 correction downward.
        k = 0.0008  # rough kg/m3 per °F correction factor (placeholder)
        df = float(temp_f or 60.0) - 60.0
        dens60 = max(0.0, float(density_obs or 0.0) - k * df * 100.0)
        api60 = _density_to_api(dens60)
        return round(api60, 2), round(dens60, 1)

# ========================= helpers =========================
def _load_yade_barges() -> List[YadeBarge]:
    try:
        with get_session() as s:
            return s.query(YadeBarge).order_by(YadeBarge.name.asc()).all()
    except Exception:
        return []


def _get_yade_date_bounds(location_id: int) -> tuple[date, date]:
    today = date.today()
    try:
        from sqlalchemy import func
        with get_session() as s:
            dmin, dmax = (
                s.query(func.min(YadeVoyage.date), func.max(YadeVoyage.date))
                 .filter(YadeVoyage.location_id == location_id)
                 .first()
            )
        if not dmin or not dmax:
            return today, today
        if dmax > today:
            dmax = today
        if dmin > dmax:
            dmin = dmax
        return dmin, dmax
    except Exception:
        return today, today


def _status_badge(_v: YadeVoyage) -> str:
    return "🟢 Active"


def _list_names_from_ops(session, location_id: int, *, asset: str, category: str) -> List[str]:
    """
    Return ACTIVE operation names for a given asset/category from Location Settings → Operations.
    Requires that location_config.OP_CATEGORIES includes the category.
    """
    from location_config import list_operations
    try:
        rows = list_operations(session, location_id, asset=asset, category=category)
        return [r["name"] for r in rows if r.get("active", True)]
    except Exception:
        return []


# --- Dip helpers (YADE) ---
_TANK_ORDER = ["C1", "C2", "P1", "P2", "S1", "S2"]

def _resolve_op_labels(operation: str) -> Tuple[str, str]:
    """
    Return ("Before {operation}", "After {operation}") using the exact
    selected operation text from the dropdown. Falls back to "Before"/"After".
    """
    op_disp = (operation or "").strip()
    if not op_disp or op_disp.upper() == "N/A":
        return "Before", "After"
    return f"Before {op_disp}", f"After {op_disp}"


def _get_barge_tanks_and_limits(yade_name: str, design: str) -> Tuple[list[str], dict]:
    """
    Determine tank ids and max total dip (cm) per tank for a YADE barge.
    Priority:
      1) Tanks that exist in YadeCalibration (sorted by standard order)
      2) Fallback to barge 'design' → 6-tank: C1,C2,P1,P2,S1,S2; 4-tank: P1,P2,S1,S2
    Note: Calibration 'dip_mm' is in millimetres; convert to cm (÷10).
    """
    try:
        from sqlalchemy import func
        with get_session() as s:
            rows = (
                s.query(
                    YadeCalibration.tank_id,
                    func.max(YadeCalibration.dip_mm).label("max_dip_mm")
                )
                .filter(YadeCalibration.yade_name == yade_name)
                .group_by(YadeCalibration.tank_id)
                .all()
            )
    except Exception:
        rows = []

    if rows:
        tank_ids = [r.tank_id for r in rows]
        # stable order
        tank_ids = sorted(tank_ids, key=lambda t: _TANK_ORDER.index(t) if t in _TANK_ORDER else 999)
        max_by_tank = {r.tank_id: (float(r.max_dip_mm or 0.0) / 10.0) for r in rows}
        return tank_ids, max_by_tank

    # Fallback to barge design:
    if str(design) == "4":
        tank_ids = ["P1", "P2", "S1", "S2"]
    else:
        tank_ids = ["C1", "C2", "P1", "P2", "S1", "S2"]
    max_by_tank = {t: 9999.0 for t in tank_ids}  # if no calibration yet
    return tank_ids, max_by_tank


def _load_existing_dips(session, voyage_id: int) -> dict:
    """Return {'before': {tid:{'total_cm':..,'water_cm':..}}, 'after': {...}} for prefill."""
    out = {"before": {}, "after": {}}
    if not voyage_id:
        return out
    rows = session.query(YadeDip).filter(YadeDip.voyage_id == voyage_id).all()
    for r in rows:
        stage = (r.stage or "").lower()
        if stage in ("before", "after"):
            out[stage][r.tank_id] = {
                "total_cm": float(r.total_cm or 0.0),
                "water_cm": float(r.water_cm or 0.0),
            }
    return out


# ========================= Sample Parameters (added) =========================
# Temperature and observed limits consistent with Tank page behavior
_TEMP_LIMITS = {"C": (0.0, 60.0), "F": (32.0, 140.0)}
_API_MIN, _API_MAX = 15.0, 70.0
_DEN_MIN, _DEN_MAX = 600.0, 1000.0

def _norm_unit(label: Optional[str]) -> str:
    lab = (label or "").strip().upper().replace("°", "")
    return "F" if lab.startswith("F") else "C"

def _temp_bounds(unit: Optional[str]) -> Tuple[float, float]:
    return _TEMP_LIMITS.get(_norm_unit(unit), _TEMP_LIMITS["C"])

def _obs_bounds(mode: str) -> Tuple[float, float]:
    return (_DEN_MIN, _DEN_MAX) if "density" in (mode or "").lower() else (_API_MIN, _API_MAX)

def _render_yade_sample_params(*, yade_no: str, voyage_no: str | None = None, ns_key: Optional[str] = None):
    """
    Render side-by-side Sample Parameters for BEFORE and AFTER.
    - Observed selector: API or Density (enforces ranges).
    - One temperature unit selector per stage that controls both Sample & Tank temps.
    - Includes CCF and BS&W %.
    Values are stored in st.session_state["yade_sample_params"][ns][stage].
    """
    if not yade_no or yade_no.startswith("-- No YADE Barges"):
        st.warning("⚠️ Add/select a YADE barge to enter sample parameters.")
        return

    safe_yade = re.sub(r"[^A-Za-z0-9]", "_", str(yade_no))
    safe_voy  = re.sub(r"[^A-Za-z0-9]", "_", str(voyage_no or "new"))
    ns = ns_key or f"ysp_{safe_yade}_{safe_voy}"

    store = st.session_state.setdefault("yade_sample_params", {})
    blk   = store.setdefault(ns, {"before": {}, "after": {}})

    st.subheader("🧫 Sample Parameters")
    st.caption("Temperature unit controls **both** Sample and Tank temperatures. Observed input switches API/Density limits.")

    col_b, col_a = st.columns(2, gap="large")

    def _block(stage_key: str, col):
        with col:
            st.markdown(f"#### {stage_key.title()}")
            obs_mode = st.selectbox(
                "Observed Input",
                ["Observed API", "Observed Density (kg/m³)"],
                index=0 if blk[stage_key].get("obs_mode", "Observed API").startswith("Observed API") else 1,
                key=f"{ns}_{stage_key}_obs_mode",
            )

            unit_label = st.selectbox(
                "Temperature Unit",
                ["°F", "°C"],
                index=0 if blk[stage_key].get("sample_unit", "F") == "F" else 1,
                key=f"{ns}_{stage_key}_unit",
            )
            ucode = _norm_unit(unit_label)
            tmin, tmax = _temp_bounds(ucode)

            c1, c2 = st.columns(2)
            with c1:
                sval = st.number_input(
                    f"Sample Temperature ({unit_label})",
                    min_value=tmin, max_value=tmax, step=0.1, format="%.1f",
                    value=float(blk[stage_key].get("sample_temp", 60.0 if ucode == "F" else 15.6)),
                    key=f"{ns}_{stage_key}_sample_temp",
                )
            with c2:
                tval = st.number_input(
                    f"Tank Temperature ({unit_label})",
                    min_value=tmin, max_value=tmax, step=0.1, format="%.1f",
                    value=float(blk[stage_key].get("tank_temp", 60.0 if ucode == "F" else 15.6)),
                    key=f"{ns}_{stage_key}_tank_temp",
                )

            omin, omax = _obs_bounds(obs_mode)
            obs_label = "Observed API" if "API" in obs_mode else "Observed Density (kg/m³)"
            oval = st.number_input(
                f"{obs_label} *",
                min_value=omin, max_value=omax, step=0.1,
                value=float(blk[stage_key].get("obs_val", (35.0 if "API" in obs_mode else 850.0))),
                key=f"{ns}_{stage_key}_obs_val",
            )

            c3, c4 = st.columns(2)
            with c3:
                ccf = st.number_input(
                    "Calibration Correction Factor (CCF)",
                    min_value=0.000001, value=float(blk[stage_key].get("ccf", 1.0)),
                    step=0.0001, format="%.4f",
                    key=f"{ns}_{stage_key}_ccf",
                )
            with c4:
                bsw = st.number_input(
                    "BS&W %",
                    min_value=0.0, max_value=100.0, step=0.01,
                    value=float(blk[stage_key].get("bsw_pct", 0.0)),
                    key=f"{ns}_{stage_key}_bsw",
                )

            # Save stage values
            blk[stage_key] = {
                "obs_mode": obs_mode,
                "obs_val": float(oval),
                "sample_unit": ucode,            # F/C for calculations if needed later
                "sample_unit_label": unit_label, # for display
                "sample_temp": float(sval),
                "tank_temp": float(tval),
                "tank_temp_unit": ucode,         # same as sample
                "ccf": float(ccf),
                "bsw_pct": float(bsw),
            }

    _block("before", col_b)
    _block("after",  col_a)

    # write back
    st.session_state["yade_sample_params"][ns] = blk


def _render_yade_dip_section(
    *,
    yade_no: str,
    design: str,
    operation: str,
    default_date: date,
    voy_id_for_prefill: Optional[int] = None,
    ns_key: Optional[str] = None,
):
    """
    Renders side-by-side 'Before …' and 'After …' dip sections.
    Stores values into st.session_state[ns_key] =
      {
        'before': {'date':..., 'time':'HH:MM', 'dips': {tid:{total_cm,water_cm}}},
        'after' : {'date':..., 'time':'HH:MM', 'dips': {tid:{total_cm,water_cm}}}
      }
    """
    if not yade_no or yade_no.startswith("-- No YADE Barges"):
        st.warning("⚠️ Add/select a YADE barge to enter dip details.")
        return

    ns = ns_key or f"yade_dips_{re.sub(r'[^A-Za-z0-9]', '_', yade_no)}"
    if ns not in st.session_state:
        st.session_state[ns] = {"before": {}, "after": {}}

    tank_ids, max_by = _get_barge_tanks_and_limits(yade_no, design)
    before_title, after_title = _resolve_op_labels(operation)

    # Prefill if editing
    existing = {"before": {}, "after": {}}
    if voy_id_for_prefill:
        with get_session() as s:
            existing = _load_existing_dips(s, voy_id_for_prefill)

    st.subheader("🧪 Dip Details")
    st.caption("All values are in **cm**. Each input is validated against the **maximum dip** from calibration.")

    # ---------- SIDE-BY-SIDE LAYOUT ----------
    col_before, col_after = st.columns(2, gap="large")

    with col_before:
        st.markdown(f"#### {before_title}")
        bc1, bc2 = st.columns(2)
        with bc1:
            before_date = st.date_input(
                "Gauging Date (Before)",
                value=st.session_state[ns].get("before", {}).get("date") or default_date,
                format="DD/MM/YYYY",
                key=f"{ns}_before_date",
            )
        with bc2:
            before_time = st.text_input(
                "Gauging Time (Before) (HH:MM)",
                value=st.session_state[ns].get("before", {}).get("time") or "07:30",
                key=f"{ns}_before_time",
            )

        st.caption("Enter **Total Dip** and **Water Dip** for each tank (cm).")
        dips_before = {}
        for tid in tank_ids:
            max_cm = float(max_by.get(tid, 9999.0))
            pre_tot = st.session_state[ns].get("before", {}).get("dips", {}).get(tid, {}).get(
                "total_cm",
                existing["before"].get(tid, {}).get("total_cm", 0.0),
            )
            pre_wat = st.session_state[ns].get("before", {}).get("dips", {}).get(tid, {}).get(
                "water_cm",
                existing["before"].get(tid, {}).get("water_cm", 0.0),
            )

            r1, r2, r3 = st.columns([0.22, 0.39, 0.39])
            with r1:
                st.text_input("Tank", value=tid, disabled=True, key=f"{ns}_before_tank_{tid}")
            with r2:
                tot = st.number_input(
                    "Total Dip (cm)",
                    min_value=0.0,
                    max_value=max_cm,
                    step=0.1,
                    value=float(pre_tot),
                    key=f"{ns}_before_total_{tid}",
                    help=f"Max **{max_cm:.1f} cm** (from calibration).",
                )
            with r3:
                wat = st.number_input(
                    "Water Dip (cm)",
                    min_value=0.0,
                    max_value=max_cm,
                    step=0.1,
                    value=float(pre_wat),
                    key=f"{ns}_before_water_{tid}",
                    help=f"Max **{max_cm:.1f} cm** (from calibration).",
                )
            dips_before[tid] = {"total_cm": float(tot or 0.0), "water_cm": float(wat or 0.0)}

        # Persist before into session
        st.session_state[ns]["before"] = {
            "date": before_date,
            "time": st.session_state.get(f"{ns}_before_time", "07:30"),
            "dips": dips_before,
        }

    with col_after:
        st.markdown(f"#### {after_title}")
        ac1, ac2 = st.columns(2)
        with ac1:
            after_date = st.date_input(
                "Gauging Date (After)",
                value=st.session_state[ns].get("after", {}).get("date") or default_date,
                format="DD/MM/YYYY",
                key=f"{ns}_after_date",
            )
        with ac2:
            after_time = st.text_input(
                "Gauging Time (After) (HH:MM)",
                value=st.session_state[ns].get("after", {}).get("time") or "17:30",
                key=f"{ns}_after_time",
            )

        st.caption("Enter **Total Dip** and **Water Dip** for each tank (cm).")
        dips_after = {}
        for tid in tank_ids:
            max_cm = float(max_by.get(tid, 9999.0))
            pre_tot = st.session_state[ns].get("after", {}).get("dips", {}).get(tid, {}).get(
                "total_cm",
                existing["after"].get(tid, {}).get("total_cm", 0.0),
            )
            pre_wat = st.session_state[ns].get("after", {}).get("dips", {}).get(tid, {}).get(
                "water_cm",
                existing["after"].get(tid, {}).get("water_cm", 0.0),
            )

            r1, r2, r3 = st.columns([0.22, 0.39, 0.39])
            with r1:
                st.text_input("Tank ", value=tid, disabled=True, key=f"{ns}_after_tank_{tid}")
            with r2:
                tot = st.number_input(
                    "Total Dip (cm) ",
                    min_value=0.0,
                    max_value=max_cm,
                    step=0.1,
                    value=float(pre_tot),
                    key=f"{ns}_after_total_{tid}",
                    help=f"Max **{max_cm:.1f} cm** (from calibration).",
                )
            with r3:
                wat = st.number_input(
                    "Water Dip (cm) ",
                    min_value=0.0,
                    max_value=max_cm,
                    step=0.1,
                    value=float(pre_wat),
                    key=f"{ns}_after_water_{tid}",
                    help=f"Max **{max_cm:.1f} cm** (from calibration).",
                )
            dips_after[tid] = {"total_cm": float(tot or 0.0), "water_cm": float(wat or 0.0)}

        # Persist after into session
        st.session_state[ns]["after"] = {
            "date": after_date,
            "time": st.session_state.get(f"{ns}_after_time", "17:30"),
            "dips": dips_after,
        }

def _render_yade_sample_params_section(
    *,
    yade_no: str,
    voyage_no: str | None,
    default_unit: str = "F",
    ns_key: Optional[str] = None,
):
    """
    Side-by-side 'Before' and 'After' Sample Parameters with dynamic validation,
    identical to Tank Entry behavior:
      - Temp unit drives allowed range for Sample/Tank temps (utils_calc.temp_bounds).
      - Observed selector (API vs Density) switches label, min/max, and help text LIVE.
      - API@60 computed using utils_calc (same path as Tank page).
    Stores values in st.session_state['yade_sample_params'][ns][stage].
    """
    if not yade_no or str(yade_no).startswith("-- No YADE Barges"):
        st.warning("⚠️ Select a YADE barge to enter sample parameters.")
        return

    safe_yade = re.sub(r"[^A-Za-z0-9]", "_", str(yade_no))
    safe_voy  = re.sub(r"[^A-Za-z0-9]", "_", str(voyage_no or "new"))
    ns = ns_key or f"yade_sp_{safe_yade}_{safe_voy}"

    store = st.session_state.setdefault("yade_sample_params", {})
    block = store.setdefault(ns, {"before": {}, "after": {}})

    st.subheader("🧪 Sample Parameters")
    st.caption("Observed selector controls the input field, label and limits. Temperature unit sets allowed ranges, same as Tank Entry.")

    col_before, col_after = st.columns(2, gap="large")

    def _stage(title: str, stage_key: str, col):
        with col:
            st.markdown(f"#### {title}")

            s1, s2 = st.columns([0.55, 0.45])
            with s1:
                obs_mode = st.selectbox(
                    "Observed Input",
                    ["Observed API", "Observed Density (kg/m³)"],
                    index=0 if (block[stage_key].get("obs_mode") in (None, "Observed API")) else 1,
                    key=f"{ns}_{stage_key}_obs_mode",
                    on_change=_st_safe_rerun,
                )
            with s2:
                unit_label = st.selectbox(
                    "Temperature Unit",
                    ["°F", "°C"],
                    index=0 if (block[stage_key].get("temp_unit") or default_unit).upper().startswith("F") else 1,
                    key=f"{ns}_{stage_key}_temp_unit_label",
                    on_change=_st_safe_rerun,
                )

            # Normalize for bounds (this flips 32–140 ↔ 0–60 dynamically)
            unit_code = _norm_unit(unit_label)
            tmin, tmax = _temp_bounds(unit_label)

            # Temperatures (Sample & Tank share the same unit/bounds)
            t1, t2 = st.columns(2)
            with t1:
                sample_temp = st.number_input(
                    f"Sample Temperature ({unit_label})",
                    min_value=tmin, max_value=tmax, step=0.1, format="%.1f",
                    value=float(block[stage_key].get("sample_temp", 60.0 if unit_code == "F" else 15.6)),
                    key=f"{ns}_{stage_key}_sample_temp",
                )
            with t2:
                tank_temp = st.number_input(
                    f"Tank Temperature ({unit_label})",
                    min_value=tmin, max_value=tmax, step=0.1, format="%.1f",
                    value=float(block[stage_key].get("tank_temp", 60.0 if unit_code == "F" else 15.6)),
                    key=f"{ns}_{stage_key}_tank_temp",
                )

            # Observed input (THIS flips the label and min/max dynamically)
            v1, v2 = st.columns([0.62, 0.38])
            if obs_mode == "Observed API":
                obs_val = v1.number_input(
                    "Observed API *",
                    min_value=15.0, max_value=70.0, step=0.1, format="%.1f",
                    value=float(block[stage_key].get("obs_val", 35.0)),
                    key=f"{ns}_{stage_key}_obs_api",
                    help="Allowed range: 15.0 – 70.0 API",
                )
                api60_val = api60_from_api_obs(float(obs_val or 0.0), float(sample_temp or 0.0), unit_label)
                approx_api = float(obs_val or 0.0)
                dens_obs   = density_from_api(approx_api) if approx_api > 0 else 0.0
            else:
                obs_val = v1.number_input(
                    "Observed Density (kg/m³) *",
                    min_value=600.0, max_value=1000.0, step=0.1, format="%.1f",
                    value=float(block[stage_key].get("obs_val", 850.0)),
                    key=f"{ns}_{stage_key}_obs_density",
                    help="Allowed range: 600 – 1000 kg/m³",
                )
                api60_val = api60_from_density_obs(float(obs_val or 0.0), float(sample_temp or 0.0), unit_label)
                dens_obs  = float(obs_val or 0.0)
                approx_api = api_from_density(dens_obs) if dens_obs > 0 else 0.0

            with v2:
                ccf = st.number_input(
                    "CCF",
                    min_value=0.000001, step=0.0001, format="%.4f",
                    value=float(block[stage_key].get("ccf", 1.0)),
                    key=f"{ns}_{stage_key}_ccf",
                    help="Calibration Correction Factor (default 1.0000).",
                )
                bsw_pct = st.number_input(
                    "BS&W %",
                    min_value=0.0, max_value=100.0, step=0.01, format="%.2f",
                    value=float(block[stage_key].get("bsw_pct", 0.0)),
                    key=f"{ns}_{stage_key}_bsw",
                )

            # Live display (same idea as Tank Entry)
            if obs_mode == "Observed API":
                st.caption(
                    f"→ API @ 60°F: **{api60_val:.2f}**   |   ↔ Approx Density: **{dens_obs:.1f} kg/m³**"
                )
            else:
                st.caption(
                    f"↔ Approx API: **{approx_api:.2f}**   |   → API @ 60°F: **{api60_val:.2f}**"
                )

            # Persist
            block[stage_key] = {
                "obs_mode": obs_mode,
                "obs_val": float(obs_val or 0.0),
                "temp_unit": unit_code,
                "temp_unit_label": unit_label,
                "sample_temp": float(sample_temp or 0.0),
                "tank_temp": float(tank_temp or 0.0),
                "ccf": float(ccf or 1.0),
                "bsw_pct": float(bsw_pct or 0.0),
                "api60_calc": float(api60_val or 0.0),
                "api_obs_approx": float(approx_api or 0.0),
                "density_obs": float(dens_obs or 0.0),
            }

    _stage("Before", "before", col_before)
    _stage("After",  "after",  col_after)

    st.session_state["yade_sample_params"][ns] = block

# ========================= YADE form (Entry / Edit tab) =========================
def _render_yade_form(location_id: int, loc_label: str, user: Dict[str, Any] | None, yade_cfg: Dict[str, Any]):
    if "yade_edit_id" not in st.session_state:
        st.session_state["yade_edit_id"] = None
    edit_id = st.session_state.get("yade_edit_id")

    # Master (YADE barges)
    barges = _load_yade_barges()
    barge_names = [b.name for b in barges]
    barge_design = {b.name: b.design for b in barges}

    # --- Pull dropdowns from Location Settings → Operations (asset='yade') ---
    with get_session() as s:
        cargo_opts = _list_names_from_ops(s, location_id, asset="yade", category="Cargo Type") or ["N/A"]
        dest_opts  = _list_names_from_ops(s, location_id, asset="yade", category="Destination") or ["N/A"]
        berth_opts = _list_names_from_ops(s, location_id, asset="yade", category="Loading Berth") or ["N/A"]
        # Your YADE operations live here too (category you configured for ops). If you used "Others" earlier, keep it:
        op_opts    = _list_names_from_ops(s, location_id, asset="yade", category="Others") or ["N/A"]

    # Prefill for edit
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

    st.subheader("🆕 YADE Voyage Entry")
    if voy:
        st.info(
            f"Editing voyage **#{voy.id}** — {voy.yade_name or 'N/A'} | "
            f"{voy.voyage_no or 'No'} on {voy.date or 'N/A'}"
        )

    # ===== Live Operation selector (outside the form so headings update immediately) =====
    c_op, _ = st.columns([1, 1])
    with c_op:
        # Initialize session value once when editing
        if voy and "yade_operation" not in st.session_state and getattr(voy, "operation", None):
            st.session_state["yade_operation"] = voy.operation if voy.operation in op_opts else (op_opts[0] if op_opts else "N/A")

        # Show the live control
        op_default_idx = 0
        if "yade_operation" in st.session_state and st.session_state["yade_operation"] in op_opts:
            op_default_idx = op_opts.index(st.session_state["yade_operation"])
        elif voy and getattr(voy, "operation", None) in op_opts:
            op_default_idx = op_opts.index(voy.operation)

        op_live = st.selectbox("Operation (live for Dip headings)", op_opts, index=op_default_idx, key="yade_operation")

    
    

    

    
    with st.form("yade_voyage_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            if not barge_names:
                yade_no = st.selectbox("YADE No *", ["-- No YADE Barges (add in Assets) --"], index=0)
                design = ""
            else:
                idx = 0
                if voy and voy.yade_name in barge_names:
                    idx = barge_names.index(voy.yade_name)
                yade_no = st.selectbox("YADE No *", barge_names, index=idx)
                design = barge_design.get(yade_no, "")

        with c2:
            voyage_no = st.text_input("Voyage No.", value=(voy.voyage_no or "") if voy else "")
            convoy_no = st.text_input("Convoy No. (digits & '-' only)", value=(voy.convoy_no or "") if voy else "")

        with c3:
            tx_date = st.date_input(
                "Date (DD/MM/YYYY)",
                value=voy.date if (voy and voy.date) else date.today(),
                format="DD/MM/YYYY",
            )
            default_time = voy.time.strftime("%H:%M") if (voy and voy.time) else "08:00"
            tx_time = st.text_input("Time (HH:MM)", value=default_time)

        c5, c6, c7 = st.columns(3)
        with c5:
            cargo_idx = cargo_opts.index(voy.cargo) if (voy and voy.cargo in cargo_opts) else 0
            cargo = st.selectbox("Cargo", cargo_opts, index=cargo_idx)
        with c6:
            dest_idx = dest_opts.index(voy.destination) if (voy and voy.destination in dest_opts) else 0
            destination = st.selectbox("Destination", dest_opts, index=dest_idx)
        with c7:
            berth_idx = berth_opts.index(voy.loading_berth) if (voy and voy.loading_berth in berth_opts) else 0
            loading_berth = st.selectbox("Loading Berth", berth_opts, index=berth_idx)

        st.caption(f"📍 Location: **{loc_label}**")
        st.markdown("---")

        save_btn = st.form_submit_button("💾 Save Header", type="primary")

    # Render DIP and Sample Parameters outside the form for live interactivity
    op_current = st.session_state.get("yade_operation", op_live)
    voy_id_for_prefill = voy.id if voy else None
    ns_key = f"dips_{re.sub(r'[^A-Za-z0-9]', '_', str(yade_no))}_{re.sub(r'[^A-Za-z0-9]', '_', str(voyage_no or 'new'))}"

    _render_yade_dip_section(
        yade_no=yade_no,
        design=str(design),
        operation=op_current,
        default_date=tx_date,
        voy_id_for_prefill=voy_id_for_prefill,
        ns_key=ns_key,
    )

    _render_yade_sample_params_section(
        yade_no=yade_no,
        voyage_no=voyage_no,
        default_unit="F",
        ns_key=f"sp_{re.sub(r'[^A-Za-z0-9]', '_', str(yade_no))}_{re.sub(r'[^A-Za-z0-9]', '_', str(voyage_no or 'new'))}",
    )
    st.markdown("---")

    if not save_btn:
        return

    # Minimal validation
    def _hhmm_ok(s: str) -> bool:
        try:
            datetime.strptime(s, "%H:%M")
            return True
        except Exception:
            return False

    if tx_time and not _hhmm_ok(tx_time):
        st.error("Time must be in HH:MM (24-hour) format.")
        return

    # Save / update (header only for now; dips are cached in session and will be persisted in the next step)
    try:
        with get_session() as s:
            current_user = (st.session_state.get("auth_user") or {}).get("username", "unknown")
            current_user_id = (st.session_state.get("auth_user") or {}).get("id")
            op_selected = st.session_state.get("yade_operation", "N/A")

            if voy:
                voy.yade_name = yade_no
                voy.design = str(design)
                voy.voyage_no = voyage_no.strip()
                voy.convoy_no = (convoy_no or "").strip()
                voy.date = tx_date
                voy.time = datetime.strptime(tx_time, "%H:%M").time() if tx_time else None
                voy.cargo = cargo
                voy.destination = destination
                voy.loading_berth = loading_berth
                setattr(voy, "operation", op_selected)  # kept on object; persist if you add column later
                voy.updated_by = current_user
                voy.updated_at = datetime.utcnow()
                voyage_id = voy.id
                action = "UPDATE"
            else:
                new_v = YadeVoyage(
                    location_id=location_id,
                    yade_name=yade_no,
                    design=str(design),
                    voyage_no=voyage_no.strip(),
                    convoy_no=(convoy_no or "").strip(),
                    date=tx_date,
                    time=datetime.strptime(tx_time, "%H:%M").time() if tx_time else None,
                    cargo=cargo,
                    destination=destination,
                    loading_berth=loading_berth,
                    created_by=current_user,
                    created_at=datetime.utcnow(),
                )
                setattr(new_v, "operation", op_selected)
                s.add(new_v)
                s.flush()
                voyage_id = new_v.id
                action = "CREATE"

            s.commit()

            try:
                SecurityManager.log_audit(
                    None,
                    username=current_user,
                    action=action,
                    resource_type="YadeVoyage",
                    resource_id=str(voyage_id),
                    details=f"{action} YADE voyage header: {yade_no} - Voyage {voyage_no}",
                    user_id=current_user_id,
                    location_id=location_id,
                    ip_address=st.session_state.get("client_ip", "N/A"),
                    success=True,
                )
            except Exception:
                pass

        st.success(f"✅ YADE Voyage header saved for {yade_no} — Voyage {voyage_no}")
        _st_safe_rerun()

    except Exception as ex:
        log_error(f"Save YADE voyage header failed: {ex}", exc_info=True)
        _audit_error(f"Save YADE voyage header failed: {ex}", user, location_id)
        st.error("Failed to save YADE Voyage header. (Logged)")


# ========================= YADE list (Voyages List tab) =========================
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
            rows = (
                s.query(YadeVoyage)
                .filter(YadeVoyage.location_id == location_id)
                .filter(YadeVoyage.date >= from_date)
                .filter(YadeVoyage.date <= to_date)
                .order_by(YadeVoyage.date.desc(), YadeVoyage.id.desc())
                .all()
            )
    except Exception as ex:
        _audit_error(f"Load YADE voyages failed: {ex}", user, location_id)
        st.error("Failed to load YADE voyages. (Logged)")
        return

    if not rows:
        st.info("No YADE voyages found in the selected date range.")
    else:
        st.caption(f"Total voyages: **{len(rows)}**")

    for v in rows:
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


# ========================= main entry point =========================
def render_yade_transactions_page(active_location_id: int | None, user: Dict[str, Any] | None):
    try:
        header("Yade Transactions")

        loc, loc_label = _guard_location(active_location_id)
        if not loc:
            return
        if not _guard_permissions(user, active_location_id):
            return

        with get_session() as s:
            cfg = LocationConfig.get_config(s, loc.id)
        if not (cfg.get("page_visibility", {}) or {}).get("show_yade_transactions", False):
            st.warning(f"YADE Transactions page is disabled for **{loc_label}**.")
            return

        yade_cfg = cfg.get("yade_transactions", {}) or {}
        st.caption(f"📍 Active Location: **{loc_label}**")

        tab_entry, tab_list = st.tabs(["🆕 Entry / Edit", "📜 Voyages List"])
        with tab_entry:
            _render_yade_form(loc.id, loc_label, user, yade_cfg)
        with tab_list:
            _render_yade_list(loc.id, user)

    except Exception as ex:
        _audit_error(f"Render YADE page failed: {ex}", user, active_location_id)
        st.error("Unexpected error while rendering YADE Transactions. (Logged)")
