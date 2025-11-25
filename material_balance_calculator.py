# material_balance_calculator.py
"""
Material Balance Calculator for Tank Transactions (location-aware from OTR)

Window per day: 06:01 (D) to 06:00 (D+1)

AGGU:
  Date, Opening Stock, Receipt, Dispatch, Book closing stock, Closing stock, Loss/Gain
BFS:
  Date, Opening Stock, Receipt-Commingled, Receipt-Condensate, Dispatch to Jetty, Book closing stock, Closing stock, Loss/Gain
NDONI:
  Date, Opening Stock, Receipt from Agu, Receipt from OFS, Other Receipts, Dispatch to barge, Book closing stock, Closing stock, Loss/Gain
UTAPATE:
  Date, Opening Stock, Receipt, Dispatch, Book closing stock, Closing stock, Loss/Gain
ASEMOKU JETTY (JETTY):
  Date, Opening stock, OKW Receipt, ANZ receipt, Other receipts, Dispatch to barge, Other dispatch, Book closing stock, Closing stock, Loss/Gain

Rules:
- Opening Stock (first day): SUM(NSV) of the FIRST entry of EACH tank within the window (06:01→06:00).
  Subsequent days: previous day's Closing Stock (continuity).
- “Receipt” / “Dispatch” columns are sums of **Net Rece/Disp (bbls)** recorded on OTR entries that match each column’s operations.
- Book Closing = Opening + (sum receipts cols) − (sum dispatch cols)
- Closing Stock = SUM(NSV) per tank using explicit 'Closing Stock' entries when available,
  otherwise the last transaction NSV within the window.
- Loss/Gain = Closing Stock − Book Closing
"""

from __future__ import annotations
from datetime import datetime, timedelta, time as dt_time
import ast
from typing import Iterable, List, Dict, Any, Optional

M3_TO_BBL = 6.289
DEFAULT_MB_START_TIME = dt_time(6, 1)
DEFAULT_MB_END_TIME = dt_time(6, 0)

try:
    from db import get_session
    from models import OTRRecord, TankTransaction, Operation
except Exception:
    get_session = None      # type: ignore
    OTRRecord = None        # type: ignore
    TankTransaction = None  # type: ignore
    Operation = None        # type: ignore

try:
    # Optional per-location Material Balance window configuration
    from location_config import get_page_section_config as _get_mb_page_cfg
    from location_config import list_operations as _list_ops
except Exception:
    _get_mb_page_cfg = None  # type: ignore
    _list_ops = None  # type: ignore


# ---------- normalization helpers ----------
def _is_iterable_entries(obj) -> bool:
    return isinstance(obj, (list, tuple))


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _norm_location(code: str) -> str:
    c = _norm_text(code)
    # Map common aliases to canonical codes used in logic
    if c in {"asemoku", "asemoku jetty", "jetty"}:
        return "JETTY"
    if c in {"aggu"}:
        return "AGGU"
    if c in {"bfs", "beneku"}:
        return "BFS"
    if c in {"ndoni"}:
        return "NDONI"
    if c in {"utapate", "oml-13", "oml13"}:
        return "UTAPATE"
    return (code or "").upper()


def _mb_window_for_location(location_id: Optional[int]) -> tuple[dt_time, dt_time]:
    """
    Resolve per-location Material Balance window.
    Falls back to 06:01 (D) to 06:00 (D/ D+1) if no custom config.
    """
    start_time = DEFAULT_MB_START_TIME
    end_time = DEFAULT_MB_END_TIME

    if location_id is None or _get_mb_page_cfg is None or get_session is None:
        return start_time, end_time

    try:
        with get_session() as s:
            cfg = _get_mb_page_cfg(s, int(location_id), page="material_balance", section="window") or {}
    except Exception:
        cfg = {}

    if not cfg or not cfg.get("use_custom_window"):
        return start_time, end_time

    def _parse_time(val: Any, default: dt_time) -> dt_time:
        try:
            txt = str(val or "").strip()
            if not txt:
                return default
            parts = [int(p) for p in txt.split(":")]
            if len(parts) == 2:
                h, m = parts
                return dt_time(h, m)
            if len(parts) >= 3:
                h, m, s = parts[0], parts[1], parts[2]
                return dt_time(h, m, s)
        except Exception:
            return default
        return default

    start_time = _parse_time(cfg.get("start_time"), start_time)
    end_time = _parse_time(cfg.get("end_time"), end_time)
    return start_time, end_time

from sqlalchemy import func
from models import TankTransaction
import math

WAT60_CONST = 999.012

def _convert_api_to_60_from_api(api_obs: float, sample_temp_f: float) -> float:
    if not api_obs or api_obs <= 0: return 0.0
    tf = float(sample_temp_f or 60.0)
    temp_diff = tf - 60.0
    rho_obs = (141.5 * WAT60_CONST / (131.5 + float(api_obs))) * ((1.0 - 0.00001278 * temp_diff) - (0.0000000062 * temp_diff * temp_diff))
    rho = rho_obs
    for _ in range(10):
        alfa = 341.0957 / (rho * rho)
        vcf = math.exp(-alfa * temp_diff - 0.8 * alfa * alfa * temp_diff * temp_diff)
        rho  = rho_obs / vcf
    api60 = 141.5 * WAT60_CONST / rho - 131.5
    return round(api60, 2)

