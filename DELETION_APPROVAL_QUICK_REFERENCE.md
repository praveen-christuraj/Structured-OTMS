# DELETION_APPROVAL_QUICK_REFERENCE.md
# Quick Reference: Deletion Approval System

## One-Line Integration

```python
from deletion_approval import render_deletion_ui

# Replace your old delete button code with this:
if render_deletion_ui(
    resource_type="TankTransaction",
    resource_id=tx_id,
    resource_label=f"Transaction #{tx_id}",
    delete_func=lambda: delete_transaction(tx_id),
    user=user,
    location_id=location_id
):
    st.rerun()  # Refresh after successful deletion
```

## What It Does

✅ **Automatic role detection**:
- Admins/Supervisors → direct deletion (one confirmation)
- Operators/Managers → requires approval (two methods)

✅ **Two approval methods**:
1. **Local**: Supervisor name + code (immediate)
2. **Remote**: Task request (async)

✅ **Full logging**:
- Audit trail automatically created
- Action logger records all deletions
- Tasks completed after deletion

✅ **Safety features**:
- Archive to recycle bin before delete
- Can't delete twice (checks existing tasks)
- Validates supervisor codes
- Error handling with admin notifications

## Role-Based Behavior

| Role | Can Delete Without Approval? | Approval Method |
|------|------------------------------|-----------------|
| Admin-IT | ✅ Yes | None needed |
| Admin-Operations | ✅ Yes | None needed |
| Supervisor | ✅ Yes | None needed |
| Manager | ❌ No | Local or Remote |
| Operator | ❌ No | Local or Remote |

## UI Flow Examples

### For Admins/Supervisors
```
[Delete Button Clicked]
  ↓
⚠️ Are you sure?
  ↓
[✅ Confirm Delete] [❌ Cancel]
  ↓
✅ Deleted successfully
```

### For Operators/Managers (Local Approval)
```
[Delete Button Clicked]
  ↓
⚠️ Supervisor approval required
  ↓
Tab: 📋 Local Approval
  ↓
Select Supervisor: [John Doe ▼]
Supervisor Code: [********]
  ↓
[🔓 Approve & Delete]
  ↓
✅ Deleted successfully
```

### For Operators/Managers (Remote Approval)
```
[Delete Button Clicked]
  ↓
⚠️ Supervisor approval required
  ↓
Tab: 📤 Remote Approval
  ↓
[📤 Send Approval Request]
  ↓
✅ Request sent! Task #123
(Operator waits...)
  ↓
[Later, after supervisor approves in My Tasks]
  ↓
✅ Remote approval granted by John Doe
[✅ Delete] [❌ Cancel]
  ↓
✅ Deleted successfully
```

## Common Patterns

### Pattern 1: Simple Transaction Deletion
```python
from deletion_approval import render_deletion_ui
from recycle_bin import RecycleBinManager

def perform_deletion():
    with get_session() as session:
        record = session.query(TankTransaction).get(tx_id)
        RecycleBinManager.archive_record(
            session, record, "TankTransaction",
            username=user.get("username"),
            label=f"TX-{tx_id}"
        )
        session.delete(record)
        session.commit()

if render_deletion_ui(
    resource_type="TankTransaction",
    resource_id=tx_id,
    resource_label=f"Transaction #{tx_id}",
    delete_func=perform_deletion,
    user=user,
    location_id=location_id
):
    st.success("Transaction deleted!")
    st.rerun()
```

### Pattern 2: Delete with Related Records
```python
def delete_voyage_with_related():
    with get_session() as session:
        # Archive main record
        voyage = session.query(YadeVoyage).get(voyage_id)
        RecycleBinManager.archive_record(
            session, voyage, "YadeVoyage",
            username=user.get("username"),
            label=f"{voyage.yade_name}-{voyage.voyage_no}"
        )
        
        # Delete related records
        session.query(YadeDip).filter_by(voyage_id=voyage_id).delete()
        session.query(YadeSampleParam).filter_by(voyage_id=voyage_id).delete()
        
        # Delete main record
        session.delete(voyage)
        session.commit()

render_deletion_ui(
    resource_type="YadeVoyage",
    resource_id=voyage_id,
    resource_label=f"{yade_name} Voyage {voyage_no}",
    delete_func=delete_voyage_with_related,
    user=user,
    location_id=location_id,
    metadata={"yade_name": yade_name, "voyage_no": voyage_no}
)
```

