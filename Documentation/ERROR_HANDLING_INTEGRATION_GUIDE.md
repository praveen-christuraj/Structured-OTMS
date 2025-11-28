# ERROR_HANDLING_INTEGRATION_GUIDE.md
# Comprehensive Error Handling & Logging Integration Guide

## Overview

This guide demonstrates how to integrate the new comprehensive error handling and logging system into OTMS pages.

## Key Components

### 1. **logger.py** - Enhanced with ActionLogger
- `ActionLogger.log_action()` - Log any action with full audit trail
- `ActionLogger.log_error_with_task()` - Log errors and create admin tasks

### 2. **error_handler.py** - Decorators and utilities
- `@handle_errors()` - Decorator for automatic error handling
- `@log_action_decorator()` - Decorator for action logging
- `ErrorContext` - Context manager for error handling in code blocks
- `safe_execute()` - Execute functions with error handling

### 3. **task_manager.py** - Enhanced task routing
- `create_error_task()` - Creates error tasks for Admin-IT and Admin-Operations
- Routes system errors to Admin-IT
- Routes application errors to Admin-Operations
- Automatic deduplication of error tasks

### 4. **action_logger_utils.py** - Quick helpers
- `log_create_action()` - Log CREATE operations
- `log_update_action()` - Log UPDATE operations
- `log_delete_action()` - Log DELETE operations
- `log_view_action()` - Log page views
- `log_export_action()` - Log data exports
- `safe_transaction_operation()` - Safe wrapper for transactions

### 5. **UI Notifications** - Sidebar badges
- Pending task count badge
- Error summary for admin users
- Visual indicators with color coding

---

## Integration Patterns

### Pattern 1: Page View Logging

Add at the start of every render function:

```python
from action_logger_utils import log_view_action

def render_tank_transactions_page(active_location_id, user):
    # Log that user viewed this page
    log_view_action(
        resource_type="TankTransactions",
        user=user,
        location_id=active_location_id,
        details="Viewed tank transactions page"
    )
    
    # Rest of your page code...
```

### Pattern 2: Wrapping Critical Operations

#### Using Decorator:
```python
from error_handler import handle_errors

@handle_errors("Creating tank transaction", severity="HIGH")
def create_tank_transaction(data, user, location_id, session):
    """Create a new tank transaction with automatic error handling"""
    # Validate data
    if not data.get('tank_id'):
        raise ValueError("Tank ID is required")
    
    # Create transaction
    transaction = TankTransaction(**data)
    session.add(transaction)
    session.commit()
    
    # Log the action
    from action_logger_utils import log_create_action
    log_create_action(
        resource_type="TankTransaction",
        resource_id=transaction.id,
        user=user,
        location_id=location_id,
        details=f"Created transaction for tank {data.get('tank_id')}",
        session=session
    )
    
    return transaction
```

#### Using ErrorContext:
```python
from error_handler import ErrorContext
from action_logger_utils import log_create_action

def handle_form_submission(form_data, user, location_id):
    with ErrorContext("Creating tank transaction", severity="HIGH"):
        with get_session() as session:
            transaction = TankTransaction(**form_data)
            session.add(transaction)
            session.commit()
            
            log_create_action(
                resource_type="TankTransaction",
                resource_id=transaction.id,
                user=user,
                location_id=location_id,
                session=session
            )
            
            st.success(f"✅ Transaction created successfully! ID: {transaction.id}")
```

### Pattern 3: Update Operations

```python
from error_handler import handle_errors
from action_logger_utils import log_update_action

@handle_errors("Updating tank transaction", severity="MEDIUM")
def update_tank_transaction(transaction_id, updates, user, location_id, session):
    transaction = session.query(TankTransaction).get(transaction_id)
    if not transaction:
        raise ValueError(f"Transaction {transaction_id} not found")
    
    # Apply updates
    for key, value in updates.items():
        setattr(transaction, key, value)
    
    session.commit()
    
    log_update_action(
        resource_type="TankTransaction",
        resource_id=transaction_id,
        user=user,
        location_id=location_id,
        details=f"Updated fields: {', '.join(updates.keys())}",
        session=session
    )
    
    return transaction
```

### Pattern 4: Delete Operations

```python
from error_handler import handle_errors
from action_logger_utils import log_delete_action
from recycle_bin import RecycleBinManager

@handle_errors("Deleting tank transaction", severity="HIGH")
def delete_tank_transaction(transaction_id, user, location_id, session):
    transaction = session.query(TankTransaction).get(transaction_id)
    if not transaction:
        raise ValueError(f"Transaction {transaction_id} not found")
    
    # Archive to recycle bin
    RecycleBinManager.archive_record(
        session=session,
        resource_type="TankTransaction",
        resource_id=transaction_id,
        record_obj=transaction,
        deleted_by=user.get("username"),
        reason="User requested deletion"
    )
    
    # Delete from database
    session.delete(transaction)
    session.commit()
    
    log_delete_action(
        resource_type="TankTransaction",
        resource_id=transaction_id,
        user=user,
        location_id=location_id,
        details=f"Deleted transaction and archived to recycle bin",
        session=session
    )
```

