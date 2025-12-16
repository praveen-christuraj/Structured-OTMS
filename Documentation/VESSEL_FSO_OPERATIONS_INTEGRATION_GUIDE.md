# VESSEL & FSO OPERATIONS - INTEGRATION GUIDE
## Step-by-Step Implementation (Phase 1)

**Version:** 1.0  
**Date:** December 14, 2025  
**Estimated Time:** 2-3 hours  
**Status:** Ready for Implementation

---

## Quick Summary

This guide provides copy-paste steps to integrate the new FastAPI + React Vessel and FSO Operations endpoints into your existing OTMS project.

**What's Included:**
- ✅ Backend validators (vessel_validators.py, fso_validators.py) - 1,200+ lines
- ✅ FastAPI routers (vessel_operations.py, fso_operations.py) - 900+ lines
- ✅ Design documentation with architecture and workflows
- ⏳ Frontend components (React/TypeScript) - Next phase
- ⏳ API client functions (api.ts updates) - Next phase

**Key Architecture:**
- Backend: FastAPI endpoints with Pydantic validation
- Validators: Comprehensive business logic validation
- Database: OTRVessel and FSOOperation models (already exist)
- Frontend: React components (to be created next phase)

---

## Step 1: Copy Validator Files

### Files to Copy

Copy these two files to your project:

**From:** Project repo validators folder  
**To:** `otms_api/validators/`

1. **`vessel_validators.py`** (550 lines)
   - VesselOperationEntryRequest (Pydantic model)
   - VesselOperationValidationResponse (response model)
   - validate_vessel_operation_entry() (main validation function)
   - validate_batch_entries() (batch validation)
   - compute_workflow_status() (quality metrics)

2. **`fso_validators.py`** (600 lines)
   - FSOOperationEntryRequest (Pydantic model)
   - FSOOperationValidationResponse (response model)
   - MaterialBalancePeriod (model for MB calculation)
   - validate_fso_operation_entry() (main validation)
   - calculate_material_balance_period() (MB calculation)
   - validate_material_balance() (quality check)
   - analyze_fso_reconciliation() (FSO vs vessel analysis)

### Verification

After copying, verify imports work:

```bash
# In project root
python -c "from otms_api.validators.vessel_validators import validate_vessel_operation_entry; print('✓ Vessel validators imported')"
python -c "from otms_api.validators.fso_validators import validate_fso_operation_entry; print('✓ FSO validators imported')"
```

---

## Step 2: Create Backend Routers

Copy these two files to your project:

**From:** Project repo routers folder  
**To:** `otms_api/routers/`

1. **`vessel_operations.py`** (400+ lines)
   - GET /vessel-operations/list
   - GET /vessel-operations/{id}
   - POST /vessel-operations (create)
   - PUT /vessel-operations/{id} (update)
   - DELETE /vessel-operations/{id}
   - POST /vessel-operations/validate
   - GET /vessel-operations/status/summary

2. **`fso_operations.py`** (500+ lines)
   - GET /fso-operations/list
   - GET /fso-operations/{id}
   - POST /fso-operations (create)
   - PUT /fso-operations/{id}
   - DELETE /fso-operations/{id}
   - POST /fso-operations/validate
   - GET /fso-operations/material-balance
   - GET /fso-operations/material-balance/validate
   - GET /fso-operations/reconciliation

---

## Step 3: Register Routers in FastAPI

### Update `otms_api/__init__.py` or Main Router File

Find where other routers are registered and add these lines:

```python
# In your main FastAPI app initialization file

from otms_api.routers import vessel_operations, fso_operations

app.include_router(vessel_operations.router)
app.include_router(fso_operations.router)
```

### Example Location

If your code looks like this:

```python
# otms_api/main.py or app.py
from fastapi import FastAPI
from otms_api.routers import yade_transactions, tanker_transactions

app = FastAPI()
app.include_router(yade_transactions.router)
app.include_router(tanker_transactions.router)
```

Add to it:

```python
from otms_api.routers import (
    yade_transactions,
    tanker_transactions,
    vessel_operations,  # ← NEW
    fso_operations     # ← NEW
)

app.include_router(yade_transactions.router)
app.include_router(tanker_transactions.router)
app.include_router(vessel_operations.router)  # ← NEW
app.include_router(fso_operations.router)     # ← NEW
```

### Verification

Test that routers are registered:

```bash
# Start API server
python run_api.py

# In another terminal, test endpoint
curl http://localhost:8000/api/vessel-operations/list?location_id=1&limit=10
# Should return { "total": X, "entries": [...] }
```

---

## Step 4: Test Backend Endpoints

### Using cURL

