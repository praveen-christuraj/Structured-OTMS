import json
import streamlit as st
from datetime import datetime

from db import get_session
from security import SecurityManager
from models import RecycleBinEntry, Location


def _is_admin(user) -> bool:
    role = (user or {}).get("role", "").lower()
    return role in ("admin-operations", "admin-it")


def _guard_location(active_location_id):
    if not active_location_id:
        return None, None
    with get_session() as s:
        loc = s.query(Location).get(active_location_id)
        if not loc:
            return None, None
        return loc, f"{loc.name} ({loc.code})"


def render_recycle_bin_page(active_location_id, user):
    st.markdown("### ♻️ Recycle Bin")

    if not _is_admin(user):
        st.warning("Only admin users can access the Recycle Bin.")
        return

    loc, loc_label = _guard_location(active_location_id)
    if not loc:
        st.caption("No active location selected. Entries may include a mix of locations.")

    # Filters
    c1, c2, c3 = st.columns([0.35, 0.35, 0.30])
    with c1:
        resource_type = st.text_input("Resource Type contains", value="", key="rb_res_type")
    with c2:
        label_search = st.text_input("Label/ID contains", value="", key="rb_label")
    with c3:
        show_current_loc_only = st.checkbox("Only current location", value=True, key="rb_only_loc")

    # Load entries
    entries = []
    try:
        with get_session() as s:
            q = s.query(RecycleBinEntry)
            if show_current_loc_only and active_location_id:
                q = q.filter(RecycleBinEntry.location_id == active_location_id)
            if resource_type.strip():
                q = q.filter(RecycleBinEntry.resource_type.ilike(f"%{resource_type.strip()}%"))
            if label_search.strip():
                q = q.filter(RecycleBinEntry.resource_label.ilike(f"%{label_search.strip()}%"))
            q = q.order_by(RecycleBinEntry.deleted_at.desc()).limit(1000)
            entries = q.all()
    except Exception as ex:
        st.error(f"Failed to load recycle bin entries: {ex}")
        return

    st.caption(f"Entries: {len(entries)}")

    if not entries:
        st.info("Recycle Bin is empty for current filters.")
        return

    # List entries
    for e in entries:
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([0.22, 0.22, 0.22, 0.22, 0.12])
            c1.markdown(f"**{e.resource_type}**")
            c2.caption(f"ID: {e.resource_id}")
            c3.caption(f"Label: {e.resource_label or '—'}")
            c4.caption(f"Deleted: {e.deleted_at:%Y-%m-%d %H:%M}")
            with c5:
                view_btn = st.button("👁️", key=f"rb_view_{e.id}", help="View payload", use_container_width=True)
                del_btn = st.button("♻️", key=f"rb_del_{e.id}", help="Permanent delete", use_container_width=True)

            if view_btn:
                try:
                    payload = json.loads(e.payload_json or "{}")
                except Exception:
                    payload = {"_error": "invalid json"}
                st.code(json.dumps(payload, indent=2, default=str), language="json")

            if del_btn:
                st.warning("This will permanently delete the archived record. This cannot be undone.")
                dc1, dc2 = st.columns(2)
                with dc1:
                    if st.button("✅ Yes, delete", key=f"rb_del_yes_{e.id}", type="primary", use_container_width=True):
                        try:
                            with get_session() as s:
                                obj = s.query(RecycleBinEntry).get(e.id)
                                if obj:
                                    s.delete(obj)
                                    SecurityManager.log_audit(
                                        s,
                                        (user or {}).get("username", "system"),
                                        "PURGE",
                                        resource_type=str(e.resource_type),
                                        resource_id=str(e.resource_id),
                                        details=f"Purged recycle bin entry {e.id}",
                                        user_id=(user or {}).get("id"),
                                        location_id=e.location_id,
                                    )
                                    s.commit()
                            st.success("Purged.")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Purge failed: {ex}")
                with dc2:
                    st.button("❌ Cancel", key=f"rb_del_no_{e.id}", use_container_width=True)
