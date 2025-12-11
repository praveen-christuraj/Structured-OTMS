# OTMS Role Permissions - Quick Reference Guide

## Role Summary

### 👷 OPERATOR
- ✅ Make entries at assigned location
- ✅ View entries, reports, Material Balance
- ❌ Cannot delete (needs supervisor approval)
- 🔒 **Location:** Own location only

### 👤 SUPERVISOR  
- ✅ Make entries at assigned location
- ✅ Delete entries (with supervisor code)
- ✅ Approve operator deletion requests
- 🔒 **Location:** Own location only
- 📋 **Tasks:** Deletion requests from operators

### 👔 MANAGER
- ✅ View ALL locations (read-only)
- ✅ View all reports and dashboards
- ❌ Cannot make entries
- ❌ Cannot edit or delete
- ❌ Not assigned to tasks
- 🔒 **Location:** All (view only)

### 💻 ADMIN-IT
- ✅ Admin pages only (Users, Audit, Backups, 2FA, Assets)
- ❌ Cannot access operational pages
- ❌ Cannot make entries or view reports
- 📋 **Tasks:** Password resets, system errors, user management

### 🏢 ADMIN-OPERATIONS
- ✅ FULL ACCESS to everything
- ✅ All pages, all locations
- ✅ Make entries everywhere, delete anywhere
- 📋 **Tasks:** ALL tasks (backup for everything)

---

## Task Assignment Rules

### Deletion Requests
- **Assigned to:** All supervisors at the location
- **Approval:** ANY ONE supervisor can approve
- **Notification:** Shows "Shared with X supervisors"

### Password Resets
- **Assigned to:** BOTH Admin-IT (primary) AND Admin-Operations (backup)
- **Completion:** Either role can complete

### Error Alerts
- **System errors:** Admin-IT
- **Application errors:** Admin-Operations  
- **Critical errors:** BOTH

---

## Logging Coverage

### All Actions Logged:
✅ CREATE - Creating records  
✅ UPDATE - Editing records  
✅ DELETE - Deleting (with approval)  
✅ VIEW - Page access  
✅ EXPORT - Data exports  
✅ FILTER - Applying filters  
✅ SEARCH - Searching  
✅ SELECT - Selecting records  
✅ DOWNLOAD - File downloads  
✅ LOGIN/LOGOUT - Authentication  
✅ SESSION_TIMEOUT - Timeouts  
✅ 2FA_SETUP/2FA_VERIFY - 2FA events

---

## Common Scenarios

### Operator wants to delete a record:
1. Click delete button
2. Choose approval method:
   - **Local:** Enter supervisor username + code
   - **Remote:** Send approval request (creates task)
3. If remote: Supervisor sees in "My Tasks"
4. Supervisor approves → deletion executes

### Multiple supervisors at location:
- Task sent to ALL supervisors
- ANY ONE can approve
- First to approve completes the task
- Others see task as "COMPLETED"

### Password reset needed:
1. User requests reset
2. Task created for Admin-IT (primary)
3. Task also created for Admin-Operations (backup)
4. Either admin can complete the reset

---

## Quick Permission Checks

```python
# Check if user can make entries
PermissionManager.can_make_entries(session, user_role, location_id)
# Returns: True for admin-operations, supervisor, operator
# Returns: False for admin-it, manager

# Check if user can delete
PermissionManager.can_delete_entries(user)
# Returns: True for admin-operations, supervisor
# Returns: False for admin-it, manager, operator

# Check if user can view all locations
PermissionManager.can_view_all_locations(user)
# Returns: True for admin-operations, manager
# Returns: False for others (location-restricted)
```

---

## Notification Badge

Shows in sidebar:
- **Total pending tasks**
- **Breakdown by type:**
  - X deletion requests
  - X errors  
  - X password resets
- **Color coding:**
  - 🔴 Red: > 5 tasks
  - 🟠 Orange: ≤ 5 tasks

---

## Files to Reference

- `permission_manager.py` - All permission logic + documentation
- `task_manager.py` - Task creation and assignment
- `deletion_approval.py` - Deletion approval workflows
- `action_logger_utils.py` - Logging utilities
- `app_pages/my_tasks.py` - Task display and actions

---

**Last Updated:** December 6, 2025  
**Status:** ✅ All systems verified and working