### Pattern 3: Conditional Deletion Logic
```python
from deletion_approval import DeletionApprovalManager

# Check if approval is needed
if DeletionApprovalManager.can_delete_without_approval(user):
    # Admin/Supervisor - show simple confirmation
    st.warning("Delete this record?")
    if st.button("✅ Yes"):
        perform_deletion()
else:
    # Operator/Manager - use full approval UI
    render_deletion_ui(...)
```

## Migration from Old Code

### Before (Old oil_app_ui.py pattern):
```python
# Old manual approval code (50+ lines)
if role == "operator":
    sup_username, sup_label = _supervisor_dropdown(...)
    code = st.text_input("Supervisor Code", type="password")
    if st.button("Delete"):
        if SecurityManager.verify_supervisor_code(code, sup_username):
            perform_deletion()
            st.success("Deleted")
        else:
            st.error("Invalid code")
elif role == "supervisor":
    if st.button("Delete"):
        perform_deletion()
        st.success("Deleted")
```

### After (New deletion_approval.py):
```python
# New unified approach (3 lines)
if render_deletion_ui(
    "TankTransaction", tx_id, f"TX-{tx_id}",
    perform_deletion, user, location_id
):
    st.rerun()
```

## Testing Checklist

- [ ] Admin can delete directly (one confirmation)
- [ ] Supervisor can delete directly (one confirmation)
- [ ] Operator sees approval tabs
- [ ] Local approval works with valid supervisor code
- [ ] Local approval rejects invalid supervisor code
- [ ] Remote approval creates task
- [ ] Supervisor can see task in "My Tasks"
- [ ] Operator can delete after remote approval
- [ ] Deletion is logged in audit trail
- [ ] Record is archived to recycle bin
- [ ] Task is marked completed after deletion

## Supervisor Code Setup

For local approval to work, supervisors must have codes set:

1. **Admin** goes to **Manage Users**
2. Select supervisor user
3. Find "Reset Supervisor Code" section
4. Enter new code (min 8 chars, uppercase, lowercase, number, special char)
5. Confirm code
6. Save

Without supervisor code → only remote approval available for operators.

## Error Scenarios

| Error | Cause | Solution |
|-------|-------|----------|
| "No supervisors available" | No supervisors at location | Assign supervisor or use remote approval |
| "Invalid supervisor code" | Wrong code entered | Re-enter correct code |
| "No supervisors with codes set" | Supervisors lack codes | Admin must set codes in Manage Users |
| "Deletion approval already requested" | Duplicate request | Wait for existing task approval |
| "Record not found" | Already deleted | Refresh page |

## API Reference

### render_deletion_ui()
```python
def render_deletion_ui(
    resource_type: str,          # E.g., "TankTransaction"
    resource_id: Any,             # Database ID
    resource_label: str,          # Display name
    delete_func: Callable,        # Function that deletes
    user: Dict[str, Any],         # Current user
    location_id: Optional[int],   # Active location
    on_success_message: str = "", # Custom success message
    metadata: Optional[Dict] = None,  # Task metadata
    button_key_prefix: str = None     # Unique button prefix
) -> bool:  # Returns True if deleted
```

### DeletionApprovalManager Methods

```python
# Check if user can delete without approval
can_delete = DeletionApprovalManager.can_delete_without_approval(user)

# Get supervisors for location
supervisors = DeletionApprovalManager.get_location_supervisors(location_id)

# Check remote approval status
approval = DeletionApprovalManager.check_remote_approval_status(
    resource_type, resource_id
)

# Request remote approval
task = DeletionApprovalManager.request_remote_approval(
    resource_type, resource_id, label, user, location_id, metadata
)

# Execute deletion with logging
success, error = DeletionApprovalManager.execute_deletion_with_approval(
    resource_type, resource_id, label, approver, method,
    delete_func, user, location_id
)
```

## Support

- Full guide: `ERROR_HANDLING_INTEGRATION_GUIDE.md` (Deletion Approval System section)
- Examples: `deletion_approval.py` (docstrings)
- Old reference: `oil_app_ui.py` (search for `_render_remote_delete_request_ui`)
