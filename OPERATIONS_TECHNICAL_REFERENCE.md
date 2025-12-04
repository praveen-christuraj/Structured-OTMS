# Technical Reference: Operations Configuration Fix

## Architecture Overview

### Before the Fix
```
Location Settings → Operations (User Interface)
                            ↓
              add_operation() → stores in config
                            ↓
Transaction Page (Tanker/Tank)
                            ↓
        get_active_operation_names() 
        (Returns ALL items from ALL categories)
                            ↓
        ❌ PROBLEM: Dropdowns showed mixed items
           - Operation dropdown also showed Cargo Type items
           - Destination dropdown showed mixed items
           - No proper category separation
```

### After the Fix
```
Location Settings → Operations (User Interface)
              ├─ Asset: Tanker
              │  ├─ Category: Operation → stores items
              │  ├─ Category: Cargo Type → stores items
              │  ├─ Category: Destination → stores items
              │  └─ Category: Loading Berth → stores items
              └─ Asset: Tank
                 ├─ Category: Operation → stores items
                 └─ Other categories...
                            ↓
Transaction Page (Tanker/Tank)
                            ↓
  get_active_operation_names_by_category()
  (asset="tanker", category="Operation")
                            ↓
        ✅ CORRECT: Each dropdown shows only
           items from its designated category
```

## Data Flow

### 1. Storage (location_config.py)

```python
# Configuration structure in LocationConfiguration.config_json:
{
    "operations": {
        "tanker": {
            "Operation": [
                {"id": "uuid1", "name": "Receipt from Aggu", "active": true},
                {"id": "uuid2", "name": "Dispatch to GPP", "active": true}
            ],
            "Cargo Type": [
                {"id": "uuid3", "name": "Crude Oil", "active": true},
                {"id": "uuid4", "name": "Condensate", "active": true}
            ],
            "Destination": [
                {"id": "uuid5", "name": "Aggu", "active": true},
                {"id": "uuid6", "name": "OFS", "active": true}
            ],
            "Loading Berth": [
                {"id": "uuid7", "name": "Berth A", "active": true}
            ]
        },
        "tank": {
            "Operation": [
                {"id": "uuid8", "name": "Opening Stock", "active": true}
            ]
        }
    }
}
```

### 2. Retrieval Functions (location_config.py)

#### Old Function (Still Available for Backward Compatibility)
```python
def get_active_operation_names(session, location_id, *, asset):
    """Returns ALL active operations for an asset (all categories)"""
    ops = list_operations(session, location_id, asset=asset)
    return [o["name"] for o in ops if o.get("active", True)]
```

#### New Function (Category-Specific)
```python
def get_active_operation_names_by_category(session, location_id, *, asset, category):
    """Returns ONLY operations for specific asset AND category"""
    ops = list_operations(session, location_id, asset=asset, category=category)
    return [o["name"] for o in ops if o.get("active", True)]
```

### 3. Usage in Transaction Pages

#### Tanker Transactions (app_pages/tanker_transactions.py)

**Cargo Dropdown:**
```python
cargo_options_cfg = get_active_operation_names_by_category(
    s, location.id, 
    asset="tanker", 
    category="Cargo Type"
) or CARGO_OPTIONS  # fallback to defaults

cargo = st.selectbox("Cargo *", cargo_options_cfg, ...)
```

**Operation Dropdown:**
```python
op_options = get_active_operation_names_by_category(
    s, location.id,
    asset="tanker",
    category="Operation"
) or ["N/A (configure in Location Settings)"]

operation = st.selectbox("Operation", op_options, ...)
```

**Destination Dropdown:**
```python
dest_options_cfg = get_active_operation_names_by_category(
    s, location.id,
    asset="tanker",
    category="Destination"
) or ["N/A (configure in Location Settings)"]

destination = st.selectbox("Destination *", dest_options_cfg, ...)
```

**Loading Bay Dropdown:**
```python
loading_options_cfg = get_active_operation_names_by_category(
    s, location.id,
    asset="tanker",
    category="Loading Berth"
) or ["N/A (configure in Location Settings)"]

loading_bay = st.selectbox("Loading Bay", loading_options_cfg, ...)
```

