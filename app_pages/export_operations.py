import streamlit as st
import streamlit.components.v1 as components
from typing import Optional, Dict, List, Any
from datetime import date

from db import get_session, get_flex_session
from models import get_custom_table_model
from permission_manager import PermissionManager
from security import SecurityManager
from location_config import get_page_section_config
from task_manager import TaskManager
from logger import log_error


def _guard_access(user: Optional[Dict]) -> bool:
    if not user:
        st.error("Please login to access this page")
        return False

    if not PermissionManager.can_access_export_operations(user):
        st.error("Access denied. You do not have Export Operations permission.")
        return False

    return True


def _st_safe_rerun():
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in [" ", "-", "/", "_"]:
            out.append("_")
    r = "".join(out)
    while "__" in r:
        r = r.replace("__", "_")
    return r.strip("_")


def render_export_operations_page(active_location_id: Optional[int], user: Optional[Dict]):
    st.markdown("### Shipment Operations")

    allowed = _guard_access(user)
    if not allowed:
        return

    st.markdown("---")
    terms: List[str] = []
    uid = (user or {}).get("id")
    uname = (user or {}).get("username") or ""
    loc_id = 0
    try:
        with get_session() as s:
            cfg = get_page_section_config(s, int(loc_id), "export_operations", "terminals") or {}
            terms = [str(x) for x in (cfg.get("items") or []) if str(x).strip()]
    except Exception as e:
        st.error(f"Error loading terminals: {str(e)}")
        terms = []

    # Debug information
    with st.expander("🔧 Debug Information", expanded=False):
        st.write(f"**Location ID used:** {loc_id}")
        st.write(f"**Terminals loaded:** {terms}")
        st.write(f"**User ID:** {uid}")
        st.write(f"**Username:** {uname}")
        if st.button("Refresh Terminals", key="debug_refresh_terms"):
            st.rerun()

    if not terms:
        st.info("Add terminals in Export Customization to begin.")
        return

    term = st.selectbox("Terminal", terms, key="exp_ops_term")

    tabs_cfg = {}
    try:
        with get_session() as s:
            tabs_cfg = get_page_section_config(s, int(loc_id), "export_operations", f"{_slug(term)}_tabs_{int(uid or 0)}") or {}
    except Exception:
        tabs_cfg = {}
    tabs = list(tabs_cfg.get("tabs") or [])

    # Main tabs: Dashboard, Shipment Manager, and Shipment Tracker are default, plus custom tabs
    tab_labels = ["Dashboard", "Shipment Manager", "Shipment Tracker"] + [t.get("label") or t.get("table") for t in tabs]
    st_tabs = st.tabs(tab_labels)
    def _load_pipeline_cfg(location_id: int, terminal_label: str) -> Dict[str, Any]:
        try:
            with get_session() as s:
                return get_page_section_config(s, location_id, "export_operations", f"pipeline_{_slug(terminal_label)}_{int(uid or 0)}") or {}
        except Exception:
            return {}
    def _create_export(location_id: int, terminal_label: str, title: str, ref_no: str, user: Dict[str, Any]) -> Optional[int]:
        try:
            from models import ExportProcess, ExportStageProgress
            with get_session() as s:
                exp = ExportProcess(
                    location_id=0,
                    terminal_label=str(terminal_label),
                    title=str(title),
                    ref_no=str(ref_no or "") or None,
                    status_overall="UPCOMING",
                    is_completed=False,
                    created_by=(user or {}).get("username"),
                )
                s.add(exp)
                s.flush()
                cfg = _load_pipeline_cfg(0, terminal_label)
                stages = list(cfg.get("stages") or [])
                if stages:
                    # Set the first stage as current
                    first = stages[0]
                    exp.current_stage_code = first.get("code")
                    
                    # Create ExportStageProgress records for ALL stages
                    for stage in stages:
                        s.add(ExportStageProgress(
                            export_id=exp.id,
                            stage_code=stage.get("code"),
                            status="Pending",
                            mandatory_complete=bool(stage.get("mandatory", True)),
                        ))
                s.commit()
                
                # Audit log the shipment creation
                try:
                    SecurityManager.log_audit(
                        s,
                        (user or {}).get("username", "system"),
                        "CREATE",
                        resource_type="ExportProcess",
                        resource_id=str(exp.id),
                        details=f"Created shipment '{title}' (Ref: {ref_no or 'N/A'}) for terminal {terminal_label}",
                        user_id=(user or {}).get("id"),
                        location_id=0,
                        ip_address=str(st.session_state.get("client_ip") or "N/A")
                    )
                except Exception as log_ex:
                    log_error(f"Failed to log audit for shipment creation: {log_ex}", exc_info=True)
                
                return exp.id
        except Exception as e:
            log_error(f"Failed to create export shipment: {e}", exc_info=True)
            try:
                TaskManager.create_error_task(
                    error_message=str(e),
                    context="Export Shipment Creation",
                    user=user,
                    location_id=0,
                    severity="HIGH",
                    additional_info=f"Terminal: {terminal_label}, Title: {title}"
                )
            except Exception as task_ex:
                log_error(f"Failed to create error task: {task_ex}", exc_info=True)
            return None
    
    def _recalculate_all_due_dates(export_id: int, cfg: Dict[str, Any]) -> None:
        """
        Recalculate and save due dates for all stages based on current status.
        Called after saving any stage to ensure all due dates are up to date.
        """
        try:
            from models import ExportProcess, ExportStageProgress
            from datetime import date as _date, timedelta as _td
            
            with get_session() as s:
                exp = s.query(ExportProcess).filter(ExportProcess.id == int(export_id)).one_or_none()
                if not exp:
                    return
                
                stages = list(cfg.get("stages") or [])
                if not stages:
                    return
                
                # Get all stage progress records
                all_progress = {
                    sp.stage_code: sp 
                    for sp in s.query(ExportStageProgress).filter(
                        ExportStageProgress.export_id == int(export_id)
                    ).all()
                }
                
                # Recalculate due date for each stage
                for stage_def in stages:
                    stage_code = stage_def.get("code")
                    default_days = int(stage_def.get("default_due_days") or 0)
                    due_source = str(stage_def.get("due_source") or "today")
                    anchor_code = str(stage_def.get("due_anchor_code") or "")
                    require_due = bool(stage_def.get("require_due_date", False))
                    
                    if not (require_due or default_days > 0):
                        continue
                    
                    progress = all_progress.get(stage_code)
                    if not progress:
                        continue
                    
                    # Calculate base date
                    base_date = None
                    try:
                        if due_source == "previous_stage":
                            codes = [s.get("code") for s in stages]
                            idx = codes.index(stage_code) if stage_code in codes else -1
                            if idx > 0:
                                prev_code = codes[idx - 1]
                                prev_progress = all_progress.get(prev_code)
                                if prev_progress and prev_progress.completed_at:
                                    base_date = prev_progress.completed_at.date()
                        elif due_source == "specific_stage" and anchor_code:
                            anchor_progress = all_progress.get(anchor_code)
                            if anchor_progress and anchor_progress.completed_at:
                                base_date = anchor_progress.completed_at.date()
                        elif due_source == "laycan_start":
                            if exp.laycan_start:
                                base_date = exp.laycan_start
                        elif due_source == "today":
                            base_date = _date.today()
                    except Exception as calc_ex:
                        log_error(f"Failed to calculate base date for {stage_code}: {calc_ex}", exc_info=True)
                    
                    # Calculate and save due date
                    if base_date:
                        try:
                            if due_source == "laycan_start":
                                # For laycan_start: SUBTRACT days
                                calculated_due = base_date - _td(days=default_days) if default_days > 0 else base_date
                            else:
                                # For all others: ADD days
                                calculated_due = base_date + _td(days=default_days) if default_days > 0 else base_date
                            
                            # Update the due date in database
                            progress.due_date = calculated_due
                        except Exception as save_ex:
                            log_error(f"Failed to save due date for {stage_code}: {save_ex}", exc_info=True)
                
                s.commit()
        except Exception as e:
            log_error(f"Failed to recalculate due dates: {e}", exc_info=True)
    
    def _list_exports(location_id: int, terminal_label: str, include_completed: bool) -> List[Dict[str, Any]]:
        out = []
        try:
            from models import ExportProcess
            with get_session() as s:
                q = s.query(ExportProcess).filter(ExportProcess.location_id == 0).filter(ExportProcess.terminal_label == str(terminal_label)).filter(ExportProcess.created_by == str(uname))
                if not include_completed:
                    q = q.filter(ExportProcess.is_completed == False)
                rows = q.order_by(ExportProcess.created_at.desc()).limit(200).all()
                for r in rows:
                    out.append({"id": r.id, "title": r.title, "ref_no": r.ref_no, "status": r.status_overall, "current_stage": r.current_stage_code, "created_at": r.created_at})
        except Exception:
            pass
        return out
    def _get_export(location_id: int, export_id: int) -> Optional[Dict[str, Any]]:
        try:
            from models import ExportProcess
            with get_session() as s:
                r = s.query(ExportProcess).filter(ExportProcess.id == int(export_id)).filter(ExportProcess.location_id == 0).filter(ExportProcess.created_by == str(uname)).one_or_none()
                if not r:
                    return None
                return {"id": r.id, "title": r.title, "ref_no": r.ref_no, "status": r.status_overall, "current_stage": r.current_stage_code, "is_completed": r.is_completed, "created_at": r.created_at, "laycan_start": getattr(r, "laycan_start", None), "laycan_end": getattr(r, "laycan_end", None)}
        except Exception:
            return None
    def _get_stage_progress(export_id: int, stage_code: str):
        try:
            from models import ExportStageProgress
            with get_session() as s:
                r = s.query(ExportStageProgress).filter(ExportStageProgress.export_id == int(export_id)).filter(ExportStageProgress.stage_code == str(stage_code)).one_or_none()
                return r
        except Exception:
            return None
    def _save_stage_status(export_id: int, stage_code: str, new_status: str, mandatory: bool, user: Dict[str, Any], due_date=None, remarks: str = None, completion_date=None, manual_completion_required: bool = False, completion_statuses=None, laycan_start=None, laycan_end=None, overdue_reason=None) -> bool:
        try:
            from models import ExportStageProgress, ExportProcess
            from datetime import datetime as _dt
            with get_session() as s:
                r = s.query(ExportStageProgress).filter(ExportStageProgress.export_id == int(export_id)).filter(ExportStageProgress.stage_code == str(stage_code)).one_or_none()
                if not r:
                    r = ExportStageProgress(export_id=int(export_id), stage_code=str(stage_code), status=new_status or "Pending", mandatory_complete=bool(mandatory))
                    s.add(r)
                else:
                    r.status = str(new_status or "Pending")
                if due_date:
                    try:
                        r.due_date = due_date
                    except Exception:
                        pass
                if remarks is not None:
                    r.remarks = (remarks or None)
                comp_list = list(completion_statuses or ["Completed"])
                if str((new_status or "")).strip() in comp_list:
                    if manual_completion_required and completion_date:
                        try:
                            from datetime import datetime as _dt2, time as _t, date as _d
                            if isinstance(completion_date, _d):
                                r.completed_at = _dt2.combine(completion_date, _t(0, 0, 0))
                            else:
                                r.completed_at = completion_date
                        except Exception:
                            r.completed_at = _dt.utcnow()
                    else:
                        r.completed_at = _dt.utcnow()
                    r.completed_by = (user or {}).get("username")
                    try:
                        if r.due_date and r.completed_at:
                            r.completed_overdue = (r.completed_at.date() > r.due_date)
                    except Exception:
                        pass
                    if overdue_reason is not None:
                        r.overdue_reason = (overdue_reason or None)
                
                # If laycan dates provided, update the export process (moved outside completion check)
                if laycan_start is not None or laycan_end is not None:
                    exp = s.query(ExportProcess).get(int(export_id))
                    if exp:
                        if laycan_start is not None:
                            log_error(f"DEBUG: Saving laycan_start={laycan_start} (type: {type(laycan_start)}) for export_id={export_id}", exc_info=False)
                            exp.laycan_start = laycan_start
                        if laycan_end is not None:
                            log_error(f"DEBUG: Saving laycan_end={laycan_end} (type: {type(laycan_end)}) for export_id={export_id}", exc_info=False)
                            exp.laycan_end = laycan_end
                        s.flush()  # Force flush to ensure dates are saved
                        log_error(f"DEBUG: After flush - exp.laycan_start={exp.laycan_start}, exp.laycan_end={exp.laycan_end}", exc_info=False)
                
                # Check if all stages are completed
                # Only set updated_at/updated_by if this is an update to an existing record
                if r.id:  # If record already has an ID, it existed before
                    r.updated_at = _dt.utcnow()
                    r.updated_by = (user or {}).get("username")
                s.flush()
                
                # Get all stages for this export and check completion
                exp = s.query(ExportProcess).get(int(export_id))
                if exp:
                    # Get the pipeline configuration to know all stages
                    all_stage_progress = s.query(ExportStageProgress).filter(
                        ExportStageProgress.export_id == int(export_id)
                    ).all()
                    
                    # Check if all stages are completed
                    if all_stage_progress:
                        all_completed = True
                        for sp in all_stage_progress:
                            sp_status = getattr(sp, "status", "")
                            # Get completion statuses for this stage from config
                            # We need to check against completion_statuses
                            if sp_status not in comp_list:
                                all_completed = False
                                break
                        
                        # If all stages are completed, mark the export as completed
                        if all_completed:
                            exp.status = "Completed"
                            try:
                                exp.is_completed = True
                            except Exception:
                                pass
                
                s.commit()
                
                # Audit log the stage update
                try:
                    SecurityManager.log_audit(
                        s,
                        (user or {}).get("username", "system"),
                        "UPDATE",
                        resource_type="ExportStageProgress",
                        resource_id=f"{export_id}_{stage_code}",
                        details=f"Updated stage '{stage_code}' to status '{new_status}' for export #{export_id}",
                        user_id=(user or {}).get("id"),
                        location_id=0,
                        ip_address=str(st.session_state.get("client_ip") or "N/A")
                    )
                except Exception as log_ex:
                    log_error(f"Failed to log audit for stage update: {log_ex}", exc_info=True)
                
                return True
        except Exception as e:
            log_error(f"Failed to save stage status: {e}", exc_info=True)
            try:
                TaskManager.create_error_task(
                    error_message=str(e),
                    context="Export Stage Status Update",
                    user=user,
                    location_id=0,
                    severity="MEDIUM",
                    additional_info=f"Export ID: {export_id}, Stage: {stage_code}, Status: {new_status}"
                )
            except Exception as task_ex:
                log_error(f"Failed to create error task: {task_ex}", exc_info=True)
            return False
    def _progress_to_next_stage(export_id: int, cfg: Dict[str, Any], user: Dict[str, Any]) -> bool:
        try:
            from models import ExportProcess, ExportStageProgress
            with get_session() as s:
                exp = s.query(ExportProcess).get(int(export_id))
                if not exp:
                    return False
                stages = list(cfg.get("stages") or [])
                codes = [st.get("code") for st in stages]
                if not codes:
                    return False
                cur = exp.current_stage_code
                if cur not in codes:
                    exp.current_stage_code = codes[0]
                    s.commit()
                    return True
                idx = codes.index(cur)
                if idx >= len(codes) - 1:
                    exp.is_completed = True
                    exp.status_overall = "COMPLETED"
                    s.commit()
                    return True
                next_code = codes[idx + 1]
                exp.current_stage_code = next_code
                # Don't create new ExportStageProgress - it already exists from _create_export
                # Just update the current_stage_code
                s.commit()
                
                # Audit log the stage advancement
                try:
                    SecurityManager.log_audit(
                        s,
                        (user or {}).get("username", "system"),
                        "UPDATE",
                        resource_type="ExportProcess",
                        resource_id=str(export_id),
                        details=f"Advanced export #{export_id} from stage '{cur}' to '{next_code}'",
                        user_id=(user or {}).get("id"),
                        location_id=0,
                        ip_address=str(st.session_state.get("client_ip") or "N/A")
                    )
                except Exception as log_ex:
                    log_error(f"Failed to log audit for stage advancement: {log_ex}", exc_info=True)
                
                return True
        except Exception as e:
            log_error(f"Failed to progress to next stage: {e}", exc_info=True)
            try:
                TaskManager.create_error_task(
                    error_message=str(e),
                    context="Export Stage Advancement",
                    user=user,
                    location_id=0,
                    severity="MEDIUM",
                    additional_info=f"Export ID: {export_id}"
                )
            except Exception as task_ex:
                log_error(f"Failed to create error task: {task_ex}", exc_info=True)
            return False
    def _upload_stage_files(export_id: int, stage_code: str, files: List, vis: str, assignees_usernames: List[str], user: Dict[str, Any]) -> bool:
        try:
            from models import ExportStageProgress, ExportAttachment, User
            with get_session() as s:
                stg = s.query(ExportStageProgress).filter(ExportStageProgress.export_id == int(export_id)).filter(ExportStageProgress.stage_code == str(stage_code)).one_or_none()
                if not stg:
                    return False
                assignee_id = None
                if vis == "restricted" and assignees_usernames:
                    u = s.query(User).filter(User.username.in_([assignees_usernames[0]])).one_or_none()
                    if u:
                        assignee_id = u.id
                for f in files or []:
                    data = f.read() if hasattr(f, "read") else None
                    name = getattr(f, "name", "uploaded.bin")
                    mime = getattr(f, "type", None)
                    size = len(data) if data else 0
                    att = ExportAttachment(stage_id=stg.id, filename=name, mime_type=mime, size_bytes=size, data=data or b"", visibility=str(vis or "global"), assigned_to_user_id=assignee_id, uploaded_by=(user or {}).get("username"))
                    s.add(att)
                s.commit()
                
                # Audit log the file uploads
                try:
                    SecurityManager.log_audit(
                        s,
                        (user or {}).get("username", "system"),
                        "UPLOAD",
                        resource_type="ExportAttachment",
                        resource_id=f"{export_id}_{stage_code}",
                        details=f"Uploaded {len(files or [])} file(s) to stage '{stage_code}' for export #{export_id}",
                        user_id=(user or {}).get("id"),
                        location_id=0,
                        ip_address=str(st.session_state.get("client_ip") or "N/A")
                    )
                except Exception as log_ex:
                    log_error(f"Failed to log audit for file upload: {log_ex}", exc_info=True)
                
                return True
        except Exception as e:
            log_error(f"Failed to upload stage files: {e}", exc_info=True)
            try:
                TaskManager.create_error_task(
                    error_message=str(e),
                    context="Export Stage File Upload",
                    user=user,
                    location_id=0,
                    severity="MEDIUM",
                    additional_info=f"Export ID: {export_id}, Stage: {stage_code}"
                )
            except Exception as task_ex:
                log_error(f"Failed to create error task: {task_ex}", exc_info=True)
            return False
    
    # Load pipeline configuration
    cfg = _load_pipeline_cfg(int(loc_id or 0), term)
    stages = list(cfg.get("stages") or [])
    
    if not stages:
        st.warning("No stages configured for this terminal. First add stages in Export Customization → Process Pipeline, then create shipments.")
        if st.button("Go to Export Customization", key="exp_go_customize"):
            components.html(
                """
                <script>
                try {
                  const url = new URL(window.location.href);
                  url.searchParams.set('chapter', 'export_customization');
                  window.open(url.toString(), '_blank');
                } catch (e) {}
                </script>
                """,
                height=0,
            )
        return
    
    # Dashboard Tab
    with st_tabs[0]:
        st.markdown("#### Dashboard")
        
        # Filters section
        filter_col1, filter_col2 = st.columns([0.7, 0.3])
        with filter_col1:
            shipment_filter = st.text_input("🔍 Filter by Shipment Name", key="exp_dash_filter", placeholder="Type to search shipments...")
        with filter_col2:
            inc_completed_dash = st.checkbox("Show completed", value=False, key="exp_show_completed_dash")
        
        rows = _list_exports(int(loc_id or 0), term, bool(inc_completed_dash))
        
        # Apply shipment name filter
        if shipment_filter:
            filter_lower = shipment_filter.lower()
            rows = [r for r in rows if filter_lower in (r.get("title") or "").lower() or filter_lower in (r.get("ref_no") or "").lower()]
        
        if rows and stages:
            st.markdown(f"**Showing {len(rows)} shipment(s)**")
            st.markdown("---")
            
            # Show process route map for each shipment directly (no expander)
            for r in rows:
                st.markdown(f"### 🛢️ {r.get('title')}")
                st.caption(f"**Reference:** {r.get('ref_no') or 'N/A'} | **Status:** {r.get('status')} | **Created:** {r.get('created_at').strftime('%d/%m/%Y') if r.get('created_at') else 'N/A'}")
                
                try:
                    export_id = r.get("id")
                    stage_codes = [s.get("code") for s in stages]
                    comp_map = {s.get("code"): list(s.get("completion_statuses") or ["Completed"]) for s in stages}
                    status_items = []
                    for sc in stage_codes:
                        row = _get_stage_progress(int(export_id), sc)
                        if not row:
                            status = "Not Started"
                            date_info = ""
                            due_note = ""
                            overdue_flag = False
                        else:
                            rs = getattr(row, "status", "Pending") or "Pending"
                            status = "Completed" if rs in comp_map.get(sc, ["Completed"]) else rs
                            
                            # Get date information
                            completed_at = getattr(row, "completed_at", None)
                            due_date = getattr(row, "due_date", None)
                            
                            if status == "Completed" and completed_at:
                                date_info = f"✅ {completed_at.strftime('%d/%m/%Y')}"
                                due_note = ""
                                overdue_flag = False
                            elif status != "Completed" and due_date:
                                from datetime import date as _d, timedelta as _td
                                today = _d.today()
                                if due_date < today:
                                    days_overdue = (today - due_date).days
                                    due_note = f"🚨 {days_overdue}d overdue"
                                    date_info = f"📅 {due_date.strftime('%d/%m/%Y')}"
                                    overdue_flag = True
                                elif due_date == today:
                                    due_note = "⚠️ Due TODAY"
                                    date_info = f"📅 {due_date.strftime('%d/%m/%Y')}"
                                    overdue_flag = False
                                elif due_date == today + _td(days=1):
                                    due_note = "📅 Tomorrow"
                                    date_info = f"📅 {due_date.strftime('%d/%m/%Y')}"
                                    overdue_flag = False
                                else:
                                    days_left = (due_date - today).days
                                    due_note = f"🗓️ {days_left}d left"
                                    date_info = f"📅 {due_date.strftime('%d/%m/%Y')}"
                                    overdue_flag = False
                            else:
                                date_info = ""
                                due_note = ""
                                overdue_flag = False
                        
                        status_items.append({
                            "code": sc, 
                            "name": (next((sd.get("name") for sd in stages if sd.get("code") == sc), sc) or sc), 
                            "status": status,
                            "date_info": date_info,
                            "due_note": due_note,
                            "overdue": overdue_flag
                        })
                    
                    def _color(s):
                        ss = (s or "").lower()
                        if ss == "completed":
                            return "#16a34a"
                        if ss in ["in progress", "approved"]:
                            return "#2563eb"
                        if ss in ["pending", "not started"]:
                            return "#6b7280"
                        return "#6b7280"
                    
                    html = "<div style=\"margin:15px 0;\">"
                    for i, it in enumerate(status_items):
                        date_html = f"<div style=\"font-size:11px;opacity:.85;margin-top:4px;\">{it['date_info']}</div>" if it['date_info'] else ""
                        note_html = f"<div style=\"font-size:11px;font-weight:600;opacity:.95;margin-top:2px;\">{it['due_note']}</div>" if it.get("due_note") else ""
                        glow = "box-shadow:0 0 10px #ef4444,0 0 20px #ef4444;" if it.get("overdue") else ""
                        html += (
                            f"<div style=\"display:inline-block;padding:12px 16px;margin:6px;border-radius:12px;background:{_color(it['status'])};color:#fff;{glow}min-width:120px;text-align:center;\">"
                            f"<div style=\"font-weight:700;font-size:13px;\">{it['name']}</div>"
                            f"<div style=\"font-size:11px;opacity:.9;margin-top:4px;\">{it['status']}</div>"
                            f"{date_html}"
                            f"{note_html}"
                            f"</div>"
                        )
                        if i < len(status_items) - 1:
                            html += "<span style=\"margin:0 6px;color:#64748b;font-size:18px;\">→</span>"
                    html += "</div>"
                    st.markdown(html, unsafe_allow_html=True)
                except Exception as ex:
                    st.error(f"Unable to load route map: {str(ex)}")
                
                st.markdown("---")
        else:
            if shipment_filter:
                st.info(f"No shipments found matching '{shipment_filter}'")
            else:
                st.info("No shipments to display")
    
    # Shipment Manager Tab
    with st_tabs[1]:
        st.markdown("#### Shipment Manager")
        st.caption("Create, edit, or delete shipments. Only Admin-Operations can delete shipments.")
        
        # Create new shipment section
        st.markdown("##### Create New Shipment")
        col1, col2 = st.columns([0.5, 0.5])
        with col1:
            # Use session state keys for clearing after save
            new_mgr_title = st.text_input("Shipment Title", key="exp_mgr_new_title", value=st.session_state.get("exp_mgr_title_value", ""))
            new_mgr_ref = st.text_input("Shipment Reference No", key="exp_mgr_new_ref", value=st.session_state.get("exp_mgr_ref_value", ""))
        with col2:
            st.markdown("")
            st.markdown("")
            if st.button("➕ Create Shipment", key="exp_mgr_create", help="Create new shipment", type="primary"):
                exp_id = _create_export(int(loc_id or 0), term, new_mgr_title or "Untitled Shipment", new_mgr_ref or "", user or {})
                if exp_id:
                    st.success("Shipment created successfully")
                    # Clear the input fields by resetting session state
                    st.session_state["exp_mgr_title_value"] = ""
                    st.session_state["exp_mgr_ref_value"] = ""
                    st.rerun()
                else:
                    st.error("Failed to create shipment")
        
        st.markdown("---")
        st.markdown("##### Manage Existing Shipments")
        
        # Show all shipments (including completed)
        mgr_rows = _list_exports(int(loc_id or 0), term, include_completed=True)
        
        if mgr_rows:
            # Check if user is Admin-Operations
            user_role = (user or {}).get("role", "").lower()
            can_delete = user_role in ["admin-operations"]
            
            if not can_delete:
                st.info("ℹ️ Only Admin-Operations can delete shipments. To request deletion, please raise a request through Services.")
            
            for row in mgr_rows:
                exp_id = row.get("id")
                exp_title = row.get("title")
                exp_ref = row.get("ref_no")
                exp_status = row.get("status")
                exp_current_stage = row.get("current_stage")
                
                with st.expander(f"🛢️ {exp_title} • {exp_ref or 'N/A'} • {exp_status}"):
                    # Edit form
                    st.markdown("**Edit Shipment Details**")
                    edit_col1, edit_col2 = st.columns([0.5, 0.5])
                    
                    with edit_col1:
                        edit_title = st.text_input("Title", value=exp_title, key=f"exp_mgr_edit_title_{exp_id}")
                        edit_ref = st.text_input("Reference No", value=exp_ref or "", key=f"exp_mgr_edit_ref_{exp_id}")
                    
                    with edit_col2:
                        st.markdown(f"**Current Stage:** {exp_current_stage or 'N/A'}")
                        st.markdown(f"**Status:** {exp_status}")
                    
                    btn_col1, btn_col2 = st.columns([0.5, 0.5])
                    
                    with btn_col1:
                        if st.button("💾 Save Changes", key=f"exp_mgr_save_{exp_id}", type="primary"):
                            # Update the export
                            try:
                                from models import ExportProcess
                                with get_session() as s:
                                    exp = s.query(ExportProcess).filter(ExportProcess.id == exp_id).one_or_none()
                                    if exp:
                                        old_title = exp.title
                                        old_ref = exp.ref_no
                                        exp.title = edit_title or "Untitled Shipment"
                                        exp.ref_no = edit_ref or ""
                                        s.commit()
                                        
                                        # Audit log the edit
                                        try:
                                            SecurityManager.log_audit(
                                                s,
                                                (user or {}).get("username", "system"),
                                                "UPDATE",
                                                resource_type="ExportProcess",
                                                resource_id=str(exp_id),
                                                details=f"Updated shipment #{exp_id}: Title '{old_title}' -> '{edit_title}', Ref '{old_ref}' -> '{edit_ref}'",
                                                user_id=(user or {}).get("id"),
                                                location_id=0,
                                                ip_address=str(st.session_state.get("client_ip") or "N/A")
                                            )
                                        except Exception as log_ex:
                                            log_error(f"Failed to log audit for shipment edit: {log_ex}", exc_info=True)
                                        
                                        st.success("Changes saved successfully")
                                        st.rerun()
                                    else:
                                        st.error("Shipment not found")
                            except Exception as ex:
                                log_error(f"Failed to save shipment changes: {ex}", exc_info=True)
                                st.error(f"Failed to save changes: {str(ex)}")
                                try:
                                    TaskManager.create_error_task(
                                        error_message=str(ex),
                                        context="Shipment Edit (Manager)",
                                        user=user,
                                        location_id=0,
                                        severity="MEDIUM",
                                        additional_info=f"Export ID: {exp_id}"
                                    )
                                except Exception as task_ex:
                                    log_error(f"Failed to create error task: {task_ex}", exc_info=True)
                    
                    with btn_col2:
                        if can_delete:
                            if st.button("🗑️ Delete Shipment", key=f"exp_mgr_delete_{exp_id}", help="Permanently delete this shipment"):
                                st.session_state[f"exp_mgr_confirm_delete_{exp_id}"] = True
                                st.rerun()
                        else:
                            st.button("🗑️ Delete (Admin Only)", key=f"exp_mgr_delete_disabled_{exp_id}", disabled=True, help="Only Admin-Operations can delete shipments")
                    
                    # Confirmation dialog for delete
                    if st.session_state.get(f"exp_mgr_confirm_delete_{exp_id}"):
                        st.warning(f"⚠️ **Are you sure you want to delete '{exp_title}'?**")
                        
                        # Checkbox for permanent deletion
                        permanent_delete = st.checkbox(
                            "🗑️ **Permanently delete from database** (cannot be recovered)", 
                            value=False, 
                            key=f"exp_mgr_permanent_delete_{exp_id}",
                            help="If checked, the shipment will be completely removed from the database. If unchecked, it will be moved to the Recycle Bin for potential recovery."
                        )
                        
                        if permanent_delete:
                            st.error("⚠️ **WARNING:** This will PERMANENTLY delete the shipment and all associated stages, attachments, and history. This action CANNOT be undone.")
                        else:
                            st.info("ℹ️ The shipment will be moved to the Recycle Bin. Administrators can restore it later if needed.")
                        
                        conf_col1, conf_col2 = st.columns([0.5, 0.5])
                        with conf_col1:
                            if st.button("✅ Yes, Delete", key=f"exp_mgr_confirm_yes_{exp_id}", type="primary"):
                                try:
                                    from models import ExportProcess
                                    from recycle_bin import RecycleBinManager
                                    
                                    with get_session() as s:
                                        exp = s.query(ExportProcess).filter(ExportProcess.id == exp_id).one_or_none()
                                        if exp:
                                            exp_title_backup = exp.title
                                            exp_ref_backup = exp.ref_no
                                            
                                            if permanent_delete:
                                                # Hard delete - completely remove from database
                                                s.delete(exp)
                                                s.commit()
                                                
                                                # Audit log the permanent deletion
                                                try:
                                                    SecurityManager.log_audit(
                                                        s,
                                                        (user or {}).get("username", "system"),
                                                        "DELETE",
                                                        resource_type="ExportProcess",
                                                        resource_id=str(exp_id),
                                                        details=f"PERMANENTLY deleted shipment #{exp_id}: '{exp_title_backup}' (Ref: {exp_ref_backup or 'N/A'}) - Hard delete",
                                                        user_id=(user or {}).get("id"),
                                                        location_id=0,
                                                        ip_address=str(st.session_state.get("client_ip") or "N/A")
                                                    )
                                                except Exception as log_ex:
                                                    log_error(f"Failed to log audit for permanent deletion: {log_ex}", exc_info=True)
                                                
                                                st.success("✅ Shipment permanently deleted from database")
                                            else:
                                                # Soft delete - move to recycle bin
                                                try:
                                                    RecycleBinManager.archive_record(
                                                        session=s,
                                                        record=exp,
                                                        resource_type="ExportProcess",
                                                        username=(user or {}).get("username", "system"),
                                                        user_id=(user or {}).get("id"),
                                                        location_id=0,
                                                        reason="User deleted shipment from Export Operations Manager",
                                                        label=f"{exp_title_backup} (Ref: {exp_ref_backup or 'N/A'})"
                                                    )
                                                    s.commit()
                                                    
                                                    # Audit log the soft deletion
                                                    try:
                                                        SecurityManager.log_audit(
                                                            s,
                                                            (user or {}).get("username", "system"),
                                                            "DELETE",
                                                            resource_type="ExportProcess",
                                                            resource_id=str(exp_id),
                                                            details=f"Moved shipment #{exp_id}: '{exp_title_backup}' (Ref: {exp_ref_backup or 'N/A'}) to Recycle Bin - Soft delete",
                                                            user_id=(user or {}).get("id"),
                                                            location_id=0,
                                                            ip_address=str(st.session_state.get("client_ip") or "N/A")
                                                        )
                                                    except Exception as log_ex:
                                                        log_error(f"Failed to log audit for soft deletion: {log_ex}", exc_info=True)
                                                    
                                                    st.success("✅ Shipment moved to Recycle Bin (can be restored by administrators)")
                                                except Exception as rb_ex:
                                                    log_error(f"Failed to move shipment to recycle bin: {rb_ex}", exc_info=True)
                                                    st.error(f"Failed to move to recycle bin: {str(rb_ex)}")
                                                    s.rollback()
                                                    raise
                                            
                                            if f"exp_mgr_confirm_delete_{exp_id}" in st.session_state:
                                                del st.session_state[f"exp_mgr_confirm_delete_{exp_id}"]
                                            if f"exp_mgr_permanent_delete_{exp_id}" in st.session_state:
                                                del st.session_state[f"exp_mgr_permanent_delete_{exp_id}"]
                                            st.rerun()
                                        else:
                                            st.error("Shipment not found")
                                except Exception as ex:
                                    log_error(f"Failed to delete shipment: {ex}", exc_info=True)
                                    st.error(f"Failed to delete shipment: {str(ex)}")
                                    try:
                                        TaskManager.create_error_task(
                                            error_message=str(ex),
                                            context="Shipment Deletion (Manager)",
                                            user=user,
                                            location_id=0,
                                            severity="HIGH",
                                            additional_info=f"Export ID: {exp_id}, Title: {exp_title}"
                                        )
                                    except Exception as task_ex:
                                        log_error(f"Failed to create error task: {task_ex}", exc_info=True)
                        
                        with conf_col2:
                            if st.button("❌ Cancel", key=f"exp_mgr_confirm_no_{exp_id}"):
                                if f"exp_mgr_confirm_delete_{exp_id}" in st.session_state:
                                    del st.session_state[f"exp_mgr_confirm_delete_{exp_id}"]
                                st.rerun()
        else:
            st.info("No shipments found. Create a new shipment above.")
    
    # Shipment Tracker Tab
    with st_tabs[2]:
        st.markdown("#### Shipment Tracker")
        st.caption("Select a shipment to track and manage its stages. Create new shipments in the Shipment Manager tab.")
        
        inc_completed = st.checkbox("Show completed shipments", value=False, key="exp_show_completed")
        rows = _list_exports(int(loc_id or 0), term, bool(inc_completed))
        
        cur_id = None
        cur_export = None
        if rows:
            exp_options = [f"{r['id']} • {r['title']}" for r in rows]
            id_map = {opt: r["id"] for opt, r in zip(exp_options, rows)}
            sel = st.selectbox("Select Shipment", options=exp_options, key="exp_sel_current")
            cur_id = id_map.get(sel)
            cur_export = _get_export(int(loc_id or 0), int(cur_id or 0)) if cur_id else None
        if cur_export and stages:
                cur_stage_code = cur_export.get("current_stage")
                
                # Show process route map with shipment name
                st.markdown(f"### 🛢️ {cur_export.get('title')}")
                st.caption(f"**Reference:** {cur_export.get('ref_no') or 'N/A'} | **Status:** {cur_export.get('status')}")
                
                try:
                    stage_codes = [s.get("code") for s in stages]
                    comp_map = {s.get("code"): list(s.get("completion_statuses") or ["Completed"]) for s in stages}
                    status_items = []
                    for sc in stage_codes:
                        row = _get_stage_progress(int(cur_id), sc)
                        if not row:
                            status = "Not Started"
                            date_info = ""
                        else:
                            rs = getattr(row, "status", "Pending") or "Pending"
                            status = "Completed" if rs in comp_map.get(sc, ["Completed"]) else rs
                            
                            # Get date information
                            completed_at = getattr(row, "completed_at", None)
                            due_date = getattr(row, "due_date", None)
                            
                            if status == "Completed" and completed_at:
                                date_info = f"Completed: {completed_at.strftime('%Y-%m-%d')}"
                            elif status != "Completed" and due_date:
                                date_info = f"Due: {due_date.strftime('%Y-%m-%d')}"
                            else:
                                date_info = ""
                        
                        status_items.append({
                            "code": sc, 
                            "name": (next((sd.get("name") for sd in stages if sd.get("code") == sc), sc) or sc), 
                            "status": status,
                            "date_info": date_info
                        })
                    
                    def _color(s):
                        ss = (s or "").lower()
                        if ss == "completed":
                            return "#16a34a"
                        if ss in ["in progress", "approved"]:
                            return "#2563eb"
                        if ss in ["pending", "not started"]:
                            return "#6b7280"
                        return "#6b7280"
                    
                    html = "<div style='margin: 20px 0;'>"
                    for i, it in enumerate(status_items):
                        date_html = f"<div style=\"font-size:11px;opacity:.85\">{it['date_info']}</div>" if it['date_info'] else ""
                        html += (
                            f"<div style=\"display:inline-block;padding:10px 14px;margin:6px;border-radius:10px;background:{_color(it['status'])};color:#fff;\">"
                            f"<div style=\"font-weight:600\">{it['name']}</div>"
                            f"<div style=\"font-size:12px;opacity:.9\">{it['status']}</div>"
                            f"{date_html}"
                            f"</div>"
                        )
                        if i < len(status_items) - 1:
                            html += "<span style=\"margin:0 4px;color:#64748b;font-size:18px\">→</span>"
                    html += "</div>"
                    st.markdown(html, unsafe_allow_html=True)
                except Exception:
                    pass
                
                st.markdown("---")
                st.markdown("##### Shipment Stages")
                
                # Show all stages with expandable sections
                for stage_idx, stage_def in enumerate(stages):
                    stage_code = stage_def.get("code")
                    stage_name = stage_def.get("name")
                    is_current = (stage_code == cur_stage_code)
                    
                    # Get progress for this stage
                    progress_row = _get_stage_progress(int(cur_id), stage_code)
                    current_status = getattr(progress_row, "status", "Pending") if progress_row else "Pending"
                    
                    # Determine completion
                    comp_list = list(stage_def.get("completion_statuses") or ["Completed"])
                    is_completed = (current_status in comp_list)
                    
                    # Visual indicator
                    if is_completed:
                        icon = "✅"
                        color = "#16a34a"
                    elif is_current:
                        icon = "🔵"
                        color = "#2563eb"
                    else:
                        icon = "⚪"
                        color = "#6b7280"
                    
                    stage_label = f"{icon} **{stage_name}** - {current_status}"
                    if is_current:
                        stage_label += " (Current)"
                    
                    # Check if data exists and is saved
                    # For new stages with only default "Pending" status and no other changes, treat as unsaved
                    has_meaningful_data = progress_row is not None and (
                        getattr(progress_row, "status", "Pending") != "Pending" or
                        getattr(progress_row, "remarks", None) is not None or
                        getattr(progress_row, "due_date", None) is not None or
                        getattr(progress_row, "completed_at", None) is not None or
                        getattr(progress_row, "updated_at", None) is not None
                    )
                    edit_key = f"exp_stage_edit_{stage_code}_{cur_id}"
                    is_editing = st.session_state.get(edit_key, not has_meaningful_data)
                    
                    with st.expander(stage_label, expanded=is_current):
                        s1, s2 = st.columns([0.5, 0.5])
                        with s1:
                            st.write(f"**Stage {stage_idx + 1}:** {stage_name}")
                            st.write(f"**Code:** {stage_code}")
                            if getattr(progress_row, "completed_at", None):
                                st.write(f"**Completed:** {getattr(progress_row, 'completed_at')}")
                                st.write(f"**Completed by:** {getattr(progress_row, 'completed_by', 'N/A')}")
                            
                            # Show edit history ONLY if the record has been explicitly updated (not just created)
                            updated_by = getattr(progress_row, "updated_by", None)
                            updated_at = getattr(progress_row, "updated_at", None)
                            if updated_by and updated_at and has_meaningful_data:
                                st.markdown(f"<span style='color:#f59e0b'>⚠️ Edited by {updated_by} on {updated_at.strftime('%Y-%m-%d %H:%M:%S')}</span>", unsafe_allow_html=True)
                            
                            # Edit button for saved stages
                            if has_meaningful_data and not is_editing:
                                if st.button("✏️ Edit", key=f"exp_stage_edit_btn_{stage_code}_{cur_id}"):
                                    st.session_state[edit_key] = True
                                    _st_safe_rerun()
                        
                        with s2:
                            # Define new_stat for use throughout the section
                            new_stat = current_status
                            
                            if is_editing:
                                statuses = list(stage_def.get("statuses") or ["Pending","In Progress","Completed"])
                                new_stat = st.selectbox("Status", options=statuses, index=max(0, statuses.index(current_status) if current_status in statuses else 0), key=f"exp_stage_status_{stage_code}_{cur_id}")
                            else:
                                st.write(f"**Status:** {current_status}")
                            
                            # Display due date from database with status notifications
                            due_val = None
                            require_due = bool(stage_def.get("require_due_date", False))
                            default_days = int(stage_def.get("default_due_days") or 0)
                            due_source = str(stage_def.get("due_source") or "today")
                            
                            if require_due or default_days > 0:
                                from datetime import date as _date, timedelta as _td
                                
                                # Get the due date from database (already calculated and saved)
                                saved_due_date = getattr(progress_row, "due_date", None) if progress_row else None
                                due_val = saved_due_date
                                
                                # Display due date with status notifications
                                if saved_due_date:
                                    today = _date.today()
                                    if saved_due_date < today:
                                        # Overdue
                                        days_overdue = (today - saved_due_date).days
                                        st.error(f"🚨 **Due Date:** {saved_due_date.strftime('%d/%m/%Y')} (Overdue by {days_overdue} days - Complete Soon!)")
                                    elif saved_due_date == today:
                                        # Due today
                                        st.warning(f"⚠️ **Due Date:** {saved_due_date.strftime('%d/%m/%Y')} (Due TODAY!)")
                                    elif saved_due_date == today + _td(days=1):
                                        # Due tomorrow
                                        st.info(f"📅 **Due Date:** {saved_due_date.strftime('%d/%m/%Y')} (Due Tomorrow)")
                                    else:
                                        # Future due date
                                        st.write(f"**Due Date:** {saved_due_date.strftime('%d/%m/%Y')}")
                                    
                                    # Show calculation info
                                    if due_source == "laycan_start":
                                        st.caption(f"📊 Calculated from Laycan Day 1 minus {default_days} days")
                                    elif due_source == "previous_stage":
                                        st.caption(f"📊 Calculated from Previous Stage completion plus {default_days} days")
                                    elif due_source == "specific_stage":
                                        st.caption(f"📊 Calculated from Anchor Stage completion plus {default_days} days")
                                    elif due_source == "today":
                                        st.caption(f"📊 Calculated from Today plus {default_days} days")
                                else:
                                    # Due date not yet calculated
                                    if due_source == "laycan_start":
                                        st.info(f"ℹ️ **Due Date:** Not yet calculated (waiting for Laycan Day 1)")
                                    elif due_source == "previous_stage":
                                        st.info(f"ℹ️ **Due Date:** Not yet calculated (waiting for previous stage completion)")
                                    elif due_source == "specific_stage":
                                        st.info(f"ℹ️ **Due Date:** Not yet calculated (waiting for anchor stage completion)")
                                    else:
                                        st.info(f"ℹ️ **Due Date:** Not yet calculated")
                            
                            rem_val = None
                            if is_editing and bool(stage_def.get("require_remarks", False)):
                                rem_val = st.text_area("Remarks", value=getattr(progress_row, "remarks", "") if progress_row else "", key=f"exp_stage_remarks_{stage_code}_{cur_id}")
                            elif not is_editing:
                                existing_remarks = getattr(progress_row, "remarks", "") if progress_row else ""
                                if existing_remarks:
                                    st.write(f"**Remarks:** {existing_remarks}")
                            
                            comp_mode = str(stage_def.get("completion_date_mode") or "auto")
                            comp_date_val = None
                            if is_editing and str(new_stat).strip() in comp_list and comp_mode == "manual_required":
                                from datetime import date as _date
                                existing_comp = getattr(progress_row, "completed_at", None)
                                existing_comp_date = (existing_comp.date() if existing_comp else None)
                                comp_date_val = st.date_input("Completion date", value=existing_comp_date or _date.today(), key=f"exp_stage_completion_date_{stage_code}_{cur_id}")
                            
                            overdue_reason_val = None
                            if is_editing:
                                try:
                                    from datetime import date as _date
                                    is_overdue = False
                                    if getattr(progress_row, "due_date", None):
                                        is_overdue = (_date.today() > getattr(progress_row, "due_date"))
                                    if (str(new_stat).strip() in comp_list) and is_overdue and bool(stage_def.get("require_overdue_reason", True)):
                                        overdue_reason_val = st.text_area("Overdue reason (required)", value=getattr(progress_row, "overdue_reason", "") if progress_row else "", key=f"exp_stage_overdue_reason_{stage_code}_{cur_id}")
                                except Exception:
                                    overdue_reason_val = overdue_reason_val
                            
                            # Laycan capture when this stage sets laycan and marked complete
                            # Laycan date inputs (show for sets_laycan stages regardless of status)
                            laycan_start_val = None
                            laycan_end_val = None
                            if is_editing and bool(stage_def.get("sets_laycan", False)):
                                from datetime import date as _date
                                # Fetch the current laycan dates from database
                                current_laycan_start = None
                                current_laycan_end = None
                                try:
                                    from models import ExportProcess
                                    with get_session() as laycan_fetch_session:
                                        exp_record = laycan_fetch_session.query(ExportProcess).filter(ExportProcess.id == int(cur_id)).one_or_none()
                                        if exp_record:
                                            current_laycan_start = exp_record.laycan_start
                                            current_laycan_end = exp_record.laycan_end
                                except Exception as laycan_fetch_ex:
                                    log_error(f"Failed to fetch current laycan dates: {laycan_fetch_ex}", exc_info=True)
                                
                                st.markdown("**📅 Laycan Dates**")
                                laycan_start_val = st.date_input("Laycan start (Day 1)", value=(current_laycan_start or _date.today()), key=f"exp_stage_laycan_start_{stage_code}_{cur_id}")
                                laycan_end_val = st.date_input("Laycan end (Day 2)", value=(current_laycan_end or laycan_start_val), key=f"exp_stage_laycan_end_{stage_code}_{cur_id}")
                                st.caption("⚠️ Important: Stages with 'Due source = Laycan Day 1' will calculate due dates as: Laycan Day 1 MINUS configured days (e.g., if Laycan = 15/12/2025 and days = 7, due date = 08/12/2025)")
                            
                            if is_editing:
                                col1, col2 = st.columns([1, 1])
                                with col1:
                                    if st.button("💾 Save", key=f"exp_stage_save_{stage_code}_{cur_id}", help="Save stage status", type="primary"):
                                        # Check if this is an edit (stage was previously saved)
                                        edit_remarks = None
                                        if has_meaningful_data and progress_row:
                                            edit_remarks = st.session_state.get(f"exp_stage_edit_remarks_{stage_code}_{cur_id}", "")
                                            if not edit_remarks:
                                                st.error("Edit remarks are required when modifying a saved stage")
                                                st.stop()
                                        
                                        if overdue_reason_val is not None and not str(overdue_reason_val).strip():
                                            st.error("Overdue reason is required when completing past due")
                                        else:
                                            ok = _save_stage_status(
                                                int(cur_id),
                                                stage_code,
                                                new_stat,
                                                bool(stage_def.get("mandatory", True)),
                                                user or {},
                                                due_date=due_val,
                                                remarks=rem_val,
                                                completion_date=comp_date_val,
                                                manual_completion_required=(comp_mode == "manual_required"),
                                                completion_statuses=comp_list,
                                                laycan_start=laycan_start_val,
                                                laycan_end=laycan_end_val,
                                                overdue_reason=overdue_reason_val,
                                            )
                                            if ok:
                                                # Recalculate all due dates after saving
                                                _recalculate_all_due_dates(int(cur_id), cfg)
                                                st.session_state.pop(edit_key, None)
                                                st.success("Status saved")
                                                _st_safe_rerun()
                                            else:
                                                st.error("Save failed")
                                with col2:
                                    if st.button("❌ Cancel", key=f"exp_stage_cancel_{stage_code}_{cur_id}", help="Cancel editing"):
                                        st.session_state.pop(edit_key, None)
                                        _st_safe_rerun()
                                
                                # Show edit remarks input if editing a saved stage
                                if has_meaningful_data and progress_row:
                                    st.text_area("Edit remarks (required)", key=f"exp_stage_edit_remarks_{stage_code}_{cur_id}", help="Explain why you are editing this stage")
                        
                        # Uploads section
                        upl = list(stage_def.get("uploads") or [])
                        if upl:
                            st.markdown("**Uploads**")
                            for udef in upl:
                                files = st.file_uploader(udef.get("name") or "Upload", accept_multiple_files=True, key=f"exp_up_{stage_code}_{udef.get('name','')}_{cur_id}")
                                if st.button("Upload", key=f"exp_up_btn_{stage_code}_{udef.get('name','')}_{cur_id}"):
                                    ok = _upload_stage_files(int(cur_id), stage_code, files or [], str(udef.get("visibility") or "global"), list(udef.get("assignees") or []), user or {})
                                    if ok:
                                        st.success("Uploaded")
                                        _st_safe_rerun()
                                    else:
                                        st.error("Upload failed")
                
                # Advance to next stage button (only for current stage)
                # 
                # ADVANCE TO NEXT STAGE LOGIC:
                # This button moves the shipment from the current stage to the next stage in the pipeline.
                # 
                # Enable Conditions (button is enabled when ANY of these are true):
                # 1. Current stage is marked as COMPLETED (status matches one of the completion_statuses defined in stage config)
                # 2. Current stage is NOT MANDATORY (mandatory flag is False in stage config)
                # 
                # Disable Conditions (button is disabled when):
                # - Current stage is MANDATORY and NOT yet completed
                # 
                # When clicked:
                # - Updates ExportProcess.current_stage_code to the next stage code in the pipeline
                # - If already at the last stage, marks the entire shipment as completed
                # - Creates/updates ExportStageProgress record for the new stage if it doesn't exist
                # 
                # Mandatory Stage Enforcement:
                # - If a stage is marked as mandatory=True in Export Customization → Process Pipeline,
                #   users MUST complete that stage (set status to one of the completion_statuses)
                #   before they can advance to the next stage.
                # - If mandatory=False, users can skip the stage and advance immediately.
                cur_def = next((s for s in stages if s.get("code") == cur_stage_code), None)
                if cur_def:
                    st.markdown("---")
                    can_advance = False
                    progress_row = _get_stage_progress(int(cur_id), cur_stage_code)
                    if progress_row:
                        stat_val = getattr(progress_row, "status", "")
                        comp_list = list(cur_def.get("completion_statuses") or ["Completed"])
                        can_advance = stat_val in comp_list or not bool(cur_def.get("mandatory", True))
                    
                    # Show help text
                    if not can_advance:
                        st.info("ℹ️ **Advance to Next Stage** is disabled because this is a mandatory stage that must be completed first. Please update the stage status to one of the completion statuses to advance.")
                    
                    adv = st.button(
                        "➡️ Advance to Next Stage", 
                        key="exp_stage_next", 
                        help="Move shipment to the next stage in the pipeline. Enabled when current stage is completed or non-mandatory.", 
                        disabled=not can_advance, 
                        type="primary"
                    )
                    if adv:
                        ok = _progress_to_next_stage(int(cur_id), cfg, user or {})
                        if ok:
                            st.success("Advanced to next stage")
                            _st_safe_rerun()
                        else:
                            st.error("Advance failed")
    for i, tdef in enumerate(tabs):
        with st_tabs[i+3]:  # Dashboard is 0, Shipment Manager is 1, Shipment Tracker is 2, custom tabs start from 3
            table_name = tdef.get("table")
            coldefs = list(tdef.get("columns") or [])
            layout = tdef.get("layout") or {}
            fit_single_row = bool(layout.get("fit_single_row") or False)
            form_rows = int(layout.get("rows") or 1)
            form_cols = int(layout.get("cols") or max(1, min(len(coldefs), 4)))
            with st.form(f"exp_ops_form_{table_name}", clear_on_submit=True):
                inputs = {}
                fields = list(coldefs)
                total = len(fields)
                idx = 0
                tx_date = None
                # Try to identify BL Date field for mapping to tx_date
                bl_candidates = [
                    c for c in coldefs
                    if (str(c.get("name") or "").lower() == "bl_date") or (str(c.get("label") or "").strip().lower() == "bl date")
                ]
                bl_field = bl_candidates[0] if bl_candidates else None
                needed_rows = (total + form_cols - 1) // form_cols
                if fit_single_row:
                    form_rows = 1
                    form_cols = max(total, form_cols)
                for r in range(max(form_rows, needed_rows if not fit_single_row else form_rows)):
                    cols_row = st.columns([*(1 for _ in range(form_cols))])
                    for cidx in range(form_cols):
                        if idx >= total:
                            break
                        f = fields[idx]
                        fname = str(f.get("name") or "").strip()
                        flabel = f.get("label") or fname
                        ftype = f.get("type") or "text"
                        with cols_row[cidx]:
                            if not fname:
                                pass
                            elif ftype == "number":
                                inputs[fname] = st.number_input(flabel, value=0.0, step=0.01, format="%.2f", key=f"exp_ops_num_{table_name}_{fname}")
                            elif ftype == "date":
                                dval = st.date_input(flabel, value=date.today(), key=f"exp_ops_dt_{table_name}_{fname}")
                                inputs[fname] = dval
                                if bl_field and (fname == str(bl_field.get("name"))):
                                    tx_date = dval
                            elif ftype == "dropdown":
                                opts = list(f.get("options") or [])
                                inputs[fname] = st.selectbox(flabel, options=opts or ["—"], key=f"exp_ops_dd_{table_name}_{fname}")
                            else:
                                inputs[fname] = st.text_input(flabel, key=f"exp_ops_txt_{table_name}_{fname}")
                        idx += 1
                submit = st.form_submit_button("💾", type="primary", help="Save Entry")
                if submit:
                    try:
                        Model = get_custom_table_model(table_name)
                        if not Model:
                            st.error("Table not available.")
                        else:
                            with get_flex_session() as s:
                                row = Model()
                                setattr(row, "location_id", int(loc_id or 0))
                                # Map BL Date to tx_date for cross-page consistency
                                try:
                                    setattr(row, "tx_date", tx_date)
                                except Exception:
                                    pass
                                u = st.session_state.get("auth_user") or {}
                                setattr(row, "created_by", u.get("username"))
                                for k, v in inputs.items():
                                    try:
                                        setattr(row, k, v)
                                    except Exception:
                                        pass
                                s.add(row)
                                s.commit()
                            st.write("Saved.")
                            _st_safe_rerun()
                    except Exception as ex:
                        st.error(f"Failed to save: {ex}")

            try:
                Model = get_custom_table_model(table_name)
                if Model:
                    import pandas as pd
                    with get_flex_session() as s:
                        # Build base query
                        qobj = s.query(Model).filter(getattr(Model, "location_id") == int(loc_id or 0))
                        # Render filters configured in customization with layout
                        filters_def = list(tdef.get("filters") or [])
                        flayout = tdef.get("filters_layout") or {}
                        if filters_def:
                            st.markdown("##### Filters")
                            fl_fit = bool(flayout.get("fit_single_row") or False)
                            fl_rows = int(flayout.get("rows") or 1)
                            fl_cols = int(flayout.get("cols") or max(1, min(len(filters_def), 4)))
                            total_f = len(filters_def)
                            needed_f_rows = (total_f + fl_cols - 1) // fl_cols
                            if fl_fit:
                                fl_rows = 1
                                fl_cols = max(total_f, fl_cols)
                            idx_f = 0
                            for rr in range(max(fl_rows, needed_f_rows if not fl_fit else fl_rows)):
                                fcols = st.columns([*(1 for _ in range(fl_cols))])
                                for cc in range(fl_cols):
                                    if idx_f >= total_f:
                                        break
                                    fdef = filters_def[idx_f]
                                    flabel = fdef.get("label") or fdef.get("field")
                                    ffield = fdef.get("field")
                                    ftype = fdef.get("type") or "text"
                                    fmode = fdef.get("mode") or ("equals" if ftype != "number" else "min_max")
                                    col = getattr(Model, ffield, None)
                                    if not col:
                                        idx_f += 1
                                        continue
                                    with fcols[cc]:
                                        if ftype == "text":
                                            val = st.text_input(flabel, key=f"exp_ops_f_txt_{table_name}_{idx_f}")
                                            if val:
                                                v = str(val)
                                                if fmode == "equals":
                                                    qobj = qobj.filter(col == v)
                                                elif fmode == "contains":
                                                    qobj = qobj.filter(col.contains(v))
                                                elif fmode == "starts_with":
                                                    qobj = qobj.filter(col.like(f"{v}%"))
                                                elif fmode == "ends_with":
                                                    qobj = qobj.filter(col.like(f"%{v}"))
                                        elif ftype == "number":
                                            if fmode == "equals":
                                                num = st.number_input(flabel, value=0.0, step=0.01, format="%.2f", key=f"exp_ops_f_num_{table_name}_{idx_f}")
                                                if num is not None:
                                                    qobj = qobj.filter(col == float(num))
                                            else:
                                                c1, c2 = st.columns(2)
                                                with c1:
                                                    nmin = st.number_input(f"{flabel} min", value=0.0, step=0.01, format="%.2f", key=f"exp_ops_f_num_min_{table_name}_{idx_f}")
                                                with c2:
                                                    nmax = st.number_input(f"{flabel} max", value=0.0, step=0.01, format="%.2f", key=f"exp_ops_f_num_max_{table_name}_{idx_f}")
                                                try:
                                                    if nmin is not None:
                                                        qobj = qobj.filter(col >= float(nmin))
                                                    if nmax is not None and float(nmax) > 0:
                                                        qobj = qobj.filter(col <= float(nmax))
                                                except Exception:
                                                    pass
                                        elif ftype == "date":
                                            if fmode == "equals":
                                                dv = st.date_input(flabel, key=f"exp_ops_f_date_{table_name}_{idx_f}")
                                                if dv:
                                                    qobj = qobj.filter(col == dv)
                                            else:
                                                c1, c2 = st.columns(2)
                                                with c1:
                                                    dfrom = st.date_input(f"{flabel} from", key=f"exp_ops_f_date_from_{table_name}_{idx_f}")
                                                with c2:
                                                    dto = st.date_input(f"{flabel} to", key=f"exp_ops_f_date_to_{table_name}_{idx_f}")
                                                try:
                                                    if dfrom:
                                                        qobj = qobj.filter(col >= dfrom)
                                                    if dto:
                                                        qobj = qobj.filter(col <= dto)
                                                except Exception:
                                                    pass
                                    idx_f += 1
                        q = (
                            qobj.order_by(getattr(Model, "id").desc())
                                .limit(50)
                                .all()
                        )
                        cols_all = [c.name for c in Model.__table__.columns]
                        reserved = {"id", "location_id", "created_by", "created_at", "updated_by", "updated_at"}
                        # Prefer BL Date column if present, fall back to tx_date
                        bl_first = "bl_date" if "bl_date" in cols_all else None
                        first_col = bl_first or ("tx_date" if "tx_date" in cols_all else None)
                        display_cols = ([first_col] if first_col else []) + [c for c in cols_all if c not in reserved and c != first_col]
                        # Show all user-defined columns
                        header = st.columns([*(1 for _ in display_cols), 0.12, 0.12])
                        for i, h in enumerate(display_cols):
                            with header[i]:
                                st.caption(h)

                        role = (user or {}).get("role", "").lower()
                        can_delete = role in ["admin-operations", "supervisor"]
                        can_edit_global = True
                        try:
                            can_edit_global = PermissionManager.can_make_entries_user(s, user or {}, int(loc_id or 0))
                        except Exception:
                            can_edit_global = True

                        for r in q:
                            created_at = getattr(r, "created_at", None)
                            age_ok = True
                            try:
                                if created_at:
                                    from datetime import datetime, timedelta
                                    age_ok = (datetime.now() - created_at).total_seconds() <= 24 * 3600
                            except Exception:
                                age_ok = True
                            cols = st.columns([*(1 for _ in display_cols), 0.12, 0.12])
                            for i, c in enumerate(display_cols):
                                with cols[i]:
                                    val = getattr(r, c, "")
                                    if isinstance(val, pd.Timestamp):
                                        val = val.date()
                                    st.write(val if val is not None else "-")
                            with cols[-2]:
                                can_edit = can_edit_global and age_ok
                                if st.button("✏️", key=f"exp_ops_edit_{table_name}_{getattr(r,'id',0)}", help="Edit entry", disabled=not can_edit):
                                    st.session_state[f"exp_ops_editing_{table_name}_{getattr(r,'id',0)}"] = True
                                    _st_safe_rerun()
                            with cols[-1]:
                                if not age_ok:
                                    st.button("🗑️", key=f"exp_ops_del_{table_name}_{getattr(r,'id',0)}", help="Delete disabled after 24 hours", disabled=True)
                                else:
                                    if st.button("🗑️", key=f"exp_ops_del_{table_name}_{getattr(r,'id',0)}", help="Delete entry", disabled=not can_delete):
                                        st.session_state[f"exp_ops_confirm_del_{table_name}_{getattr(r,'id',0)}"] = True

                            if st.session_state.get(f"exp_ops_editing_{table_name}_{getattr(r,'id',0)}"):
                                st.markdown("---")
                                with st.form(f"exp_ops_edit_form_{table_name}_{getattr(r,'id',0)}"):
                                    edit_inputs = {}
                                    for c in coldefs:
                                        cname = str(c.get("name") or "").strip()
                                        clabel = c.get("label") or cname
                                        ctype = c.get("type") or "text"
                                        if not cname:
                                            continue
                                        cur = getattr(r, cname, None)
                                        if ctype == "number":
                                            edit_inputs[cname] = st.number_input(clabel, value=float(cur or 0.0), step=0.01, format="%.2f")
                                        elif ctype == "date":
                                            dval = cur if isinstance(cur, date) else date.today()
                                            edit_inputs[cname] = st.date_input(clabel, value=dval)
                                        elif ctype == "dropdown":
                                            opts = list(c.get("options") or [])
                                            idx = opts.index(cur) if (cur in opts) else 0
                                            edit_inputs[cname] = st.selectbox(clabel, options=opts or ["—"], index=max(0, idx))
                                        else:
                                            edit_inputs[cname] = st.text_input(clabel, value=str(cur or ""))

                                    ec1, ec2 = st.columns([0.12, 0.12])
                                    with ec1:
                                        esave = st.form_submit_button("💾", type="primary", help="Save", disabled=not (can_edit_global and age_ok))
                                    with ec2:
                                        ecancel = st.form_submit_button("✖️", help="Cancel")
                                    if esave:
                                        try:
                                            with get_flex_session() as s2:
                                                row_obj = s2.query(Model).filter(getattr(Model, "id") == getattr(r, "id")).one_or_none()
                                                if row_obj:
                                                    for k, v in edit_inputs.items():
                                                        try:
                                                            setattr(row_obj, k, v)
                                                        except Exception:
                                                            pass
                                                    row_obj.updated_by = (user or {}).get("username")
                                                    s2.commit()
                                                    try:
                                                        SecurityManager.log_audit(
                                                            s2,
                                                            (user or {}).get("username", "system"),
                                                            "UPDATE",
                                                            resource_type=f"ExportOps:{table_name}",
                                                            resource_id=str(getattr(r, "id", "")),
                                                            details="Updated export record",
                                                            user_id=(user or {}).get("id"),
                                                            location_id=int(loc_id or 0),
                                                        )
                                                    except Exception:
                                                        pass
                                            st.write("Updated.")
                                            st.session_state.pop(f"exp_ops_editing_{table_name}_{getattr(r,'id',0)}", None)
                                            _st_safe_rerun()
                                        except Exception as ex:
                                            st.error(f"Update failed: {ex}")
                                    if ecancel:
                                        st.session_state.pop(f"exp_ops_editing_{table_name}_{getattr(r,'id',0)}", None)
                                        _st_safe_rerun()

                            if st.session_state.get(f"exp_ops_confirm_del_{table_name}_{getattr(r,'id',0)}"):
                                st.warning("Confirm delete?")
                                dc1, dc2 = st.columns([0.12, 0.12])
                                with dc1:
                                    if st.button("✅", key=f"exp_ops_del_yes_{table_name}_{getattr(r,'id',0)}", type="primary", help="Yes, delete", disabled=not can_delete):
                                        try:
                                            with get_flex_session() as s3:
                                                row_obj = s3.query(Model).filter(getattr(Model, "id") == getattr(r, "id")).one_or_none()
                                                if row_obj:
                                                    s3.delete(row_obj)
                                                    try:
                                                        SecurityManager.log_audit(
                                                            s3,
                                                            (user or {}).get("username", "system"),
                                                            "DELETE",
                                                            resource_type=f"ExportOps:{table_name}",
                                                            resource_id=str(getattr(r, "id", "")),
                                                            details="Deleted export record",
                                                            user_id=(user or {}).get("id"),
                                                            location_id=int(loc_id or 0),
                                                        )
                                                    except Exception:
                                                        pass
                                                    s3.commit()
                                            st.write("Deleted.")
                                            st.session_state.pop(f"exp_ops_confirm_del_{table_name}_{getattr(r,'id',0)}", None)
                                            _st_safe_rerun()
                                        except Exception as ex:
                                            st.error(f"Delete failed: {ex}")
                                with dc2:
                                    if st.button("❌", key=f"exp_ops_del_no_{table_name}_{getattr(r,'id',0)}", help="Cancel"):
                                        st.session_state.pop(f"exp_ops_confirm_del_{table_name}_{getattr(r,'id',0)}", None)
                                        _st_safe_rerun()
            except Exception:
                st.caption("Unable to load recent records.")

    if not tabs:
        with st_tabs[2]:  # Shipment Tracker tab (when no custom tabs exist)
            st.info("No additional export tabs configured. Go to Export Customization to add export tabs.")

    try:
        SecurityManager.log_audit(
            None,
            (user or {}).get("username", "unknown"),
            "OPEN",
            resource_type="ExportOperations",
            resource_id=None,
            details="Opened Export Operations hub",
            user_id=(user or {}).get("id"),
            location_id=active_location_id,
        )
    except Exception:
        pass
