# yade_toa_calculator.py
"""
YADE TOA (Transfer of Account) Calculator
Calculates volume and quality metrics for YADE voyages
"""

from sqlalchemy.orm import Session
from typing import Dict, List
import math

def calculate_yade_toa(
    yade_name: str,
    dip_data: Dict,
    sample_data: Dict,
    session: Session
) -> Dict:
    """
    Calculate TOA for a YADE voyage
    
    Args:
        yade_name: Name of YADE barge
        dip_data: {"before": {tank_id: {total_cm, water_cm}}, "after": {...}}
        sample_data: {"before": {params}, "after": {params}}
        session: Database session
    
    Returns:
        {
            "before": {gov_bbl, gsv_bbl, bsw_pct, bsw_bbl, nsv_bbl, lt, mt, fw_bbl},
            "after": {...},
            "loaded": {...}
        }
    """
    from models import YadeCalibration
    
    try:
        # Calculate for before and after stages
        results = {}
        
        for stage in ["before", "after"]:
            stage_dips = dip_data.get(stage, {})
            stage_params = sample_data.get(stage, {})
            
            # Get all tank volumes
            total_gov = 0.0
            total_fw = 0.0
            
            for tank_id, dips in stage_dips.items():
                total_cm = dips.get("total_cm", 0.0)
                water_cm = dips.get("water_cm", 0.0)
                
                # Interpolate volumes from calibration
                total_vol_bbl = interpolate_yade_volume(
                    session, yade_name, tank_id, total_cm * 10  # Convert cm to mm
                )
                water_vol_bbl = interpolate_yade_volume(
                    session, yade_name, tank_id, water_cm * 10
                )
                
                gov = total_vol_bbl - water_vol_bbl
                total_gov += gov
                total_fw += water_vol_bbl
            
            # Get quality parameters
            bsw_pct = float(stage_params.get("bsw_pct", 0.0))
            tank_temp = float(stage_params.get("tank_temp", 60.0))
            sample_temp = float(stage_params.get("sample_temp", 60.0))
            obs_val = float(stage_params.get("obs_val", 0.0))
            obs_mode = stage_params.get("obs_mode", "API")
            ccf = float(stage_params.get("ccf", 1.0))
            
            # Calculate API@60
            if obs_mode == "Observed API" or "API" in obs_mode:
                api60 = convert_api_to_60(obs_val, sample_temp, "API")
            else:
                api60 = convert_density_to_api60(obs_val, sample_temp)
            
            # Calculate VCF
            vcf = calculate_vcf(api60, tank_temp)
            
            # Apply CCF
            vcf = vcf * ccf
            
            # Calculate volumes
            gsv_bbl = total_gov * vcf
            bsw_bbl = gsv_bbl * (bsw_pct / 100.0)
            nsv_bbl = gsv_bbl - bsw_bbl
            
            # Calculate LT factor
            lt_factor = lookup_lt_factor(session, api60)
            
            # Calculate weight
            lt_tons = nsv_bbl * lt_factor
            mt_tons = lt_tons * 1.01605
            
            results[stage] = {
                "gov_bbl": round(total_gov, 2),
                "gsv_bbl": round(gsv_bbl, 2),
                "bsw_pct": round(bsw_pct, 2),
                "bsw_bbl": round(bsw_bbl, 2),
                "nsv_bbl": round(nsv_bbl, 2),
                "lt": round(lt_factor, 4),
                "mt": round(mt_tons, 2),
                "fw_bbl": round(total_fw, 2),
            }
        
        # Calculate loaded values (difference)
        loaded = {
            "gov_bbl": results["after"]["gov_bbl"] - results["before"]["gov_bbl"],
            "gsv_bbl": results["after"]["gsv_bbl"] - results["before"]["gsv_bbl"],
            "nsv_bbl": results["after"]["nsv_bbl"] - results["before"]["nsv_bbl"],
        }
        
        results["loaded"] = loaded
        
        return results
    
    except Exception as e:
        print(f"⚠️  TOA calculation error: {e}")
        import traceback
        traceback.print_exc()
        return None


