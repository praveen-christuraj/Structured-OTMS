# report_scheduler.py
"""
Report Scheduler Service

Handles scheduled report execution:
- Cron-based scheduling
- Filter overrides for scheduled runs
- Multi-destination delivery
- Execution logging
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from croniter import croniter  # pip install croniter

from db import get_session
from models import ReportDefinition, ReportSchedule, ReportExecutionLog
from report_engine import ReportEngine
from report_destinations import send_report_to_destinations
from logger import log_info, log_error, log_warning


def calculate_next_run(schedule: ReportSchedule) -> datetime:
    """Calculate the next run time for a schedule."""
    now = datetime.utcnow()
    
    if schedule.cron_expression:
        # Use cron expression
        cron = croniter(schedule. cron_expression, now)
        return cron.get_next(datetime)
    
    # Build cron from frequency + time
    run_time = schedule. run_time or "00:00"
    hour, minute = run_time.split(":")
    
    if schedule.frequency == "daily":
        cron_expr = f"{minute} {hour} * * *"
    elif schedule.frequency == "weekly":
        day_of_week = schedule.run_day or 0  # Default Monday
        cron_expr = f"{minute} {hour} * * {day_of_week}"
    elif schedule.frequency == "monthly":
        day_of_month = schedule.run_day or 1
        cron_expr = f"{minute} {hour} {day_of_month} * *"
    else:
        # Default to daily
        cron_expr = f"{minute} {hour} * * *"
    
    cron = croniter(cron_expr, now)
    return cron.get_next(datetime)


def get_scheduled_filter_overrides(schedule: ReportSchedule) -> Dict[str, Any]:
    """Get filter overrides for a scheduled run."""
    overrides = {}
    
    if schedule.filter_overrides_json:
        try:
            overrides = json.loads(schedule.filter_overrides_json)
        except:
            pass
    
    # Auto-calculate date ranges based on frequency
    now = datetime.utcnow()
    
    if schedule. frequency == "daily":
        # Yesterday's data
        start_date = (now - timedelta(days=1)).date()
        end_date = start_date
    elif schedule.frequency == "weekly":
        # Last 7 days
        end_date = (now - timedelta(days=1)).date()
        start_date = end_date - timedelta(days=6)
    elif schedule.frequency == "monthly":
        # Last month
        first_of_this_month = now. replace(day=1)
        end_date = (first_of_this_month - timedelta(days=1)). date()
        start_date = end_date. replace(day=1)
    else:
        # Default: yesterday
        start_date = (now - timedelta(days=1)).date()
        end_date = start_date
    
    overrides. setdefault("date_range", [start_date, end_date])
    
    return overrides


def execute_scheduled_report(schedule_id: int) -> Dict[str, Any]:
    """
    Execute a scheduled report.
    
    Args:
        schedule_id: ID of the ReportSchedule to execute
    
    Returns:
        Execution result dictionary
    """
    result = {
        "schedule_id": schedule_id,
        "success": False,
        "started_at": datetime. utcnow(),
        "completed_at": None,
        "row_count": 0,
        "destinations": [],
        "error": None
    }
    
    with get_session() as session:
        schedule = session.query(ReportSchedule).filter(
            ReportSchedule.id == schedule_id
        ). first()
        
        if not schedule:
            result["error"] = f"Schedule not found: {schedule_id}"
            return result
        
        if not schedule.is_active:
            result["error"] = "Schedule is not active"
            return result
        
        report = schedule.report
        if not report or not report.is_active:
            result["error"] = "Report is not active or not found"
            return result
        
        # Create execution log
        log_entry = ReportExecutionLog(
            report_id=report. id,
            schedule_id=schedule. id,
            execution_type="scheduled",
            status="started",
            started_at=result["started_at"],
            executed_by="scheduler"
        )
        session.add(log_entry)
        session.flush()
        
        try:
            # Update schedule status
            schedule.last_run_at = result["started_at"]
            schedule.last_run_status = "running"
            session. commit()
            
            # Parse report config
            config = json.loads(report. config_json or "{}")
            
            # Get filter overrides
            filters = get_scheduled_filter_overrides(schedule)
            
            # Store location_id from report if not in filters
            if report.location_id and "location_id" not in filters:
                filters["location_id"] = report.location_id
            
            log_entry.filters_json = json.dumps(filters, default=str)
            
            # Execute report
            engine = ReportEngine(config)
            df = engine.execute_report(filters)
            
            result["row_count"] = len(df)
            log_entry.row_count = result["row_count"]
            
            if df.empty:
                log_warning(f"Scheduled report {schedule.name} returned no data")
            
            # Generate exports
            export_formats = [f.strip(). lower() for f in schedule.export_formats. split(",")]
            data_by_format = {}
            
            for fmt in export_formats:
                if fmt == "csv":
                    data_by_format["csv"] = engine.export_csv(df)
                elif fmt == "xlsx":
                    data_by_format["xlsx"] = engine.export_xlsx(df)
                elif fmt == "pdf":
                    data_by_format["pdf"] = engine. export_pdf(df, report.name)
                elif fmt == "json":
                    data_by_format["json"] = df.to_json(orient="records"). encode("utf-8")
                elif fmt == "xml":
                    data_by_format["xml"] = df.to_xml(). encode("utf-8")
                elif fmt == "html":
                    data_by_format["html"] = df.to_html().encode("utf-8")
            
            # Send to destinations
            destinations = []
            if schedule.destinations_json:
                try:
                    destinations = json.loads(schedule.destinations_json)
                except:
                    pass
            
            if destinations:
                dest_results = send_report_to_destinations(
                    report. name,
                    data_by_format,
                    destinations
                )
                result["destinations"] = dest_results
                
                # Check if all destinations succeeded
                all_success = all(d. get("success", False) for d in dest_results)
                if not all_success:
                    failed = [d for d in dest_results if not d.get("success")]
                    log_warning(f"Some destinations failed: {failed}")
            
            # Update success
            result["success"] = True
            result["completed_at"] = datetime.utcnow()
            
            # Update log entry
            log_entry.status = "success"
            log_entry.completed_at = result["completed_at"]
            log_entry.duration_seconds = (
                result["completed_at"] - result["started_at"]
            ). total_seconds()
            
            # Update schedule
            schedule.last_run_status = "success"
            schedule. last_run_message = f"Generated {result['row_count']} rows"
            schedule.next_run_at = calculate_next_run(schedule)
            
            session.commit()
            log_info(f"Scheduled report {schedule.name} completed successfully")
            
        except Exception as e:
            result["error"] = str(e)
            result["completed_at"] = datetime.utcnow()
            
            # Update log entry
            log_entry.status = "failed"
            log_entry.completed_at = result["completed_at"]
            log_entry. error_message = str(e)
            log_entry.duration_seconds = (
                result["completed_at"] - result["started_at"]
            ). total_seconds()
            
            # Update schedule
            schedule. last_run_status = "failed"
            schedule.last_run_message = str(e)
            schedule.next_run_at = calculate_next_run(schedule)
            
            session.commit()
            log_error(f"Scheduled report {schedule.name} failed: {str(e)}")
            
            # Send failure notification if configured
            if schedule.notify_on_failure and schedule.notification_emails:
                try:
                    send_failure_notification(schedule, str(e))
                except Exception as notify_error:
                    log_error(f"Failed to send failure notification: {notify_error}")
    
    return result


def send_failure_notification(schedule: ReportSchedule, error_message: str):
    """Send email notification for failed scheduled report."""
    from report_destinations import EmailDestination
    
    emails = [e.strip() for e in schedule.notification_emails. split(",")]
    
    config = {
        "smtp_host": os.environ.get("SMTP_HOST", "localhost"),
        "smtp_port": os.environ.get("SMTP_PORT", 587),
        "use_tls": True,
        "username": os.environ. get("SMTP_USERNAME"),
        "password": os.environ.get("SMTP_PASSWORD"),
        "from_email": os. environ.get("SMTP_FROM", "noreply@system.local"),
        "recipients": emails,
        "subject": f"⚠️ Report Failed: {schedule.name}",
        "body": f"""
