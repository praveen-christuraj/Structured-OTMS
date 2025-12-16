# YADE & Tanker Tx Workflow Enhancement Guide

## Overview
Comprehensive implementation guide for full YADE entry (dips/samples/seals/TOA) and Tanker Tx (create + receiver) workflows using FastAPI backend and React/TypeScript frontend.

---

## 1. YADE FULL WORKFLOW (Dips/Samples/Seals/TOA)

### 1.1 Current State Analysis

**Backend (FastAPI):**
- `otms_api/routers/yade_transactions.py` - Main YADE transaction endpoints
- Endpoints available:
  - `GET /voyages` - List YADE voyages with filters
  - `POST /voyages` - Create new YADE voyage
  - `GET /voyages/{voyage_id}` - Get voyage details
  - `PUT /voyages/{voyage_id}/dips` - Upsert dips (BEFORE/AFTER)
  - `PUT /voyages/{voyage_id}/sample` - Upsert sample parameters
  - `PUT /voyages/{voyage_id}/seals` - Upsert seal details
  - `POST /voyages/{voyage_id}/toa/recompute` - Recompute TOA calculation
  - `GET /voyages/{voyage_id}/toa/pdf` - Download TOA PDF

**Frontend (React):**
- `frontend/src/YadeTransactions.tsx` - Main YADE component (821 lines)
- Tab-based interface: DETAILS | DIPS | SAMPLES | SEALS | TOA
- State management for all workflow stages
- API integration via `frontend/src/api.ts`

**Database Models:**
- `YadeVoyage` - Master voyage record
- `YadeDip` - Dip readings (BEFORE/AFTER per tank)
- `YadeSampleParam` - Sample parameters (API, density, temp, etc.)
- `YadeSealDetail` - Seal information (MH1, MH2, lock, diphatch per tank)
- `TOAYadeSummary` - Calculated TOA results
- `TOAYadeStage` - Stage calculations (intermediate)
- `YadeCalibration` - Tank calibration volume tables

### 1.2 Enhancement Priorities

#### Priority 1: Dips Entry - Full Validation & UX
**Current Issues:**
- Minimal validation of dip readings
- No guidance on tank limits
- No real-time calculation feedback
- Missing water_cm validation (water cannot exceed total)

**Enhancements:**
```typescript
// frontend/src/YadeTransactions.tsx - Enhanced dip validation
interface DipValidation {
  tank_id: string
  total_cm: number
  water_cm: number
  errors: string[]
  warnings: string[]
  max_cm: number
  totalVolumeBbl?: number
  waterVolumeBbl?: number
  govBbl?: number
}

function validateDips(rows: DipRow[], maxLimits: Record<string, number>): DipValidation[] {
  // - water_cm <= total_cm
  // - total_cm <= max_cm
  // - All required tanks present
  // - Reasonable ranges
}
```

#### Priority 2: Sample Parameters - Enhanced Input & Calculation Preview
**Current Issues:**
- Limited UI for mode selection (Observed API vs Density)
- No live preview of calculated API60
- Temperature unit selection not clear
- CCF and BSW% validation missing

**Enhancements:**
```typescript
// frontend/src/components/YadeSampleParamsForm.tsx (new file)
interface SampleParamsPreview {
  obs_mode: 'Observed API' | 'Observed Density'
  obs_val: number
  sample_temp: number
  sample_unit: string
  calculated_api60: number
  vcf: number
  tank_temp: number
  ccf: number
  bsw_pct: number
  validationErrors: string[]
}
```

#### Priority 3: Seals Entry - Grid-based UI
**Current Issues:**
- Minimal seal details entry
- No structured layout for MH1, MH2, lock, diphatch
- Tank organization unclear

**Enhancements:**
```typescript
// frontend/src/components/YadeSealDetailsGrid.tsx (new file)
interface SealRow {
  tank_id: string
  mh1: string
  mh2: string
  lock: string
  diphatch: string
}

// Render as sortable grid with tank order maintained
```

#### Priority 4: TOA Calculation & PDF
**Current State:** Already working
**Enhancements:**
- Add "Summary Preview" before confirming
- Show before/after/loaded volume comparison
- Enhanced PDF with visual charts

#### Priority 5: Workflow State Management
**Enhancements:**
- Prevent out-of-order saves (must save header before dips/samples/seals)
- Track completion status (green checkmarks)
- Auto-save drafts to localStorage
- Wizard-style progressive disclosure

---

## 2. TANKER TX WORKFLOW (Create + Receiver)

### 2.1 Current State Analysis

