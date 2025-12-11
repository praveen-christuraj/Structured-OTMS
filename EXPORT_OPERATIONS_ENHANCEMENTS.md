# Export Operations Page Enhancements

## Overview
The Export Operations page has been redesigned with a comprehensive 3-tab structure providing better shipment management, visualization, and tracking capabilities.

## Tab Structure

### 1. Dashboard Tab (Tab 0)
**Purpose:** Visual overview of all shipments and their progress

**Features:**
- **Shipment Status Chart:** Altair visualization showing all shipments mapped to their current stage
- **Process Route Maps:** Expandable sections for each shipment showing:
  - Stage progression with color-coded status indicators:
    - 🟢 **Green:** Completed stages
    - 🔵 **Blue:** In Progress/Approved stages
    - ⚫ **Gray:** Pending/Not Started stages
  - **Date Information:**
    - For completed stages: Shows completion date (format: "Completed: YYYY-MM-DD")
    - For pending stages: Shows due date if set (format: "Due: YYYY-MM-DD")
  - Visual arrows (→) connecting stages to show workflow progression
- **Toggle:** "Show completed shipments" checkbox to filter completed shipments

**Use Case:** Quick overview dashboard for managers to see status of all active shipments at a glance

---

### 2. Shipment Manager Tab (Tab 1)
**Purpose:** Create, edit, and delete shipments

**Features:**

#### Create New Shipment
- Input fields for:
  - Shipment Title (required)
  - Shipment Reference No (optional)
- ➕ **Create Shipment** button to create new shipment
- On creation:
  - Creates `ExportProcess` record with `location_id=0`
  - Sets `current_stage_code` to first stage in pipeline
  - Records `created_by` username
  - Creates initial `ExportStageProgress` records for all stages

#### Manage Existing Shipments
- Shows **ALL shipments** (including completed)
- Each shipment displayed in expandable section showing:
  - 🚢 Shipment title
  - Reference number
  - Current status

**Per-Shipment Actions:**
- **Edit:**
  - Modify shipment title
  - Modify reference number
  - View current stage and status (read-only)
  - 💾 **Save Changes** button to update

- **Delete:**
  - 🗑️ **Delete Shipment** button (Admin-Operations only)
  - Two-step confirmation dialog to prevent accidental deletion
  - Cascade delete: Removes shipment + all stages + all attachments + all history
  - For non-admin users: Button is disabled with tooltip explaining permission requirement

**Permission Requirements:**
- **Access:** All users with `can_access_export_operations` permission
- **Create/Edit:** All users
- **Delete:** Only `Admin-Operations` role

**User Guidance:**
- Info message for non-admin users: "Only Admin-Operations can delete shipments. To request deletion, please raise a request through Services."

---

### 3. Shipment Tracker Tab (Tab 2)
**Purpose:** Detailed stage-by-stage tracking and management of individual shipments

**Features:**

#### Shipment Selection
- **Create Shipment Section:**
  - Shipment Title input
  - Shipment Reference No input
  - ➕ Create Shipment button
- **Shipment Filter:**
  - "Show completed shipments" checkbox
  - Altair chart showing stage progress visualization
  - Dropdown selector showing all shipments in format: `{id} • {title}`

#### Selected Shipment View
When a shipment is selected:

1. **Shipment Header:**
   - 🚢 Shipment title
   - Reference number
   - Current status

2. **Process Route Map:**
   - Visual representation of all stages
   - Color-coded status indicators
   - **Date information display:**
     - Completed stages: "Completed: YYYY-MM-DD"
     - Pending stages: "Due: YYYY-MM-DD" (if set)
   - Arrow connectors between stages

3. **Stage Management:**
   - All stages displayed as expandable sections
   - Current stage highlighted with 🎯 emoji
   - Per-stage information:
     - Stage name
     - Current status
     - Due date (editable)
     - Remarks (editable)
     - Last updated info (timestamp + username)
     - Overdue reason (if applicable)

4. **Edit Lock Mechanism:**
   - ✏️ **Edit** button to enter edit mode
   - In edit mode:
     - Status dropdown (from configured status options)
     - Due date picker
     - Remarks text area (mandatory when saving changes)
     - 💾 **Save** button (requires remarks)
     - ❌ **Cancel** button
   - **Edit History Tracking:**
     - Records `updated_at` timestamp
     - Records `updated_by` username
     - Records `completed_at` and `completed_by` when status changes to completion status
   - **Validation:**
     - Remarks are mandatory when saving stage changes
     - Error message if remarks are empty

5. **Attachments:**
   - Upload files to specific stage
   - Download existing attachments
   - Visibility options:
     - Global (all users can see)
     - Restricted (only assigned users can see)
   - Assignee selection for restricted attachments

