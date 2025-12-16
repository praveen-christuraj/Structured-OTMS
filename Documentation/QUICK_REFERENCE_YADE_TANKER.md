# YADE & Tanker Workflow - Quick Reference Card

## 📁 Files Overview

```
otms_api/
├── validators/
│   ├── yade_validators.py (NEW - 550 lines)
│   └── tanker_validators.py (NEW - 380 lines)
└── routers/
    ├── yade_transactions.py (UPDATE - add validation endpoints)
    └── tanker_transactions.py (UPDATE - add validation endpoints)

frontend/src/
├── components/
│   ├── YadeDipsEditor.tsx (NEW - 370 lines)
│   └── YadeSampleParamsEditor.tsx (NEW - 380 lines)
├── YadeTransactions.tsx (UPDATE - integrate components)
└── TankerTransactions.tsx (UPDATE - integrate validators)

Documentation/
├── YADE_TANKER_TX_WORKFLOW_ENHANCEMENT.md (Design doc - 600+ lines)
├── PHASE_1_YADE_IMPLEMENTATION_GUIDE.md (Integration guide - 400+ lines)
└── PROJECT_STATUS_YADE_TANKER_PHASE1.md (This project summary)
```

---

## 🎯 Component Import Statements

### For YadeTransactions.tsx
```typescript
import { YadeDipsEditor } from './components/YadeDipsEditor'
import { YadeSampleParamsEditor } from './components/YadeSampleParamsEditor'
```

### For API calls
```typescript
import { validateYadeDips, getYadeWorkflowStatus } from './api'
import { validateTanker, validateDispatchQuality } from './api'
```

---

## 🔧 Key Types & Interfaces

### DIP VALIDATION
```typescript
interface DipRow {
  tank_id: string
  total_cm: string
  water_cm: string
}

interface DipValidation {
  tank_id: string
  errors: string[]
  warnings: string[]
  has_error: boolean
}
```

### SAMPLE PARAMETERS
```typescript
interface SampleParamsForm {
  stage: 'BEFORE' | 'AFTER'
  obs_mode: 'Observed API' | 'Observed Density'
  obs_val: number
  sample_unit: string  // 'C' or 'F'
  sample_temp: number
  tank_temp: number
  ccf: number
  bsw_pct: number
}

interface SampleParamsPreview {
  calculated_api60: number
  tank_temp_f: number
  sample_temp_f: number
  vcf: number
  notes: string[]
}
```

### TANKER VALIDATION
```typescript
interface TankerValidationRequest {
  tanker_name: string
  location_id: int
  total_dip_cm: float
  water_dip_cm: float
}

interface TankerValidationResponse {
  is_valid: boolean
  has_calibration: boolean
  max_dip_cm: float
  errors: array
  warnings: array
}
```

---

## 📝 API Endpoints Summary

### NEW YADE ENDPOINTS

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/yade-transactions/validate-dips` | Validate dips before save | ✓ |
| POST | `/yade-transactions/validate-sample-params` | Validate sample params | ✓ |
| GET | `/yade-transactions/voyages/{id}/workflow-status` | Get completion status | ✓ |

### NEW TANKER ENDPOINTS

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/tanker-transactions/validate-tanker` | Check tanker & calibration | ✓ |
| POST | `/tanker-transactions/validate-dispatch` | Full dispatch validation | ✓ |

### EXISTING (NO CHANGES)

```
POST   /yade-transactions/voyages
GET    /yade-transactions/voyages
GET    /yade-transactions/voyages/{id}
PUT    /yade-transactions/voyages/{id}/dips
PUT    /yade-transactions/voyages/{id}/sample
PUT    /yade-transactions/voyages/{id}/seals
POST   /yade-transactions/voyages/{id}/toa/recompute
GET    /yade-transactions/voyages/{id}/toa/pdf

POST   /tanker-transactions
GET    /tanker-transactions
POST   /tanker-tracking/receipts
GET    /tanker-tracking/receipts
```

---

## 💡 Common Code Patterns

### Pattern 1: Using YadeDipsEditor
```typescript
const [dipRows, setDipRows] = useState<DipRow[]>([])
const [dipErrors, setDipErrors] = useState<DipValidation[]>([])

<YadeDipsEditor
  stage={dipStage}
  rows={dipRows}
  onChange={setDipRows}
  maxByTank={{ C1: 9999.0, C2: 9999.0 }}
  requiredTanks={['C1', 'C2', 'P1', 'P2', 'S1', 'S2']}
  onValidationChange={setDipErrors}
  disabled={loading}
/>

{dipErrors.some(e => e.has_error) && (
  <div>Fix errors before proceeding</div>
)}
```