**Backend (FastAPI):**
- `otms_api/routers/tanker_transactions.py` - Create dispatch transactions
- `otms_api/routers/tanker_tracking.py` - Receiver workflows (receipts)
- Endpoints available:
  - `GET /transactions` - List dispatch transactions
  - `POST /` - Create new tanker dispatch
  - `GET /receipts` - List receipts (receiver side)
  - `POST /receipts` - Create/update receipt

**Frontend (React):**
- `frontend/src/TankerTransactions.tsx` - Dispatch creation (464 lines)
- `frontend/src/TankerTracking.tsx` - Receiver workflows (tracking component)
- State management for both sender and receiver workflows

**Database Models:**
- `TankerTransaction` - Dispatch records (sender location)
- `TankerReceipt` - Receipt records (receiver location)
- `TankerCalibration` - Tank volume calibration

### 2.2 Enhancement Priorities

#### Priority 1: Dispatch Creation - Enhanced Form & Validation
**Current Issues:**
- Form fields not grouped logically
- Missing cargo/destination pre-fill from location config
- No calibration validation until submission
- Limited feedback on tanker selection

**Enhancements:**
```typescript
// frontend/src/components/TankerDispatchForm.tsx (new file)
interface DispatchFormValidation {
  section: 'basic' | 'identification' | 'quality' | 'seals'
  fieldName: string
  errors: string[]
  warnings: string[]
  suggestedValues?: string[]
}

// Implement progressive form with:
// 1. Basic Info (tanker, convoy, cargo, destination)
// 2. Identification (date, time, manhole, loading bay)
// 3. Quality Parameters (dips, temps, obs mode, seals)
// 4. Review & Confirm
```

#### Priority 2: Receiver Workflow - Multi-stage Receipt Process
**Current Issues:**
- Receiver interface may not clearly show incoming dispatches
- Missing reconciliation between dispatch and receipt
- Limited tracking of variance (dispatch vs receipt volumes)
- No visual status indicators for pending/completed

**Enhancements:**
```typescript
// frontend/src/components/TankerReceiverWorkflow.tsx (new file)
interface ReceiverDispatchItem {
  dispatch_id: number
  tanker_name: string
  convoy_no: string
  cargo: string
  destination: string
  dispatch_nsv_bbl: number
  
  // Receiver section
  receipt_status: 'PENDING' | 'RECEIVED' | 'RECONCILED'
  receipt_arrival_date?: string
  receipt_arrival_time?: string
  receipt_dip_cm?: number
  receipt_water_cm?: number
  receipt_nsv_bbl?: number
  receipt_variance?: number
  receiver_notes?: string
}

// Multi-tab interface:
// - Incoming (filter for this location)
// - Received (completed receipts)
// - Reconciliation (variance analysis)
```

#### Priority 3: Tanker Validation & Calibration Check
**Current Issues:**
- Calibration validation happens late in submission
- No early warning if tanker calibration missing
- Dip limits not shown in UI

**Enhancements:**
```typescript
// otms_api/routers/tanker_transactions.py
class TankerValidationResponse:
    is_valid: bool
    tanker_name: str
    has_calibration: bool
    max_dip_cm: float
    capacity_litres: float
    suggested_cargo_options: List[str]
    errors: List[str]

@router.get("/validate-tanker/{tanker_name}")
def validate_tanker(tanker_name: str, location_id: int, db: Session):
    """Validate tanker before dispatch creation"""
```

#### Priority 4: Dispatch -> Receipt Matching
**Current Issues:**
- Manual matching might be error-prone
- No automated destination matching
- Missing reference number tracking

**Enhancements:**
```typescript
// Enhanced TankerReceipt model with:
// - dispatch_id (foreign key - enforced)
// - destination_match_confidence (fuzzy match algorithm)
// - auto_matched: bool (system matched automatically)
// - manual_confirmation: bool (user confirmed)

// Receiver location sees filtered list:
// - WHERE dispatch.destination MATCHES receiver_aliases
// - ORDER BY match_confidence DESC
```

#### Priority 5: Tracking & Analytics
**Current Issues:**
- Limited visibility into dispatch pipeline
- No volume reconciliation reports
- Missing transit time tracking

**Enhancements:**
```typescript
// New analytics endpoints:
// GET /dispatch-summary (sender perspective)
// GET /receipt-summary (receiver perspective)
// GET /variance-analysis (reconciliation)
// GET /transit-times (performance metrics)
```

---

## 3. IMPLEMENTATION ROADMAP

### Phase 1: YADE Enhancements (1-2 weeks)
1. **Backend Validators** (yade_transactions.py)
   - Dip validation service
   - Sample parameter validation
   - Seal detail validation
   - Cross-stage validation (dips must exist before seals)

