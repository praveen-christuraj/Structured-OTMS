# Role-Based Access Control (RBAC) - OTMS

## Overview
This document defines the access control rules for all roles in the OTMS application.

## Role Definitions

### 1. Operator
**Purpose:** Front-line user who performs daily operations

**Permissions:**
- ✅ Create entries (Tank Transactions, YADE Transactions, Tanker Operations, FSO Operations, etc.)
- ✅ View entries **limited to their assigned location only**
- ✅ View reports (Material Balance, Dashboards) **limited to their location**
- ❌ **CANNOT** delete entries without supervisor approval
- ❌ **CANNOT** edit entries without proper authorization
- ❌ **CANNOT** access other locations

**Deletion Workflow for Operators:**
When an operator needs to delete an entry, they have two options:
1. **Local Approval:** Supervisor enters their username and supervisor code immediately
2. **Remote Approval:** Request is sent as a task to ALL supervisors assigned to that location

**Task Assignment:**
- Can see their own raised tasks (deletion requests, password resets, etc.)
- Receives notifications when their tasks are approved/rejected

**Location Restrictions:**
- **STRICTLY** limited to their assigned location
- Cannot view or access data from other locations
- All queries must filter by their location_id

---

### 2. Supervisor
**Purpose:** Location manager who oversees operations and approves deletions

**Permissions:**
- ✅ Create entries at their location
- ✅ View all entries **limited to their assigned location only**
- ✅ **Delete entries directly** without approval (at their location)
- ✅ Approve deletion requests from operators at their location
- ✅ View all reports **limited to their location**
- ❌ **CANNOT** access other locations

**Deletion Workflow for Supervisors:**
- Can delete entries directly without any approval
- Can approve deletion requests from operators using their supervisor code

**Task Assignment:**
- Receives deletion approval requests from operators at their location
- **Multiple supervisors per location:** If more than one supervisor is assigned to a location, deletion requests are sent to ALL of them - **ANY ONE** can approve
- Receives notifications for pending tasks at their location

**Location Restrictions:**
- **STRICTLY** limited to their assigned location
- Cannot view or access data from other locations
- All queries must filter by their location_id

**Supervisor Code:**
- Must set a supervisor code in their profile settings
- Code is hashed using bcrypt for security
- Required for local deletion approvals

---

### 3. Manager
**Purpose:** View-only oversight role across all locations

**Permissions:**
- ✅ **View** all entries across **ALL locations**
- ✅ **View** all reports across **ALL locations**
- ❌ **CANNOT** create entries
- ❌ **CANNOT** edit entries
- ❌ **CANNOT** delete entries
- ❌ **NOT** assigned to any tasks

**Task Assignment:**
- **NEVER** assigned tasks
- Does not see task notifications
- View-only role - cannot take action on tasks

**Location Access:**
- **FULL** read-only access to all locations
- Can switch between locations to view data
- No location restrictions for viewing

---

### 4. Admin-IT
**Purpose:** Technical administrator for system management

**Permissions:**
- ✅ **Full access** to Admin pages:
  - Home
  - My Tasks
  - 2FA Settings
  - Manage Locations
  - Manage Users
  - Audit Log
  - Error Monitoring
  - Asset Management
  - Deleted Records (Recycle Bin)
- ❌ **CANNOT** access operational pages (Tank Transactions, YADE, Tanker, FSO, etc.)
- ❌ **CANNOT** create, modify, or delete operational entries

**Task Assignment:**
- Receives **password reset requests**
- Receives **user management requests** (account creation, role changes)
- Receives **forgot password requests**
- Receives **system error alerts** (database, connection, server issues)
- Receives **ALL high-priority and critical errors**

**Error Routing to Admin-IT:**
```python
# System errors (database, network, etc.)
is_system_error = any(keyword in context.lower() for keyword in 
    ['database', 'connection', 'sql', 'server', 'network', 'timeout'])

if is_system_error or severity == "CRITICAL":
    # Task assigned to admin-it
```

**Location Access:**
- Not location-restricted for admin functions
- Cannot access location-specific operational data

---

### 5. Admin-Operations
**Purpose:** Full administrator with complete system access

**Permissions:**
- ✅ **FULL ACCESS** to all pages (Admin + Operational)
- ✅ Create, edit, delete all entries across all locations
- ✅ View all reports across all locations
- ✅ Customize reports and dashboards
- ✅ Manage all system configurations

**Task Assignment:**
- Receives **ALL task types**:
  - Password reset requests
  - User management requests
  - Forgot password requests
  - Application error alerts
  - Business logic errors
  - System errors (also sent to Admin-IT)
- **ALWAYS** notified of errors regardless of type

**Error Routing to Admin-Operations:**
```python
# Admin-Operations ALWAYS gets a task for every error
task_ops = Task(
    title=f"[OPS] {title}",
    target_role="admin-operations",
    # ... always created
)
```

**Location Access:**
- **FULL** access to all locations
- Can create/modify/delete across any location
- No location restrictions

---

## Deletion Approval Matrix

