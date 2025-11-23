# utils_calc.py
import math
from typing import Optional, Tuple
import pandas as pd
from sqlalchemy.orm import Session

from models import CalibrationTank, Table11


# =========================
# Linear interpolation utils
# =========================
def _interp(x1, y1, x2, y2, x):
    """Simple linear interpolation between (x1,y1) and (x2,y2) for x."""
    if float(x2) == float(x1):
        return float(y1)
    return float(y1) + (float(x) - float(x1)) * (float(y2) - float(y1)) / (float(x2) - float(x1))


def _two_point(df: pd.DataFrame, xcol: str, ycol: str, x: float) -> float:
    """
    Look up bounding points around x and interpolate.
    If x is out of range, clamp to nearest endpoint.
    """
    if df.empty:
        raise ValueError("No data for interpolation")
    df = df.sort_values(xcol)

    lower = df[df[xcol] <= x].tail(1)
    upper = df[df[xcol] >= x].head(1)

    if lower.empty and upper.empty:
        raise ValueError("No data points for interpolation")

    if lower.empty:
        return float(upper[ycol].values[0])
    if upper.empty:
        return float(lower[ycol].values[0])

    x1, y1 = float(lower[xcol].values[0]), float(lower[ycol].values[0])
    x2, y2 = float(upper[xcol].values[0]), float(upper[ycol].values[0])
    return _interp(x1, y1, x2, y2, float(x))


# =========================
# Tank calibration lookups
# =========================
def tank_volume_from_dip_cm(sess: Session, tank_name: str, dip_cm: float) -> float:
    """
    Interpolate TOV (bbl) from calibration by dip_cm.
    Uses same dip->volume curve for both product and water heights.
    """
    rows = (
        sess.query(CalibrationTank)
        .filter(CalibrationTank.tank_name == tank_name)
        .all()
    )
    if not rows:
        raise ValueError(f"No tank calibration for {tank_name}")
    df = pd.DataFrame(
        [{"dip_cm": r.dip_cm, "volume_bbl": r.volume_bbl} for r in rows]
    ).sort_values("dip_cm")
    return float(_two_point(df, "dip_cm", "volume_bbl", float(dip_cm or 0.0)))


def free_water_from_water_cm(sess: Session, tank_name: str, water_cm: float) -> float:
    """FW (bbl) from water dip (cm) using the same calibration curve."""
    if water_cm is None or float(water_cm) <= 0:
        return 0.0
    return tank_volume_from_dip_cm(sess, tank_name, float(water_cm))


# =========================
# Physical constants / helpers
# =========================
WAT60 = 999.012  # kg/m3 (water @60°F)

_TEMP_LIMITS = {
    "C": (0.0, 60.0),
    "F": (32.0, 140.0),
}

def normalize_temp_unit(unit: Optional[str]) -> str:
    """Normalize '°C'/'C'/'c' or '°F'/'F' to 'C' or 'F'."""
    label = (unit or "").strip().upper().replace("°", "")
    return "F" if label.startswith("F") else "C"

def temp_bounds(unit: Optional[str]) -> Tuple[float, float]:
    return _TEMP_LIMITS.get(normalize_temp_unit(unit), _TEMP_LIMITS["C"])

def bounded_temp(val: float, unit: Optional[str]) -> float:
    lo, hi = temp_bounds(unit)
    v = float(val or 0.0)
    if v < lo: return lo
    if v > hi: return hi
    return v

def _to_f(c_or_f: float, is_celsius: bool) -> float:
    return (float(c_or_f) * 1.8) + 32.0 if is_celsius else float(c_or_f)

def c_to_f(c: float) -> float:
    return (float(c) * 1.8) + 32.0

def f_to_c(f: float) -> float:
    return (float(f) - 32.0) / 1.8


