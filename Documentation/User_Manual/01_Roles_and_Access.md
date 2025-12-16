# Roles and Access

This is a user-focused summary of how access works in OTMS.
For the full RBAC reference, see `Documentation/ROLE_BASED_ACCESS_CONTROL.md`.

## Roles

### Operator
- Typically creates entries at their assigned location.
- Cannot delete records directly (deletion approval workflow may be required).
- If assigned to a **Head Office** location, the operator can switch Active Location to view other locations but is treated as **view-only** on entry pages.

### Supervisor
- Can create and manage entries at their assigned location.
- Can approve deletion requests (and/or delete directly depending on the workflow).
- If assigned to a **Head Office** location, the supervisor can switch Active Location across locations.

### Manager
- Read-only across all locations.
- Can switch Active Location to view other locations, reports, and dashboards.

### Admin-IT
- Access to system administration pages (users, audit log, error monitoring, backups, etc.).
- Does not perform operational entries.

### Admin-Operations
- Full access to both admin and operational pages.
- Can work across all locations.

## Location-based visibility

Even if your role allows a page, the page may still be disabled for the Active Location by **Location Settings → Page Access**.