The scheduled report "{schedule.name}" failed to execute. 

Error: {error_message}

Schedule ID: {schedule.id}
Report ID: {schedule.report_id}
Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

Please check the system logs for more details. 
        """
    }
    
    handler = EmailDestination(config)
    handler.send("error_notification. txt", config["body"]. encode("utf-8"), "text/plain")


def get_due_schedules() -> List[ReportSchedule]:
    """Get all schedules that are due to run."""
    now = datetime.utcnow()
    
    with get_session() as session:
        schedules = session.query(ReportSchedule).filter(
            ReportSchedule. is_active == True,
            ReportSchedule.next_run_at <= now
        ).all()
        
        # Detach from session for use outside
        for s in schedules:
            session.expunge(s)
        
        return schedules


def run_scheduler_tick():
    """
    Run one tick of the scheduler. 
    Call this from a background job (e.g., APScheduler, Celery, cron). 
    """
    log_info("Scheduler tick started")
    
    due_schedules = get_due_schedules()
    
    for schedule in due_schedules:
        log_info(f"Executing due schedule: {schedule. name} (ID: {schedule.id})")
        try:
            execute_scheduled_report(schedule.id)
        except Exception as e:
            log_error(f"Error executing schedule {schedule.id}: {str(e)}")
    
    log_info(f"Scheduler tick completed.  Processed {len(due_schedules)} schedules.")


# =============================================================================
# SCHEDULER INITIALIZATION (for APScheduler integration)
# =============================================================================

def init_background_scheduler():
    """
    Initialize APScheduler for background report scheduling.
    Call this during application startup.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            run_scheduler_tick,
            trigger=IntervalTrigger(minutes=1),
            id="report_scheduler",
            name="Report Scheduler",
            replace_existing=True
        )
        scheduler.start()
        log_info("Background report scheduler started")
        return scheduler
        
    except ImportError:
        log_warning("APScheduler not installed. Scheduled reports will not run automatically.")
        log_warning("Install with: pip install apscheduler")
        return None