# =========================
# API / Density converters
# =========================
def density_from_api(api: float) -> float:
    """
    Approx density at 60°F from API.
    density = SG * water60, where SG = 141.5 / (API + 131.5)
    """
    api = float(api or 0.0)
    if api <= 0:
        return 0.0
    sg = 141.5 / (api + 131.5)
    return round(sg * WAT60, 1)

def api_from_density(density: float) -> float:
    """
    Approx API from density at 60°F.
    SG = density / water60; API = 141.5/SG - 131.5
    """
    dens = float(density or 0.0)
    if dens <= 0:
        return 0.0
    sg = dens / WAT60
    if sg <= 0:
        return 0.0
    return round(141.5 / sg - 131.5, 2)


# =========================
# VCF (ASTM Table 6A–style)
# =========================
def calculate_vcf(api60: float, temp_f: float) -> float:
    """
    VCF from API@60 and tank temperature (°F):
      alpha = 341.0957 / rho60^2
      vcf   = exp(-alpha*ΔT - 0.8*alpha^2*ΔT^2)
    """
    api60 = float(api60 or 0.0)
    if api60 <= 0:
        raise ValueError("API gravity must be positive")

    temp_diff = float(temp_f) - 60.0
    rho60 = (141.5 * WAT60) / (api60 + 131.5)
    alpha = 341.0957 / (rho60 * rho60)
    vcf = math.exp(-alpha * temp_diff - 0.8 * alpha * alpha * temp_diff * temp_diff)
    return round(float(vcf), 5)

def vcf_from_api60_and_tank_temp(api60: float, tank_temp: float, tank_unit: str) -> float:
    """
    Convenience wrapper: accepts tank temp in °C/°F and returns VCF.
    """
    unit = normalize_temp_unit(tank_unit)
    temp_f = float(tank_temp or 0.0) if unit == "F" else c_to_f(float(tank_temp or 0.0))
    return calculate_vcf(float(api60 or 0.0), temp_f)


# =========================
# LT factor from Table 11
# =========================
def get_lt_factor(sess: Session, api60: float) -> float:
    """Linear interpolation over Table11(api60, lt_factor)."""
    rows = sess.query(Table11).order_by(Table11.api60).all()
    if not rows:
        raise ValueError("Table11 is empty. Please import data.")
    df = pd.DataFrame([{"api60": r.api60, "lt_factor": r.lt_factor} for r in rows]).sort_values("api60")
    return float(_two_point(df, "api60", "lt_factor", float(api60)))


# =========================
# API/Density conversions to API@60
# =========================
def api_observed_to_api60(api_obs: float, temp_obs_f: float) -> float:
    """
    Observed API @ sample temp(°F) -> API@60°F (iterative).
    """
    api_obs = float(api_obs or 0.0)
    tf = float(temp_obs_f or 60.0)
    temp_diff = tf - 60.0

    rho_obs = (141.5 * WAT60 / (131.5 + api_obs)) * (
        (1.0 - 0.00001278 * temp_diff) - (0.0000000062 * temp_diff * temp_diff)
    )

    RH = rho_obs
    for _ in range(10):
        alfa = 341.0957 / (RH * RH)
        vcf = math.exp(-alfa * temp_diff - 0.8 * alfa * alfa * temp_diff * temp_diff)
        RH = rho_obs / vcf

    api60 = 141.5 * WAT60 / RH - 131.5
    return float(api60)


def density_obs_to_api60(density_obs: float, sample_temp_c: float) -> Tuple[float, float]:
    """
    Observed Density(kg/m3) @ sample temp(°C) -> (API@60°F, density@15°C).
    Uses hydrocarbon thermal correction:
      hyc = (1 - 0.00001278*ΔT) - (0.0000000062*ΔT^2), ΔT = T°C - 15
    Iterative rho15 loop (17 iterations).
    """
    dens = float(density_obs or 0.0)
    t_c = float(sample_temp_c or 15.0)
    dt = t_c - 15.0

    hyc = (1.0 - 0.00001278 * dt) - (0.0000000062 * dt * dt)
    rho_obs_corr = dens * hyc

    rho15 = rho_obs_corr
    for _ in range(17):
        K = 613.9723 / (rho15 * rho15)
        vcf = math.exp(-K * dt * (1.0 + 0.8 * K * dt))
        rho15 = rho_obs_corr / vcf

    density15 = rho15
    sg60 = density15 / WAT60 if WAT60 > 0 else 0.0
    api60 = 141.5 / sg60 - 131.5 if sg60 > 0 else 0.0

    return float(api60), float(density15)


