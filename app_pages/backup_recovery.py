import streamlit as st
import pandas as pd
from datetime import datetime
from db import get_session
from ui import header
from security import SecurityManager
from backup_manager import BackupManager
from location_manager import LocationManager

def render_backup_recovery_page(active_location_id, user):
    role = (user or {}).get("role", "")
    if role not in ["admin-operations", "admin-it"]:
        header("Backup & Recovery")
        st.error("You do not have permission to access this page. Admin-Operations or Admin-IT only.")
        st.stop()

    header("Backup & Recovery")
    st.markdown("### Database Backup & Recovery Management")

    tab1, tab2, tab3 = st.tabs(["🗄️ Backups", "🗄️ Create Backup", "📤 Export Location"])

    with tab1:
        st.markdown("#### Available Backups")
        try:
            backups = BackupManager.list_backups()
            if backups:
                df = pd.DataFrame([
                    {
                        "Timestamp": datetime.fromisoformat(b["datetime"]).strftime("%Y-%m-%d %H:%M:%S"),
                        "Type": str(b.get("type", "")).title(),
                        "Description": b.get("description"),
                        "Size (MB)": b.get("size_mb"),
                        "File": b.get("filename"),
                    }
                    for b in backups
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.caption(f"Total backups: {len(backups)}")

                st.markdown("---")
                st.markdown("#### Restore from Backup")
                col1, col2 = st.columns([0.6, 0.4])
                with col1:
                    backup_options = {
                        f"{datetime.fromisoformat(b['datetime']).strftime('%Y-%m-%d %H:%M:%S')} - {b.get('description')} ({b.get('size_mb')} MB)": b["timestamp"]
                        for b in backups
                    }
                    selected_backup = st.selectbox(
                        "Select backup to restore",
                        options=list(backup_options.keys()),
                        key="br_restore_backup_select",
                    )
                    if selected_backup:
                        backup_ts = backup_options[selected_backup]
                        backup_info = BackupManager.get_backup_info(backup_ts)
                        if backup_info and backup_info.get("tables"):
                            tables_data = []
                            for table, count in backup_info["tables"].items():
                                tables_data.append({"Table": str(table).title(), "Records": count})
                            st.table(pd.DataFrame(tables_data))
                        st.warning("⚠️ Restoring will replace your current database")
                        st.caption("A backup of the current database will be created before restoration.")
                        confirm_restore = st.text_input('Type "RESTORE" to confirm', key="br_restore_confirm")
                        if st.button("♻️", key="br_restore_btn", type="primary", help="Restore Database"):
                            if confirm_restore == "RESTORE":
                                try:
                                    result = BackupManager.restore_backup(backup_ts, create_backup_before=True)
                                    st.success(f"Database restored successfully from {backup_ts}")
                                    if result.get("pre_restore_backup"):
                                        st.info(f"Pre-restore backup created: {result['pre_restore_backup']['filename']}")
                                    st.warning("Please restart the application for changes to take effect.")
                                    with get_session() as s:
                                        SecurityManager.log_audit(
                                            s,
                                            user.get("username"),
                                            "RESTORE_BACKUP",
                                            details=f"Restored from {backup_ts}",
                                            user_id=user.get("id"),
                                            location_id=user.get("location_id"),
                                        )
                                except Exception as ex:
                                    st.error(f"Restore failed: {ex}")
                            else:
                                st.error('Please type "RESTORE" to confirm.')
                with col2:
                    st.markdown("##### Delete Backup")
                    delete_backup_options = {
                        f"{datetime.fromisoformat(b['datetime']).strftime('%Y-%m-%d %H:%M:%S')} - {b.get('description')} ({b.get('size_mb')} MB)": b["timestamp"]
                        for b in backups
                    }
                    delete_backup = st.selectbox(
                        "Select backup to delete",
                        options=list(delete_backup_options.keys()),
                        key="br_delete_backup_select",
                    )
                    if delete_backup:
                        backup_ts = delete_backup_options[delete_backup]
                        if "delete_backup_step" not in st.session_state:
                            st.session_state.delete_backup_step = 0
                        if "delete_backup_pending" not in st.session_state:
                            st.session_state.delete_backup_pending = None
                        if st.session_state.delete_backup_step == 0:
                            if st.button("🗑️", key="br_delete_backup_btn_step1", help="Delete Backup"):
                                st.session_state.delete_backup_step = 1
                                st.session_state.delete_backup_pending = backup_ts
                                st.rerun()
                        elif st.session_state.delete_backup_step == 1:
                            st.warning("⚠️ Are you sure you want to delete this backup?")
                            st.caption("This action cannot be undone")
                            confirm_text = backup_ts
                            st.info(f"Type {confirm_text} to confirm deletion")
                            user_input = st.text_input("Confirmation", key="br_delete_backup_confirm_input", placeholder=confirm_text)
                            col_confirm, col_cancel = st.columns(2)
                            with col_confirm:
                                if st.button("✅", key="br_delete_backup_btn_step2", type="primary", help="Confirm Delete"):
                                    if user_input.strip() == confirm_text:
                                        try:
                                            BackupManager.delete_backup(st.session_state.delete_backup_pending)
                                            with get_session() as s:
                                                SecurityManager.log_audit(
                                                    s,
                                                    user.get("username"),
                                                    "DELETE_BACKUP",
                                                    details=f"Deleted backup {st.session_state.delete_backup_pending}",
                                                    user_id=user.get("id"),
                                                    location_id=user.get("location_id"),
                                                )
                                            st.success(f"Backup deleted: {st.session_state.delete_backup_pending}")
                                            st.session_state.delete_backup_step = 0
                                            st.session_state.delete_backup_pending = None
                                            st.rerun()
                                        except Exception as ex:
                                            st.error(f"Failed to delete: {ex}")
                                    else:
                                        st.error("Confirmation text does not match")
                            with col_cancel:
                                if st.button("❌", key="br_delete_backup_cancel", help="Cancel"):
                                    st.session_state.delete_backup_step = 0
                                    st.session_state.delete_backup_pending = None
                                    st.info("Deletion cancelled")
                                    st.rerun()
                st.markdown("---")
                st.markdown("#### Cleanup Old Backups")
                cleanup_col1, cleanup_col2 = st.columns(2)
                with cleanup_col1:
                    days = st.number_input("Delete backups older than (days)", min_value=1, value=30, step=1, key="br_cleanup_days")
                    keep_min = st.number_input("Always keep minimum", min_value=1, value=5, step=1, key="br_cleanup_keep_min")
                with cleanup_col2:
                    if st.button("🧹", key="br_cleanup_btn", help="Run Cleanup"):
                        try:
                            result = BackupManager.cleanup_old_backups(days=days, keep_minimum=keep_min)
                            st.success(f"Cleanup complete. Deleted: {result['deleted']}, Kept: {result['kept']}")
                            if result["deleted"] > 0:
                                st.rerun()
                        except Exception as ex:
                            st.error(f"Cleanup failed: {ex}")
            else:
                st.info("No backups found. Create your first backup in the 'Create Backup' tab.")
        except Exception as ex:
            st.error(f"Failed to load backups: {ex}")

    with tab2:
        st.markdown("#### Create Manual Backup")
        with st.form("br_create_backup_form"):
            description = st.text_input("Backup Description", placeholder="e.g., Before data migration, End of month backup, etc.", key="br_backup_description")
            submitted = st.form_submit_button("🗄️", type="primary", help="Create Backup Now")
            if submitted:
                try:
                    backup_info = BackupManager.create_backup(description=description or "Manual backup", backup_type="manual")
                    st.success("Backup created successfully")
                    col1, col2 = st.columns(2)
                    col1.metric("Filename", backup_info["filename"])
                    col2.metric("Size", f"{backup_info['size_mb']} MB")
                    st.info(f"Location: backups/{backup_info['filename']}")
                    with get_session() as s:
                        SecurityManager.log_audit(
                            s,
                            user.get("username"),
                            "CREATE_BACKUP",
                            details=description or "Manual backup",
                            user_id=user.get("id"),
                            location_id=user.get("location_id"),
                        )
                    st.rerun()
                except Exception as ex:
                    st.error(f"Backup creation failed: {ex}")
        st.markdown("---")
        st.markdown("#### Current Database Statistics")
        try:
            from models import Location, User, Tank, TankTransaction, YadeVoyage, OTRRecord
            with get_session() as s:
                stats = {
                    "Locations": s.query(Location).count(),
                    "Users": s.query(User).count(),
                    "Tanks": s.query(Tank).count(),
                    "Tank Transactions": s.query(TankTransaction).count(),
                    "YADE Voyages": s.query(YadeVoyage).count(),
                    "OTR Records": s.query(OTRRecord).count(),
                }
            col1, col2, col3, col4 = st.columns(4)
            cols = [col1, col2, col3, col4]
            for i, (key, value) in enumerate(stats.items()):
                cols[i % 4].metric(key, f"{value:,}")
        except Exception as ex:
            st.error(f"Failed to load stats: {ex}")

    with tab3:
        st.markdown("#### Export Location Data")
        st.caption("Export all data for a specific location to a ZIP file")
        try:
            with get_session() as s:
                locations = LocationManager.get_all_locations(s, active_only=False)
            if locations:
                loc_options = {f"{loc.name} ({loc.code})": loc.id for loc in locations}
                selected_loc = st.selectbox("Select Location to Export", options=list(loc_options.keys()), key="br_export_location_select")
                if st.button("📤", key="br_export_location_btn", type="primary", help="Export Location Data"):
                    if selected_loc:
                        loc_id = loc_options[selected_loc]
                        with st.spinner("Exporting location data..."):
                            try:
                                export_path = BackupManager.export_location_data(loc_id)
                                st.success("Location data exported successfully")
                                st.info(f"File: {export_path.name}")
                                with open(export_path, "rb") as f:
                                    st.download_button("⬇️", data=f.read(), file_name=export_path.name, mime="application/zip", help="Download Export")
                                with get_session() as s:
                                    SecurityManager.log_audit(
                                        s,
                                        user.get("username"),
                                        "EXPORT_LOCATION",
                                        resource_type="Location",
                                        resource_id=str(loc_id),
                                        details=f"Exported {selected_loc}",
                                        user_id=user.get("id"),
                                        location_id=user.get("location_id"),
                                    )
                            except Exception as ex:
                                st.error(f"Export failed: {ex}")
            else:
                st.warning("No locations found.")
        except Exception as ex:
            st.error(f"Failed to load locations: {ex}")
