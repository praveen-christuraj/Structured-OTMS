# UI Components Implementation Guide

## Overview
This guide demonstrates how to use the new professional UI components from the `ui_components` package to create attractive, consistent, and modern interfaces across all OTMS pages.

## Component Library

### 1. **apply_custom_css()**
Apply global custom CSS styling to enhance the visual appearance of your Streamlit app.

```python
from ui_components import apply_custom_css

def render_my_page():
    apply_custom_css()
    # ... rest of your page code
```

**Features:**
- Professional gradient buttons with hover effects
- Rounded input fields and containers
- Modern color scheme
- Enhanced shadows and transitions

---

### 2. **DashboardCard**
Display metrics and statistics in professional card layouts.

#### metric_card()
```python
from ui_components import DashboardCard

# Basic usage
DashboardCard.metric_card(
    title="Total Users",
    value="245",
    subtitle="Active this month",
    icon="👥",
    color="blue"
)

# Available colors: blue, green, red, orange, purple, teal
```

#### info_card()
```python
DashboardCard.info_card(
    title="Important Notice",
    content="Your monthly report is ready for review.",
    icon="ℹ️"
)
```

#### status_badge()
```python
DashboardCard.status_badge(
    status="active",  # active, inactive, pending, failed, completed
    label="System Active"
)
```

**Example: Dashboard Summary**
```python
col1, col2, col3, col4 = st.columns(4)

with col1:
    DashboardCard.metric_card("Total Tanks", "12", "All locations", "🛢️", "blue")

with col2:
    DashboardCard.metric_card("Active", "10", "Operating", "✅", "green")

with col3:
    DashboardCard.metric_card("Maintenance", "2", "Scheduled", "🔧", "orange")

with col4:
    DashboardCard.metric_card("Stock Level", "85%", "Capacity", "📊", "purple")
```

---

### 3. **FormBuilder**
Create consistent, professional forms with labeled inputs.

#### section_header()
```python
FormBuilder.section_header(
    title="User Information",
    description="Enter the user's basic details"
)
```

#### input_field()
```python
# Text input
username = FormBuilder.input_field(
    label="Username",
    key="user_username",
    placeholder="Enter username",
    input_type="text",  # text, number, password
    required=True
)

# Password input
password = FormBuilder.input_field(
    label="Password",
    key="user_password",
    placeholder="Enter password",
    input_type="password",
    required=True
)
```

#### select_field()
```python
role = FormBuilder.select_field(
    label="User Role",
    options=["Admin", "Manager", "Operator"],
    key="user_role",
    required=True
)
```

#### date_field()
```python
transaction_date = FormBuilder.date_field(
    label="Transaction Date",
    key="trans_date",
    required=True
)
```

#### textarea_field()
```python
notes = FormBuilder.textarea_field(
    label="Additional Notes",
    key="trans_notes",
    placeholder="Enter any additional information...",
    rows=4,
    required=False
)
```

#### form_row()
```python
# Create two-column layout
col1, col2 = FormBuilder.form_row(2)

with col1:
    first_name = FormBuilder.input_field("First Name", "fname", required=True)

with col2:
    last_name = FormBuilder.input_field("Last Name", "lname", required=True)
```

#### form_submit_button()
```python
submitted = FormBuilder.form_submit_button("Save Changes", "✓")
```