### Pattern 5: Export Operations

```python
from action_logger_utils import log_export_action
from error_handler import ErrorContext

def export_transactions_to_excel(transactions, user, location_id):
    with ErrorContext("Exporting transactions to Excel", severity="MEDIUM"):
        df = pd.DataFrame([t.to_dict() for t in transactions])
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Transactions')
        
        log_export_action(
            resource_type="TankTransaction",
            export_format="Excel",
            record_count=len(transactions),
            user=user,
            location_id=location_id
        )
        
        return buffer.getvalue()
```

### Pattern 6: Bulk Operations

```python
from error_handler import ErrorContext
from logger import ActionLogger

def bulk_import_transactions(import_data, user, location_id):
    success_count = 0
    error_count = 0
    errors = []
    
    with get_session() as session:
        for idx, row in enumerate(import_data):
            try:
                # Process each row
                transaction = TankTransaction(**row)
                session.add(transaction)
                session.flush()
                success_count += 1
                
            except Exception as e:
                error_count += 1
                error_msg = f"Row {idx + 1}: {str(e)}"
                errors.append(error_msg)
                
                # Log individual row errors (don't create tasks for each)
                ActionLogger.log_action(
                    action="IMPORT_ERROR",
                    resource_type="TankTransaction",
                    username=user.get("username"),
                    user_id=user.get("id"),
                    location_id=location_id,
                    details=error_msg,
                    success=False
                )
        
        if error_count > 0:
            # Create a single error task for bulk import issues
            ActionLogger.log_error_with_task(
                error=Exception(f"Bulk import had {error_count} errors"),
                context="Bulk Transaction Import",
                user=user,
                location_id=location_id,
                severity="MEDIUM",
                additional_info=f"Successful: {success_count}\nFailed: {error_count}\n\nErrors:\n" + "\n".join(errors[:10])
            )
        
        session.commit()
    
    return success_count, error_count, errors
```

---

## Deletion Approval System

### Overview

All deletions in OTMS require proper authorization based on user roles:

- **Admin-IT, Admin-Operations, Supervisor**: Can delete directly without approval
- **Operator, Manager**: Must obtain approval via one of two methods:
  1. **Local Approval**: Immediate approval with supervisor username + code
  2. **Remote Approval**: Request sent to supervisors via task system

### Quick Integration

```python
from deletion_approval import render_deletion_ui

def handle_delete_transaction(transaction_id, user, location_id):
    """Handle transaction deletion with approval workflow"""
    
    def perform_deletion():
        with get_session() as session:
            tx = session.query(TankTransaction).get(transaction_id)
            if tx:
                # Archive to recycle bin
                RecycleBinManager.archive_record(
                    session, tx, "TankTransaction",
                    username=user.get("username"),
                    user_id=user.get("id"),
                    location_id=location_id,
                    reason="User requested deletion",
                    label=f"TX-{transaction_id}"
                )
                session.delete(tx)
                session.commit()
    
    # Render deletion UI (handles all approval logic)
    deleted = render_deletion_ui(
        resource_type="TankTransaction",
        resource_id=transaction_id,
        resource_label=f"Tank Transaction #{transaction_id}",
        delete_func=perform_deletion,
        user=user,
        location_id=location_id,
        on_success_message=f"✅ Transaction #{transaction_id} deleted successfully",
        metadata={"page": "Tank Transactions"},
        button_key_prefix=f"del_tx_{transaction_id}"
    )
    
    if deleted:
        st.rerun()  # Refresh the page after successful deletion
```

### Approval Methods Explained

#### Method 1: Local Approval (Immediate)

Best for:
- Supervisor is physically present
- Urgent deletions
- Real-time operations

Flow:
1. Operator/Manager clicks delete
2. UI shows supervisor selector + code input
3. Enter supervisor username and code
4. System verifies code → deletion executes immediately

```python
# Local approval happens automatically via render_deletion_ui
# Supervisor code is verified using SecurityManager.verify_supervisor_code()
```

#### Method 2: Remote Approval (Task-Based)

Best for:
- Supervisor not immediately available
- Audit trail requirements
- Non-urgent deletions

Flow:
1. Operator/Manager requests approval
2. Task created and assigned to location supervisors
3. Supervisor reviews in "My Tasks" page
4. Supervisor approves/rejects
5. Operator can delete with approved task

```python
# Remote approval also handled by render_deletion_ui
# Task is created via TaskManager.create_delete_request()
# Status checked via DeletionApprovalManager.check_remote_approval_status()
```