# ---- Compatibility aliases (to keep older calls working) ----
def api60_from_api_obs(api_obs: float, sample_temp: float, sample_unit: str) -> float:
    """Old signature wrapper for API observed route."""
    unit = normalize_temp_unit(sample_unit)
    temp_f = float(sample_temp or 0.0) if unit == "F" else c_to_f(float(sample_temp or 0.0))
    return api_observed_to_api60(float(api_obs or 0.0), temp_f)

def api60_from_density_obs(density_obs: float, sample_temp: float, sample_unit: str) -> float:
    """Old signature wrapper for density observed route (returns api60 only)."""
    unit = normalize_temp_unit(sample_unit)
    temp_c = float(sample_temp or 0.0) if unit == "C" else f_to_c(float(sample_temp or 0.0))
    api60, _density15 = density_obs_to_api60(float(density_obs or 0.0), temp_c)
    return api60


# =========================
# Small building-block helpers (used by pages)
# =========================
def gsv_from_gov_vcf(gov_bbl: float, vcf: float) -> int:
    """GSV = round(GOV * VCF, 0)."""
    gov = max(float(gov_bbl or 0.0), 0.0)
    v   = max(float(vcf or 1.0), 0.0)
    return int(round(gov * v, 0))

def bsw_volume_from_gsv_pct(gsv_bbl: float, bsw_pct: float) -> int:
    """BSW volume (bbl) from GSV and BS&W %, with bounds [0, 100]."""
    gsv = max(float(gsv_bbl or 0.0), 0.0)
    pct = float(bsw_pct or 0.0)
    if pct < 0.0: pct = 0.0
    if pct > 100.0: pct = 100.0
    return int(round(gsv * (pct / 100.0), 0))

def nsv_from_gsv_bsw(gsv_bbl: float, bsw_bbl: float) -> int:
    """NSV = round(GSV - BSW, 0), clamped to ≥ 0."""
    gsv = max(float(gsv_bbl or 0.0), 0.0)
    bsw = max(float(bsw_bbl or 0.0), 0.0)
    return max(int(round(gsv - bsw, 0)), 0)

def nsv_from_gsv_bsw_pct(gsv_bbl: float, bsw_pct: float) -> int:
    """NSV from GSV and BS&W % (does GSV*% first, then subtract)."""
    bsw_bbl = bsw_volume_from_gsv_pct(gsv_bbl, bsw_pct)
    return nsv_from_gsv_bsw(gsv_bbl, bsw_bbl)


def lt_from_nsv_api(sess: Session, nsv_bbl: float, api60: float) -> Tuple[int, float]:
    """Returns (LT, lt_factor) where LT = round(NSV * lt_factor, 0)."""
    lf = float(get_lt_factor(sess, float(api60 or 0.0))) if float(api60 or 0.0) > 0 else 0.0
    lt = int(round(float(nsv_bbl or 0.0) * lf, 0))
    return lt, lf

def mt_from_lt(lt_bbl: float) -> int:
    """MT = round(LT * 1.01605, 0)."""
    return int(round(float(lt_bbl or 0.0) * 1.01605, 0))