**Complete Form Example:**
```python
from ui_components import FormBuilder, Notifications

FormBuilder.section_header("Create New Tank", "Add a new tank to the location")

with st.form("create_tank_form"):
    col1, col2 = FormBuilder.form_row(2)
    
    with col1:
        tank_name = FormBuilder.input_field("Tank Name", "tank_name", "e.g., Tank-01", required=True)
        capacity = FormBuilder.input_field("Capacity (BBL)", "tank_capacity", input_type="number", required=True)
    
    with col2:
        product = FormBuilder.select_field("Product Type", ["Crude Oil", "Diesel", "Gasoline"], "tank_product", required=True)
        status = FormBuilder.select_field("Status", ["Active", "Inactive", "Maintenance"], "tank_status", required=True)
    
    notes = FormBuilder.textarea_field("Notes", "tank_notes", "Additional information...")
    
    submitted = FormBuilder.form_submit_button("Create Tank", "✓")
    
    if submitted:
        if not tank_name or not capacity:
            Notifications.error_alert("Please fill in all required fields", "Validation Error")
        else:
            # Save tank logic here
            Notifications.success_alert(f"Tank '{tank_name}' created successfully!", "Success")
```

---

### 4. **Notifications**
Display professional alert messages for user feedback.

#### success_alert()
```python
Notifications.success_alert(
    message="Your data has been saved successfully.",
    title="Success"
)
```

#### error_alert()
```python
Notifications.error_alert(
    message="Failed to process your request. Please try again.",
    title="Error"
)
```

#### warning_alert()
```python
Notifications.warning_alert(
    message="Your session will expire in 5 minutes.",
    title="Warning"
)
```

#### info_alert()
```python
Notifications.info_alert(
    message="Please review the updated terms and conditions.",
    title="Info"
)
```

**Example: Form Validation Feedback**
```python
if submitted:
    if not username or not password:
        Notifications.error_alert(
            "Please enter both username and password.",
            "Login Failed"
        )
        return
    
    # Authentication logic
    if authenticated:
        Notifications.success_alert(
            f"Welcome back, {username}!",
            "Login Successful"
        )
    else:
        Notifications.error_alert(
            "Invalid credentials. Please try again.",
            "Authentication Failed"
        )
```

---

### 5. **TableDisplay**
Display data tables with professional styling and optional search functionality.

#### display_data_table()
```python
import pandas as pd
from ui_components import TableDisplay

# Basic table
df = pd.DataFrame({
    'Name': ['John', 'Jane', 'Bob'],
    'Role': ['Admin', 'Manager', 'Operator'],
    'Status': ['Active', 'Active', 'Inactive']
})

TableDisplay.display_data_table(
    dataframe=df,
    title="User List",
    searchable=True
)
```

#### display_stats_row()
```python
stats = {
    "Total Records": 150,
    "Active": 120,
    "Inactive": 30
}

TableDisplay.display_stats_row(stats)
```

**Complete Data View Example:**
```python
# Summary statistics
col1, col2, col3, col4 = st.columns(4)
with col1:
    DashboardCard.metric_card("Total Records", str(len(df)), "All transactions", "📊", "blue")
with col2:
    DashboardCard.metric_card("Completed", str(completed_count), "Success rate: 95%", "✅", "green")
with col3:
    DashboardCard.metric_card("Pending", str(pending_count), "Awaiting approval", "⏳", "orange")
with col4:
    DashboardCard.metric_card("Failed", str(failed_count), "Requires attention", "❌", "red")

st.markdown("---")

# Data table with search
TableDisplay.display_data_table(
    dataframe=df,
    title="Transaction History",
    searchable=True
)
```

---

## Page Header Template

Create professional page headers with gradient backgrounds:

```python
def render_my_page(active_location_id, user):
    apply_custom_css()
    
    # Modern gradient header
    st.markdown("""
    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 2.5rem; border-radius: 12px; margin-bottom: 2rem;'>
        <h1 style='color: white; margin: 0; font-size: 2.5rem;'>📊 Page Title</h1>
        <p style='color: rgba(255,255,255,0.9); margin: 0.5rem 0 0 0; font-size: 1.1rem;'>
            Page subtitle or description
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Page content here...
```

---

## Complete Page Example

Here's a complete example of a professional page using all UI components:

```python
import streamlit as st
from datetime import date
from ui_components import (
    apply_custom_css,
    DashboardCard,
    FormBuilder,
    Notifications,
    TableDisplay
)

def render_transactions_page(active_location_id, user):
    """Professional transaction management page"""
    apply_custom_css()
    
    # Header
    st.markdown("""
    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 2.5rem; border-radius: 12px; margin-bottom: 2rem;'>
        <h1 style='color: white; margin: 0; font-size: 2.5rem;'>🛢️ Tank Transactions</h1>
        <p style='color: rgba(255,255,255,0.9); margin: 0.5rem 0 0 0; font-size: 1.1rem;'>
            Manage tank receipts and dispatches
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Summary cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        DashboardCard.metric_card("Today's Transactions", "15", "+3 from yesterday", "📊", "blue")
    with col2:
        DashboardCard.metric_card("Total Receipt", "25,450 BBL", "This month", "📥", "green")
    with col3:
        DashboardCard.metric_card("Total Dispatch", "22,100 BBL", "This month", "📤", "orange")
    with col4:
        DashboardCard.metric_card("Net Balance", "+3,350 BBL", "Positive flow", "💹", "purple")
    
    st.markdown("---")
    
    # Tabs for different sections
    tab1, tab2, tab3 = st.tabs(["➕ New Transaction", "📋 View History", "📊 Analytics"])
    
    with tab1:
        FormBuilder.section_header("Create New Transaction", "Enter transaction details below")
        
        with st.form("new_transaction_form"):
            col1, col2 = FormBuilder.form_row(2)
            
            with col1:
                tank = FormBuilder.select_field("Tank", ["Tank-01", "Tank-02", "Tank-03"], "trans_tank", required=True)
                operation = FormBuilder.select_field("Operation", ["Receipt", "Dispatch"], "trans_op", required=True)
                volume = FormBuilder.input_field("Volume (BBL)", "trans_vol", input_type="number", required=True)
            
            with col2:
                trans_date = FormBuilder.date_field("Transaction Date", "trans_date", required=True)
                ticket_id = FormBuilder.input_field("Ticket ID", "trans_ticket", required=True)
                temperature = FormBuilder.input_field("Temperature (°F)", "trans_temp", input_type="number", required=True)
            
            notes = FormBuilder.textarea_field("Notes", "trans_notes", "Additional information...", rows=3)
            
            submitted = FormBuilder.form_submit_button("Save Transaction", "✓")
            
            if submitted:
                if not all([tank, operation, volume, trans_date, ticket_id]):
                    Notifications.error_alert("Please fill in all required fields", "Validation Error")
                else:
                    # Save logic here
                    Notifications.success_alert(
                        f"Transaction saved successfully! Ticket: {ticket_id}",
                        "Transaction Created"
                    )
    
    with tab2:
        FormBuilder.section_header("Transaction History", "View and search past transactions")
        
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            filter_tank = st.selectbox("Filter by Tank", ["All Tanks", "Tank-01", "Tank-02", "Tank-03"])
        with col2:
            filter_op = st.selectbox("Filter by Operation", ["All Operations", "Receipt", "Dispatch"])
        with col3:
            filter_date = st.date_input("From Date", value=date.today())
        
        # Sample data
        import pandas as pd
        df = pd.DataFrame({
            'Date': ['2024-01-15', '2024-01-14', '2024-01-13'],
            'Ticket ID': ['TKT-001', 'TKT-002', 'TKT-003'],
            'Tank': ['Tank-01', 'Tank-02', 'Tank-01'],
            'Operation': ['Receipt', 'Dispatch', 'Receipt'],
            'Volume (BBL)': [5000, 3500, 4200],
            'Status': ['✅ Complete', '✅ Complete', '⏳ Pending']
        })
        
        TableDisplay.display_data_table(df, title="Recent Transactions", searchable=True)
    
    with tab3:
        st.info("Analytics dashboard coming soon...")

# Run the page
if __name__ == "__main__":
    render_transactions_page(
        active_location_id=st.session_state.get("active_location_id"),
        user=st.session_state.get("auth_user")
    )
```

