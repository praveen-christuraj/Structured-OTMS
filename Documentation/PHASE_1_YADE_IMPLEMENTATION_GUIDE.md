# Phase 1 Implementation Guide - YADE Enhancements

## Summary
This guide covers integrating the new YADE validation components and backend validators into your existing FastAPI + React application.

---

## Files Created

### Backend (FastAPI)
1. **`otms_api/validators/yade_validators.py`** (NEW)
   - Pydantic models for validation requests/responses
   - Validation functions for dips, sample params, seals
   - Workflow status tracking
   - ~550 lines of production-ready code

2. **`otms_api/validators/tanker_validators.py`** (NEW)
   - Tanker selection & calibration validation
   - Quality parameter validation
   - Complete dispatch validation
   - Receipt reconciliation analysis
   - ~380 lines of production-ready code

### Frontend (React/TypeScript)
1. **`frontend/src/components/YadeDipsEditor.tsx`** (NEW)
   - Enhanced dips entry with real-time validation
   - Grid UI with tank ordering
   - Error and warning display
   - ~370 lines with inline styling

2. **`frontend/src/components/YadeSampleParamsEditor.tsx`** (NEW)
   - Sample parameters entry with 3 form sections
   - Live calculation preview
   - Temperature unit conversion
   - API/Density mode toggling
   - ~380 lines with inline styling

### Documentation
1. **`YADE_TANKER_TX_WORKFLOW_ENHANCEMENT.md`**
   - Comprehensive workflow design
   - Implementation roadmap
   - Code templates
   - Testing checklist

---

## Integration Steps

### Step 1: Create Backend Validator Endpoints

Add to `otms_api/routers/yade_transactions.py`:

```python
from otms_api.validators.yade_validators import (
    DipEntryRequest,
    DipValidationResponse,
    SampleParamRequest,
    SampleParamValidationResponse,
    validate_dip_entries,
    validate_sample_params,
)

@router.post("/validate-dips")
def validate_yade_dips(
    req: DipEntryRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db)
) -> DipValidationResponse:
    """Validate dip entries before save"""
    required_tanks = ["C1", "C2", "P1", "P2", "S1", "S2"]  # From config
    return validate_dip_entries(req, required_tanks)


@router.post("/validate-sample-params")
def validate_yade_sample(
    req: SampleParamRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db)
) -> SampleParamValidationResponse:
    """Validate sample parameters"""
    return validate_sample_params(req)


@router.get("/voyages/{voyage_id}/workflow-status")
def get_yade_workflow_status(
    voyage_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db)
) -> dict:
    """Get current workflow completion status"""
    from otms_api.validators.yade_validators import get_workflow_status
    
    voyage = db.query(YadeVoyage).filter(YadeVoyage.id == voyage_id).one_or_none()
    if not voyage:
        raise HTTPException(status_code=404, detail="Voyage not found")
    
    # Check what's been entered
    has_dips_before = db.query(YadeDip).filter(
        YadeDip.voyage_id == voyage_id,
        YadeDip.stage == "BEFORE"
    ).first() is not None
    
    has_dips_after = db.query(YadeDip).filter(
        YadeDip.voyage_id == voyage_id,
        YadeDip.stage == "AFTER"
    ).first() is not None
    
    has_samples_before = db.query(YadeSampleParam).filter(
        YadeSampleParam.voyage_id == voyage_id,
        YadeSampleParam.stage == "BEFORE"
    ).first() is not None
    
    has_samples_after = db.query(YadeSampleParam).filter(
        YadeSampleParam.voyage_id == voyage_id,
        YadeSampleParam.stage == "AFTER"
    ).first() is not None
    
    has_seals = db.query(YadeSealDetail).filter(
        YadeSealDetail.voyage_id == voyage_id
    ).first() is not None
    
    status = get_workflow_status(
        voyage_id,
        has_dips_before,
        has_dips_after,
        has_samples_before,
        has_samples_after,
        has_seals
    )
    
    return {
        "status": status.model_dump()
    }
```

### Step 2: Update Frontend API Client

Add to `frontend/src/api.ts`:

```typescript
export interface DipValidationPayload {
  voyage_id: number
  stage: 'BEFORE' | 'AFTER'
  dips: Array<{ tank_id: string; total_cm: number; water_cm: number }>
  max_by_tank: Record<string, number>
}

export interface DipValidationResponse {
  is_valid: boolean
  can_proceed: boolean
  errors: Array<{ tank_id: string; field: string; message: string; suggested_value?: number }>
  warnings: string[]
  previews?: Array<{ tank_id: string; gov_bbl: number; [key: string]: any }>
}

export async function validateYadeDips(
  token: string,
  payload: DipValidationPayload
): Promise<DipValidationResponse> {
  return apiFetch<DipValidationResponse>('/yade-transactions/validate-dips', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  })
}

export async function getYadeWorkflowStatus(
  token: string,
  voyageId: number
): Promise<any> {
  return apiFetch(`/yade-transactions/voyages/${voyageId}/workflow-status`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}
```