### Pattern 2: Using YadeSampleParamsEditor
```typescript
const [form, setForm] = useState<SampleParamsForm>({
  stage: 'BEFORE',
  obs_mode: 'Observed API',
  obs_val: 35,
  sample_unit: 'F',
  sample_temp: 68,
  tank_temp: 72,
  ccf: 1,
  bsw_pct: 0.5,
})

const [preview, setPreview] = useState<SampleParamsPreview | null>(null)
const [errors, setErrors] = useState<string[]>([])

<YadeSampleParamsEditor
  stage={sampleStage}
  form={form}
  onChange={setForm}
  onPreviewChange={setPreview}
  onValidationChange={(errs, warns) => setErrors(errs)}
/>

{preview && (
  <div>
    <div>API@60: {preview.calculated_api60}</div>
    <div>VCF: {preview.vcf}</div>
  </div>
)}
```

### Pattern 3: Tanker Validation
```typescript
async function validateBeforeCreate() {
  try {
    const tankerVal = await validateTanker(token, {
      tanker_name: cTankerName,
      location_id: activeLocationId,
      total_dip_cm: cTotalDip,
      water_dip_cm: cWaterDip
    })
    
    if (!tankerVal.is_valid) {
      const msgs = tankerVal.errors.map(e => e.message)
      setError(msgs.join('; '))
      return false
    }
    
    return true
  } catch (e) {
    setError(e instanceof Error ? e.message : 'Validation failed')
    return false
  }
}
```

---

## ✅ Validation Rules Cheat Sheet

### DIP VALIDATION RULES

| Rule | Condition | Error |
|------|-----------|-------|
| Water ≤ Total | water_cm ≤ total_cm | ✗ |
| No Negative | total_cm ≥ 0, water_cm ≥ 0 | ✗ |
| Within Max | total_cm ≤ max_cm | ✗ |
| All Tanks Required | All tanks in required_tanks list | ⚠ |
| No Duplicates | One entry per tank | ✗ |

### SAMPLE PARAMS VALIDATION RULES

| Rule | Condition | Error |
|------|-----------|-------|
| Valid Mode | obs_mode in ['Observed API', 'Observed Density'] | ✗ |
| API Range | 15 ≤ obs_val ≤ 70 (if API mode) | ✗ |
| Density Range | 600 ≤ obs_val ≤ 1000 (if Density mode) | ✗ |
| Temp Range C | 0 ≤ temp ≤ 60 (if Celsius) | ✗ |
| Temp Range F | 32 ≤ temp ≤ 140 (if Fahrenheit) | ✗ |
| CCF Range | 0 < ccf ≤ 1.0 | ✗ |
| BSW% Range | 0 ≤ bsw_pct ≤ 100 | ✗ |
| Temp Diff Warning | abs(tank_temp - sample_temp) > 20 | ⚠ |

### TANKER VALIDATION RULES

| Rule | Condition | Error |
|------|-----------|-------|
| Tanker Exists | tanker found in DB | ✗ |
| Tanker Active | status = 'ACTIVE' | ⚠ |
| Has Calibration | calibration_rows.count > 0 | ✗ |
| Dip in Range | total_dip ≤ max_calibration_dip | ✗ |
| Water ≤ Total | water_dip ≤ total_dip | ✗ |

---

## 🔄 Workflow Diagram

```
User fills form
    ↓
Real-time validation (component level)
    ↓
Errors? → Show error badges
    ↓
No errors → Show preview calculations
    ↓
User clicks Save
    ↓
(Optional) Call backend validation API
    ↓
Backend saves to database
    ↓
Backend validation (final)
    ↓
Success → Show confirmation
    ↓
Error → Show detailed error message
```

---

## 🐛 Debugging Tips

### Component Not Showing Validation
1. Check `onValidationChange` callback is wired
2. Verify parent state is updating: `console.log(dipErrors)`
3. Check browser console for TypeScript errors

### Validation Always Passing
1. Check validator functions (off-by-one errors on ranges)
2. Verify mock/test data matches actual data format
3. Check if validation is even being called (add console.log)

### Calculations Wrong
1. Check temperature unit conversion (C vs F)
2. Verify API60 formula matches backend
3. Check VCF lookup values