def _convert_api_to_60_from_density(dens_obs_kgm3: float, sample_temp_c: float) -> float:
    if not dens_obs_kgm3 or dens_obs_kgm3 <= 0: return 0.0
    tc = float(sample_temp_c or 15.0)
    temp_diff = tc - 15.0
    hyc = 1.0 - 0.000023 * temp_diff - 0.00000002 * temp_diff * temp_diff
    rho_obs_corrected = float(dens_obs_kgm3) * hyc
    rho15 = rho_obs_corrected
    for _ in range(17):
        K = 613.9723 / (rho15 * rho15)
        vcf = math.exp(-K * temp_diff * (1.0 + 0.8 * K * temp_diff))
        rho15 = rho_obs_corrected / vcf
    sg60 = rho15 / WAT60_CONST
    if sg60 <= 0: return 0.0
    api60 = 141.5 / sg60 - 131.5
    return round(api60, 2)

def _vcf_from_api60_and_temp(api60: float, tank_temp_c: float, input_mode: str = "api") -> float:
    if not api60 or api60 <= 0: return 1.00000
    tank_temp_f = (float(tank_temp_c or 0.0) * 1.8) + 32.0
    delta_t = tank_temp_f - 60.0
    if abs(delta_t) < 0.01: return 1.00000
    sg60 = 141.5 / (api60 + 131.5)
    rho60 = sg60 * WAT60_CONST
    K0 = 341.0957
    alpha = K0 / (rho60 * rho60)
    vcf = math.exp(-alpha * delta_t * (1.0 + 0.8 * alpha * delta_t))
    return round(float(vcf), 5)

def _sum_bfs_condensate_gsv(sess, location_id: int, day_date) -> float:
    # All condensate TankTransactions for the specific day (use your op labels)
    rows = (
        sess.query(TankTransaction)
        .filter(
            TankTransaction.location_id == location_id,
            func.date(TankTransaction.date) == day_date,
        )
        .all()
    )
    total = 0.0
    for r in rows:
        label = (r.operation.value if hasattr(r.operation, "value") else str(r.operation or ""))
        if "condensate" not in (label or "").lower():
            continue

        opening = float(r.opening_meter_reading or 0.0)
        closing = float(r.closing_meter_reading or opening)
        qty_m3  = max(closing - opening, 0.0)
        gov_bbl = qty_m3 * 6.289

        api_obs = float(r.api_observed or 0.0)
        dens_obs = float(r.density_observed or 0.0)
        sample_f = float(r.sample_temp_f or ((r.sample_temp_c or 0.0) * 1.8 + 32.0))
        api60 = _convert_api_to_60_from_api(api_obs, sample_f) if api_obs > 0 else (
                _convert_api_to_60_from_density(dens_obs, float(r.sample_temp_c or 0.0)) if dens_obs > 0 else 0.0
        )
        tank_temp_c = float(r.tank_temp_c or ((r.tank_temp_f - 32.0) / 1.8) if r.tank_temp_f else 0.0)
        vcf = _vcf_from_api60_and_temp(api60, tank_temp_c, "api" if api_obs > 0 else "density")

        total += gov_bbl * vcf
    return round(total, 2)


