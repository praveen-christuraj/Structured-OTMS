# Audit Log and Activity Logging

## What gets logged

OTMS maintains an audit trail for key actions, including (examples):
- user login/logout and security events
- create/update/delete operations on records
- configuration changes (locations, users, customizations)
- exports (where implemented)
- system events (session expiry, errors)

## Where to view logs

- Go to `Audit Log` (admin/manager visibility depending on policy)
- Filter by date range and user

## Timestamps / Timezone

- Audit events are stored as **UTC**
- UI pages display audit timestamps as **Nigeria Time (WAT, UTC+1)** where timezone utilities are available

If you see a time mismatch, check whether the page is showing local time vs UTC.

## Related documentation

- `Documentation/LOGGING_IMPLEMENTATION_SUMMARY.md`
- `Documentation/DELETION_APPROVAL_QUICK_START.md`