#### Tank Transactions (app_pages/tank_transactions.py)

**Operation Dropdown:**
```python
def _get_operation_labels_for_tank(location_id):
    with get_session() as s:
        names = get_active_operation_names_by_category(
            s, location_id,
            asset="tank",
            category="Operation"
        )
    return names or []

op_labels = _get_operation_labels_for_tank(loc.id)
selected_op = st.selectbox("🔁 Operation", op_labels, ...)
```

## Code Modifications Summary

### 1. location_config.py
**Lines Added**: ~20 lines (new function)
**Function Added**: `get_active_operation_names_by_category()`

```python
# NEW FUNCTION
def get_active_operation_names_by_category(
    session: Session,
    location_id: int,
    *,
    asset: str,
    category: str,
) -> List[str]:
    """Get active operation names for specific asset AND category."""
    ops = list_operations(session, location_id, asset=asset, category=category)
    return [o["name"] for o in ops if o.get("active", True)]
```

### 2. tanker_transactions.py
**Lines Modified**: ~15 lines
**Changes**:
- Added import: `get_active_operation_names_by_category`
- Updated 2 functions (`_render_entry_form` and `_render_entry_form_legacy`) to:
  - Use category-specific getters for each dropdown
  - Show fallback messages if no items configured
  - Change Cargo dropdown from hardcoded to dynamic

**Before**:
```python
from location_config import LocationConfig, get_active_operation_names, list_operations
```

**After**:
```python
from location_config import LocationConfig, get_active_operation_names, get_active_operation_names_by_category, list_operations
```

### 3. tank_transactions.py
**Lines Modified**: ~3 lines
**Changes**:
- Added import: `get_active_operation_names_by_category`
- Updated function: `_get_operation_labels_for_tank()` to use category-specific getter

**Before**:
```python
names = get_active_operation_names(s, location_id, asset="tank")
```

**After**:
```python
names = get_active_operation_names_by_category(s, location_id, asset="tank", category="Operation")
```

## Testing Matrix

| Test Case | Location | Expected Behavior | Status |
|-----------|----------|-------------------|--------|
| Add Operation to Tanker | Location Settings → Operations | Appears only in Operation dropdown | ✅ |
| Add Cargo Type to Tanker | Location Settings → Operations | Appears only in Cargo dropdown | ✅ |
| Add Destination to Tanker | Location Settings → Operations | Appears only in Destination dropdown | ✅ |
| Add Loading Berth to Tanker | Location Settings → Operations | Appears only in Loading Bay dropdown | ✅ |
| Add Operation to Tank | Location Settings → Operations | Appears only in Tank Entry Operation dropdown | ✅ |
| Cargo items not in Operation | Tanker Transactions | Operation dropdown should only have operations | ✅ |
| Destination items not in Cargo | Tanker Transactions | Cargo dropdown should only have cargo types | ✅ |
| Fallback values show | Empty category | Shows "N/A (configure in Location Settings)" | ✅ |

## Performance Impact

**Minimal**: 
- One additional parameter to `list_operations()` for filtering
- Filtering happens in-memory on already-loaded operations list
- No additional database queries

## Backward Compatibility

**Full Backward Compatibility**:
- Old function `get_active_operation_names()` still available
- Existing code using it continues to work
- Used in `view_transactions.py` and other pages where all-category lookup is needed
- No breaking changes to public APIs

## Future Enhancements

Possible improvements:
1. Add caching for frequently-accessed operation lists
2. Add validation to prevent duplicate category items within same asset
3. Add bulk import/export functionality for operations
4. Add operation templates for common setups (e.g., standard tanker operations)
5. Add deprecation warning for `get_active_operation_names()` (if needed in future)

## Related Functions (location_config.py)

- `list_operations()` - Core function that lists and filters operations
- `add_operation()` - Add new operation to config
- `set_operation_active()` - Toggle active/inactive status
- `delete_operation()` - Remove operation from config
- `get_active_operation_names()` - OLD: Get all operations for asset
- `get_active_operation_names_by_category()` - NEW: Get operations for specific category