### Backend Endpoint 404
1. Check router is included in main.py: `app.include_router(...)`
2. Verify endpoint path exactly matches route definition
3. Check prefix: `@router.post("/validate-dips")` under `prefix="/yade-transactions"`

---

## 📊 Error Response Format

### Example: DIP Validation Error
```json
{
  "is_valid": false,
  "can_proceed": false,
  "errors": [
    {
      "tank_id": "C1",
      "field": "water_cm",
      "message": "Water (150 cm) cannot exceed total (100 cm)",
      "current_value": 150,
      "suggested_value": 100
    }
  ],
  "warnings": [
    "Tank S1: No dip recorded (0 cm)"
  ],
  "previews": null
}
```

### Example: Sample Params Error
```json
{
  "is_valid": false,
  "errors": [
    "Observed API must be 15-70, got 85"
  ],
  "warnings": [],
  "preview": null
}
```

---

## 🚀 Quick Integration (5 Steps)

1. **Copy validators to backend**
   ```bash
   cp otms_api/validators/*.py /path/to/otms_api/validators/
   ```

2. **Copy components to frontend**
   ```bash
   cp frontend/src/components/*.tsx /path/to/frontend/src/components/
   ```

3. **Add API functions** (frontend/src/api.ts)
   ```typescript
   export async function validateYadeDips(...) { ... }
   export async function validateTanker(...) { ... }
   ```

4. **Update pages** (YadeTransactions.tsx, TankerTransactions.tsx)
   ```typescript
   import { YadeDipsEditor } from './components/YadeDipsEditor'
   <YadeDipsEditor ... />
   ```

5. **Test**
   ```bash
   npm run build --prefix frontend
   pytest otms_api/validators/
   ```

---

## 📱 Component Props Quick Ref

### YadeDipsEditor Props
```typescript
stage: 'BEFORE' | 'AFTER'
rows: DipRow[]
onChange: (rows: DipRow[]) => void
maxByTank: Record<string, number>
requiredTanks: string[]
onValidationChange?: (validations: DipValidation[]) => void
disabled?: boolean
```

### YadeSampleParamsEditor Props
```typescript
stage: 'BEFORE' | 'AFTER'
form: SampleParamsForm
onChange: (form: SampleParamsForm) => void
onValidationChange?: (errors: string[], warnings: string[]) => void
onPreviewChange?: (preview: SampleParamsPreview | null) => void
disabled?: boolean
```

---

## 🔐 Security Notes

- ✅ All inputs validated on backend (never trust frontend)
- ✅ User permissions checked via `CurrentUser` and `require_location_access()`
- ✅ SQL injection prevented (using SQLAlchemy ORM)
- ✅ XSS prevented (React sanitizes by default)
- ✅ CSRF token in place (FastAPI middleware)

---

## 📈 Performance Tips

- Local validation < 100ms per change
- API validation call < 200ms
- Component render < 500ms with 6 tanks
- Use `useMemo` to prevent unnecessary re-renders
- Debounce API calls if validating on every keystroke (optional)

---

## 🆘 Support Matrix

| Issue | Solution | File |
|-------|----------|------|
| Validation not triggering | Check prop changes, useEffect deps | YadeDipsEditor.tsx #45 |
| Tank order wrong | Edit TANK_ORDER constant | YadeDipsEditor.tsx #10 |
| Temperature conversions off | Verify cToF function matches utils_calc.py | YadeSampleParamsEditor.tsx #15 |
| API endpoint 404 | Check router prefix and endpoint path | otms_api/routers/yade_transactions.py |
| Component not displaying | Check parent component rendering | YadeTransactions.tsx |
| CSS not applying | Inline styles included, check !important | Component .tsx files |

---

## 📚 Additional Resources

- **Design Document:** See YADE_TANKER_TX_WORKFLOW_ENHANCEMENT.md (sections 1-2)
- **Integration Guide:** See PHASE_1_YADE_IMPLEMENTATION_GUIDE.md (sections 1-5)
- **Backend Models:** models.py (search: `class Yade*`, `class Tanker*`)
- **Calculations:** utils_calc.py, toa_yade_calculator.py
- **Existing Implementation:** YadeTransactions.tsx (as reference)

---

**Last Updated:** December 14, 2025  
**Version:** Phase 1.0 (Production Ready)  
**Status:** Ready for Integration