```bash
# 1. List Vessel Operations
curl -X GET "http://localhost:8000/api/vessel-operations/list?location_id=1&limit=10" \
  -H "Authorization: Bearer YOUR_TOKEN"

# 2. Validate a Vessel Operation Entry (preview)
curl -X POST "http://localhost:8000/api/vessel-operations/validate?location_id=1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "date": "2025-12-14",
    "time": "14:30",
    "shuttle_no": "SH-001",
    "vessel_id": 5,
    "operation_id": 2,
    "opening_stock": 1000.0,
    "opening_water": 50.0,
    "closing_stock": 1250.0,
    "closing_water": 62.5,
    "remarks": "Test entry"
  }'

# 3. Create a Vessel Operation Entry
curl -X POST "http://localhost:8000/api/vessel-operations?location_id=1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "date": "2025-12-14",
    "time": "14:30",
    "shuttle_no": "SH-001",
    "vessel_id": 5,
    "operation_id": 2,
    "opening_stock": 1000.0,
    "opening_water": 50.0,
    "closing_stock": 1250.0,
    "closing_water": 62.5,
    "remarks": "Test entry"
  }'

# 4. Get Workflow Status
curl -X GET "http://localhost:8000/api/vessel-operations/status/summary?location_id=1&date_from=2025-12-01&date_to=2025-12-14" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Using Postman

1. Import collection (create new):
   - Name: Vessel & FSO Operations
   - Base URL: `http://localhost:8000/api`

2. Create requests:

| Method | URL | Query Params |
|--------|-----|--------------|
| GET | /vessel-operations/list | location_id=1&limit=10 |
| POST | /vessel-operations/validate | location_id=1 |
| POST | /vessel-operations | location_id=1 |
| GET | /fso-operations/list | location_id=2&fso_vessel=MT%20TULJA%20TANVI |
| POST | /fso-operations/validate | location_id=2 |

---

## Step 5: API Client Functions (Next Phase)

These functions will be added to `frontend/src/api.ts` in the next phase:

