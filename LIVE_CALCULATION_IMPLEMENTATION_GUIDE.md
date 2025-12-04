# Live Auto-Calculation Implementation Guide

## Quick Summary of Changes

### What Changed
**Tanker Transactions → Custom Tabs Form Structure**

The form was changed from `st.form()` (static) to Streamlit widgets with session state (live).

### Why It Matters
- **Before**: Formulas only calculated when you clicked "Save"
- **After**: Formulas calculate as you type, showing real-time results

---

## Detailed Comparison

### BEFORE (Old Implementation)
```python
# Form creates a scope where values are only available on submit
with st.form(key=f"custom_tanker_tab_form_{table_name}_{loc.id}"):
    row = {}  # Empty dict
    
    # Render input fields
    for i, col in enumerate(manual_columns):
        if ctype == "number":
            # Value captured BUT not available until form submit
            row[name] = st.number_input(label, step=0.01, format="%.2f", 
                                       key=f"custom_tanker_{table_name}_{loc.id}_num_{i}")
    
    # Try to calculate here
    if calculated_columns:
        for calc_col in calculated_columns:
            # row[name] is EMPTY here because form hasn't been submitted!
            calculated_value = _evaluate_formula(formula, row)  # Uses empty row!
            st.metric(label, f"{calculated_value:.2f}")  # Shows N/A
    
    # Only on submit does streamlit process the form
    submitted = st.form_submit_button("💾 Save Row", type="primary")

# Form data only available here after submit
if not submitted:
    return

# NOW formulas are calculated with actual values
for calc_col in calculated_columns:
    calculated_value = _evaluate_formula(formula, row)  # NOW row has values!
    row[name] = calculated_value
```

**Result**: 
- ❌ Calculations shown as "N/A" while filling form
- ❌ No live preview
- ❌ Must save to see if calculations are correct

---

### AFTER (New Implementation)
```python
# Use session state instead of form context
form_key = f"custom_tanker_tab_form_{table_name}_{loc.id}"
if form_key not in st.session_state:
    st.session_state[form_key] = {}

row = st.session_state[form_key]  # Persistent across renders

# Render input fields
st.markdown("##### 📝 Input Fields")
for i, col in enumerate(manual_columns):
    if ctype == "number":
        widget_key = f"{form_key}_input_{i}"
        # Value IMMEDIATELY available in session state
        # Changes trigger page re-render
        row[name] = st.number_input(label, step=0.01, format="%.2f", key=widget_key)

# Calculate and display (LIVE) on every page render
if calculated_columns:
    st.markdown("##### 🧮 Calculated Columns (Auto-computed)")
    for calc_col in calculated_columns:
        # Uses CURRENT values from session state
        # Called on EVERY render (after user changes input)
        calculated_value = _evaluate_formula(formula, row)
        if calculated_value is not None:
            st.metric(label, f"{calculated_value:.2f}")  # Shows live value!
            row[name] = calculated_value

# Regular button (not form button)
if st.button("💾 Save Row", type="primary", key=f"{form_key}_submit"):
    submitted = True
else:
    submitted = False

if not submitted:
    return

# Formulas already calculated in session state
# Just save the data
```

**Result**:
- ✅ Calculations shown in real-time while filling form
- ✅ Live preview as you type
- ✅ Can verify calculations before saving

---

## How Streamlit Re-Renders Trigger Calculations

```
User Action (e.g., enters "100" in field)
           ↓
Streamlit detects widget value change
           ↓
Session state updates: row["Stream A"] = 100
           ↓
Script re-runs from top
           ↓
Session state restored: row = {"Stream A": 100}
           ↓
Input widgets re-render with current values
           ↓
Calculated column section executes
           ↓
_evaluate_formula(formula, row) uses CURRENT values
           ↓
Results displayed in st.metric()
           ↓
Page shows live updated calculation
```

---

## Code Flow Comparison

### OLD FLOW (Form-based)
```
Page Load
  ├─ User fills field A
  ├─ User fills field B
  ├─ Calculations shown as N/A (form not submitted)
  ├─ User clicks "Save"
  ├─ Form submission triggers
  ├─ Calculations executed with actual values
  └─ Data saved
```