---

## Best Practices

### 1. **Consistent Color Usage**
```python
# Use consistent colors for similar metrics
DashboardCard.metric_card("Success Count", "150", color="green")    # Success
DashboardCard.metric_card("Error Count", "5", color="red")          # Errors
DashboardCard.metric_card("Pending Count", "20", color="orange")    # Warnings
DashboardCard.metric_card("Total Count", "175", color="blue")       # Info
```

### 2. **Form Validation Pattern**
```python
with st.form("my_form"):
    # Form fields
    field1 = FormBuilder.input_field("Field 1", "f1", required=True)
    field2 = FormBuilder.input_field("Field 2", "f2", required=True)
    
    submitted = FormBuilder.form_submit_button("Submit", "✓")
    
    if submitted:
        # Validate
        if not field1 or not field2:
            Notifications.error_alert("All fields are required", "Validation Error")
            return
        
        try:
            # Process data
            save_data(field1, field2)
            Notifications.success_alert("Data saved successfully!", "Success")
        except Exception as e:
            Notifications.error_alert(f"Failed to save: {str(e)}", "Error")
```

### 3. **Progressive Disclosure**
Use tabs and expanders to organize complex pages:

```python
tab1, tab2, tab3 = st.tabs(["📝 Entry", "📋 History", "📊 Reports"])

with tab1:
    # Entry form
    FormBuilder.section_header("New Entry", "Create a new record")
    # ... form here

with tab2:
    # History table
    TableDisplay.display_data_table(df, "History", searchable=True)

with tab3:
    # Reports and analytics
    # ... charts here
```

### 4. **Feedback for All Actions**
Always provide user feedback:

```python
if st.button("Delete Record"):
    try:
        delete_record(record_id)
        Notifications.success_alert("Record deleted successfully", "Deleted")
        st.rerun()
    except Exception as e:
        Notifications.error_alert(f"Failed to delete: {str(e)}", "Error")
```

---

## Migration Checklist

When updating an existing page:

- [ ] Import UI components at the top
- [ ] Add `apply_custom_css()` at the start of render function
- [ ] Replace page title with gradient header
- [ ] Replace `st.text_input()` with `FormBuilder.input_field()`
- [ ] Replace `st.selectbox()` with `FormBuilder.select_field()`
- [ ] Replace `st.date_input()` with `FormBuilder.date_field()`
- [ ] Replace `st.success()` with `Notifications.success_alert()`
- [ ] Replace `st.error()` with `Notifications.error_alert()`
- [ ] Replace `st.warning()` with `Notifications.warning_alert()`
- [ ] Replace `st.info()` with `Notifications.info_alert()`
- [ ] Add `DashboardCard.metric_card()` for key metrics
- [ ] Use `TableDisplay.display_data_table()` for data tables
- [ ] Use `FormBuilder.section_header()` for section titles

---

## Color Reference

### Dashboard Card Colors
- **blue** (#667eea): General information, counts
- **green** (#28a745): Success, active items, positive metrics
- **red** (#dc3545): Errors, failures, alerts
- **orange** (#ff9800): Warnings, pending items
- **purple** (#764ba2): Special metrics, totals
- **teal** (#17a2b8): Info, neutral metrics

### Gradient Headers
```css
/* Primary gradient */
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

/* Success gradient */
background: linear-gradient(135deg, #28a745 0%, #20c997 100%);

/* Warning gradient */
background: linear-gradient(135deg, #ff9800 0%, #ffc107 100%);

/* Info gradient */
background: linear-gradient(135deg, #17a2b8 0%, #0dcaf0 100%);
```

---

## Support

For questions or issues with UI components:
1. Check component docstrings in `ui_components/` folder
2. Review existing implementations in `app_pages/home.py`, `app_pages/login.py`
3. Refer to this guide for examples

---

**Last Updated:** November 28, 2025  
**Version:** 1.0
