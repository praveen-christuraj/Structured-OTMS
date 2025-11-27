from __future__ import annotations

import streamlit as st
from typing import Dict, Any, Optional
from io import BytesIO
from datetime import datetime
import uuid

from db import get_session
from ui import header
from security import SecurityManager
from models import SharedFile, Location
from logger import ActionLogger


def _is_admin(user: Optional[Dict[str, Any]]) -> bool:
    role = (user or {}).get("role", "").lower()
    return role in ("admin-operations", "admin-it")


def render_sharing_page(active_location_id: Optional[int], user: Dict[str, Any]):
    header("Sharing")

    if not user:
        st.error("Please login to access this page.")
        st.stop()

    tabs = st.tabs(["Upload", "Shared Files"])

    with tabs[0]:
        st.markdown("#### Upload a File to Share")
        file = st.file_uploader("Select file", type=None, accept_multiple_files=False, key="sharing_uploader")
        remarks = st.text_area("Remarks (optional)", placeholder="Enter context or instructions for the recipient")

        share_btn = st.button("Share", type="primary")
        if share_btn:
            if not file:
                st.error("Please select a file to upload.")
            else:
                try:
                    data = file.read()
                    unique_id = str(uuid.uuid4())
                    filename = file.name or "uploaded.bin"
                    mime_type = getattr(file, "type", None)
                    size_bytes = len(data) if data else 0
                    with get_session() as s:
                        rec = SharedFile(
                            unique_id=unique_id,
                            location_id=active_location_id,
                            filename=filename,
                            mime_type=mime_type,
                            size_bytes=size_bytes,
                            data=data or b"",
                            remarks=(remarks or None),
                            uploaded_by=user.get("username", "unknown"),
                            uploaded_by_role=(user.get("role") or "").lower(),
                        )
                        s.add(rec)
                        s.flush()
                        SecurityManager.log_audit(
                            s,
                            user.get("username"),
                            "CREATE",
                            resource_type="SharedFile",
                            resource_id=str(rec.id),
                            details=f"Shared file '{filename}' ({size_bytes} bytes) uid={unique_id}",
                            user_id=user.get("id"),
                            location_id=active_location_id,
                            success=True,
                        )
                        s.commit()
                    st.success(f"File shared successfully. Unique ID: {unique_id}")
                except Exception as ex:
                    st.error(f"Failed to share file: {ex}")
                    try:
                        ActionLogger.log_error_with_task(
                            ex,
                            context="Sharing upload",
                            user=user,
                            location_id=active_location_id,
                            severity="HIGH",
                            additional_info=f"filename={file.name if file else ''}"
                        )
                    except Exception:
                        pass

    with tabs[1]:
        st.markdown("#### Shared Files")
        is_admin = _is_admin(user)
        loc_label = "All Locations" if is_admin and not active_location_id else "Current Location"
        st.caption(f"Viewing: {loc_label}")

        with get_session() as s:
            q = s.query(SharedFile).filter(SharedFile.is_deleted == False)
            if active_location_id and not is_admin:
                q = q.filter(SharedFile.location_id == active_location_id)
            rows = q.order_by(SharedFile.uploaded_at.desc()).limit(500).all()

            loc_map = {l.id: l.name for l in s.query(Location).all()}

        if not rows:
            st.info("No shared files yet.")
        else:
            for rec in rows:
                label = f"{rec.filename} • {rec.size_bytes or 0} bytes"
                meta = f"ID: {rec.unique_id} • Uploaded: {rec.uploaded_at} • By: {rec.uploaded_by}"
                if rec.location_id:
                    loc_name = loc_map.get(rec.location_id, "Unknown")
                    meta += f" • Location: {loc_name}"
                st.write(f"**{label}**")
                st.caption(meta)
                if rec.remarks:
                    st.write(rec.remarks)

                c1, c2, c3 = st.columns([0.3, 0.3, 0.4])
                with c1:
                    st.download_button(
                        label="📥 Download",
                        data=rec.data or b"",
                        file_name=rec.filename,
                        mime=rec.mime_type or "application/octet-stream",
                        use_container_width=True,
                        key=f"dl_{rec.unique_id}",
                        on_click=lambda: SecurityManager.log_audit(
                            None,
                            user.get("username"),
                            "READ",
                            resource_type="SharedFile",
                            resource_id=str(rec.id),
                            details=f"Downloaded '{rec.filename}' uid={rec.unique_id}",
                            user_id=user.get("id"),
                            location_id=active_location_id,
                            success=True,
                        ),
                    )
                with c2:
                    if is_admin:
                        del_key = f"del_{rec.unique_id}"
                        if st.button("🗑️ Delete", use_container_width=True, key=del_key):
                            try:
                                with get_session() as s:
                                    dbrec = s.query(SharedFile).get(rec.id)
                                    if dbrec and not dbrec.is_deleted:
                                        dbrec.is_deleted = True
                                        dbrec.deleted_by = user.get("username")
                                        dbrec.deleted_at = datetime.utcnow()
                                        s.commit()
                                        SecurityManager.log_audit(
                                            s,
                                            user.get("username"),
                                            "DELETE",
                                            resource_type="SharedFile",
                                            resource_id=str(rec.id),
                                            details=f"Deleted uid={rec.unique_id}",
                                            user_id=user.get("id"),
                                            location_id=active_location_id,
                                            success=True,
                                        )
                                st.success("File deleted.")
                                st.experimental_rerun()
                            except Exception as ex:
                                st.error(f"Delete failed: {ex}")
                                try:
                                    ActionLogger.log_error_with_task(
                                        ex,
                                        context="Sharing delete",
                                        user=user,
                                        location_id=active_location_id,
                                        severity="MEDIUM",
                                        additional_info=f"unique_id={rec.unique_id}"
                                    )
                                except Exception:
                                    pass
                    else:
                        st.button("🗑️ Delete (Admin only)", disabled=True, use_container_width=True, key=f"d_{rec.unique_id}")
                with c3:
                    st.caption(" ")
                st.markdown("---")