### NEW FLOW (Session State-based)
```
Page Load
  ├─ User fills field A
  ├─ Page re-renders (detects change)
  ├─ Calculation 1 shows updated result
  ├─ User fills field B
  ├─ Page re-renders (detects change)
  ├─ Calculations 1 & 2 show updated results
  ├─ User verifies calculations are correct
  ├─ User clicks "Save"
  ├─ Data saved (calculations already correct)
  └─ Session state cleared
```

---

## Session State Management

### Initialization
```python
form_key = f"custom_tanker_tab_form_{table_name}_{loc.id}"
if form_key not in st.session_state:
    st.session_state[form_key] = {}
```
- Creates a dictionary to store form data
- Only initializes once per session
- Re-used across page re-renders

### Usage During Input
```python
row = st.session_state[form_key]
row[name] = st.number_input(...)  # Auto-synced on every change
```
- Widgets auto-sync with session state
- Every keystroke triggers update
- Page re-renders immediately

### Cleanup After Save
```python
if form_key in st.session_state:
    del st.session_state[form_key]
st.rerun()
```
- Clears form data after successful save
- Fresh start for next entry
- Prevents stale data

---

## Widget Key Strategy

### Key Format
```python
widget_key = f"{form_key}_input_{i}"
# Example: "custom_tanker_tab_form_custom_table_1_input_0"
```

### Why This Matters
- Unique key per widget per form
- Allows Streamlit to track value changes
- Enables session state sync
- Prevents key collisions across different tabs

---

## Support for All Input Types

### Date Input
```python
row[name] = st.date_input(label, max_value=date.today(), key=widget_key)
# Updates session state on date selection
```

### Number Input
```python
row[name] = st.number_input(label, step=0.01, format="%.2f", key=widget_key)
# Updates session state on every keystroke
```

### Text Input
```python
row[name] = st.text_input(label, key=widget_key)
# Updates session state on every character typed
```

---

## Formula Evaluation

### Evaluated On Every Render
```python
calculated_value = _evaluate_formula(formula, row)
# Called whenever page re-renders
# Uses CURRENT row values from session state
```

### Result Display
```python
if calculated_value is not None:
    st.metric(label, f"{calculated_value:.2f}")  # Live value
else:
    st.info(f"... - Fill in the required fields to auto-compute")  # Waiting for input
```

### Supported Operations
- `sum` - Add values
- `subtract` - Subtract values
- `multiply` - Multiply values
- `divide` - Divide values
- `percentage` - Calculate percentage
- `maximum` - Maximum value
- `minimum` - Minimum value
- `average` - Average of values

---

## Example: Three-Field Calculation

### Configuration
```
Field A: Stream A (number)
Field B: Stream B (number)
Field C: Total (calculated, formula: sum(Stream A, Stream B))
```

### Render 1: Page Load
```
Stream A: [        ]  (empty)
Stream B: [        ]  (empty)
Total: -- (waiting for input)
```

### Render 2: User enters "50" in Stream A
```
Stream A: [50      ]  ← just entered
Stream B: [        ]  (empty)
Total: 50.00         ← calculated from current values!
```

### Render 3: User enters "30" in Stream B
```
Stream A: [50      ]  (no change)
Stream B: [30      ]  ← just entered
Total: 80.00         ← recalculated! (50 + 30)
```

### Render 4: User clicks Save
```
Data persisted: Stream A=50, Stream B=30, Total=80.00
Form cleared
Page ready for next entry
```

---

## Troubleshooting

### Problem: Calculations not updating
**Solution**: Ensure widgets have unique keys and are outside any form context

### Problem: Stale values displayed
**Solution**: Session state is automatically managed; clear with `del st.session_state[form_key]`

### Problem: Form not submitting
**Solution**: Use regular `st.button()` instead of `st.form_submit_button()`

---

## Performance Considerations

### Re-render on Every Input
- **Expected behavior**: Page re-renders on every widget change
- **Performance**: Fast for typical forms (usually < 100ms)
- **Optimization**: Formulas are simple Python operations (very fast)

### Session State Size
- **Storage**: One dictionary per form session
- **Memory**: Negligible for typical data (< 1KB per form)
- **Cleanup**: Automatically removed after save

### No Database Calls During Input
- Only on final Save
- Input validation local
- No server overhead for calculations