2. **Frontend Components** (React)
   - `YadeDipsValidator.tsx` - Real-time dip validation
   - `YadeSampleParamsForm.tsx` - Enhanced sample entry with preview
   - `YadeSealDetailsGrid.tsx` - Grid-based seal entry
   - `YadeWorkflowStatus.tsx` - Completion status tracker

3. **API Enhancements**
   - Add validation endpoints (return detailed errors)
   - Add preview endpoints (show calculated values)
   - Add workflow state endpoint

### Phase 2: Tanker Tx Enhancements (1-2 weeks)
1. **Backend Validators** (tanker_transactions.py)
   - Tanker existence & calibration check
   - Dip vs calibration validation
   - Temperature/obs mode validation
   - Quality parameter validation

2. **Frontend Components** (React)
   - `TankerDispatchForm.tsx` - Progressive form with sections
   - `TankerReceiverWorkflow.tsx` - Multi-tab receiver interface
   - `DispatchReconciliation.tsx` - Variance analysis view
   - `TransitTracking.tsx` - Timeline and status view

3. **API Enhancements**
   - Add tanker validation endpoint
   - Add dispatch summary endpoint
   - Add receipt reconciliation endpoint
   - Add auto-matching algorithm

### Phase 3: Integration & Testing (1 week)
1. End-to-end workflow testing
2. Performance optimization
3. Error handling and edge cases
4. Documentation updates

---

## 4. CODE TEMPLATES

### 4.1 Backend Validator Pattern (Python)

```python
# otms_api/validators/yade_validators.py
from pydantic import BaseModel, validator
from typing import List, Optional

class DipValidationRequest(BaseModel):
    voyage_id: int
    stage: str  # "BEFORE" or "AFTER"
    dips: List[dict]  # {tank_id, total_cm, water_cm}
    max_by_tank: dict  # tank_id -> max_cm

    @validator('dips')
    def validate_dips(cls, v):
        for dip in v:
            if dip['water_cm'] > dip['total_cm']:
                raise ValueError(f"Water cannot exceed total for {dip['tank_id']}")
        return v

class DipValidationResponse(BaseModel):
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    calculated_volumes: Optional[dict]  # Previews

@router.post("/validate-dips")
def validate_dips(req: DipValidationRequest, db: Session):
    """Validate dips before save"""
    errors = []
    warnings = []
    
    # Check all tanks represented
    # Check ranges
    # Calculate volumes if valid
    
    return DipValidationResponse(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        calculated_volumes={...}
    )
```

### 4.2 Frontend Component Pattern (React/TypeScript)

```typescript
// frontend/src/components/YadeDipsValidator.tsx
import { useState, useEffect } from 'react'

interface DipRow {
  tank_id: string
  total_cm: number
  water_cm: number
}

interface DipValidationResult {
  is_valid: boolean
  errors: string[]
  warnings: string[]
  calculated_volumes?: Record<string, {gov_bbl: number, tov_bbl: number}>
}

interface Props {
  voyageId: number
  stage: 'BEFORE' | 'AFTER'
  dips: DipRow[]
  maxByTank: Record<string, number>
  onValidate: (result: DipValidationResult) => void
}

export function YadeDipsValidator({ voyageId, stage, dips, maxByTank, onValidate }: Props) {
  const [validation, setValidation] = useState<DipValidationResult | null>(null)
  
  useEffect(() => {
    validateDips()
  }, [dips, stage])
  
  async function validateDips() {
    const result = await validateYadeDips({
      voyage_id: voyageId,
      stage,
      dips,
      max_by_tank: maxByTank,
    })
    setValidation(result)
    onValidate(result)
  }
  
  return (
    <div className="validation-panel">
      {validation?.is_valid ? (
        <div className="success">✓ Valid dips</div>
      ) : (
        <div className="errors">
          {validation?.errors.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}
      {validation?.warnings && (
        <div className="warnings">
          {validation.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
        </div>
      )}
      {validation?.calculated_volumes && (
        <div className="preview">
          <h4>Calculated Volumes</h4>
          {Object.entries(validation.calculated_volumes).map(([tank, vol]) => (
            <div key={tank}>
              {tank}: {vol.gov_bbl} bbl GOV
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

### 4.3 Progressive Form Pattern (React)

```typescript
// frontend/src/components/TankerDispatchForm.tsx
type FormSection = 'basic' | 'identification' | 'quality' | 'review'

interface FormData {
  // Section 1: Basic
  tanker_name: string
  cargo: string
  destination: string
  
  // Section 2: Identification
  transaction_date: string
  transaction_time: string
  manhole: string
  loading_bay?: string
  