### Step 3: Integrate Components into YadeTransactions

In `frontend/src/YadeTransactions.tsx`:

```typescript
import { YadeDipsEditor } from './components/YadeDipsEditor'
import { YadeSampleParamsEditor } from './components/YadeSampleParamsEditor'

export default function YadeTransactions({ token, activeLocationId }: Props) {
  // ... existing code ...

  // Replace dips tab rendering with:
  {tab === 'DIPS' ? (
    <div className="form">
      <YadeDipsEditor
        stage={dipStage}
        rows={dipRows}
        onChange={setDipRows}
        maxByTank={detail?.max_by_tank || {}}
        requiredTanks={detail?.required_tanks || ['C1', 'C2', 'P1', 'P2', 'S1', 'S2']}
        onValidationChange={(validations) => {
          // Handle validation results
          const hasErrors = validations.some((v) => v.has_error)
          // Disable save button if errors
        }}
        disabled={detailLoading}
      />
      <button 
        className="btn primary" 
        onClick={onSaveDips}
        disabled={detailLoading}
      >
        Save Dips
      </button>
    </div>
  ) : null}

  {tab === 'SAMPLES' ? (
    <div className="form">
      <YadeSampleParamsEditor
        stage={sampleStage}
        form={sampleForm}
        onChange={setSampleForm}
        onValidationChange={(errors, warnings) => {
          // Handle validation
        }}
        onPreviewChange={(preview) => {
          // Show calculated values
        }}
        disabled={detailLoading}
      />
      <button 
        className="btn primary" 
        onClick={onSaveSample}
        disabled={detailLoading}
      >
        Save Sample Params
      </button>
    </div>
  ) : null}
}
```

### Step 4: Add API Endpoints for Tanker Validators

Add to `otms_api/routers/tanker_transactions.py`:

```python
from otms_api.validators.tanker_validators import (
    TankerValidationRequest,
    TankerValidationResponse,
    validate_tanker_selection,
)

@router.post("/validate-tanker")
def validate_tanker(
    req: TankerValidationRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db)
) -> TankerValidationResponse:
    """Validate tanker before dispatch creation"""
    return validate_tanker_selection(req, db)
```

### Step 5: Run Tests

```bash
# Backend tests (if using pytest)
pytest otms_api/validators/

# Frontend - compile TypeScript to check for errors
npm run build --prefix frontend
```

---

## API Endpoint Summary

### YADE Validation Endpoints (New)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/yade-transactions/validate-dips` | Validate dip entries |
| POST | `/yade-transactions/validate-sample-params` | Validate sample parameters |
| GET | `/yade-transactions/voyages/{id}/workflow-status` | Get workflow completion status |

### Tanker Validation Endpoints (New)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/tanker-transactions/validate-tanker` | Validate tanker selection |
| POST | `/tanker-transactions/validate-dispatch` | Validate complete dispatch |

---

## Frontend Component Usage

### YadeDipsEditor

```typescript
<YadeDipsEditor
  stage="BEFORE"  // or "AFTER"
  rows={[
    { tank_id: "C1", total_cm: "250.5", water_cm: "10.2" },
    // ...
  ]}
  onChange={(rows) => { /* Update state */ }}
  maxByTank={{ C1: 9999.0, C2: 9999.0 }}
  requiredTanks={['C1', 'C2', 'P1', 'P2', 'S1', 'S2']}
  onValidationChange={(validations) => {
    // validations = [{ tank_id, errors[], warnings[], has_error }]
  }}
  disabled={false}
/>
```

**Features:**
- ✓ Real-time validation with visual feedback
- ✓ Tank ordering maintained (C1, C2, P1, P2, S1, S2)
- ✓ Water <= Total enforcement
- ✓ Calibration max limit checks
- ✓ Add/remove rows dynamically
- ✓ Status badges (Valid/Errors/Warnings)
- ✓ Inline error messages

### YadeSampleParamsEditor

```typescript
<YadeSampleParamsEditor
  stage="BEFORE"
  form={{
    stage: 'BEFORE',
    obs_mode: 'Observed API',
    obs_val: 35.5,
    sample_unit: 'F',
    sample_temp: 68,
    tank_temp: 72,
    ccf: 1.0,
    bsw_pct: 0.5,
  }}
  onChange={(form) => { /* Update state */ }}
  onValidationChange={(errors, warnings) => {
    // Validation feedback
  }}
  onPreviewChange={(preview) => {
    // { obs_mode, obs_val, calculated_api60, tank_temp_f, ... }
  }}
  disabled={false}
/>
```

**Features:**
- ✓ Three-section form layout
- ✓ Mode toggling (Observed API ↔ Observed Density)
- ✓ Temperature unit conversion (C ↔ F)
- ✓ Live calculation preview (API60, VCF)
- ✓ Range validation for all fields
- ✓ Temperature difference warnings
- ✓ CCF and BS&W% validation