6. **Advance to Next Stage:**
   - ➡️ **Advance to Next Stage** button
   - **Enable Logic:**
     - Enabled when current stage is completed (status matches `completion_statuses`)
     - OR enabled when current stage is non-mandatory (`mandatory=False`)
   - **Disable Logic:**
     - Disabled when current stage is mandatory AND not yet completed
     - Shows info message explaining why it's disabled
   - **Action:**
     - Updates `ExportProcess.current_stage_code` to next stage in pipeline
     - Creates/updates `ExportStageProgress` for new stage
     - If at last stage, marks entire shipment as completed

---

### Custom Export Tabs (Tab 3+)
Custom tabs defined in Export Customization are rendered starting from index 3.

**Index Calculation:**
- Dashboard: `st_tabs[0]`
- Shipment Manager: `st_tabs[1]`
- Shipment Tracker: `st_tabs[2]`
- Custom tabs: `st_tabs[i+3]` where `i` is the tab index in the custom tabs list

---

## Stage Lifecycle & Mandatory Logic

### Mandatory Stage Enforcement

**Configuration:** Set in Export Customization → Process Pipeline

**Mandatory Stage Behavior (`mandatory=True`):**
- Stage **MUST** be completed before advancing to next stage
- Status must be set to one of the `completion_statuses` (e.g., "Completed", "Approved")
- "Advance to Next Stage" button is **disabled** until completed
- User sees info message: "Advance to Next Stage is disabled because this is a mandatory stage that must be completed first."

**Non-Mandatory Stage Behavior (`mandatory=False`):**
- Stage can be skipped
- "Advance to Next Stage" button is **enabled** even if stage is not completed
- Allows flexible workflow for optional stages

### Stage Completion Statuses

**Configuration:** Set in Export Customization → Process Pipeline
- Each stage can define multiple completion statuses (e.g., ["Completed", "Approved", "Finalized"])
- Stage is considered "completed" when its status matches ANY of the completion statuses

**Completion Tracking:**
- `ExportStageProgress.status`: Current status of the stage
- `ExportStageProgress.completed_at`: Timestamp when status changed to completion status
- `ExportStageProgress.completed_by`: Username who marked it as complete

---

## Data Model

### ExportProcess (Main Shipment Record)
```python
{
    "id": int,
    "location_id": 0,  # Always 0 for user-dependent exports
    "terminal_label": str,  # Terminal name
    "title": str,  # Shipment title
    "ref_no": str,  # Reference number
    "current_stage_code": str,  # Current stage in pipeline
    "status": str,  # Overall shipment status
    "created_by": str,  # Username who created
    "created_at": datetime,
    "updated_at": datetime
}
```

### ExportStageProgress (Per-Stage Status)
```python
{
    "id": int,
    "export_id": int,  # FK to ExportProcess
    "stage_code": str,  # Stage identifier
    "status": str,  # Current status (e.g., "Pending", "In Progress", "Completed")
    "due_date": date,  # Target completion date
    "completed_at": datetime,  # When marked complete
    "completed_by": str,  # Username who completed
    "updated_at": datetime,  # Last update timestamp
    "updated_by": str,  # Last updater username
    "remarks": str,  # User comments/notes
    "overdue_reason": str,  # Explanation if overdue
}
```

### ExportAttachment (Stage Attachments)
```python
{
    "id": int,
    "stage_id": int,  # FK to ExportStageProgress
    "filename": str,
    "mime_type": str,
    "size_bytes": int,
    "data": bytes,  # Binary file data
    "visibility": str,  # "global" or "restricted"
    "assigned_to_user_id": int,  # For restricted visibility
    "uploaded_by": str,  # Username
    "uploaded_at": datetime
}
```

---

## Permission Model

### Page Access
- **Required Permission:** `PermissionManager.can_access_export_operations(user)`
- Checked at page entry via `_guard_access()` function

### Role-Based Actions

| Action | Required Role | Validation |
|--------|--------------|------------|
| View Export Operations | Any user with export_operations permission | `PermissionManager.can_access_export_operations()` |
| Create Shipment | Any user with export_operations permission | User-specific exports |
| Edit Shipment Details | Owner or Admin | User sees only their own shipments |
| Edit Stage Details | Owner or Admin | Edit lock with mandatory remarks |
| Upload Attachments | Owner or Admin | Stage-level uploads |
| Delete Shipment | Admin-Operations only | `user.role in ["admin-operations"]` |
| Advance to Next Stage | Owner or Admin | Subject to mandatory stage validation |

### Visibility Rules
- **Shipments:** Users see only shipments they created (`created_by = username`)
- **Attachments:** 
  - Global visibility: All users can see
  - Restricted visibility: Only assigned user can see
- **Custom Export Tabs:** Follow existing permission model

---

## Configuration Requirements

### Export Customization Setup (Prerequisites)

Before using Export Operations, configure in **Export Customization** page:

1. **Terminals:** Define terminal names
2. **Pipeline Stages:** For each terminal:
   - Stage Code (unique identifier)
   - Stage Name (display name)
   - Status Options (dropdown choices)
   - Completion Statuses (list of statuses that mark stage as complete)
   - Mandatory Flag (true/false)
   - Sets Laycan Flag (true/false, only one stage can set laycan dates)

### Pipeline Configuration Storage
- **Key Pattern:** `pipeline_{terminal_slug}_{username}`
- **Storage:** JSON in `location_config.py` with `location_id=0`
- **Structure:**
```json
{
  "stages": [
    {
      "code": "stage_code",
      "name": "Stage Name",
      "statuses": ["Pending", "In Progress", "Completed"],
      "completion_statuses": ["Completed"],
      "mandatory": true,
      "sets_laycan": false
    }
  ]
}
```

---

## UI/UX Improvements

### Visual Indicators
- 🚢 Ship emoji for shipment titles
- 🎯 Target emoji for current stage
- ➕ Plus for create actions
- ✏️ Pencil for edit actions
- 💾 Floppy disk for save actions
- 🗑️ Trash for delete actions
- ➡️ Arrow for advance/progress actions
- ❌ X for cancel actions
- ⚠️ Warning for confirmations

### Color Coding
- **Green (#16a34a):** Completed stages
- **Blue (#2563eb):** Active/In Progress stages
- **Gray (#6b7280):** Pending/Not Started stages

### User Feedback
- Success messages on successful operations
- Error messages with details on failures
- Info messages for guidance and explanations
- Warning messages for destructive actions
- Confirmation dialogs for irreversible operations

### Responsive Design
- Column layouts adapt to content
- Expandable sections reduce clutter
- Sticky headers for easy navigation
- Container width usage for charts

---

## Error Handling

### Graceful Degradation
- Try-except blocks around all database operations
- Fallback displays for failed visualizations
- Clear error messages for users
- No silent failures

### Common Error Scenarios
1. **No stages configured:** Show warning + link to customization
2. **No shipments found:** Show info message
3. **Database connection issues:** Show error with details
4. **Permission denied:** Show access denied message
5. **Failed to advance stage:** Show advance failed message
6. **Failed to save changes:** Show save failed message with exception details

---

## Technical Implementation Notes

### Database Session Management
- Uses `get_session()` context manager from `db.py`
- All operations wrapped in try-except-finally
- Automatic session cleanup
- Transaction commits after successful operations
- Rollback on exceptions

### State Management
- Streamlit session_state for:
  - Edit mode tracking: `exp_stage_edit_{stage_code}_{export_id}`
  - Delete confirmation: `exp_mgr_confirm_delete_{export_id}`
- Automatic rerun after state-changing operations using `_st_safe_rerun()`

### Performance Considerations
- Lazy loading of shipment data
- On-demand stage progress queries
- Efficient SQL queries with proper filters
- Index on `ExportProcess.created_by` and `ExportStageProgress.export_id`

---

## Future Enhancements (Potential)

1. **Bulk Operations:** Select multiple shipments for batch actions
2. **Advanced Filters:** Filter by date range, status, stage, terminal
3. **Export to Excel:** Download shipment data and stage history
4. **Email Notifications:** Notify on stage completion or overdue stages
5. **Analytics Dashboard:** Metrics on average stage completion times, bottlenecks
6. **Comments/Discussion:** Per-stage threaded comments for collaboration
7. **Calendar Integration:** Due date reminders and calendar sync
8. **Mobile Optimization:** Responsive design for mobile devices

---

## Changelog

### Version 1.0 (Current)
- ✅ Implemented 3-tab structure (Dashboard, Shipment Manager, Shipment Tracker)
- ✅ Added visual process route maps with date information
- ✅ Implemented Shipment Manager with CRUD operations
- ✅ Added Admin-Operations-only delete permissions
- ✅ Enhanced route maps to show completion and due dates
- ✅ Added detailed "Advance to Next Stage" functionality
- ✅ Implemented mandatory stage validation logic
- ✅ Added edit lock mechanism with mandatory remarks
- ✅ Fixed custom tabs indexing (now starts at i+3)
- ✅ Added comprehensive user guidance and help text
- ✅ Implemented confirmation dialogs for destructive actions

---

## Support & Documentation

For configuration help, see:
- **OPERATIONS_USER_GUIDE.md** - End-user guide for Export Operations
- **OPERATIONS_TECHNICAL_REFERENCE.md** - Technical reference for developers
- **PDF_CUSTOMIZATION_USER_GUIDE.md** - PDF export customization guide

For issues or questions:
- Check error messages in the UI for guidance
- Review stage configuration in Export Customization
- Verify user has appropriate permissions
- Contact system administrator for role/permission changes