  // Section 3: Quality
  total_dip_cm: number
  water_dip_cm: number
  tank_temp_value: number
  tank_temp_unit: string
  sample_temp_value: number
  sample_temp_unit: string
  obs_mode: 'Observed API' | 'Observed Density'
  api_observed?: number
  density_observed?: number
  bsw_pct: number
  
  // Seals
  seal_c1?: string
  seal_c2?: string
}

export function TankerDispatchForm({ onSubmit }: { onSubmit: (data: FormData) => void }) {
  const [currentSection, setCurrentSection] = useState<FormSection>('basic')
  const [formData, setFormData] = useState<FormData>({...})
  const [sectionErrors, setSectionErrors] = useState<Record<FormSection, string[]>>({})
  
  function canProceedToNext(section: FormSection): boolean {
    // Validate section before proceeding
    const errors = validateSection(section, formData)
    setSectionErrors(prev => ({ ...prev, [section]: errors }))
    return errors.length === 0
  }
  
  function handleNext() {
    if (canProceedToNext(currentSection)) {
      const sections: FormSection[] = ['basic', 'identification', 'quality', 'review']
      const idx = sections.indexOf(currentSection)
      if (idx < sections.length - 1) {
        setCurrentSection(sections[idx + 1])
      }
    }
  }
  
  return (
    <form>
      <div className="form-sections">
        {currentSection === 'basic' && <BasicInfoSection />}
        {currentSection === 'identification' && <IdentificationSection />}
        {currentSection === 'quality' && <QualitySection />}
        {currentSection === 'review' && <ReviewSection />}
      </div>
      
      <div className="form-nav">
        <button onClick={() => setCurrentSection(sections[sections.indexOf(currentSection) - 1])}>
          Back
        </button>
        {currentSection !== 'review' && (
          <button onClick={handleNext}>Next</button>
        )}
        {currentSection === 'review' && (
          <button onClick={() => onSubmit(formData)} className="primary">
            Create Dispatch
          </button>
        )}
      </div>
    </form>
  )
}
```

---

## 5. TESTING CHECKLIST

### YADE Workflow
- [ ] Create voyage with all required fields
- [ ] Enter BEFORE dips for all tanks
- [ ] Validate water_cm <= total_cm
- [ ] Enter sample parameters (API and Density modes)
- [ ] Calculate and preview API60, VCF
- [ ] Enter seals for all tanks
- [ ] Recompute TOA
- [ ] Verify TOA calculation matches manual
- [ ] Download TOA PDF
- [ ] Edit voyage and seals
- [ ] Delete voyage with audit trail

### Tanker Workflow (Sender)
- [ ] Create dispatch with all required fields
- [ ] Validate tanker calibration before save
- [ ] Select observation mode (API vs Density)
- [ ] Verify calculation of api60, vcf, gsv, nsv
- [ ] Save dispatch with seals
- [ ] Edit dispatch before receiver processes
- [ ] Track dispatch in list

### Tanker Workflow (Receiver)
- [ ] Filter incoming dispatches by destination
- [ ] See dispatch details
- [ ] Create receipt with arrival time
- [ ] Enter dip readings and recalculate volumes
- [ ] See variance vs dispatch
- [ ] Enter remarks
- [ ] Update receipt status (RECEIVED, RECONCILED)
- [ ] Track reconciliation

---

## 6. DATABASE SCHEMA NOTES

### New/Enhanced Fields Needed

**YadeVoyage**
- `status` - 'DRAFT' | 'COMPLETE' | 'REVIEWED'
- `has_dips` - bool
- `has_samples` - bool
- `has_seals` - bool

**TankerTransaction**
- `status` - 'CREATED' | 'DISPATCHED' | 'IN_TRANSIT'
- `receipt_required` - bool (default True)

**TankerReceipt**
- `match_confidence` - float (0-1 for auto-match)
- `auto_matched` - bool
- `user_confirmed` - bool

---

## 7. NEXT STEPS

1. **Review & Approve** this design
2. **Create detailed issue tickets** for each enhancement
3. **Start Phase 1** with YADE backend validators
4. **Daily standups** on progress
5. **Integration testing** before rollout

---

## 8. USEFUL REFERENCES

- Backend: `otms_api/routers/yade_transactions.py` (632 lines)
- Backend: `otms_api/routers/tanker_transactions.py` (435 lines)  
- Backend: `otms_api/routers/tanker_tracking.py` (650+ lines)
- Frontend: `frontend/src/YadeTransactions.tsx` (821 lines)
- Frontend: `frontend/src/TankerTransactions.tsx` (464 lines)
- Calculations: `toa_yade_calculator.py`, `utils_calc.py`
- Models: `models.py` (search for Yade*, Tanker* classes)