class MaterialBalanceCalculator:
    # ------------- field readers -------------
    @staticmethod
    def _op_name_norm(entry) -> str:
        """Normalized operation string from an OTR entry (lower, trimmed)."""
        op = getattr(entry, 'operation', None)
        if op is None:
            return ''
        val = getattr(op, 'value', None)
        s = val if isinstance(val, str) else str(op)
        return _norm_text(s)

    @staticmethod
    def _nsv(entry) -> float:
        v = getattr(entry, 'nsv_bbl', None)
        try:
            return float(v if v is not None else 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _qty(entry) -> float:
        """
        Net receipt/dispatch value calculated from NSV difference.
        Note: This returns NSV; net movement is computed in _sum_where by per-tank diffs.
        """
        return MaterialBalanceCalculator._nsv(entry)

    @staticmethod
    def _entry_dt(e) -> Optional[datetime]:
        """
        Build a datetime from separate e.date and e.time attributes typical of OTRRecord.
        """
        try:
            t = e.time
            if isinstance(t, str):
                parts = t.split(':')
                hh = int(parts[0]); mm = int(parts[1]) if len(parts) > 1 else 0
                t = dt_time(hh, mm)
            return datetime.combine(e.date, t)
        except Exception:
            return None

    # ------------- generic utilities -------------
    @staticmethod
    def _window_filter(entries: Iterable, start: datetime, end: datetime) -> List:
        out = []
        for e in entries:
            dt = MaterialBalanceCalculator._entry_dt(e)
            if dt is None:
                continue
            if start <= dt <= end:
                out.append(e)
        return out

    @staticmethod
    def _sum_net_movements(
        entries: Iterable,
        op_names_norm: set[str],
        prev_day_closing: dict | None = None,
        mode: str = "receipt",
        debug=False,
    ) -> float:
        """
        Sum per-tank net movement (current NSV - previous NSV) for matching ops.
        mode: "receipt" (positive deltas only) or "dispatch" (absolute value of negative deltas).
        """
        sorted_entries = sorted(entries, key=lambda e: MaterialBalanceCalculator._entry_dt(e) or datetime.min)

        from collections import defaultdict
        tank_prev_nsv = defaultdict(lambda: None)
        if prev_day_closing:
            for k, v in prev_day_closing.items():
                try:
                    tank_prev_nsv[k] = float(v or 0.0)
                except Exception:
                    tank_prev_nsv[k] = 0.0

        total_net = 0.0
        for e in sorted_entries:
            tank_id = getattr(e, 'tank_id', None)
            if tank_id is None:
                continue
            current_nsv = MaterialBalanceCalculator._nsv(e)
            op_norm = MaterialBalanceCalculator._op_name_norm(e)

            prev_val = tank_prev_nsv[tank_id]
            if op_norm in op_names_norm and prev_val is not None:
                net_movement = current_nsv - prev_val
                if mode == "dispatch":
                    if net_movement < 0:
                        total_net += abs(net_movement)
                else:  # receipt
                    if net_movement > 0:
                        total_net += net_movement
                if debug:
                    print(f"    Net: Tank={tank_id}, Op={op_norm}, Prev={prev_val:.2f}, Curr={current_nsv:.2f}, Net={net_movement:.2f}")

            tank_prev_nsv[tank_id] = current_nsv

        return round(total_net, 2)

    # ---------- tank-aware opening/closing helpers ----------
    @staticmethod
    def _opening_stock_for_first_day(period_entries: List) -> float:
        """
        Sum NSV (bbl) only for entries explicitly labeled as Opening Stock.
        """
        total = 0.0
        for e in period_entries:
            if MaterialBalanceCalculator._op_name_norm(e) == "opening stock":
                total += float(MaterialBalanceCalculator._nsv(e) or 0.0)
        return round(total, 2)


    @staticmethod
    def _closing_nsv_by_tank(period_entries: List) -> Dict[int, float]:
        """
        Determine per-tank closing NSV, preferring explicit Closing Stock entries.
        """
        per_tank_latest: Dict[int, tuple[datetime, float]] = {}
        per_tank_closing: Dict[int, tuple[datetime, float]] = {}

        for e in period_entries:
            tank_id = getattr(e, "tank_id", None)
            if tank_id is None:
                continue
            dt = MaterialBalanceCalculator._entry_dt(e)
            if dt is None:
                continue
            nsv = MaterialBalanceCalculator._nsv(e)

            latest = per_tank_latest.get(tank_id)
            if latest is None or dt > latest[0]:
                per_tank_latest[tank_id] = (dt, nsv)

            op_norm = MaterialBalanceCalculator._op_name_norm(e)
            if op_norm == "closing stock":
                closing_entry = per_tank_closing.get(tank_id)
                if closing_entry is None or dt > closing_entry[0]:
                    per_tank_closing[tank_id] = (dt, nsv)

        out: Dict[int, float] = {}
        for tank_id, (_dt, nsv) in per_tank_latest.items():
            if tank_id in per_tank_closing:
                out[tank_id] = float(per_tank_closing[tank_id][1] or 0.0)
            else:
                out[tank_id] = float(nsv or 0.0)
        return out

    @staticmethod
    def _closing_stock(
        period_entries: List,
        prev_day_closing: dict | None = None
    ) -> tuple[float, dict]:
        """
        Tank-aware closing sum leveraging _closing_nsv_by_tank helper and carrying
        forward tanks with no activity in the current window.
        Returns (total_closing, per_tank_closing_map).
        """
        per_tank_today = MaterialBalanceCalculator._closing_nsv_by_tank(period_entries)
        combined: dict = {}

        if prev_day_closing:
            for tank_id, nsv in prev_day_closing.items():
                try:
                    combined[tank_id] = float(nsv or 0.0)
                except Exception:
                    combined[tank_id] = 0.0

        for tank_id, nsv in per_tank_today.items():
            try:
                combined[tank_id] = float(nsv or 0.0)
            except Exception:
                combined[tank_id] = 0.0

        total = round(sum(combined.values()), 2)
        return total, combined

    @staticmethod
    def _fetch_entries(location_id: Optional[int], date_from, date_to) -> List:
        """Fetch OTR rows from DB for the location & date range."""
        if get_session is None or OTRRecord is None or location_id is None:
            return []
        try:
            from models import ensure_otr_net_columns
            ensure_otr_net_columns()
        except Exception:
            pass
        with get_session() as s:
            q = s.query(OTRRecord).filter(
                OTRRecord.location_id == int(location_id),
                OTRRecord.date >= date_from,
                OTRRecord.date <= date_to,
            )
            return list(q.all())

    @staticmethod
    def _condensate_receipts_by_day(location_id: Optional[int], date_from, date_to) -> Dict[str, float]:
        """
        Aggregate condensate receipts as GSV (bbls) per date directly from tank_transactions.
        Uses meter readings → GOV(bbls) and applies VCF (via API@60) to get GSV.
        """
        if get_session is None or TankTransaction is None or location_id is None:
            return {}

        # Prefer enum match if available; otherwise we'll filter in Python
        op_value = None
        if Operation is not None:
            try:
                op_value = Operation.RECEIPT_CONDENSATE
            except AttributeError:
                op_value = None

        with get_session() as s:
            rows = (
                s.query(TankTransaction)
                .filter(
                    TankTransaction.location_id == int(location_id),
                    TankTransaction.date >= date_from,
                    TankTransaction.date <= date_to,
                )
                .all()
            )

        totals: Dict[str, float] = {}
        for row in rows:
            # Keep only condensate ops (robust Python-side filter)
            op_obj = getattr(row, "operation", None)
            label = op_obj.value if hasattr(op_obj, "value") else str(op_obj or "")
            label_norm = _norm_text(label)
            tank_norm = _norm_text(getattr(row, "tank_name", ""))
            has_meter = any([
                getattr(row, "opening_meter_reading", None) is not None,
                getattr(row, "closing_meter_reading", None) is not None,
                getattr(row, "condensate_qty_m3", None) is not None,
            ])
            if (
                "condensate" not in label_norm
                and "condensate" not in tank_norm
                and not has_meter
            ):
                continue

            # 1) qty in m³ from meter (or derive from meter readings)
            qty_m3 = getattr(row, "condensate_qty_m3", None)
            if qty_m3 is None:
                opening_val = float(getattr(row, "opening_meter_reading", 0.0) or 0.0)
                closing_val = float(getattr(row, "closing_meter_reading", opening_val) or opening_val)
                qty_m3 = max(closing_val - opening_val, 0.0)

            # 2) GOV (bbls) – prefer stored bbls if present, else convert from m³
            gov_bbl = float(getattr(row, "qty_bbls", 0.0) or 0.0)
            if gov_bbl <= 0:
                gov_bbl = float(qty_m3 or 0.0) * M3_TO_BBL

            # 3) API@60 (from observed API or density)
            api_obs  = float(getattr(row, "api_observed", 0.0) or 0.0)
            dens_obs = float(getattr(row, "density_observed", 0.0) or 0.0)
            st_f = float(
                (getattr(row, "sample_temp_f", None) or 0.0)
                or ((getattr(row, "sample_temp_c", 0.0) or 0.0) * 1.8 + 32.0)
            )
            if api_obs > 0:
                api60 = _convert_api_to_60_from_api(api_obs, st_f)
            elif dens_obs > 0:
                api60 = _convert_api_to_60_from_density(dens_obs, float(getattr(row, "sample_temp_c", 0.0) or 0.0))
            else:
                api60 = 0.0

            # 4) VCF (using tank temperature)
            t_c = getattr(row, "tank_temp_c", None)
            t_f = getattr(row, "tank_temp_f", None)
            if t_c is None and t_f is not None:
                tank_c = (float(t_f) - 32.0) / 1.8
            else:
                tank_c = float(t_c or 0.0)

            vcf = _vcf_from_api60_and_temp(api60, tank_c, "api" if api_obs > 0 else "density")

            # 5) GSV (bbls)
            gsv_bbl = round(gov_bbl * vcf, 2)

            # Group per calendar date
            try:
                dt_key = row.date.strftime("%Y-%m-%d")
            except Exception:
                dt_key = str(row.date)

            totals[dt_key] = round(totals.get(dt_key, 0.0) + gsv_bbl, 2)

        return totals


    # ------------- public API -------------
    @staticmethod
    def calculate_material_balance(
        entries: Optional[Iterable],
        location_code: str,
        date_from,
        date_to,
        location_id: Optional[int] = None,
        debug: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Compute material balance rows for each day in [date_from, date_to].

        - entries: Iterable of OTRRecord-like objects; if None (or not iterable), fetched via DB using location_id.
        - location_code: 'AGGU', 'BFS', 'NDONI', 'UTAPATE', 'JETTY' (or any alias).
        - date_from, date_to: dates
        - location_id: used when entries is None / not iterable
        """
        # Normalize / fetch
        if not _is_iterable_entries(entries):
            entries = MaterialBalanceCalculator._fetch_entries(location_id, date_from, date_to)
        else:
            entries = list(entries or [])

        code = _norm_location(location_code)
        rows: List[Dict[str, Any]] = []
        prev_closing: Optional[float] = None

        # Pre-build normalized op name sets for all locations (supports your OTR op labels)
        # ASEMOKU JETTY mapping → columns
        OP_OKW = {"okw receipt", "okw receipts", "receipt okw", "receipts okw"}
        OP_ANZ = {"anz receipt", "anz receipts", "receipt anz", "receipts anz"}
        OP_OTHER_RCPT = {"other receipts", "other receipt", "receipts other", "receipt other"}
        OP_DISP_BARGE = {"dispatch to barge", "dispatches to barge", "barge dispatch", "barge dispatches"}
        OP_OTHER_DISP = {"other dispatch", "other dispatches", "dispatches other", "dispatch other"}

        # Generic sites
        OP_RECEIPT = {"receipt", "receipts"}
        OP_DISPATCH = {"dispatch", "dispatches"}

        # BFS specifics
        OP_BFS_REC_COMMINGLED = {
            "receipt - commingled", "receipt commingled", "receipts commingled",
            "commingled receipt", "commingled receipts",
            # legacy aliases
            "receipt - crude", "receipt crude", "receipts crude", "crude receipt", "crude receipts",
        }
        OP_BFS_REC_COND  = {"receipt - condensate", "receipt condensate", "receipts condensate", "condensate receipt", "condensate receipts"}
        OP_BFS_DISP_JETTY= {"dispatch to jetty", "dispatches to jetty", "jetty dispatch", "jetty dispatches"}

        # NDONI specifics
        OP_ND_RCPT_AGU   = {"receipt from agu", "receipts from agu", "agu receipt", "agu receipts"}
        OP_ND_RCPT_OFS   = {"receipt from ofs", "receipts from ofs", "ofs receipt", "ofs receipts"}
        OP_ND_OTHER_RCPT = {"other receipts", "other receipt", "receipts other", "receipt other"}
        OP_ND_DISP_BARGE = {"dispatch to barge", "dispatches to barge", "barge dispatch", "barge dispatches"}

        # Track previous day's closing NSV per tank for net movement calculation
        prev_day_tank_nsv: dict[int, float] = {}

        # Per-location daily window (may be customized)
        win_start_time, win_end_time = _mb_window_for_location(location_id)

        is_bfs = code == "BFS"
        cur = date_from
        while cur <= date_to:
            # Build per-day window, allowing wrap into next day if end <= start
            start_dt = datetime.combine(cur, win_start_time)
            if win_end_time <= win_start_time:
                end_dt = datetime.combine(cur + timedelta(days=1), win_end_time)
            else:
                end_dt = datetime.combine(cur, win_end_time)

            day_entries = MaterialBalanceCalculator._window_filter(entries, start_dt, end_dt)

            if not day_entries:
                # continuity: carry forward previous closing (or 0 on first day)
                if code == "JETTY":
                    closing_val = round(prev_closing or 0.0, 2)
                    base = {
                        "Date": cur.strftime("%Y-%m-%d"),
                        "Opening Stock": closing_val,
                        "OKW Receipt": 0.0,
                        "ANZ Receipt": 0.0,
                        "Other Receipts": 0.0,
                        "Dispatch to barge": 0.0,
                        "Other dispatch": 0.0,
                        "Book Closing Stock": closing_val,
                        "Closing Stock": closing_val,
                        "Loss/Gain": 0.0,
                    }
                elif code == "BFS":
                    closing_val = round(prev_closing or 0.0, 2)
                    book = closing_val
                    base = {
                        "Date": cur.strftime("%Y-%m-%d"),
                        "Opening Stock": closing_val,
                        "Receipt-Commingled": 0.0,
                        "Receipt-Condensate": 0.0,
                        "Dispatch to Jetty": 0.0,
                        "Book Closing Stock": book,
                        "Closing Stock": closing_val,
                        "Loss/Gain": round(closing_val - book, 2),
                    }
                elif code == "NDONI":
                    closing_val = round(prev_closing or 0.0, 2)
                    base = {
                        "Date": cur.strftime("%Y-%m-%d"),
                        "Opening Stock": closing_val,
                        "Receipt from Agu": 0.0,
                        "Receipt from OFS": 0.0,
                        "Other Receipts": 0.0,
                        "Dispatch to barge": 0.0,
                        "Book Closing Stock": closing_val,
                        "Closing Stock": closing_val,
                        "Loss/Gain": 0.0,
                    }
                else:  # AGGU / UTAPATE
                    closing_val = round(prev_closing or 0.0, 2)
                    base = {
                        "Date": cur.strftime("%Y-%m-%d"),
                        "Opening Stock": closing_val,
                        "Receipt": 0.0,
                        "Dispatch": 0.0,
                        "Book Closing Stock": closing_val,
                        "Closing Stock": closing_val,
                        "Loss/Gain": 0.0,
                    }
                rows.append(base)
                prev_closing = closing_val
                cur += timedelta(days=1)
                continue

            # Opening stock
            if prev_closing is None:
                opening = MaterialBalanceCalculator._opening_stock_for_first_day(day_entries)
            else:
                opening = prev_closing

            # Per-location calculations
            if code == "JETTY":
                okw = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_OKW, prev_day_tank_nsv, mode="receipt")
                anz = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_ANZ, prev_day_tank_nsv, mode="receipt")
                oth = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_OTHER_RCPT, prev_day_tank_nsv, mode="receipt")
                d_b = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_DISP_BARGE, prev_day_tank_nsv, mode="dispatch")
                d_o = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_OTHER_DISP, prev_day_tank_nsv, mode="dispatch")

                total_receipts = okw + anz + oth
                total_dispatch = d_b + d_o
                book = round(opening + total_receipts - total_dispatch, 2)
                close_val, closing_by_tank = MaterialBalanceCalculator._closing_stock(day_entries, prev_day_tank_nsv)

                out = {
                    "Date": cur.strftime("%Y-%m-%d"),
                    "Opening Stock": round(opening, 2),
                    "OKW Receipt": round(okw, 2),
                    "ANZ Receipt": round(anz, 2),
                    "Other Receipts": round(oth, 2),
                    "Dispatch to barge": round(d_b, 2),
                    "Other dispatch": round(d_o, 2),
                    "Book Closing Stock": book,
                    "Closing Stock": close_val,
                    "Loss/Gain": round(close_val - book, 2)
                }

            elif code == "BFS":
                r_commingled = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_BFS_REC_COMMINGLED, prev_day_tank_nsv, mode="receipt")
                r_cond = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_BFS_REC_COND, prev_day_tank_nsv, mode="receipt")
                d_jetty = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_BFS_DISP_JETTY, prev_day_tank_nsv, mode="dispatch")
                total_receipts = r_commingled  # Receipt-Condensate excluded from book calculation
                total_dispatch = d_jetty
                book = round(opening + total_receipts - total_dispatch, 2)
                close_val, closing_by_tank = MaterialBalanceCalculator._closing_stock(day_entries, prev_day_tank_nsv)

                out = {
                    "Date": cur.strftime("%Y-%m-%d"),
                    "Opening Stock": round(opening, 2),
                    "Receipt-Commingled": round(r_commingled, 2),
                    "Receipt-Condensate": round(r_cond, 2),
                    "Dispatch to Jetty": round(d_jetty, 2),
                    "Book Closing Stock": book,
                    "Closing Stock": close_val,
                    "Loss/Gain": round(close_val - book, 2)
                }

            elif code == "NDONI":
                r_agu  = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_ND_RCPT_AGU, prev_day_tank_nsv, mode="receipt")
                r_ofs  = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_ND_RCPT_OFS, prev_day_tank_nsv, mode="receipt")
                r_oth  = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_ND_OTHER_RCPT, prev_day_tank_nsv, mode="receipt")
                d_barg = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_ND_DISP_BARGE, prev_day_tank_nsv, mode="dispatch")

                total_receipts = r_agu + r_ofs + r_oth
                total_dispatch = d_barg
                book = round(opening + total_receipts - total_dispatch, 2)
                close_val, closing_by_tank = MaterialBalanceCalculator._closing_stock(day_entries, prev_day_tank_nsv)

                out = {
                    "Date": cur.strftime("%Y-%m-%d"),
                    "Opening Stock": round(opening, 2),
                    "Receipt from Agu": round(r_agu, 2),
                    "Receipt from OFS": round(r_ofs, 2),
                    "Other Receipts": round(r_oth, 2),
                    "Dispatch to barge": round(d_barg, 2),
                    "Book Closing Stock": book,
                    "Closing Stock": close_val,
                    "Loss/Gain": round(close_val - book, 2)
                }

            else:  # AGGU, UTAPATE
                r = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_RECEIPT, prev_day_tank_nsv, mode="receipt")
                d = MaterialBalanceCalculator._sum_net_movements(day_entries, OP_DISPATCH, prev_day_tank_nsv, mode="dispatch")

                total_receipts = r
                total_dispatch = d
                book = round(opening + total_receipts - total_dispatch, 2)
                close_val, closing_by_tank = MaterialBalanceCalculator._closing_stock(day_entries, prev_day_tank_nsv)

                out = {
                    "Date": cur.strftime("%Y-%m-%d"),
                    "Opening Stock": round(opening, 2),
                    "Receipt": round(r, 2),
                    "Dispatch": round(d, 2),
                    "Book Closing Stock": book,
                    "Closing Stock": close_val,
                    "Loss/Gain": round(close_val - book, 2)
                }

            rows.append(out)
            prev_closing = close_val
            prev_day_tank_nsv = closing_by_tank.copy()

            cur += timedelta(days=1)

        return rows

    @staticmethod
    def _get_custom_columns(location_id: Optional[int]) -> List[Dict[str, Any]]:
        if location_id is None or _get_mb_page_cfg is None or get_session is None:
            return []
        try:
            with get_session() as s:
                cfg = _get_mb_page_cfg(s, int(location_id), page="material_balance", section="columns") or {}
            cols = list(cfg.get("columns", []))
            out = []
            for c in cols:
                label = (c.get("label") or "").strip()
                ctype = (c.get("type") or "").strip().lower()
                src = (c.get("data_source") or "").strip()
                field = (c.get("field") or "").strip()
                ops = list(c.get("operations", []))
                formula = c.get("formula")
                if label and ctype in {"receipt", "dispatch", "compute", "opening", "closing"}:
                    out.append({
                        "label": label,
                        "type": ctype,
                        "data_source": (src or None),
                        "field": (field or None),
                        "operations": ops,
                        "formula": formula,
                    })
            return out
        except Exception:
            return []

    @staticmethod
    def _norm_ops_set(names: List[str]) -> set[str]:
        return { _norm_text(n) for n in (names or []) if (n or "").strip() }

    @staticmethod
    def _sum_field_for_ops(entries: Iterable, field: str, ops_norm: set[str]) -> float:
        total = 0.0
        for e in entries:
            if ops_norm:
                op_norm = MaterialBalanceCalculator._op_name_norm(e)
                if op_norm not in ops_norm:
                    continue
            try:
                val = getattr(e, field)
            except Exception:
                val = None
            try:
                total += float(val or 0.0)
            except Exception:
                pass
        return round(total, 2)

    @staticmethod
    def calculate_material_balance_custom(
        entries: Optional[Iterable],
        date_from,
        date_to,
        location_id: Optional[int] = None,
        debug: bool = False
    ) -> List[Dict[str, Any]]:
        if not _is_iterable_entries(entries):
            entries = MaterialBalanceCalculator._fetch_entries(location_id, date_from, date_to)
        else:
            entries = list(entries or [])

        cols = MaterialBalanceCalculator._get_custom_columns(location_id)
        if not cols:
            return []

        win_start_time, win_end_time = _mb_window_for_location(location_id)

        rows: List[Dict[str, Any]] = []
        prev_closing: Optional[float] = None
        prev_day_tank_nsv: dict[int, float] = {}

        cur = date_from
        while cur <= date_to:
            start_dt = datetime.combine(cur, win_start_time)
            if win_end_time <= win_start_time:
                end_dt = datetime.combine(cur + timedelta(days=1), win_end_time)
            else:
                end_dt = datetime.combine(cur, win_end_time)

            day_entries_otr = MaterialBalanceCalculator._window_filter(entries, start_dt, end_dt)

            if prev_closing is None:
                opening = MaterialBalanceCalculator._opening_stock_for_first_day(day_entries_otr)
            else:
                opening = prev_closing

            out = { "Date": cur.strftime("%Y-%m-%d") }

            total_receipts = 0.0
            total_dispatch = 0.0

            def _get_model(src: str):
                try:
                    from models import get_custom_table_model
                    return get_custom_table_model(src)
                except Exception:
                    return None

            def _fetch_source(location_id: Optional[int], src: str, dfrom, dto) -> list:
                Model = _get_model(src)
                if Model is None or get_session is None:
                    return []
                with get_session() as s:
                    q = s.query(Model)
                    if hasattr(Model, 'location_id') and location_id is not None:
                        q = q.filter(getattr(Model, 'location_id') == int(location_id))
                    if hasattr(Model, 'date'):
                        q = q.filter(getattr(Model, 'date') >= dfrom).filter(getattr(Model, 'date') <= dto)
                    elif hasattr(Model, 'tx_date'):
                        q = q.filter(getattr(Model, 'tx_date') >= dfrom).filter(getattr(Model, 'tx_date') <= dto)
                    return list(q.all())

            def _entry_dt_generic(e):
                try:
                    dt = None
                    if hasattr(e, 'date'):
                        d = getattr(e, 'date')
                        t = getattr(e, 'time', None)
                        if isinstance(t, str):
                            parts = t.split(':'); hh = int(parts[0]); mm = int(parts[1]) if len(parts) > 1 else 0
                            t = dt_time(hh, mm)
                        dt = datetime.combine(d, t or dt_time(0,0))
                    elif hasattr(e, 'tx_date'):
                        d = getattr(e, 'tx_date')
                        dt = datetime.combine(d, dt_time(0,0))
                    return dt
                except Exception:
                    return None

            def _tank_id(e):
                for name in ('tank_id', 'tankid', 'tankID'):
                    if hasattr(e, name):
                        try:
                            return int(getattr(e, name))
                        except Exception:
                            return getattr(e, name)
                return None

            def _is_closing_row(e):
                try:
                    if hasattr(e, 'operation'):
                        op = str(getattr(e, 'operation') or '').lower()
                        return ('closing' in op) or ('closing stock' in op) or ('close' in op)
                except Exception:
                    pass
                return False

            def _sum_first_by_tank(entries_list: list, field_name: str) -> float:
                by_tank = {}
                for e in entries_list:
                    dt = _entry_dt_generic(e)
                    if dt is None:
                        continue
                    tid = _tank_id(e)
                    key = tid if tid is not None else '__global__'
                    prev = by_tank.get(key)
                    if prev is None or dt < prev[0]:
                        by_tank[key] = (dt, e)
                total = 0.0
                for _, (_, e) in by_tank.items():
                    try:
                        total += float(getattr(e, field_name) or 0.0)
                    except Exception:
                        pass
                return round(total, 2)

            def _sum_last_by_tank(entries_list: list, field_name: str) -> float:
                by_tank = {}
                closing_candidates = {}
                for e in entries_list:
                    dt = _entry_dt_generic(e)
                    if dt is None:
                        continue
                    tid = _tank_id(e)
                    key = tid if tid is not None else '__global__'
                    prev = by_tank.get(key)
                    if prev is None or dt > prev[0]:
                        by_tank[key] = (dt, e)
                    if _is_closing_row(e):
                        pc = closing_candidates.get(key)
                        if pc is None or dt > pc[0]:
                            closing_candidates[key] = (dt, e)
                total = 0.0
                for key in by_tank.keys():
                    _, e = closing_candidates.get(key, by_tank[key])
                    try:
                        total += float(getattr(e, field_name) or 0.0)
                    except Exception:
                        pass
                return round(total, 2)

            opening_cfgs = [c for c in cols if (c.get("type") or "").strip().lower() == "opening"]
            closing_cfgs = [c for c in cols if (c.get("type") or "").strip().lower() == "closing"]
            opening_labels = [c.get("label") for c in opening_cfgs]
            closing_labels = [c.get("label") for c in closing_cfgs]

            if opening_labels:
                if prev_closing is None and opening_cfgs and opening_cfgs[0].get('data_source') and opening_cfgs[0].get('field'):
                    src = opening_cfgs[0]['data_source']
                    fld = opening_cfgs[0]['field']
                    src_entries = _fetch_source(location_id, src, date_from, date_to)
                    day_src = []
                    for e in src_entries:
                        dt = _entry_dt_generic(e)
                        if dt is None:
                            continue
                        if start_dt <= dt <= end_dt:
                            day_src.append(e)
                    opening = _sum_first_by_tank(day_src, fld)
                out[opening_labels[0]] = round(opening, 2)
            else:
                out["Opening Stock"] = round(opening, 2)

            for c in [x for x in cols if not x.get("formula") and (x.get("type") or "").strip().lower() in {"receipt", "dispatch"}]:
                ops_norm = MaterialBalanceCalculator._norm_ops_set(c.get("operations") or [])
                src = c.get("data_source")
                if src:
                    src_entries = _fetch_source(location_id, src, date_from, date_to)
                    day_src = []
                    for e in src_entries:
                        dt = _entry_dt_generic(e)
                        if dt is None:
                            continue
                        if start_dt <= dt <= end_dt:
                            day_src.append(e)
                    val = MaterialBalanceCalculator._sum_field_for_ops(day_src, (c.get("field") or ""), ops_norm)
                else:
                    val = MaterialBalanceCalculator._sum_field_for_ops(day_entries_otr, (c.get("field") or ""), ops_norm)
                out[c.get("label")] = val
                if c.get("type") == "receipt":
                    total_receipts += val
                elif c.get("type") == "dispatch":
                    total_dispatch += val

            for c in [x for x in cols if x.get("formula")]:
                f = c.get("formula") or {}
                op = (f.get("op") or "").strip().lower()
                ref = list(f.get("cols") or [])
                vals = [float(out.get(r, 0.0) or 0.0) for r in ref]
                val = 0.0
                if op == "sum":
                    val = round(sum(vals), 2)
                elif op == "subtract":
                    if vals:
                        val = round(vals[0] - sum(vals[1:]), 2)
                elif op == "multiply":
                    val = 1.0
                    for v in vals:
                        val *= v
                    val = round(val, 2)
                elif op == "divide":
                    if vals:
                        base = vals[0]
                        for v in vals[1:]:
                            try:
                                base = base / v if v not in (0, None) else 0.0
                            except Exception:
                                base = 0.0
                        val = round(base, 4)
                elif op == "average":
                    val = round((sum(vals) / len(vals)) if vals else 0.0, 2)
                elif op == "percentage":
                    if len(vals) >= 2 and vals[1] not in (0, None):
                        val = round((vals[0] / vals[1]) * 100.0, 2)
                    else:
                        val = 0.0
                elif op == "equation":
                    expr = (f.get("expr") or "").strip()
                    def _eval(node):
                        if isinstance(node, ast.Expression):
                            return _eval(node.body)
                        if isinstance(node, ast.BinOp):
                            a = _eval(node.left); b = _eval(node.right)
                            if isinstance(node.op, ast.Add):
                                return a + b
                            if isinstance(node.op, ast.Sub):
                                return a - b
                            if isinstance(node.op, ast.Mult):
                                return a * b
                            if isinstance(node.op, ast.Div):
                                try:
                                    return a / b
                                except Exception:
                                    return 0.0
                            return 0.0
                        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
                            return -_eval(node.operand)
                        if isinstance(node, ast.Num):
                            return float(node.n)
                        if isinstance(node, ast.Constant):
                            return float(node.value) if isinstance(node.value, (int, float)) else 0.0
                        if isinstance(node, ast.Name):
                            return float(out.get(node.id, 0.0) or 0.0)
                        return 0.0
                    try:
                        tree = ast.parse(expr, mode='eval')
                        val = round(float(_eval(tree)), 2)
                    except Exception:
                        val = 0.0
                out[c.get("label")] = val
                if c.get("type") == "receipt":
                    total_receipts += val
                elif c.get("type") == "dispatch":
                    total_dispatch += val

            book = round(opening + total_receipts - total_dispatch, 2)
            close_val, closing_by_tank = MaterialBalanceCalculator._closing_stock(day_entries_otr, prev_day_tank_nsv)
            if closing_cfgs and closing_cfgs[0].get('data_source') and closing_cfgs[0].get('field'):
                src = closing_cfgs[0]['data_source']
                fld = closing_cfgs[0]['field']
                src_entries = _fetch_source(location_id, src, date_from, date_to)
                day_src = []
                for e in src_entries:
                    dt = _entry_dt_generic(e)
                    if dt is None:
                        continue
                    if start_dt <= dt <= end_dt:
                        day_src.append(e)
                close_val = _sum_last_by_tank(day_src, fld)

            out["Book Closing Stock"] = book
            if closing_labels:
                out[closing_labels[0]] = close_val
            else:
                out["Closing Stock"] = close_val
            out["Loss/Gain"] = round(close_val - book, 2)

            rows.append(out)
            prev_closing = close_val
            prev_day_tank_nsv = closing_by_tank.copy()
            cur += timedelta(days=1)

        return rows
