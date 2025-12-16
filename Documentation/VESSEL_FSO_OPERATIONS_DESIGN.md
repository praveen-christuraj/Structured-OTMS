# VESSEL OPERATIONS & FSO OPERATIONS
## FastAPI + React/TypeScript Implementation Guide

**Version:** 1.0  
**Date:** December 14, 2025  
**Architecture:** FastAPI (Python) + React (TypeScript) + SQLAlchemy ORM  
**Status:** Phase 1 Design & Implementation Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Vessel Operations Architecture](#vessel-operations-architecture)
3. [FSO Operations Architecture](#fso-operations-architecture)
4. [Database Models](#database-models)
5. [API Specifications](#api-specifications)
6. [Frontend Components](#frontend-components)
7. [Validation Rules](#validation-rules)
8. [Integration Checklist](#integration-checklist)
9. [Testing Strategy](#testing-strategy)

---

## Overview

### Purpose
Migrate legacy Streamlit pages (vessel_operations.py, fso_operations.py) to modern FastAPI + React/TypeScript architecture for:
- **Better UI/UX**: Responsive, real-time validation, instant feedback
- **Scalability**: API-first architecture supports future mobile apps, integrations
- **Maintainability**: Separated concerns (backend validation, frontend presentation)
- **Performance**: Async operations, optimized queries, caching

### Key Differences from Streamlit
| Aspect | Streamlit | FastAPI + React |
|--------|-----------|-----------------|
| Validation | Inline in UI | Server-side + Client preview |
| State Management | Session state | React hooks + API responses |
| Real-time Feedback | Page rerun | Live validation on field change |
| Exports | Button click | API endpoint with streaming |
| Data Refresh | Button click | Auto-refresh or manual trigger |

---

## Vessel Operations Architecture

### Current State (Streamlit)
- **File**: `app_pages/vessel_operations.py` (744 lines)
- **Model**: `OTRVessel` (location_id, date, time, shuttle_no, vessel_id, operation_id, stocks, water)
- **Workflow**:
  1. User selects location
  2. Filters by date range, shuttle, vessel, operation
  3. Creates/edits entries with inline validation
  4. Views list with pagination
  5. Exports to CSV/Excel/PDF
- **Database**: OTRVessel table with audit fields (created_by, created_at, updated_by, updated_at)

### Target State (FastAPI + React)
- **Backend**: `otms_api/routers/vessel_operations.py` (new)
- **Frontend**: `frontend/src/VesselOperations.tsx` (new)
- **Validators**: `otms_api/validators/vessel_validators.py` (created)
- **Workflow**:
  1. API: GET /vessel-operations/list → filter + paginate
  2. API: GET /vessel-operations/{id} → detail
  3. API: POST /vessel-operations → create with validation
  4. API: PUT /vessel-operations/{id} → update
  5. API: DELETE /vessel-operations/{id} → soft delete to recycle bin
  6. API: GET /vessel-operations/export → CSV/Excel/PDF streaming
  7. Frontend: Real-time validation, instant error messages, auto-calculations

### Data Flow

```
React Component (VesselOperations.tsx)
    ↓
Form Input (date, time, shuttle, vessel, operation, stocks, water)
    ↓ onChange event
Client-side Preview Calculation (net stock, net water, water %)
    ↓ onSubmit
POST /vessel-operations/validate (optional)
    ↓
Server Validation (vessel_validators.py)
    ↓ Response: errors[], warnings[], calculation
React: Display errors/warnings with suggestions
    ↓ User confirms
POST /vessel-operations (or PUT for edit)
    ↓
Server: Create/Update OTRVessel
    ↓ Response: { id, ...entry }
React: Success toast, refresh list
    ↓
GET /vessel-operations/list (refetch)
    ↓
UI: Updated table with new entry
```

### Key Features
1. **Real-time Validation**
   - Water ≤ Stock per field
   - Negative value checks
   - Time format HH:MM
   - Date ≤ Today

2. **Automatic Calculations**
   - Net Receipt/Dispatch = Closing - Opening
   - Net Water = Closing Water - Opening Water
   - Water % = (Closing Water / Closing Stock) * 100

3. **Operation-Aware Warnings**
   - Loading op with negative net → warning
   - Discharging op with positive net → warning
   - Water > 50% of stock → warning

4. **List Filtering**
   - Date range (from/to)
   - Shuttle number (contains)
   - Vessel (dropdown)
   - Operation (dropdown)

5. **Exports**
   - CSV (OpenPyXL)
   - Excel (.xlsx)
   - PDF (ReportLab, landscape A4)

---

## FSO Operations Architecture

### Current State (Streamlit)
- **File**: `app_pages/fso_operations.py` (2264 lines)
- **Model**: `FSOOperation` (FSO-specific location, fso_vessel, OTR fields, variance, vessel_quantity)
- **Workflow**:
  1. User selects FSO vessel assigned to location
  2. Filters OTR by date range, shuttle, vessel, operation
  3. Creates/edits OTR entries
  4. Triggers auto-calculation of Material Balance (06:01-06:00 periods)
  5. Displays loss/gain analysis with charts
  6. Exports to CSV/Excel/PDF
- **Features**:
  - Out-Turn Report (OTR): Daily vessel operations
  - Material Balance: 06:01-06:00 closing periods with loss/gain
  - Reconciliation: FSO stock vs vessel declaration
  - Charts: Trends, receipts/exports, loss/gain

### Target State (FastAPI + React)
- **Backend**: `otms_api/routers/fso_operations.py` (new)
- **Frontend**: `frontend/src/FSOOperations.tsx` (new)
- **Validators**: `otms_api/validators/fso_validators.py` (created)
- **Workflow**:
  1. API: GET /fso-operations/list → OTR entries
  2. API: POST /fso-operations → create OTR entry
  3. API: PUT /fso-operations/{id} → update OTR entry
  4. API: GET /fso-operations/material-balance → auto-calculated periods
  5. API: GET /fso-operations/material-balance/validate → MB quality analysis
  6. API: GET /fso-operations/reconciliation → FSO vs vessel variance
  7. Frontend: Dual-tab UI (OTR | Material Balance) with live charts

### Material Balance Calculation

**Period Definition**: 06:01 of date N to 06:00 of date N+1

**Entries Included**:
- Sort all entries by date+time
- Filter entries within 06:01-06:00 window
- Use datetime.combine(entry.date, entry.time)

**Calculation**:
```
Opening Stock = first entry.opening_stock at 06:01
Receipts = sum of net +values for "Receipt" operations
Exports = sum of |net -values| for "Export" operations
Closing Stock = last entry.closing_stock at 06:00
Loss/Gain = Opening + Receipts - Exports - Closing
```

**Quality Metrics**:
- Loss/Gain % = |Loss/Gain| / Average Stock * 100
- Status: Balanced (<0.5%), Minor (<2%), Major (>2%)

### Key Features

1. **Out-Turn Report (Tab 1)**
   - Same as Vessel Ops + vessel_quantity field
   - Variance = closing_stock - vessel_quantity
   - Variance % for reconciliation

2. **Material Balance (Tab 2)**
   - Auto-group entries by 06:01-06:00 periods
   - Table: Date, Opening, Receipts, Exports, Closing, Loss/Gain
   - Charts: 
     - Trend: Opening/Closing over time (line)
     - Receipts/Exports (bar, grouped)
     - Loss/Gain (bar, red=loss, green=gain)

3. **Reconciliation Analysis**
   - FSO closing vs vessel quantity
   - Variance in bbls and %
   - Status color coding (green=matched, yellow=minor, red=major)

4. **Data Quality Score**
   - Based on complete entries, valid vessels, consistent data
   - Deduction for missing operations, high variance entries
   - Bonus for good period coverage

---

## Database Models

### OTRVessel (Vessel Operations)

```sql
CREATE TABLE otr_vessel (
    id INTEGER PRIMARY KEY,
    location_id INTEGER NOT NULL REFERENCES locations(id),
    date DATE NOT NULL,
    time VARCHAR(5) NOT NULL,  -- HH:MM format
    shuttle_no VARCHAR(50) NOT NULL,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id),
    operation_id INTEGER NOT NULL REFERENCES vessel_operations(id),
    
    -- Stock values (bbls)
    opening_stock FLOAT NOT NULL DEFAULT 0,
    opening_water FLOAT NOT NULL DEFAULT 0,
    closing_stock FLOAT NOT NULL DEFAULT 0,
    closing_water FLOAT NOT NULL DEFAULT 0,
    net_receipt_dispatch FLOAT NOT NULL DEFAULT 0,
    net_water FLOAT NOT NULL DEFAULT 0,
    
    remarks VARCHAR(500),
    created_by VARCHAR(100),
    created_at DATETIME,
    updated_by VARCHAR(100),
    updated_at DATETIME
);

CREATE INDEX idx_otr_vessel_location_date ON otr_vessel(location_id, date);
CREATE INDEX idx_otr_vessel_shuttle ON otr_vessel(shuttle_no);
```

### FSOOperation (FSO Out-Turn Report)

```sql
CREATE TABLE fso_operations (
    id INTEGER PRIMARY KEY,
    location_id INTEGER NOT NULL REFERENCES locations(id),
    fso_vessel VARCHAR(50) NOT NULL,  -- e.g., "MT TULJA TANVI"
    date DATE NOT NULL,
    time TIME NOT NULL,
    shuttle_no VARCHAR(50) NOT NULL,
    vessel_name VARCHAR(100) NOT NULL,
    operation VARCHAR(50) NOT NULL,  -- Receipt, Export, Stock Opening
    
    -- Stock values (bbls)
    opening_stock FLOAT NOT NULL,
    opening_water FLOAT NOT NULL DEFAULT 0,
    closing_stock FLOAT NOT NULL,
    closing_water FLOAT NOT NULL DEFAULT 0,
    net_receipt_dispatch FLOAT NOT NULL,
    net_water FLOAT NOT NULL DEFAULT 0,
    
    -- Reconciliation
    vessel_quantity FLOAT,  -- Vessel declared quantity
    variance FLOAT,  -- closing_stock - vessel_quantity
    
    remarks TEXT,
    created_by VARCHAR(50) NOT NULL,
    created_at DATETIME,
    updated_by VARCHAR(50),
    updated_at DATETIME
);

CREATE INDEX idx_fso_ops_location_vessel_date ON fso_operations(location_id, fso_vessel, date);
```

### FSOMaterialBalance (Material Balance Snapshots)

```sql
CREATE TABLE fso_mb_table (
    id INTEGER PRIMARY KEY,
    location_id INTEGER NOT NULL REFERENCES locations(id),
    fso_vessel VARCHAR(50) NOT NULL,
    date DATE NOT NULL,  -- Period start date (06:01)
    
    opening_stock FLOAT NOT NULL DEFAULT 0,
    opening_water FLOAT NOT NULL DEFAULT 0,
    receipts FLOAT NOT NULL DEFAULT 0,
    exports FLOAT NOT NULL DEFAULT 0,
    closing_stock FLOAT NOT NULL DEFAULT 0,
    closing_water FLOAT NOT NULL DEFAULT 0,
    loss_gain FLOAT NOT NULL DEFAULT 0,
    
    created_by VARCHAR(64),
    created_at DATETIME,
    updated_by VARCHAR(64),
    updated_at DATETIME
);

CREATE UNIQUE INDEX idx_fso_mb_unique ON fso_mb_table(location_id, fso_vessel, date);
```

---

## API Specifications

### Vessel Operations Endpoints

#### 1. List Entries
```
GET /api/vessel-operations
Query Params:
  - location_id: int
  - date_from: YYYY-MM-DD (optional)
  - date_to: YYYY-MM-DD (optional)
  - shuttle_no: string (optional, contains filter)
  - vessel_id: int (optional)
  - operation_id: int (optional)
  - limit: int (default 100, max 1000)
  - offset: int (default 0)

Response 200:
{
  "total": 245,
  "limit": 100,
  "offset": 0,
  "entries": [
    {
      "id": 101,
      "location_id": 1,
      "date": "2025-12-10",
      "time": "14:30",
      "shuttle_no": "SH-001",
      "vessel_id": 5,
      "vessel_name": "MT Vessel A",
      "operation_id": 2,
      "operation_name": "Loading",
      "opening_stock": 1000.0,
      "opening_water": 50.0,
      "closing_stock": 1250.0,
      "closing_water": 62.5,
      "net_receipt_dispatch": 250.0,
      "net_water": 12.5,
      "remarks": "Normal operations",
      "created_by": "operator1",
      "created_at": "2025-12-10T15:00:00Z"
    },
    ...
  ]
}
```

#### 2. Get Detail
```
GET /api/vessel-operations/{id}

Response 200:
{ ...same as list entry... }

Response 404:
{ "detail": "Entry not found" }
```

#### 3. Create Entry
```
POST /api/vessel-operations
Content-Type: application/json

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
  "remarks": "Normal load"
}

Response 201:
{
  "id": 245,
  "location_id": 1,
  ...entry details...
}

Response 422:
{
  "detail": [
    {
      "loc": ["body", "time"],
      "msg": "Time must be in HH:MM format",
      "type": "value_error"
    }
  ]
}
```

#### 4. Validate Entry (Preview)
```
POST /api/vessel-operations/validate
Content-Type: application/json

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
  "remarks": null
}

Response 200:
{
  "is_valid": true,
  "can_save": true,
  "errors": [],
  "warnings": [],
  "calculation": {
    "opening_stock": 1000.0,
    "closing_stock": 1250.0,
    "net_receipt_dispatch": 250.0,
    "opening_water": 50.0,
    "closing_water": 62.5,
    "net_water": 12.5,
    "water_percentage": 5.0
  },
  "messages": [
    "Validation Summary:",
    "✓ Vessel: MT Vessel A",
    "✓ Operation: Loading",
    "✓ Time: 14:30",
    "✓ Shuttle: SH-001"
  ]
}
```

#### 5. Update Entry
```
PUT /api/vessel-operations/{id}
Content-Type: application/json

{ ...same fields as create... }

Response 200:
{ ...updated entry... }

Response 404:
{ "detail": "Entry not found" }
```

#### 6. Delete Entry
```
DELETE /api/vessel-operations/{id}

Response 204:
(No content)

Response 404:
{ "detail": "Entry not found" }
```

#### 7. Export Data
```
GET /api/vessel-operations/export
Query Params:
  - location_id: int
  - date_from: YYYY-MM-DD
  - date_to: YYYY-MM-DD
  - format: csv | excel | pdf (default: csv)

Response 200:
Content-Type: text/csv (or application/vnd.ms-excel, application/pdf)
Content-Disposition: attachment; filename="vessel_ops_2025-12-14.csv"

{CSV/Excel/PDF data}
```

#### 8. Workflow Status
```
GET /api/vessel-operations/status
Query Params:
  - location_id: int
  - date_from: YYYY-MM-DD
  - date_to: YYYY-MM-DD

Response 200:
{
  "location_id": 1,
  "date_range": "2025-12-01 to 2025-12-14",
  "total_entries": 45,
  "by_vessel": {
    "MT Vessel A": 20,
    "MT Vessel B": 25
  },
  "by_operation": {
    "Loading": 30,
    "Discharging": 15
  },
  "total_stock": 5000.0,
  "total_water": 250.0,
  "average_water_pct": 4.5,
  "date_coverage": 85.7,
  "data_quality_score": 92
}
```

---

### FSO Operations Endpoints

#### 1. List OTR Entries
```
GET /api/fso-operations
Query Params:
  - location_id: int
  - fso_vessel: string
  - date_from: YYYY-MM-DD (optional)
  - date_to: YYYY-MM-DD (optional)
  - shuttle_no: string (optional)
  - operation: string (optional)
  - limit: int (default 100)
  - offset: int (default 0)

Response 200:
{
  "total": 156,
  "entries": [
    {
      "id": 51,
      "location_id": 2,
      "fso_vessel": "MT TULJA TANVI",
      "date": "2025-12-10",
      "time": "14:30:00",
      "shuttle_no": "SH-015",
      "vessel_name": "MT ABC-100",
      "operation": "Receipt",
      "opening_stock": 500.0,
      "closing_stock": 1200.0,
      "net_receipt_dispatch": 700.0,
      "vessel_quantity": 695.0,
      "variance": 5.0,
      "variance_pct": 0.72,
      "remarks": null,
      "created_by": "operator1",
      "created_at": "2025-12-10T15:00:00Z"
    },
    ...
  ]
}
```

#### 2. Create OTR Entry
```
POST /api/fso-operations
Content-Type: application/json

{
  "fso_vessel": "MT TULJA TANVI",
  "date": "2025-12-14",
  "time": "14:30",
  "shuttle_no": "SH-020",
  "vessel_name": "MT XYZ-200",
  "operation": "Receipt",
  "opening_stock": 500.0,
  "closing_stock": 1200.0,
  "vessel_quantity": 695.0,
  "remarks": "Normal receipt"
}

Response 201:
{ ...entry with id... }
```

#### 3. Validate OTR Entry
```
POST /api/fso-operations/validate
{ ...same as create payload... }

Response 200:
{
  "is_valid": true,
  "can_save": true,
  "errors": [],
  "warnings": [
    {
      "field": "vessel_quantity",
      "message": "Minor variance: FSO closing (1200) vs Vessel (695) = 505 bbls (72.66%)",
      "suggestion": "Review gauging accuracy or vessel declaration"
    }
  ],
  "calculation": {
    "opening_stock": 500.0,
    "closing_stock": 1200.0,
    "net_receipt_dispatch": 700.0,
    "water_percentage": 0.0,
    "variance": 505.0,
    "variance_pct": 72.66
  },
  "messages": [...]
}
```

#### 4. Get Material Balance (Auto-calculated)
```
GET /api/fso-operations/material-balance
Query Params:
  - location_id: int
  - fso_vessel: string
  - date_from: YYYY-MM-DD
  - date_to: YYYY-MM-DD

Response 200:
{
  "periods": [
    {
      "fso_vessel": "MT TULJA TANVI",
      "period_date": "2025-12-10",
      "opening_stock": 500.0,
      "receipts": 2400.0,
      "exports": 1500.0,
      "closing_stock": 1400.0,
      "loss_gain": -0.0,
      "entries_count": 8
    },
    {
      "fso_vessel": "MT TULJA TANVI",
      "period_date": "2025-12-11",
      "opening_stock": 1400.0,
      "receipts": 3000.0,
      "exports": 2100.0,
      "closing_stock": 2300.0,
      "loss_gain": 0.0,
      "entries_count": 9
    }
  ]
}
```

#### 5. Validate Material Balance
```
GET /api/fso-operations/material-balance/validate
Query Params: (same as material balance)

Response 200:
{
  "is_valid": true,
  "period_count": 5,
  "entries_count": 42,
  "total_receipts": 10000.0,
  "total_exports": 8500.0,
  "total_loss_gain": 0.5,
  "loss_gain_pct": 0.02,
  "warnings": [],
  "messages": [
    "✓ Balanced: no loss or gain"
  ]
}
```

#### 6. Get Reconciliation
```
GET /api/fso-operations/reconciliation
Query Params:
  - location_id: int
  - fso_vessel: string
  - date: YYYY-MM-DD (latest entry for this date)

Response 200:
{
  "fso_closing": 2300.0,
  "vessel_quantity": 2285.0,
  "variance": 15.0,
  "variance_pct": 0.66,
  "status": "MATCHED",
  "notes": [
    "✓ Stock matched within acceptable tolerance"
  ]
}
```

---

## Frontend Components

### VesselOperations.tsx (600+ lines)

**Structure**:
```
VesselOperations
├── FilterSection
│   ├── DateRangePicker (from/to)
│   ├── TextInput (shuttle filter)
│   ├── Dropdown (vessel filter)
│   └── Dropdown (operation filter)
├── ActionBar
│   └── Button (➕ Add New Entry)
├── CreateFormModal
│   ├── FormSection (basic info)
│   ├── FormSection (stocks)
│   ├── FormSection (water)
│   ├── Preview (net values)
│   └── ValidationSummary (errors/warnings)
├── EntriesTable
│   ├── Header row
│   └── DataRow[] (with edit/delete buttons)
└── ExportSection
    ├── Button (📥 CSV)
    ├── Button (📊 Excel)
    └── Button (💾 PDF)
```

**Key State**:
```typescript
interface VesselOperation {
  id: number;
  location_id: number;
  date: string; // ISO
  time: string; // HH:MM
  shuttle_no: string;
  vessel_id: number;
  vessel_name: string;
  operation_id: number;
  operation_name: string;
  opening_stock: number;
  opening_water: number;
  closing_stock: number;
  closing_water: number;
  net_receipt_dispatch: number;
  net_water: number;
  water_pct: number;
  remarks?: string;
  created_by: string;
  created_at: string;
}

interface FormState {
  date: string;
  time: string;
  shuttle_no: string;
  vessel_id: number;
  operation_id: number;
  opening_stock: number;
  opening_water: number;
  closing_stock: number;
  closing_water: number;
  remarks?: string;
}

interface ValidationResult {
  is_valid: boolean;
  errors: ValidationError[];
  warnings: ValidationWarning[];
  calculation: StockCalculation;
}
```

**Key Features**:
1. Real-time form validation (onChange)
2. Automatic net value calculation
3. Water % display
4. Operation-context warnings
5. Error/warning badges
6. Edit inline or modal
7. Delete with undo (recycle bin)
8. Bulk export
9. Pagination (limit 100)
10. Auto-refresh on create/update

### FSOOperations.tsx (800+ lines)

**Structure**:
```
FSOOperations
├── VesselSelector
│   └── Dropdown (FSO vessel, from assignment)
├── Tabs
│   ├── Tab 1: Out-Turn Report (OTR)
│   │   ├── FilterSection (same as Vessel Ops)
│   │   ├── CreateFormModal
│   │   │   └── (includes vessel_quantity field)
│   │   ├── EntriesTable
│   │   │   └── Variance column (bbls and %)
│   │   └── ExportSection
│   │
│   └── Tab 2: Material Balance
│       ├── DateRangePicker
│       ├── AutoCalcButton (Recalculate)
│       ├── ValidationSummary
│       ├── MaterialBalanceTable
│       │   ├── Period, Opening, Receipts, Exports, Closing, Loss/Gain, Entries
│       │   └── Color-coded loss/gain (red/green)
│       ├── Charts
│       │   ├── Trend (Opening/Closing line chart)
│       │   ├── Receipts/Exports (bar chart)
│       │   └── Loss/Gain (bar chart, color-coded)
│       ├── ReconciliationPanel
│       │   ├── FSO Closing
│       │   ├── Vessel Quantity
│       │   ├── Variance display
│       │   └── Status badge (Matched/Minor/Major)
│       └── DataQualityScore
```

**Key Differences from Vessel Ops**:
- Vessel selector at top (FSO-specific)
- vessel_quantity field in form
- Variance calculation and display
- Material balance auto-calculation
- Period-based table (06:01-06:00)
- Charts (Plotly integration)
- Reconciliation panel
- Quality score indicator

---

## Validation Rules

### Vessel Operations

| Field | Rule | Error | Warning |
|-------|------|-------|---------|
| date | ≤ today | ❌ Future date | - |
| time | HH:MM format | ❌ Invalid format | - |
| time | 00:00-23:59 | ❌ Out of range | - |
| shuttle_no | Non-empty | ❌ Required | - |
| vessel_id | Must exist | ❌ Not found | - |
| operation_id | Must exist | ❌ Not found | - |
| opening_stock | ≥ 0 | ❌ Negative | - |
| closing_stock | ≥ 0 | ❌ Negative | - |
| opening_water | ≥ 0 | ❌ Negative | - |
| closing_water | ≥ 0 | ❌ Negative | - |
| opening_water | ≤ opening_stock | - | ⚠️ Exceeds opening |
| closing_water | ≤ closing_stock | - | ⚠️ Exceeds closing |
| water % | > 50% | - | ⚠️ High water |
| Loading op | net > 0 | - | ⚠️ Should be positive |
| Discharging op | net < 0 | - | ⚠️ Should be negative |

### FSO Operations

| Field | Rule | Error | Warning |
|-------|------|-------|---------|
| (same as Vessel Ops) | - | - | - |
| fso_vessel | In assigned FSOs | ❌ Not found | - |
| operation | Receipt\|Export\|Stock Opening | ❌ Invalid | - |
| vessel_quantity | > 0 if provided | - | ⚠️ If variance > 2% |
| variance | calculated | - | ⚠️ Major > 5% |

### Material Balance

| Metric | Rule | Status |
|--------|------|--------|
| Loss/Gain % | < 0.5% | ✓ Balanced |
| Loss/Gain % | 0.5% - 2% | ⚠️ Minor variance |
| Loss/Gain % | > 2% | ❌ Major variance |

---

## Integration Checklist

### Phase 1: Setup (Day 1)
- [ ] Create `otms_api/validators/vessel_validators.py` (550 lines)
- [ ] Create `otms_api/validators/fso_validators.py` (600 lines)
- [ ] Copy to project and ensure imports work

### Phase 2: Backend (Days 2-3)
- [ ] Create `otms_api/routers/vessel_operations.py` endpoints
- [ ] Create `otms_api/routers/fso_operations.py` endpoints
- [ ] Add to `otms_api/__init__.py` router registration
- [ ] Test all endpoints with Postman/curl

### Phase 3: Frontend (Days 4-5)
- [ ] Create `frontend/src/VesselOperations.tsx` component
- [ ] Create `frontend/src/FSOOperations.tsx` component
- [ ] Update `frontend/src/api.ts` with new functions
- [ ] Update `frontend/src/App.tsx` routing

### Phase 4: Testing (Days 6-7)
- [ ] Unit tests for validators
- [ ] Component tests for React
- [ ] E2E tests for workflows
- [ ] Manual testing on all browsers

### Phase 5: Deployment (Day 8)
- [ ] Database migrations (if needed)
- [ ] Deploy backend
- [ ] Deploy frontend
- [ ] Monitor logs for errors

---

## Testing Strategy

### Backend Unit Tests (vessel_validators.py)

```python
import pytest
from otms_api.validators.vessel_validators import (
    validate_vessel_operation_entry,
    VesselOperationEntryRequest
)

def test_validate_entry_success():
    entry = VesselOperationEntryRequest(
        date=date(2025, 12, 14),
        time="14:30",
        shuttle_no="SH-001",
        vessel_id=5,
        operation_id=2,
        opening_stock=1000.0,
        opening_water=50.0,
        closing_stock=1250.0,
        closing_water=62.5,
        remarks="Test"
    )
    vessel_dict = {5: "MT Vessel A"}
    operation_dict = {2: "Loading"}
    
    result = validate_vessel_operation_entry(entry, vessel_dict, operation_dict, 1)
    
    assert result.is_valid is True
    assert result.can_save is True
    assert len(result.errors) == 0
    assert result.calculation.net_receipt_dispatch == 250.0

def test_validate_entry_future_date():
    entry = VesselOperationEntryRequest(
        date=date(2026, 1, 1),  # Future
        time="14:30",
        shuttle_no="SH-001",
        vessel_id=5,
        operation_id=2,
        opening_stock=1000.0,
        opening_water=50.0,
        closing_stock=1250.0,
        closing_water=62.5
    )
    # Should raise validation error
    with pytest.raises(ValueError):
        entry

def test_validate_entry_water_exceeds_stock():
    entry = VesselOperationEntryRequest(
        date=date(2025, 12, 14),
        time="14:30",
        shuttle_no="SH-001",
        vessel_id=5,
        operation_id=2,
        opening_stock=1000.0,
        opening_water=1100.0,  # Exceeds stock
        closing_stock=1250.0,
        closing_water=62.5
    )
    vessel_dict = {5: "MT Vessel A"}
    operation_dict = {2: "Loading"}
    
    result = validate_vessel_operation_entry(entry, vessel_dict, operation_dict, 1)
    
    assert result.is_valid is True  # Not an error
    assert len(result.warnings) > 0  # But a warning
    assert any("opening_water" in w.field for w in result.warnings)

# ... more tests
```

### Frontend Component Tests (VesselOperations.tsx)

```typescript
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import VesselOperations from "../VesselOperations";

describe("VesselOperations", () => {
  it("renders filter section and entries table", () => {
    render(<VesselOperations />);
    
    expect(screen.getByText(/Filters/i)).toBeInTheDocument();
    expect(screen.getByText(/Vessel Operations/i)).toBeInTheDocument();
  });

  it("creates entry with validation", async () => {
    render(<VesselOperations />);
    
    fireEvent.click(screen.getByText(/Add New Entry/i));
    
    // Fill form
    fireEvent.change(screen.getByLabelText(/Shuttle No/i), {
      target: { value: "SH-001" }
    });
    
    // Wait for validation
    await waitFor(() => {
      expect(screen.getByText(/✓ Shuttle/i)).toBeInTheDocument();
    });
    
    // Submit
    fireEvent.click(screen.getByText(/Save/i));
    
    // Check success
    await waitFor(() => {
      expect(screen.getByText(/Success/i)).toBeInTheDocument();
    });
  });

  // ... more tests
});
```

---

## Appendices

### A. Key Calculation Formulas

**Vessel Operations**:
- Net Receipt/Dispatch = Closing Stock - Opening Stock
- Net Water = Closing Water - Opening Water
- Water % = (Closing Water / Closing Stock) * 100 [capped at 100%]

**FSO Operations (OTR)**:
- Same as Vessel Operations
- Variance = Closing Stock - Vessel Quantity
- Variance % = (Variance / Vessel Quantity) * 100

**Material Balance**:
- Loss/Gain = Opening Stock + Receipts - Exports - Closing Stock
- Loss/Gain % = |Loss/Gain| / Average Stock * 100

### B. Date/Time Handling

- Dates: ISO format (YYYY-MM-DD), max today
- Times: 24-hour format HH:MM (00:00-23:59)
- Material Balance periods: 06:01 of date N to 06:00 of date N+1

### C. Export Formats

- **CSV**: Tab-separated, UTF-8, includes headers
- **Excel**: OpenPyXL, single sheet, formatted with colors
- **PDF**: ReportLab, landscape A4, includes totals and summary

### D. Permission Checks

- Can make entries: `PermissionManager.can_make_entries_user(s, user, location_id)`
- Can delete: Role in ["supervisor", "admin-operations"] or approval
- Can view: `PermissionManager.can_access_feature(s, location_id, "feature", role)`

---

**End of Design Document**