def interpolate_yade_volume(session: Session, yade_name: str, tank_id: str, dip_mm: float) -> float:
    """Linear interpolation for YADE volume from calibration data"""
    from models import YadeCalibration
    
    cal_data = session.query(YadeCalibration).filter(
        YadeCalibration.yade_name == yade_name,
        YadeCalibration.tank_id == tank_id
    ).order_by(YadeCalibration.dip_mm.asc()).all()
    
    if not cal_data:
        return 0.0
    
    xs = [float(c.dip_mm) for c in cal_data]
    ys = [float(c.vol_bbl) for c in cal_data]
    
    if dip_mm <= xs[0]:
        return ys[0]
    if dip_mm >= xs[-1]:
        return ys[-1]
    
    import bisect
    i = bisect.bisect_left(xs, dip_mm)
    x1, y1 = xs[i-1], ys[i-1]
    x2, y2 = xs[i], ys[i]
    
    if x2 == x1:
        return y1
    
    t = (dip_mm - x1) / (x2 - x1)
    return y1 + t * (y2 - y1)


def convert_api_to_60(api_obs: float, temp: float, temp_unit: str = "F") -> float:
    """Convert observed API to API@60"""
    WAT60 = 999.012
    
    if not api_obs or api_obs <= 0:
        return 0.0
    
    # Convert to Fahrenheit if needed
    if temp_unit.upper().startswith("C"):
        temp_f = (temp * 1.8) + 32.0
    else:
        temp_f = temp
    
    temp_diff = temp_f - 60.0
    
    # Initial density calculation
    rho_obs = (141.5 * WAT60 / (131.5 + api_obs)) * (
        (1.0 - 0.00001278 * temp_diff) - (0.0000000062 * temp_diff * temp_diff)
    )
    
    # Iterative correction (10 iterations)
    rho = rho_obs
    for _ in range(10):
        alfa = 341.0957 / (rho * rho)
        vcf = math.exp(-alfa * temp_diff - 0.8 * alfa * alfa * temp_diff * temp_diff)
        rho = rho_obs / vcf
    
    api60 = 141.5 * WAT60 / rho - 131.5
    return round(api60, 2)


def convert_density_to_api60(density: float, temp: float, temp_unit: str = "C") -> float:
    """Convert observed density to API@60"""
    WAT60 = 999.012
    
    if not density or density <= 0:
        return 0.0
    
    # Convert to Celsius if needed
    if temp_unit.upper().startswith("F"):
        temp_c = (temp - 32.0) / 1.8
    else:
        temp_c = temp
    
    temp_diff = temp_c - 15.0
    
    # Hydrometer correction
    hyc = 1.0 - 0.000023 * temp_diff - 0.00000002 * temp_diff * temp_diff
    rho_obs_corrected = density * hyc
    
    # Iterative VCF calculation (17 iterations)
    rho15 = rho_obs_corrected
    for _ in range(17):
        K = 613.9723 / (rho15 * rho15)
        vcf = math.exp(-K * temp_diff * (1.0 + 0.8 * K * temp_diff))
        rho15 = rho_obs_corrected / vcf
    
    sg60 = rho15 / WAT60
    if sg60 <= 0:
        return 0.0
    
    api60 = 141.5 / sg60 - 131.5
    return round(api60, 2)


def calculate_vcf(api60: float, tank_temp: float, temp_unit: str = "F") -> float:
    """Calculate VCF using ASTM D1250 Table 6A method"""
    if not api60 or api60 <= 0:
        return 1.00000
    
    # Convert to Fahrenheit if needed
    if temp_unit.upper().startswith("C"):
        tank_temp_f = (tank_temp * 1.8) + 32.0
    else:
        tank_temp_f = tank_temp
    
    delta_t = tank_temp_f - 60.0
    
    if abs(delta_t) < 0.01:
        return 1.00000
    
    sg60 = 141.5 / (api60 + 131.5)
    rho60 = sg60 * 999.012
    
    K0 = 341.0957
    alpha = K0 / (rho60 * rho60)
    
    vcf = math.exp(-alpha * delta_t * (1.0 + 0.8 * alpha * delta_t))
    
    return round(float(vcf), 5)


def lookup_lt_factor(session: Session, api60: float) -> float:
    """Lookup LT factor from ASTM Table 11"""
    from models import Table11
    
    rows = session.query(Table11).order_by(Table11.api60).all()
    if not rows:
        return 0.0
    
    xs = [float(r.api60) for r in rows]
    ys = [float(r.lt_factor) for r in rows]
    
    if api60 <= xs[0]:
        return ys[0]
    if api60 >= xs[-1]:
        return ys[-1]
    
    import bisect
    i = bisect.bisect_left(xs, api60)
    x1, y1 = xs[i-1], ys[i-1]
    x2, y2 = xs[i], ys[i]
    
    if x2 == x1:
        return y1
    
    t = (api60 - x1) / (x2 - x1)
    return y1 + t * (y2 - y1)