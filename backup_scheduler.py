# backup_scheduler.py
"""
Automated backup scheduler.

Runs backups based on a simple JSON config written by the app:
    backups/auto_backup_config.json

Config schema (all keys optional; sensible defaults apply):
{
    "enabled": true,                   # enable/disable scheduler
    "mode": "daily",                  # "minutes" | "hours" | "daily"
    "interval": 6,                    # used for minutes/hours modes
    "time": "02:00"                   # HH:MM, used for daily mode
}

Run this as a separate process or Windows Task Scheduler job.
The process watches the config file and applies changes at runtime.
"""

import schedule
import time
import json
from pathlib import Path
from datetime import datetime
from backup_manager import BackupManager

def run_daily_backup():
    """Perform daily automated backup"""
    try:
        print(f"\n{'='*60}")
        print(f"🔄 Starting automated backup: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        
        backup_info = BackupManager.create_backup(
            description="Automated daily backup",
            backup_type="auto"
        )
        
        print(f"✅ Backup created successfully!")
        print(f"   Filename: {backup_info['filename']}")
        print(f"   Size: {backup_info['size_mb']} MB")
        print(f"   Location: backups/{backup_info['filename']}")
        
        # Log audit entry for this automated backup
        # We attempt to record the backup operation in the audit log using the
        # SecurityManager. If the audit logging infrastructure is not
        # available (e.g. outside of the full application context), we catch
        # and report the exception so the backup can still complete.
        try:
            # Import session management and security logging only when needed
            from db import get_session  # type: ignore
            from security import SecurityManager  # type: ignore

            with get_session() as _session:
                # Log the backup with a system user. The action uses the same
                # code as manual backups (CREATE_BACKUP) so that all backups
                # appear consistently in the audit log. Details identify this
                # as an automated hourly backup.
                SecurityManager.log_audit(
                    _session,
                    "system",  # username; could be replaced with a service account
                    "CREATE_BACKUP",
                    details="Automated hourly backup",
                    user_id=None,
                    location_id=None,
                    ip_address=None,
                )
        except Exception as log_ex:
            # If logging fails, print an informative message and continue
            print(f"⚠️  Failed to write audit log: {log_ex}")

        # Cleanup old backups (keep last 30 days, minimum 5 backups)
        cleanup_result = BackupManager.cleanup_old_backups(days=30, keep_minimum=5)
        print(f"   Cleanup: Deleted {cleanup_result['deleted']} old backup(s)")
        
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"❌ Backup failed: {e}")

def main():
    """Main scheduler loop with dynamic config reload"""
    CONFIG_PATH = Path("backups") / "auto_backup_config.json"

    def load_config() -> dict:
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {
                        "enabled": bool(data.get("enabled", True)),
                        "mode": str(data.get("mode", "daily")),
                        "interval": int(data.get("interval", 24)),
                        "time": str(data.get("time", "02:00"))[:5],
                    }
        except Exception as ex:
            print(f"⚠️  Failed to read config: {ex}")
        return {"enabled": True, "mode": "daily", "interval": 24, "time": "02:00"}

    def apply_schedule(conf: dict):
        schedule.clear()
        if not conf.get("enabled", True):
            print("⏸️  Scheduler disabled by config.")
            return
        mode = conf.get("mode", "daily").lower()
        interval = max(1, int(conf.get("interval", 24) or 1))
        if mode == "minutes":
            schedule.every(interval).minutes.do(run_daily_backup)
            print(f"🗓️  Schedule: Every {interval} minute(s)")
        elif mode == "hours":
            schedule.every(interval).hours.do(run_daily_backup)
            print(f"🗓️  Schedule: Every {interval} hour(s)")
        else:
            at_time = str(conf.get("time", "02:00"))[:5]
            try:
                # Basic HH:MM validation
                _ = datetime.strptime(at_time, "%H:%M")
            except ValueError:
                at_time = "02:00"
            schedule.every().day.at(at_time).do(run_daily_backup)
            print(f"🗓️  Schedule: Daily at {at_time}")

    print("=" * 60)
    print("📅 OTMS Backup Scheduler Started")
    print("=" * 60)
    print(f"Retention: 30 days (minimum 5 backups)")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Ensure config directory exists
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Initial schedule
    conf = load_config()
    apply_schedule(conf)
    last_mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else 0

    print("\n⏳ Waiting for scheduled time...")
    print("   (Press Ctrl+C to stop)\n")

    while True:
        # Hot-reload config if changed
        try:
            if CONFIG_PATH.exists():
                mtime = CONFIG_PATH.stat().st_mtime
                if mtime != last_mtime:
                    print("🔁 Detected config change. Reloading schedule...")
                    conf = load_config()
                    apply_schedule(conf)
                    last_mtime = mtime
        except Exception as ex:
            print(f"⚠️  Config watch error: {ex}")
        schedule.run_pending()
        time.sleep(30)  # Check twice a minute

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Backup scheduler stopped by user.")