```typescript
// Vessel Operations
export async function listVesselOperations(
  locationId: number,
  dateFrom?: string,
  dateTo?: string,
  limit = 100,
  offset = 0
): Promise<VesselOperation[]> {
  const params = new URLSearchParams({
    location_id: locationId.toString(),
    limit: limit.toString(),
    offset: offset.toString(),
  });
  if (dateFrom) params.append('date_from', dateFrom);
  if (dateTo) params.append('date_to', dateTo);
  
  const res = await fetch(`/api/vessel-operations/list?${params}`, {
    headers: { 'Authorization': `Bearer ${getToken()}` }
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  const data = await res.json();
  return data.entries;
}

export async function validateVesselOperation(
  locationId: number,
  entry: VesselOperationEntry
): Promise<ValidationResponse> {
  const res = await fetch(`/api/vessel-operations/validate?location_id=${locationId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${getToken()}`
    },
    body: JSON.stringify(entry)
  });
  if (!res.ok) throw new Error(`Validation failed: ${res.status}`);
  return await res.json();
}

export async function createVesselOperation(
  locationId: number,
  entry: VesselOperationEntry
): Promise<VesselOperation> {
  const res = await fetch(`/api/vessel-operations?location_id=${locationId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${getToken()}`
    },
    body: JSON.stringify(entry)
  });
  if (!res.ok) throw new Error(`Create failed: ${res.status}`);
  return await res.json();
}

// Similar functions for FSO Operations...
```

---

## Step 6: Testing Checklist

### Backend Testing

- [ ] All validator functions work with valid input
- [ ] All validator functions return errors for invalid input
- [ ] All endpoints accessible via API
- [ ] Endpoints require authentication
- [ ] Endpoints check location access
- [ ] Create endpoints generate audit logs
- [ ] Delete endpoints move to recycle bin
- [ ] List endpoints support filtering
- [ ] Pagination works (limit, offset)

### Unit Test Example

```python
# tests/test_vessel_validators.py
import pytest
from datetime import date
from otms_api.validators.vessel_validators import (
    validate_vessel_operation_entry,
    VesselOperationEntryRequest
)

def test_validate_valid_entry():
    entry = VesselOperationEntryRequest(
        date=date(2025, 12, 14),
        time="14:30",
        shuttle_no="SH-001",
        vessel_id=5,
        operation_id=2,
        opening_stock=1000.0,
        opening_water=50.0,
        closing_stock=1250.0,
        closing_water=62.5
    )
    vessel_dict = {5: "MT Vessel A"}
    operation_dict = {2: "Loading"}
    
    result = validate_vessel_operation_entry(entry, vessel_dict, operation_dict, 1)
    
    assert result.is_valid is True
    assert result.can_save is True
    assert len(result.errors) == 0
    assert result.calculation.net_receipt_dispatch == 250.0

def test_validate_negative_stock():
    entry = VesselOperationEntryRequest(
        date=date(2025, 12, 14),
        time="14:30",
        shuttle_no="SH-001",
        vessel_id=5,
        operation_id=2,
        opening_stock=-100.0,  # Invalid
        opening_water=50.0,
        closing_stock=1250.0,
        closing_water=62.5
    )
    vessel_dict = {5: "MT Vessel A"}
    operation_dict = {2: "Loading"}
    
    result = validate_vessel_operation_entry(entry, vessel_dict, operation_dict, 1)
    
    assert result.is_valid is False
    assert len(result.errors) > 0
    assert any("negative" in e.message.lower() for e in result.errors)

# Run: pytest tests/test_vessel_validators.py -v
```

---

## Step 7: Database Verification

Ensure these tables exist:

### OTRVessel Table
```sql
-- Check if table exists and has all required fields
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'otr_vessel'
ORDER BY ordinal_position;

-- Expected columns:
-- id (INT PRIMARY KEY)
-- location_id (INT)
-- date (DATE)
-- time (VARCHAR)
-- shuttle_no (VARCHAR)
-- vessel_id (INT)
-- operation_id (INT)
-- opening_stock, opening_water, closing_stock, closing_water (FLOAT)
-- net_receipt_dispatch, net_water (FLOAT)
-- remarks (VARCHAR)
-- created_by, created_at, updated_by, updated_at (timestamps)
```

### FSOOperation Table
```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'fso_operations'
ORDER BY ordinal_position;

-- Expected: Same as OTRVessel + fso_vessel, vessel_quantity, variance fields
```

---

## Step 8: Troubleshooting

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'otms_api.validators.vessel_validators'`

**Solution:**
1. Ensure files are in `otms_api/validators/` directory
2. Check `otms_api/validators/__init__.py` exists (create if missing)
3. Restart FastAPI server
4. Check Python path includes project root

### Permission Errors

**Problem:** `HTTPException 403: Not authorized`

**Solution:**
1. Verify user has `can_make_entries` permission
2. Check PermissionManager configuration
3. Verify location assignment
4. Check role in database

### Validation Errors

**Problem:** All entries fail validation

**Solution:**
1. Ensure vessel_dict and operation_dict are populated
2. Check that vessel_id/operation_id exist in database
3. Review validation error messages for specific field issues

### Database Connection

**Problem:** `Connection refused` or `Database locked`

**Solution:**
1. Verify database is running
2. Check connection string in config
3. Run migrations if needed
4. Check for locks: `PRAGMA integrity_check;`

---

## Next Phase: Frontend Components

After backend is working, we'll create:

### VesselOperations.tsx (600+ lines)
- Filter section (dates, shuttle, vessel, operation)
- Create form modal with validation
- Entries table with pagination
- Edit/delete functionality
- Export buttons (CSV/Excel/PDF)

### FSOOperations.tsx (800+ lines)
- FSO vessel selector
- Dual tabs: OTR | Material Balance
- OTR form (same as Vessel Ops + vessel_quantity)
- Material Balance table + charts
- Reconciliation panel

### API Client Updates
- listVesselOperations()
- validateVesselOperation()
- createVesselOperation()
- updateVesselOperation()
- deleteVesselOperation()
- (same for FSO operations)

---

## Completion Checklist

- [ ] Copy vessel_validators.py to otms_api/validators/
- [ ] Copy fso_validators.py to otms_api/validators/
- [ ] Copy vessel_operations.py to otms_api/routers/
- [ ] Copy fso_operations.py to otms_api/routers/
- [ ] Register routers in main FastAPI app
- [ ] Verify imports work (run python -c tests)
- [ ] Test endpoints with cURL/Postman
- [ ] Verify database tables exist
- [ ] Check audit logging works
- [ ] Run unit tests for validators
- [ ] Document any custom modifications
- [ ] Ready for Phase 2 (Frontend components)

---

## Support & Questions

**Common Issues:**
- Router not found: Check registration in main app file
- Validation always fails: Debug vessel_dict/operation_dict population
- Permission errors: Check user role and location assignment
- Time parsing errors: Ensure HH:MM format (24-hour)

**Testing Workflow:**
1. Start FastAPI server: `python run_api.py`
2. Open Postman or curl terminal
3. Create test entry: POST /vessel-operations
4. Check response for id and calculated values
5. List entries: GET /vessel-operations/list
6. Verify data persisted in database

---

**End of Integration Guide**