### Advanced Usage

#### Custom Deletion Logic

```python
from deletion_approval import DeletionApprovalManager

# Check if user needs approval
if DeletionApprovalManager.can_delete_without_approval(user):
    # Direct deletion for admins/supervisors
    delete_record()
else:
    # Show approval UI for operators/managers
    render_deletion_ui(...)
```

#### Manual Approval Check

```python
# Check for existing remote approval
approval = DeletionApprovalManager.check_remote_approval_status(
    resource_type="TankTransaction",
    resource_id=123
)

if approval:
    st.success(f"Approved by {approval.get('approved_by')}")
    # Allow deletion
else:
    # Show approval UI
```

#### Request Remote Approval Programmatically

```python
task = DeletionApprovalManager.request_remote_approval(
    resource_type="YadeVoyage",
    resource_id=voyage_id,
    resource_label=f"YADE Voyage {voyage_no}",
    user=user,
    location_id=location_id,
    metadata={
        "page": "Yade Transactions",
        "yade_name": yade_name,
        "voyage_no": voyage_no
    }
)

st.info(f"Approval request created: Task #{task['id']}")
```

### Integration Examples

#### Example 1: Tank Transactions Deletion

```python
# In tank_transactions.py
from deletion_approval import render_deletion_ui
from recycle_bin import RecycleBinManager

def render_tank_transaction_delete_ui(tx_id, user, location_id):
    def delete_transaction():
        with get_session() as session:
            tx = session.query(TankTransaction).get(tx_id)
            if not tx:
                raise ValueError("Transaction not found")
            
            # Archive first
            RecycleBinManager.archive_record(
                session, tx, "TankTransaction",
                username=user.get("username"),
                label=f"TX-{tx_id}"
            )
            
            # Delete
            session.delete(tx)
            session.commit()
    
    deleted = render_deletion_ui(
        resource_type="TankTransaction",
        resource_id=tx_id,
        resource_label=f"Tank Transaction #{tx_id}",
        delete_func=delete_transaction,
        user=user,
        location_id=location_id
    )
    
    return deleted
```

#### Example 2: Yade Voyage Deletion

```python
# In yade_transactions.py
def handle_yade_deletion(voyage_id, voyage_label, user, location_id):
    def delete_voyage():
        with get_session() as session:
            # Delete voyage and related records
            voyage = session.query(YadeVoyage).get(voyage_id)
            
            # Archive to recycle bin
            RecycleBinManager.archive_record(
                session, voyage, "YadeVoyage",
                username=user.get("username"),
                label=voyage_label
            )
            
            # Delete related dips, samples, etc.
            session.query(YadeDip).filter_by(voyage_id=voyage_id).delete()
            session.query(YadeSampleParam).filter_by(voyage_id=voyage_id).delete()
            session.query(YadeSealDetail).filter_by(voyage_id=voyage_id).delete()
            
            session.delete(voyage)
            session.commit()
    
    return render_deletion_ui(
        resource_type="YadeVoyage",
        resource_id=voyage_id,
        resource_label=voyage_label,
        delete_func=delete_voyage,
        user=user,
        location_id=location_id,
        metadata={"page": "Yade Transactions"}
    )
```

#### Example 3: User Deletion (Admin Only)

```python
# In manage_users.py - users can only be deleted by admins
from deletion_approval import DeletionApprovalManager

def delete_user_ui(user_id, username_to_delete, current_user):
    # Check permissions (only admins can delete users)
    if current_user.get("role") not in ["admin-it", "admin-operations"]:
        st.error("Only administrators can delete users")
        return False
    
    def delete_user():
        with get_session() as session:
            user = session.query(User).get(user_id)
            RecycleBinManager.archive_record(
                session, user, "User",
                username=current_user.get("username"),
                label=username_to_delete
            )
            session.delete(user)
            session.commit()
    
    # Admin deletion (no approval needed)
    st.warning(f"⚠️ Delete user **{username_to_delete}**?")
    
    col1, col2 = st.columns(2)
    if col1.button("✅ Confirm", key=f"del_user_{user_id}"):
        try:
            delete_user()
            st.success(f"User {username_to_delete} deleted")
            return True
        except Exception as e:
            st.error(f"Error: {e}")
    
    if col2.button("❌ Cancel", key=f"cancel_user_{user_id}"):
        st.info("Cancelled")
    
    return False
```

### Supervisor Code Management

Supervisors must have a supervisor code set to approve local deletions:

1. **Setting Supervisor Code** (Admin only):
   - Go to **Manage Users**
   - Select supervisor
   - Use "Reset Supervisor Code" section
   - Enter and confirm new code

2. **Verifying Codes**:
   ```python
   from security import SecurityManager
   
   is_valid = SecurityManager.verify_supervisor_code(
       code="entered_code",
       supervisor_username="supervisor_username"
   )
   ```

