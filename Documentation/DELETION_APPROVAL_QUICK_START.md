# Deletion Approval System - Quick Start Guide

## 🎯 Role Permission Summary

| Role | Create | View | Edit | Delete | Location Access | Tasks |
|------|--------|------|------|--------|----------------|-------|
| **Operator** | ✅ | ✅ Own location | ✅ | ⚠️ Needs approval | Own location only | Own raised tasks |
| **Supervisor** | ✅ | ✅ Own location | ✅ | ✅ Direct | Own location only | Location deletion requests |
| **Manager** | ❌ | ✅ All locations | ❌ | ❌ | All (read-only) | None |
| **Admin-IT** | ❌ Ops pages | ✅ Admin pages | ❌ Ops pages | ❌ Ops pages | Not location-based | IT/System errors, User mgmt |
| **Admin-Operations** | ✅ | ✅ | ✅ | ✅ | All locations | Everything |

---

## 🚀 Quick Integration Example

### Before (Simple Confirmation):
```python
if st.button("🗑️ Delete"):
    st.session_state["confirm_delete"] = True

if st.session_state.get("confirm_delete"):
    if st.button("✅ Yes"):
        delete_record()
        st.success("Deleted")
```

### After (Deletion Approval System):
```python
from deletion_approval import render_deletion_ui

if st.button("🗑️ Delete"):
    st.session_state["show_delete_ui"] = True

if st.session_state.get("show_delete_ui"):
    if render_deletion_ui(
        resource_type="TankTransaction",
        resource_id=record.id,
        resource_label=f"Transaction #{record.id}",
        delete_func=lambda: delete_record(),
        user=st.session_state.user,
        location_id=st.session_state.location_id,
        on_success_message="Transaction deleted successfully"
    ):
        st.session_state["show_delete_ui"] = False
        st.rerun()
```

---

## 📋 What Happens for Each Role?

### Admin-Operations or Supervisor
```
Click Delete → ⚠️ Confirm Delete? → ✅ Confirm → ✅ Deleted
```

### Manager
```
Click Delete → ❌ "Managers have view-only access"
```

### Admin-IT
```
Click Delete → ❌ "Admin-IT does not have operational access"
```

### Operator
```
Click Delete → Two Tabs:
  
  Tab 1: Local Approval (Immediate)
    → Select supervisor from dropdown
    → Enter supervisor code
    → ✅ Deleted

  Tab 2: Remote Approval (Task Request)
    → Click "Send Approval Request"
    → Task created for ALL supervisors at location
    → Any supervisor can approve
    → Once approved, operator can delete
```

---

## 🔧 Core Functions

### Check if User Can Delete
```python
from deletion_approval import DeletionApprovalManager

can_delete = DeletionApprovalManager.can_delete_without_approval(user)
# True: admin-operations, supervisor
# False: operator, manager, admin-it
```

### Get Location Supervisors
```python
supervisors = DeletionApprovalManager.get_location_supervisors(location_id)
# Returns: [{"id": 1, "username": "super1", "full_name": "John Doe", "has_code": True}, ...]
```

### Verify Local Approval
```python
valid, error = DeletionApprovalManager.verify_local_approval(
    supervisor_username="super1",
    supervisor_code="1234"
)
# Returns: (True, "") or (False, "Invalid supervisor code")
```

### Check Remote Approval Status
```python
approved_task = DeletionApprovalManager.check_remote_approval_status(
    resource_type="TankTransaction",
    resource_id=123
)
# Returns: Task dict if approved, None otherwise
```

### Request Remote Approval
```python
task = DeletionApprovalManager.request_remote_approval(
    resource_type="TankTransaction",
    resource_id=123,
    resource_label="Tank Transaction #123",
    user=current_user,
    location_id=current_location,
    metadata={"tank_id": 5}
)
# Creates task assigned to ALL supervisors at location
```

---

## 🎨 Full Integration Pattern

```python
from deletion_approval import render_deletion_ui

# In your page rendering:
def render_transaction_list(transactions, user, location_id):
    for i, txn in enumerate(transactions):
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
        
        with col1:
            st.write(f"Transaction #{txn.id}")
        with col2:
            st.button("👁️ View", key=f"view_{i}")
        with col3:
            st.button("✏️ Edit", key=f"edit_{i}")
        with col4:
            if st.button("🗑️ Delete", key=f"del_{i}"):
                st.session_state[f"show_delete_{i}"] = True
        
        # Deletion approval UI
        if st.session_state.get(f"show_delete_{i}"):
            
            def delete_this_transaction():
                with get_session() as s:
                    # Archive to recycle bin
                    RecycleBinManager.archive_record(
                        s, txn, "TankTransaction",
                        username=user["username"],
                        user_id=user["id"],
                        location_id=location_id,
                        reason="User deleted transaction",
                        label=f"Transaction #{txn.id}"
                    )
                    s.commit()
            
            if render_deletion_ui(
                resource_type="TankTransaction",
                resource_id=txn.id,
                resource_label=f"Transaction #{txn.id} ({txn.tx_date})",
                delete_func=delete_this_transaction,
                user=user,
                location_id=location_id,
                on_success_message="Transaction deleted successfully",
                metadata={"tank_id": txn.tank_id, "tx_date": str(txn.tx_date)},
                button_key_prefix=f"del_txn_{i}"
            ):
                st.session_state[f"show_delete_{i}"] = False
                st.rerun()
```

