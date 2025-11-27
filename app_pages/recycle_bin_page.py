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
    st.markdown("### 🗑️ Deleted Records")

    if not _is_admin(user):
        st.warning("Only admin users can access Deleted Records.")
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
        st.info("No deleted records for current filters.")
        return

    ids = [e.id for e in entries]
    hdr = st.container(border=True)
    with hdr:
        h0, h1, h2, h3, h4, h5 = st.columns([0.10, 0.24, 0.18, 0.26, 0.12, 0.10])
        with h0:
            b_all = st.button("✔️ All", key="rb_mark_all", use_container_width=True)
            b_none = st.button("✖️ None", key="rb_unmark_all", use_container_width=True)
        h1.caption("Type")
        h2.caption("ID")
        h3.caption("Deleted At")
        h4.caption("View")
        h5.caption("Purge")

    if b_all:
        for _id in ids:
            st.session_state[f"rb_mark_{_id}"] = True
        st.rerun()
    if b_none:
        for _id in ids:
            st.session_state[f"rb_mark_{_id}"] = False
        st.rerun()

    selected_ids = []
    for e in entries:
        row = st.container(border=False)
        with row:
            c0, c1, c2, c3, c4, c5 = st.columns([0.10, 0.24, 0.18, 0.26, 0.12, 0.10])
            mark_key = f"rb_mark_{e.id}"
            current_mark = bool(st.session_state.get(mark_key, False))
            marked = c0.checkbox("", key=mark_key, value=current_mark)
            if marked:
                selected_ids.append(e.id)
            c1.caption(str(e.resource_type))
            c2.caption(str(e.resource_id))
            c3.caption(f"{e.deleted_at:%Y-%m-%d %H:%M}")
            with c4:
                view_btn = st.button("👁️", key=f"rb_view_{e.id}", help="View payload", use_container_width=True)
            with c5:
                purge_click = st.button("🗑️", key=f"rb_del_{e.id}", help="Permanent delete", use_container_width=True)

        view_key = f"rb_view_open_{e.id}"
        if view_btn:
            st.session_state[view_key] = True
        if st.session_state.get(view_key):
            try:
                payload = json.loads(e.payload_json or "{}")
            except Exception:
                payload = {"_error": "invalid json"}
            vp = st.container(border=True)
            with vp:
                st.code(json.dumps(payload, indent=2, default=str), language="json")
                cc = st.columns([0.12, 0.88])
                with cc[0]:
                    if st.button("✖️ Close", key=f"rb_view_close_{e.id}", use_container_width=True):
                        st.session_state[view_key] = False
                        st.rerun()

        key_flag = f"rb_confirm_{e.id}"
        if purge_click:
            st.session_state[key_flag] = True
        if st.session_state.get(key_flag):
            cc1, cc2 = st.columns([0.12, 0.12])
            with cc1:
                if st.button("✅", key=f"rb_del_yes_{e.id}", help="Confirm purge", type="primary", use_container_width=True):
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
                        st.session_state[key_flag] = False
                        st.success("Purged.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Purge failed: {ex}")
            with cc2:
                if st.button("❌", key=f"rb_del_no_{e.id}", help="Cancel", use_container_width=True):
                    st.session_state[key_flag] = False

    if selected_ids:
        bulk = st.container(border=True)
        with bulk:
            bc1, bc2 = st.columns([0.18, 0.82])
            with bc1:
                bulk_click = st.button("🗑️ Purge Selected", key="rb_bulk_purge", type="primary", use_container_width=True)
            if bulk_click:
                st.session_state["rb_bulk_confirm"] = True
            if st.session_state.get("rb_bulk_confirm"):
                bc_yes, bc_no = st.columns([0.12, 0.12])
                with bc_yes:
                    if st.button("✅ Confirm", key="rb_bulk_yes", use_container_width=True):
                        try:
                            with get_session() as s:
                                count = 0
                                for _id in list(selected_ids):
                                    obj = s.query(RecycleBinEntry).get(_id)
                                    if obj:
                                        s.delete(obj)
                                        SecurityManager.log_audit(
                                            s,
                                            (user or {}).get("username", "system"),
                                            "PURGE",
                                            resource_type=str(obj.resource_type),
                                            resource_id=str(obj.resource_id),
                                            details=f"Purged recycle bin entry {_id}",
                                            user_id=(user or {}).get("id"),
                                            location_id=obj.location_id,
                                        )
                                        count += 1
                                s.commit()
                            for _id in list(selected_ids):
                                st.session_state.pop(f"rb_mark_{_id}", None)
                            st.session_state["rb_bulk_confirm"] = False
                            st.success(f"Purged {count} selected record(s).")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Bulk purge failed: {ex}")
                with bc_no:
                    if st.button("❌ Cancel", key="rb_bulk_no", use_container_width=True):
                        st.session_state["rb_bulk_confirm"] = False
