# VESSEL & FSO OPERATIONS - QUICK REFERENCE CARD
**One-page cheat sheet for developers**

---

## File Locations

| Component | Path | Lines |
|-----------|------|-------|
| Vessel Validators | `otms_api/validators/vessel_validators.py` | 550 |
| FSO Validators | `otms_api/validators/fso_validators.py` | 600 |
| Vessel Router | `otms_api/routers/vessel_operations.py` | 400 |
| FSO Router | `otms_api/routers/fso_operations.py` | 500 |

---

## Vessel Operations API

### List Entries
```
GET /api/vessel-operations/list
  ?location_id=1
  &date_from=2025-12-01
  &date_to=2025-12-14
  &shuttle_no=SH-001
  &limit=100&offset=0
```

### Create Entry
```
POST /api/vessel-operations?location_id=1
{
  "date": "2025-12-14",
  "time": "14:30",
  "shuttle_no": "SH-001",
  "vessel_id": 5,
  "operation_id": 2,
  "opening_stock": 1000.0,
  "opening_water": 50.0,
  "closing_stock": 1250.0,
  "closing_water": 62.5,
  "remarks": "notes"
}
```

### Validate (Preview)
```
POST /api/vessel-operations/validate?location_id=1
{ ...same body as create... }

Response:
{
  "is_valid": true,
  "errors": [],
  "warnings": [],
  "calculation": {
    "net_receipt_dispatch": 250.0,
    "net_water": 12.5,
    "water_percentage": 5.0
  }
}
```

### Update Entry
```
PUT /api/vessel-operations/{id}
{ ...same body as create... }
```

### Get Status
```
GET /api/vessel-operations/status/summary
  ?location_id=1
  &date_from=2025-12-01
  &date_to=2025-12-14

Response:
{
  "total_entries": 45,
  "by_vessel": {"MT A": 20, "MT B": 25},
  "total_stock": 5000.0,
  "data_quality_score": 92
}
```

---

## FSO Operations API

### List OTR Entries
```
GET /api/fso-operations/list
  ?location_id=2
  &fso_vessel=MT%20TULJA%20TANVI
  &date_from=2025-12-01
```

### Create OTR Entry
```
POST /api/fso-operations?location_id=2
{
  "fso_vessel": "MT TULJA TANVI",
  "date": "2025-12-14",
  "time": "14:30",
  "shuttle_no": "SH-020",
  "vessel_name": "MT XYZ",
  "operation": "Receipt",
  "opening_stock": 500.0,
  "closing_stock": 1200.0,
  "vessel_quantity": 695.0,
  "remarks": "notes"
}
```

### Get Material Balance
```
GET /api/fso-operations/material-balance
  ?location_id=2
  &fso_vessel=MT%20TULJA%20TANVI
  &date_from=2025-12-01

Response:
{
  "periods": [
    {
      "period_date": "2025-12-10",
      "opening_stock": 500.0,
      "receipts": 2400.0,
      "exports": 1500.0,
      "closing_stock": 1400.0,
      "loss_gain": 0.0
    }
  ]
}
```

### Validate Material Balance
```
GET /api/fso-operations/material-balance/validate
  ?location_id=2&fso_vessel=...

Response:
{
  "is_valid": true,
  "loss_gain_pct": 0.02,
  "warnings": []
}
```

### Get Reconciliation
```
GET /api/fso-operations/reconciliation
  ?location_id=2&fso_vessel=...&date=2025-12-14

Response:
{
  "fso_closing": 2300.0,
  "vessel_quantity": 2285.0,
  "variance": 15.0,
  "variance_pct": 0.66,
  "status": "MATCHED"
}
```

---

## Validation Rules

### Vessel Operations

| Field | Rule | Error | Warning |
|-------|------|-------|---------|
| date | ≤ today | ❌ | - |
| time | HH:MM format | ❌ | - |
| shuttle_no | Required | ❌ | - |
| vessel_id | Must exist | ❌ | - |
| opening_stock | ≥ 0 | ❌ | - |
| closing_water | ≤ closing_stock | - | ⚠️ |
| water % | > 50% | - | ⚠️ |
| Loading | net > 0 | - | ⚠️ |
| Discharging | net < 0 | - | ⚠️ |

### FSO Operations

| Field | Rule | Error | Warning |
|-------|------|-------|---------|
| fso_vessel | Assigned to location | ❌ | - |
| operation | Receipt\|Export\|Opening | ❌ | - |
| vessel_quantity | Variance > 2% | - | ⚠️ |
| Loss/Gain % | > 2% | - | ⚠️ Major |
| Loss/Gain % | 0.5-2% | - | ⚠️ Minor |

---

## Key Functions

### vessel_validators.py
```python
validate_vessel_operation_entry(entry, vessel_dict, operation_dict, location_id)
  → VesselOperationValidationResponse

validate_batch_entries(entries, vessel_dict, operation_dict, location_id)
  → BatchValidationResponse

compute_workflow_status(entries, location_id, vessel_dict, operation_dict, date_from, date_to)
  → VesselOperationWorkflowStatus
```

### fso_validators.py
```python
validate_fso_operation_entry(entry, location_id, valid_fsos, valid_operations)
  → FSOOperationValidationResponse

calculate_material_balance_period(period_entries, period_date, fso_vessel, location_id)
  → MaterialBalancePeriod

validate_material_balance(periods)
  → MaterialBalanceValidationResponse

analyze_fso_reconciliation(fso_closing, vessel_quantity)
  → ReconciliationResult
```