---

## 🔔 Task Notifications

### Sidebar Notification Count
```python
from task_manager import TaskManager

pending_count = TaskManager.count_pending_tasks_for_user(user)

if pending_count > 0:
    st.sidebar.info(f"📬 {pending_count} pending task{'s' if pending_count != 1 else ''}")
```

### Fetch Tasks for User
```python
from task_manager import TaskManager

tasks = TaskManager.fetch_tasks_for_user(
    user=current_user,
    statuses=["PENDING"],
    include_history=False
)

for task in tasks:
    st.write(f"{task['title']} - {task['status']}")
```

---

## 🧪 Testing Scenarios

### Test 1: Operator Local Approval
1. Login as operator
2. Try to delete entry
3. See "Local Approval" tab
4. Select supervisor from dropdown
5. Enter supervisor code
6. Click "Approve & Delete"
7. ✅ Entry deleted with approver logged

### Test 2: Operator Remote Approval
1. Login as operator
2. Try to delete entry
3. See "Remote Approval" tab
4. Click "Send Approval Request"
5. Task created for supervisors
6. Login as supervisor at same location
7. Go to "My Tasks"
8. Approve deletion request
9. Login back as operator
10. Try delete again
11. See "Remote approval granted"
12. Click "Delete"
13. ✅ Entry deleted

### Test 3: Supervisor Direct Delete
1. Login as supervisor
2. Try to delete entry
3. See simple "Confirm Delete" prompt
4. Click "Confirm"
5. ✅ Entry deleted immediately

### Test 4: Manager Blocked
1. Login as manager
2. Try to delete entry
3. ❌ See error: "Managers have view-only access"

### Test 5: Multiple Supervisors
1. Create location with 3 supervisors
2. Login as operator at that location
3. Request deletion approval (remote)
4. Login as supervisor #1
5. See task in "My Tasks"
6. Login as supervisor #2
7. See same task in "My Tasks"
8. Supervisor #2 approves
9. ✅ Task completed, operator can delete

---

## 📊 Task Routing Rules

### Deletion Requests
```
Operator at Location A requests deletion
  ↓
Task created:
  - target_role = "supervisor"
  - location_id = Location A
  ↓
ALL supervisors at Location A see task
  ↓
ANY ONE supervisor approves
  ↓
Operator can complete deletion
```

### Error Tasks
```
Error occurs in application
  ↓
Is it a system error? (database, network, etc.)
  YES → Task to Admin-IT + Admin-Operations
  NO  → Task to Admin-Operations only
  ↓
Is severity CRITICAL?
  YES → Tasks to BOTH Admin-IT and Admin-Operations
```

### User Management Tasks
```
Password reset / User creation / Role change
  ↓
Tasks created for BOTH:
  - Admin-IT
  - Admin-Operations
  ↓
Either can handle the request
```

---

## 🔐 Security Checklist

- [ ] Supervisor codes set for all supervisors
- [ ] Operators restricted to their location in all queries
- [ ] Supervisors restricted to their location in all queries
- [ ] Managers cannot create/edit/delete
- [ ] Admin-IT blocked from operational pages
- [ ] All deletions logged with approver details
- [ ] Tasks filtered by location for supervisors
- [ ] Multiple supervisors can see same deletion request
- [ ] Task completed automatically after deletion

---

## 📁 Key Files

| File | Purpose |
|------|---------|
| `deletion_approval.py` | Core deletion approval logic and UI |
| `task_manager.py` | Task creation, routing, and filtering |
| `security.py` | Supervisor code verification |
| `logger.py` | Action logging and error tracking |
| `ui.py` | Notification badges and UI helpers |
| `Documentation/ROLE_BASED_ACCESS_CONTROL.md` | Complete role permissions reference |
| `Documentation/DELETION_APPROVAL_IMPLEMENTATION.md` | Implementation guide and patterns |

---

## 🎯 Next Step

**Apply this pattern to:**
1. `app_pages/view_transactions.py` (lines ~1673-1738)
2. `app_pages/yade_view.py`
3. `app_pages/tanker_view.py`
4. Any other pages with delete functionality

**Pattern:** Replace simple Yes/Cancel with `render_deletion_ui()` call as shown above.