# --- Direct MT from (GSV, API@60) using Table 11 + 1.01605 ---
def mass_mt_from_gsv_api60(gsv_bbl: float, api60: float) -> int:
    """
    Compute MT directly from GSV and API@60 by:
      LT_factor = Table11(API@60)
      LT        = GSV * LT_factor
      MT        = round(LT * 1.01605, 0)
    Note: uses Table 11 from DB for the LT factor. If DB not available, returns 0.
    """
    try:
        # lazy import to avoid circulars if utils_calc is imported early
        from db import get_session  # type: ignore
        with get_session() as _s:
            lf = float(get_lt_factor(_s, float(api60 or 0.0))) if float(api60 or 0.0) > 0 else 0.0
    except Exception:
        lf = 0.0
    lt_val = float(gsv_bbl or 0.0) * lf
    return int(round(lt_val * 1.01605, 0))

def mass_lt_from_mt(mt_bbl: float) -> int:
    """LT from MT: LT = round(MT / 1.01605, 0)."""
    return int(round(float(mt_bbl or 0.0) / 1.01605, 0))
# =========================
# Driver: compute all for Tank Tx
# =========================
def compute_all_for_tank_tx(
    sess: Session,
    *,
    tank_name: str,
    dip_cm: float,
    water_cm: float,
    tank_temp_c: Optional[float],
    tank_temp_f: Optional[float],
    api_observed: Optional[float],
    density_observed: Optional[float],
    sample_temp_c: Optional[float],
    sample_temp_f: Optional[float],
    bsw_pct: Optional[float],
) -> dict:
    """
    Core calculation (shared by Tanks / YADE / Tankers):
      - TOV/FW/GOV from calibration
      - API@60 from observed API(°F sample) or observed Density(°C sample)
      - VCF from API@60 and tank temp (°F)
      - GSV = round(GOV * VCF, 0)
      - BS&W vol = round(GSV * bsw%, 0)
      - NSV = round(GSV - BS&W, 0)
      - LT via Table11(api60); LT = round(NSV * lt_factor, 0)
      - MT = round(LT * 1.01605, 0)
    Returns ints for stock/mass to match reporting.
    """
    # 1) TOV / FW / GOV
    TOV = tank_volume_from_dip_cm(sess, tank_name, float(dip_cm or 0.0))
    FW = free_water_from_water_cm(sess, tank_name, float(water_cm or 0.0))
    GOV = max(TOV - FW, 0.0)

    # 2) API@60 route
    api60 = 0.0
    density15 = 0.0
    if (api_observed or 0) > 0 and (sample_temp_f or 0) > 0:
        api60 = api_observed_to_api60(float(api_observed), float(sample_temp_f))
    elif (density_observed or 0) > 0 and (sample_temp_c or 0) > 0:
        api60, density15 = density_obs_to_api60(float(density_observed), float(sample_temp_c))
    else:
        api60 = 0.0

    # 3) Tank temp in °F for VCF
    if tank_temp_f is None and tank_temp_c is not None:
        tank_temp_f = (float(tank_temp_c) * 1.8) + 32.0
    tank_temp_f = float(tank_temp_f or 60.0)

    # 4) VCF
    vcf = calculate_vcf(float(api60), float(tank_temp_f)) if api60 and api60 > 0 else 1.0

    # 5) GSV / BSW / NSV
    GSV = gsv_from_gov_vcf(GOV, vcf)
    bsw_vol = bsw_volume_from_gsv_pct(GSV, float(bsw_pct or 0.0))
    NSV = nsv_from_gsv_bsw(GSV, bsw_vol)

    # 6) LT / MT
    LT, lt_factor = lt_from_nsv_api(sess, NSV, api60)
    MT = mt_from_lt(LT)

    return {
        "TOV": float(TOV),
        "FW": float(FW),
        "GOV": float(GOV),
        "api60": float(api60 or 0.0),
        "density15": float(density15 or 0.0),
        "vcf": float(vcf),
        "GSV": int(GSV),
        "bsw_vol": int(bsw_vol),
        "NSV": int(NSV),
        "lt_factor": float(lt_factor or 0.0),
        "LT": int(LT),
        "MT": int(MT),
    }
