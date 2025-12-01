import streamlit as st
import pandas as pd
from typing import List, Dict, Tuple, Optional

from sqlalchemy import inspect, Table, MetaData

from db import engine, flex_engine, get_session
from models import Location
from security import SecurityManager


def _is_admin(user) -> bool:
    role = (user or {}).get("role", "").lower()
    return role in ("admin-operations", "admin-it")


def _require_admin(user):
    if not _is_admin(user):
        st.warning("You don’t have permission to view this page.")
        return False
    return True


def _list_tables() -> List[Tuple[str, str]]:
    tables: List[Tuple[str, str]] = []
    try:
        if engine:
            insp = inspect(engine)
            for t in insp.get_table_names():
                tables.append(("primary", t))
    except Exception:
        pass
    try:
        if flex_engine:
            insp = inspect(flex_engine)
            for t in insp.get_table_names():
                tables.append(("flex", t))
    except Exception:
        pass
    # de-duplicate keeping first occurrence
    seen = set()
    deduped: List[Tuple[str, str]] = []
    for dbname, t in tables:
        key = (dbname, t)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((dbname, t))
    return sorted(deduped, key=lambda x: (0 if x[0] == "primary" else 1, x[1]))


def _get_table_columns(dbname: str, table_name: str) -> List[Dict]:
    eng = engine if dbname == "primary" else flex_engine
    if not eng:
        return []
    ins = inspect(eng)
    cols = ins.get_columns(table_name)
    pk = ins.get_pk_constraint(table_name) or {}
    pk_cols = set(pk.get("constrained_columns") or [])
    return [
        {
            "name": c.get("name"),
            "type": str(c.get("type")),
            "nullable": bool(c.get("nullable", True)),
            "default": c.get("default"),
            "primary_key": c.get("name") in pk_cols,
        }
        for c in cols
    ]


def _reflect_table(dbname: str, table_name: str) -> Optional[Table]:
    eng = engine if dbname == "primary" else flex_engine
    if not eng:
        return None
    md = MetaData()
    try:
        return Table(table_name, md, autoload_with=eng)
    except Exception:
        return None


def _read_upload(file) -> pd.DataFrame:
    name = (file.name or "").lower()
    if name.endswith(".csv"):
        return pd.read_csv(file)
    if name.endswith(".xlsx"):
        return pd.read_excel(file)
    raise ValueError("Unsupported file type. Please upload CSV or XLSX.")


def render_back_data_page(active_location_id: int, user: Dict):
    st.subheader("📥 Back Data Upload")
    st.caption("Upload previous-year data into any database table. CSV or XLSX with exact columns.")

    if not _require_admin(user):
        return

    if not active_location_id:
        st.info("No active location selected. Go to Home and select a location.")
        return
    try:
        with get_session() as s:
            loc = s.query(Location).get(active_location_id)
            if loc:
                st.caption(f"Active Location: {loc.name} ({loc.code})")
    except Exception:
        pass

    # Select table
    tables = _list_tables()
    if not tables:
        st.error("No tables found in database.")
        return

    options = [f"primary • {t}" if db == "primary" else f"flex • {t}" for db, t in tables]
    idx_default = 0
    selected = st.selectbox("Select target table", options, index=idx_default, key="backdata_table_select")
    sel_idx = options.index(selected)
    dbname, table_name = tables[sel_idx]

    # Show required columns
    cols_meta = _get_table_columns(dbname, table_name)
    if not cols_meta:
        st.warning("Unable to read table columns.")
        return

    all_cols = [c["name"] for c in cols_meta]
    has_location = any(c["name"].lower() == "location_id" for c in cols_meta)
    # Define required columns conservatively: non-nullable or primary key (except auto id)
    req_cols = []
    for c in cols_meta:
        n = c["name"]
        is_required = (not c["nullable"]) or c["primary_key"]
        if n.lower() == "id":
            is_required = False  # allow auto-increment id to be omitted
        if has_location and n.lower() == "location_id":
            is_required = False  # auto-filled from active location
        if is_required:
            req_cols.append(n)

    st.markdown("#### Columns")
    st.dataframe(
        pd.DataFrame(cols_meta),
        use_container_width=True,
        hide_index=True,
    )
    if has_location:
        st.info("'location_id' is auto-filled from the active location. 'id' may be omitted if auto-increment.")
    else:
        st.info("The upload file must include all columns. Primary key 'id' may be omitted if auto-increment.")

    # Template download
    tmpl_cols = [c for c in all_cols if c.lower() not in ("id", "location_id")]
    template_csv = (",".join(tmpl_cols)) + "\n"
    st.download_button(
        "Download CSV template",
        data=template_csv.encode("utf-8"),
        file_name=f"{table_name}_template.csv",
        mime="text/csv",
    )

    # Upload
    up = st.file_uploader("Select CSV/XLSX file", type=["csv", "xlsx"], key="backdata_uploader")

    df: Optional[pd.DataFrame] = None
    if up is not None:
        try:
            df = _read_upload(up)
            # exact column match (case-sensitive)
            df_cols = [str(c) for c in df.columns]
            missing = [c for c in all_cols if c not in df_cols and c in req_cols]
            extra = [c for c in df_cols if c not in all_cols]

            with st.expander("Preview (first 50 rows)", expanded=True):
                st.dataframe(df.head(50), use_container_width=True, hide_index=True)

            if extra:
                st.error(f"Unexpected columns present: {', '.join(extra)}")
            if missing:
                st.error(f"Missing required columns: {', '.join(missing)}")

            if not missing and not extra:
                st.success("Column validation passed.")
        except Exception as ex:
            st.error(f"Upload error: {ex}")

    # Import button
    if df is not None:
        if st.button("Import to Database", type="primary"):
            table = _reflect_table(dbname, table_name)
            if table is None:
                st.error("Failed to reflect target table.")
                return
            eng = engine if dbname == "primary" else flex_engine
            try:
                # Prepare records dict with only known columns
                df_cols = [str(c) for c in df.columns]
                # If 'id' not provided, skip it
                insert_cols = [c for c in all_cols if c in df_cols]
                records = df[insert_cols].to_dict(orient="records")
                if has_location:
                    for r in records:
                        r["location_id"] = int(active_location_id)

                total = 0
                with eng.begin() as conn:
                    chunk = 1000
                    for i in range(0, len(records), chunk):
                        batch = records[i : i + chunk]
                        if not batch:
                            continue
                        conn.execute(table.insert(), batch)
                        total += len(batch)

                try:
                    with get_session() as s:
                        SecurityManager.log_audit(
                            s,
                            (user or {}).get("username", "system"),
                            "IMPORT",
                            resource_type=table_name,
                            resource_id="batch",
                            details=f"Imported {total} rows into {dbname}:{table_name}",
                            user_id=(user or {}).get("id"),
                            location_id=active_location_id,
                        )
                except Exception:
                    pass

                st.success(f"Imported {total} rows into {dbname}:{table_name}.")
                st.experimental_rerun()
            except Exception as ex:
                st.error(f"Failed to import: {ex}")