---

## Data Flow Diagram

```
Frontend (React)
    ↓
YadeDipsEditor / YadeSampleParamsEditor
    ↓
User input validation (local)
    ↓
API Call to /validate-* endpoints
    ↓
Backend (FastAPI)
    ↓
Pydantic models → validate_* functions
    ↓
Return DipValidationResponse / SampleParamValidationResponse
    ↓
Frontend displays errors/warnings/preview
    ↓
User fixes and submits via /voyages/{id}/dips or /sample
    ↓
Final validation + save to database
```

---

## Testing Checklist

### Backend Validation Tests

```python
# test_yade_validators.py

from otms_api.validators.yade_validators import validate_dip_entries, DipEntryRequest

def test_dip_validation_water_exceeds_total():
    req = DipEntryRequest(
        voyage_id=1,
        stage="BEFORE",
        dips=[{"tank_id": "C1", "total_cm": 100.0, "water_cm": 150.0}],
        max_by_tank={"C1": 9999.0}
    )
    result = validate_dip_entries(req, ["C1"])
    assert not result.is_valid
    assert any("cannot exceed total" in e.message for e in result.errors)

def test_dip_validation_exceeds_max():
    req = DipEntryRequest(
        voyage_id=1,
        stage="BEFORE",
        dips=[{"tank_id": "C1", "total_cm": 500.0, "water_cm": 10.0}],
        max_by_tank={"C1": 300.0}
    )
    result = validate_dip_entries(req, ["C1"])
    assert not result.is_valid
    assert any("exceeds calibration" in e.message for e in result.errors)
```

### Frontend Component Tests

```typescript
// YadeDipsEditor.test.tsx

import { render, screen, fireEvent } from '@testing-library/react'
import { YadeDipsEditor } from './YadeDipsEditor'

test('shows error when water exceeds total', () => {
  const onChange = jest.fn()
  const onValidation = jest.fn()

  render(
    <YadeDipsEditor
      stage="BEFORE"
      rows={[{ tank_id: 'C1', total_cm: '100', water_cm: '150' }]}
      onChange={onChange}
      maxByTank={{ C1: 9999.0 }}
      requiredTanks={['C1']}
      onValidationChange={onValidation}
    />
  )

  const validations = onValidation.mock.calls[0][0]
  expect(validations[0].has_error).toBe(true)
  expect(validations[0].errors[0]).toContain('cannot exceed')
})

test('allows adding new tank row', () => {
  const onChange = jest.fn()
  const { getByText } = render(
    <YadeDipsEditor
      stage="BEFORE"
      rows={[]}
      onChange={onChange}
      maxByTank={{}}
      requiredTanks={[]}
      onValidationChange={() => {}}
    />
  )

  fireEvent.click(getByText('+ Add Tank'))
  expect(onChange).toHaveBeenCalled()
})
```

---

## Performance Notes

- **Component Re-renders:** YadeDipsEditor and YadeSampleParamsEditor use local state for form fields. Validation runs on every change (debounce optional if needed for large datasets).
- **API Calls:** Currently validation is called locally in components. Can optionally call backend endpoints for secondary validation before final save.
- **Memory:** Components are lightweight and don't hold large datasets.

---

## Common Issues & Troubleshooting

### Issue: Validation not triggering
**Solution:** Check that `rows` or `form` prop changes trigger `useEffect` in components. Ensure parent component is re-rendering.

### Issue: Error messages not displaying
**Solution:** Verify `onValidationChange` callback is being called and state is being updated in parent component.

### Issue: Tank order not maintained
**Solution:** YadeDipsEditor uses `TANK_ORDER` constant. Verify tank IDs match exactly (case-sensitive).

### Issue: Temperature conversion incorrect
**Solution:** Check `cToF` and `fToC` functions match those in `utils_calc.py` backend.

---

## Next Steps

1. **Integrate validators into YadeTransactions.tsx** (1-2 hours)
2. **Add backend endpoints** (1 hour)
3. **Test full workflow** (2-3 hours)
4. **Create Seal Details Grid component** (2 hours)
5. **Enhance TOA preview** (2 hours)

---

## Phase 2: Tanker Workflow Enhancements

See YADE_TANKER_TX_WORKFLOW_ENHANCEMENT.md for detailed roadmap on:
- Progressive dispatch form
- Receiver workflow improvements
- Reconciliation analysis
- Transit tracking

---

## Support & Questions

For issues or questions:
1. Check the full design doc: `YADE_TANKER_TX_WORKFLOW_ENHANCEMENT.md`
2. Review existing implementations: `frontend/src/YadeTransactions.tsx`
3. Examine backend models: `models.py` (search Yade*)
4. Check calculations: `toa_yade_calculator.py`, `utils_calc.py`

