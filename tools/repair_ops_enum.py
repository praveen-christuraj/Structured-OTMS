# tools/repair_ops_enum.py
from __future__ import annotations
import sys, pathlib
from typing import List, Optional

# --- Ensure project root is importable ---
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import get_session
from sqlalchemy import text
from sqlalchemy import Enum as SAEnum
from models import TankTransaction as TT


def _get_allowed_enum_values() -> List[str]:
    """
    Return uppercase allowed enum values for TT.operation if it is an Enum column.
    Empty list means: not an Enum or cannot detect.
    """
    try:
        op_col = TT.__table__.columns.get("operation")
    except Exception:
        return []

    if op_col is None:
        return []

    coltype = getattr(op_col, "type", None)
    if coltype is None:
        return []

    # Case 1: SQLAlchemy Enum with string values
    if isinstance(coltype, SAEnum):
        enums = getattr(coltype, "enums", None)
        if enums:
            return [str(v).upper() for v in enums]

    # Case 2: Enum backed by a Python Enum class
    enum_class = getattr(coltype, "enum_class", None)
    if enum_class:
        return [str(member.name).upper() for member in enum_class]

    return []


def _has_operation_text_column() -> bool:
    return TT.__table__.columns.get("operation_text") is not None


def _map_human_to_allowed(value: str, allowed: List[str]) -> Optional[str]:
    """
    Heuristic mapping from human strings like 'Opening Stock' to the closest allowed enum.
    We try category keywords first, then fall back to RECEIPT or first allowed.
    """
    up = value.upper()

    buckets = [
        ("OPEN", "OPENING"),
        ("CLOS", "CLOSING"),
        ("RECEIPT", "RECEIPT"),
        ("DISPATCH", "DISPATCH"),
        ("DRAIN", "DRAINING"),
        ("SETTL", "SETTLING"),
    ]

    for needle, canonical in buckets:
        if needle in up:
            for a in allowed:
                if canonical in a:
                    return a

    # Fallbacks
    for a in allowed:
        if a.startswith("RECEIPT"):
            return a
    return allowed[0] if allowed else None


def repair_operations():
    with get_session() as s:
        # Detect allowed enum values on the model
        allowed = _get_allowed_enum_values()
        tbl = TT.__table__.name

        if not allowed:
            print("ℹ️ 'operation' is not an Enum (or enum values not detectable). Nothing to normalize.")
            return

        # Fetch **raw** distinct values from DB (bypass ORM enum coercion)
        # Quote the table name to be safe across backends
        rows = s.execute(text(f'SELECT DISTINCT "operation" FROM "{tbl}"')).fetchall()

        bad_values = []
        for (opval,) in rows:
            if opval is None:
                continue
            try:
                up = str(opval).upper()
            except Exception:
                continue
            if up not in allowed:
                bad_values.append(str(opval))

        if not bad_values:
            print("✅ No invalid enum values found. You're good.")
            return

        has_op_text = _has_operation_text_column()
        updated = 0

        for bad in bad_values:
            mapped = _map_human_to_allowed(bad, allowed)
            if mapped:
                # Normalize to a valid enum value
                s.execute(
                    text(f'UPDATE "{tbl}" SET "operation" = :good WHERE "operation" = :bad'),
                    {"good": mapped, "bad": bad},
                )
                updated += 1
            else:
                if has_op_text:
                    # Preserve human text into operation_text, set enum to NULL
                    s.execute(
                        text(
                            f'UPDATE "{tbl}" '
                            f'SET "operation_text" = :bad, "operation" = NULL '
                            f'WHERE "operation" = :bad'
                        ),
                        {"bad": bad},
                    )
                    updated += 1
                else:
                    # Last resort: force to first allowed
                    fallback = allowed[0]
                    s.execute(
                        text(f'UPDATE "{tbl}" SET "operation" = :good WHERE "operation" = :bad'),
                        {"good": fallback, "bad": bad},
                    )
                    updated += 1

        s.commit()
        print(f"✅ Repaired {updated} rows. Invalid enum strings normalized.")


if __name__ == "__main__":
    repair_operations()