---

## Calculations

### Vessel Operations
```
Net Receipt/Dispatch = Closing Stock - Opening Stock
Net Water = Closing Water - Opening Water
Water % = (Closing Water / Closing Stock) * 100 [capped 100%]
Quality Score = 100 - penalties + bonuses
```

### FSO Operations (OTR)
```
Variance = Closing Stock - Vessel Quantity
Variance % = (Variance / Vessel Quantity) * 100
```

### FSO Material Balance
```
Loss/Gain = Opening + Receipts - Exports - Closing
Loss/Gain % = |Loss/Gain| / Average Stock * 100
Status:
  < 0.5%  → MATCHED
  0.5-2%  → MINOR_VARIANCE
  > 2%    → MAJOR_VARIANCE
```

---

## Database Queries

### Get All Vessel Operations for Location
```sql
SELECT * FROM otr_vessel 
WHERE location_id = ? 
ORDER BY date DESC, time DESC;
```

### Get FSO Operations by Vessel
```sql
SELECT * FROM fso_operations
WHERE location_id = ? AND fso_vessel = ?
ORDER BY date DESC, time DESC;
```

### Get Material Balance for Period
```sql
SELECT * FROM fso_mb_table
WHERE location_id = ? AND fso_vessel = ?
AND date BETWEEN ? AND ?
ORDER BY date;
```

---

## Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| Module not found | Router not registered | Add `app.include_router()` |
| 403 Forbidden | Location access denied | Check `require_location_access()` |
| 422 Validation | Invalid entry data | Check validation response errors |
| 404 Not found | Entry doesn't exist | Verify ID in database |
| Time parsing error | Wrong HH:MM format | Use 24-hour format (00:00-23:59) |
| Vessel not found | vessel_id doesn't exist | Check vessels table |
| FSO not assigned | FSO not assigned to location | Check LocationVessel table |

---

## Testing Examples

### cURL: List Vessel Operations
```bash
curl -X GET \
  "http://localhost:8000/api/vessel-operations/list?location_id=1&limit=10" \
  -H "Authorization: Bearer TOKEN"
```

### cURL: Create Vessel Entry
```bash
curl -X POST \
  "http://localhost:8000/api/vessel-operations?location_id=1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
  -d '{
    "date": "2025-12-14",
    "time": "14:30",
    "shuttle_no": "SH-001",
    "vessel_id": 5,
    "operation_id": 2,
    "opening_stock": 1000.0,
    "opening_water": 50.0,
    "closing_stock": 1250.0,
    "closing_water": 62.5
  }'
```

### Python: Validate Entry
```python
from otms_api.validators.vessel_validators import validate_vessel_operation_entry

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

result = validate_vessel_operation_entry(
    entry,
    vessel_dict={5: "MT Vessel A"},
    operation_dict={2: "Loading"},
    location_id=1
)

if result.is_valid:
    print("✓ Valid entry")
    print(f"Net: {result.calculation.net_receipt_dispatch}")
else:
    print("✗ Validation errors:")
    for error in result.errors:
        print(f"  - {error.field}: {error.message}")
```

---

## Pydantic Models Quick Reference

### VesselOperationEntryRequest
```python
date: date              # YYYY-MM-DD, ≤ today
time: str              # HH:MM format
shuttle_no: str        # Required, non-empty
vessel_id: int         # Must exist
operation_id: int      # Must exist
opening_stock: float   # ≥ 0
opening_water: float   # ≥ 0
closing_stock: float   # ≥ 0
closing_water: float   # ≥ 0
remarks: Optional[str] # Max 500 chars
```

### FSOOperationEntryRequest
```python
fso_vessel: str        # Must be assigned
date: date             # YYYY-MM-DD, ≤ today
time: str              # HH:MM format
shuttle_no: str        # Required
vessel_name: str       # Required
operation: str         # Receipt|Export|Stock Opening
opening_stock: float   # ≥ 0
opening_water: float   # ≥ 0
closing_stock: float   # ≥ 0
closing_water: float   # ≥ 0
vessel_quantity: Optional[float]  # For reconciliation
remarks: Optional[str] # Max 500 chars
```

---

## Integration Checklist

- [ ] Copy validators to `otms_api/validators/`
- [ ] Copy routers to `otms_api/routers/`
- [ ] Register routers in main app
- [ ] Test endpoints with cURL
- [ ] Verify database tables
- [ ] Run unit tests
- [ ] Check audit logging
- [ ] Deploy to staging
- [ ] UAT testing
- [ ] Deploy to production

---

## Documentation References

| Document | Purpose |
|----------|---------|
| `VESSEL_FSO_OPERATIONS_DESIGN.md` | Full architecture & design |
| `VESSEL_FSO_OPERATIONS_INTEGRATION_GUIDE.md` | Step-by-step integration |
| `PROJECT_STATUS_VESSEL_FSO_PHASE1.md` | Project status & metrics |
| `vessel_validators.py` | Validation logic source |
| `fso_validators.py` | FSO validation source |
| `vessel_operations.py` | Router source code |
| `fso_operations.py` | FSO router source code |

---

**Print this card and keep it at your desk while integrating! 🚀**