| Role | Can Delete Without Approval | Approval Method | Task Routing |
|------|----------------------------|-----------------|--------------|
| **Operator** | ❌ No | Local (supervisor code) or Remote (task) | → ALL supervisors at location |
| **Supervisor** | ✅ Yes (at their location) | N/A | N/A |
| **Manager** | ❌ No (view-only) | N/A | Not allowed to delete |
| **Admin-IT** | ❌ No (no operational access) | N/A | Not allowed on operational pages |
| **Admin-Operations** | ✅ Yes (all locations) | N/A | N/A |

---

## Task Routing Rules

### 1. Deletion Requests
```
Operator requests deletion
  → Task created with target_role = "supervisor"
  → Task.location_id = operator's location
  → ALL supervisors at that location see the task
  → ANY ONE supervisor can approve
  → Once approved, operator can complete deletion
```

### 2. Password Reset Requests
```
User requests password reset
  → Tasks created for BOTH:
     - Admin-IT (primary handler)
     - Admin-Operations (backup handler)
  → Either can approve
```

### 3. Error Alerts
```
Error occurs in application
  → System Error (database, network, etc.):
     - Task to Admin-IT [priority]
     - Task to Admin-Operations [backup]
  
  → Application Error (business logic):
     - Task to Admin-Operations [primary]
  
  → Critical Error (severity="CRITICAL"):
     - Tasks to BOTH Admin-IT and Admin-Operations
```

### 4. User Management Requests
```
New user creation / Role change
  → Tasks created for BOTH:
     - Admin-IT
     - Admin-Operations
  → Either can approve
```

---

## Task Visibility by Role

### Admin-Operations
```python
# Sees ALL tasks
query = session.query(Task)
# No filtering - full access
```

### Admin-IT
```python
# Sees IT-related tasks only
query = query.filter(
    or_(
        Task.target_role == "admin-it",
        Task.task_type.in_([
            TaskType.PASSWORD_RESET,
            TaskType.USER_CREATION,
            TaskType.ERROR_ALERT
        ])
    )
)
```

### Supervisor
```python
# Sees tasks for their location only
query = query.filter(
    Task.location_id == location_id,
    Task.target_role == "supervisor"
)
```

### Operator
```python
# Sees only their own raised tasks
query = query.filter(Task.raised_by == username)
```

### Manager
```python
# Sees NO tasks (not assigned to tasks)
return []
```

---

## Location Access Rules

### Strictly Location-Restricted Roles
- **Operator:** Can ONLY access their assigned location
- **Supervisor:** Can ONLY access their assigned location

### Multi-Location Access Roles
- **Manager:** Read-only access to ALL locations
- **Admin-Operations:** Full access to ALL locations
- **Admin-IT:** Not location-restricted (admin functions only)

---

## Implementation Code Examples

### Deletion Approval in Pages
```python
from deletion_approval import render_deletion_ui

# In delete operation (e.g., tank_transactions.py)
if render_deletion_ui(
    resource_type="TankTransaction",
    resource_id=transaction.id,
    resource_label=f"Tank Transaction #{transaction.id}",
    delete_func=lambda: delete_transaction(transaction.id),
    user=st.session_state.user,
    location_id=st.session_state.location_id,
    on_success_message="Tank transaction deleted successfully",
    metadata={"tank_id": transaction.tank_id}
):
    st.rerun()  # Refresh after deletion
```

### Task Count for Notifications
```python
from task_manager import TaskManager

# In sidebar
pending_count = TaskManager.count_pending_tasks_for_user(
    st.session_state.user
)

if pending_count > 0:
    st.sidebar.badge(f"{pending_count} pending tasks")
```

### Role-Based Page Access
```python
def check_operational_access(user):
    """Check if user can access operational pages"""
    role = user.get("role")
    
    # Admin-IT cannot access operational pages
    if role == "admin-it":
        st.error("❌ Admin-IT role does not have access to operational pages")
        st.stop()
    
    # Managers have view-only access
    if role == "manager":
        st.info("ℹ️ You have view-only access to this page")
        return "view-only"
    
    return "full-access"
```

---

## Security Notes

1. **Supervisor Codes:**
   - Stored as bcrypt hashes in `User.supervisor_code_hash`
   - Never stored in plaintext
   - Required for local deletion approvals

2. **Location Isolation:**
   - Operators and Supervisors MUST be filtered by `location_id`
   - Never allow cross-location access for these roles
   - Validate location_id in all queries

3. **Task Assignment:**
   - Deletion requests go to ALL supervisors at location
   - Any one approval is sufficient
   - Tasks automatically completed once deletion executed

4. **Error Notifications:**
   - All errors sent to Admin-Operations
   - System errors also sent to Admin-IT
   - Critical errors sent to BOTH

---

## Testing Checklist

- [ ] Operator cannot delete without approval
- [ ] Supervisor can delete directly at their location
- [ ] Manager cannot delete (blocked by UI)
- [ ] Admin-IT blocked from operational pages
- [ ] Admin-Operations has full access
- [ ] Deletion request sent to ALL supervisors at location
- [ ] Any supervisor can approve deletion request
- [ ] Operator can only access their location
- [ ] Supervisor can only access their location
- [ ] Manager can view all locations (read-only)
- [ ] Task notifications appear in sidebar
- [ ] Error tasks routed to correct admin roles
- [ ] Password reset tasks sent to both admins