### Task Approval Flow

When remote approval is requested:

1. **Task Creation**: Operator requests deletion → task created
2. **Task Assignment**: Task appears in "My Tasks" for supervisors
3. **Supervisor Action**: Supervisor reviews and approves/rejects
4. **Operator Notified**: Operator sees approval status
5. **Deletion Execution**: Operator completes deletion with approved task

### Best Practices

1. **Always use `render_deletion_ui()`** - It handles all approval logic automatically
2. **Wrap deletion logic** in a function - Pass as `delete_func` parameter
3. **Archive before deleting** - Use `RecycleBinManager.archive_record()`
4. **Use unique button keys** - Prefix with resource type and ID
5. **Add metadata** - Include page name and context for task tracking
6. **Log deletions** - Automatic via `DeletionApprovalManager.execute_deletion_with_approval()`

### Testing Your Integration

1. **Test as admin**: Should see direct "Confirm Delete" button
2. **Test as supervisor**: Should see direct "Confirm Delete" button
3. **Test as operator** (with supervisor present):
   - Click delete
   - See local approval tab
   - Enter supervisor username + code
   - Verify immediate deletion
4. **Test as operator** (remote):
   - Click delete
   - Go to remote approval tab
   - Request approval
   - Check "My Tasks" as supervisor
   - Approve task
   - Return as operator
   - Verify deletion allowed

---

## Quick Implementation Checklist

For each page in `app_pages/`, add:

1. ✅ **Page view logging** at the start of render function
   ```python
   from action_logger_utils import log_view_action
   log_view_action("PageName", user, location_id)
   ```

2. ✅ **Wrap all database operations** with error handlers
   ```python
   from error_handler import handle_errors
   
   @handle_errors("Operation description", severity="HIGH")
   def database_operation(...):
       # Your code
   ```

3. ✅ **Log all CRUD operations**
   ```python
   from action_logger_utils import log_create_action, log_update_action, log_delete_action
   
   # After create
   log_create_action("ResourceType", resource_id)
   
   # After update
   log_update_action("ResourceType", resource_id, details="What changed")
   
   # After delete
   log_delete_action("ResourceType", resource_id)
   ```

4. ✅ **Log exports**
   ```python
   from action_logger_utils import log_export_action
   log_export_action("ResourceType", "Excel", len(records))
   ```

5. ✅ **Use ErrorContext for complex operations**
   ```python
   from error_handler import ErrorContext
   
   with ErrorContext("Complex operation", severity="HIGH"):
       # Multiple steps
       step1()
       step2()
       step3()
   ```

---

## Error Severity Guidelines

- **CRITICAL**: System failures, database corruption, security breaches
  - Creates tasks for both Admin-IT and Admin-Operations
  - Re-raises the exception (doesn't suppress)
  - Examples: Database connection loss, authentication system failure

- **HIGH**: Operation failures that affect user workflows
  - Creates task for Admin-Operations (Admin-IT if system-related)
  - Suppresses exception and shows user-friendly error
  - Examples: Failed transaction creation, data validation errors

- **MEDIUM**: Non-critical errors that can be recovered
  - Creates task for Admin-Operations
  - Logs error but continues operation
  - Examples: Export failures, bulk import partial failures

- **LOW**: Minor issues, warnings
  - Logs only, no task creation
  - Examples: Data formatting issues, optional field validation

---

## Testing Your Integration

1. **Test error logging**: Intentionally cause an error and verify:
   - Error appears in logs
   - Task is created for admin
   - User sees friendly error message
   - Stack trace is captured

2. **Test action logging**: Perform CRUD operations and verify:
   - Actions appear in audit log
   - Correct user/location recorded
   - Timestamps are accurate

3. **Test notifications**: Check sidebar shows:
   - Pending task count badge
   - Error summary for admin users
   - Color coding based on severity

4. **Test task routing**: Verify:
   - System errors go to Admin-IT
   - Application errors go to Admin-Operations
   - Both admins can see and resolve tasks

---

## Migration Priority

**High Priority Pages** (implement first):
1. Tank Transactions
2. Tanker Transactions
3. Yade Transactions
4. Manage Users
5. Manage Locations

**Medium Priority Pages**:
6. FSO Operations
7. Vessel Operations
8. Material Balance
9. Reports/Reporting
10. Asset Management

**Low Priority Pages**:
11. Dashboard Customization
12. Page Customization
13. Settings pages

---

## Support and Questions

If you need help integrating error handling:
1. Check the examples in `action_logger_utils.py`
2. Review existing integrations in updated pages
3. Test with low-severity operations first
4. Monitor logs to verify behavior

The system is designed to be fail-safe - if error handling itself fails, it won't break your application.
