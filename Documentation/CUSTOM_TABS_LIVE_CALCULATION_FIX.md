# Custom Tabs Live Auto-Calculation Fix

## Problem
When creating custom tabs in Tank & Tanker transactions pages through Page Customization, auto-computed (calculated) field values were only computed AFTER saving the entries, not while users were entering data.

## Root Cause
The custom tab form was wrapped in `st.form()`, which only captures and processes widget values when the form is submitted. This meant:
- User enters values in input fields
- Form is displayed but no calculations happen
- User clicks "Save Row"
- Only then are formulas evaluated
- Result: No live preview of calculated values

## Solution
Removed the `st.form()` wrapper and implemented live calculation using Streamlit's session state:

### Key Changes in `app_pages/tanker_transactions.py`

**Function Modified**: `_render_custom_tanker_tab()`

#### Before (Form-based - No Live Calculation):
```python
with st.form(key=f"custom_tanker_tab_form_{table_name}_{loc.id}"):
    row = {}
    # Render input fields
    # Calculate and display (but row is empty until submit!)
    submitted = st.form_submit_button("💾 Save Row", type="primary")
```

#### After (Session State-based - Live Calculation):
```python
# Initialize session state
form_key = f"custom_tanker_tab_form_{table_name}_{loc.id}"
if form_key not in st.session_state:
    st.session_state[form_key] = {}

row = st.session_state[form_key]

# Render input fields (live updates session state)
for col in manual_columns:
    row[name] = st.date_input(...) # or number_input, text_input
    # Session state updates on every keystroke/change!

# Calculate and display (uses CURRENT row values from session state)
for calc_col in calculated_columns:
    calculated_value = _evaluate_formula(formula, row)
    st.metric(label, f"{calculated_value:.2f}")
    row[name] = calculated_value

# Regular button (not form button)
if st.button("💾 Save Row", type="primary", key=f"{form_key}_submit"):
    submitted = True
```

## How It Works Now

### Live Calculation Flow:
1. **User enters value** in a field (e.g., "100" in "Stream A")
2. **Session state updates immediately** (Streamlit detects widget change)
3. **Page re-renders** 
4. **Formula evaluates using CURRENT values** from session state
5. **Calculated field displays updated value** (e.g., "100.00")
6. **User sees result in real-time** before clicking Save

### User Experience:
- **Before**: Enter data → Click Save → See calculations
- **After**: Enter data → See calculations instantly → Click Save when ready

## Benefits

✅ **Live Preview**: Users see calculated values as they type
✅ **Instant Feedback**: No need to save to see results
✅ **Better UX**: Users know values are correct before saving
✅ **Formula Debugging**: Users can see which fields affect the calculation

## Technical Details

### Session State Management:
```python
# Initialize
form_key = f"custom_tanker_tab_form_{table_name}_{loc.id}"
if form_key not in st.session_state:
    st.session_state[form_key] = {}

# Use
row = st.session_state[form_key]
row[name] = widget_value  # Auto-updates on widget change

# Clean up after save
if form_key in st.session_state:
    del st.session_state[form_key]
```

### Widget Keys:
- Each widget gets a unique key: `{form_key}_input_{i}`
- This allows Streamlit to track changes and update session state

### Formula Evaluation:
- Uses existing `_evaluate_formula()` function
- Evaluates on EVERY page render (after Streamlit detects change)
- Supports: sum, subtract, multiply, divide, percentage, maximum, minimum, average

## Example Scenario

### Configuration (Page Customization):
- **Column A**: "Stream A" (type: number)
- **Column B**: "Stream B" (type: number)
- **Column C**: "Total" (type: calculated, formula: sum(Stream A, Stream B))

### User Experience:
```
User enters "50" in Stream A
  ↓
Page re-renders
  ↓
Formula evaluates: sum(50) = 50
  ↓
"Total" field shows: 50.00

User enters "30" in Stream B
  ↓
Page re-renders
  ↓
Formula evaluates: sum(50, 30) = 80
  ↓
"Total" field shows: 80.00

User clicks "Save Row"
  ↓
Data saved with: Stream A=50, Stream B=30, Total=80.00
  ↓
Session state cleared
  ↓
Form reset, ready for next entry
```

## Files Modified
- `app_pages/tanker_transactions.py` - Function: `_render_custom_tanker_tab()`

## What Stayed Intact
- All other functionality remains unchanged
- Save logic unchanged
- Validation logic unchanged
- Database operations unchanged
- Formula evaluation logic unchanged
- Audit logging unchanged
- Error handling unchanged

## Testing
✅ Syntax verified - No errors
✅ Form structure fixed - Enables live updates
✅ Session state properly managed
✅ Cleanup after save implemented

## Notes
- This fix applies only to Tanker Transactions custom tabs
- Tank Transactions doesn't have custom tabs yet
- If Tank Transactions gets custom tabs in the future, apply the same fix
- The formula evaluator (`_evaluate_formula`) remains in `tank_transactions.py` for backward compatibility
