# UI Components Quick Reference

## Import Statement
```python
from ui_components import (
    apply_custom_css,
    DashboardCard,
    FormBuilder,
    Notifications,
    TableDisplay
)
```

---

## Common Patterns

### Page Header
```python
st.markdown("""
<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            padding: 2.5rem; border-radius: 12px; margin-bottom: 2rem;'>
    <h1 style='color: white; margin: 0; font-size: 2.5rem;'>🎯 Page Title</h1>
    <p style='color: rgba(255,255,255,0.9); margin: 0.5rem 0 0 0; font-size: 1.1rem;'>
        Page Description
    </p>
</div>
""", unsafe_allow_html=True)
```

### Metrics Row
```python
col1, col2, col3, col4 = st.columns(4)
with col1:
    DashboardCard.metric_card("Title", "100", "Subtitle", "📊", "blue")
with col2:
    DashboardCard.metric_card("Title", "50", "Subtitle", "✅", "green")
with col3:
    DashboardCard.metric_card("Title", "25", "Subtitle", "⚠️", "orange")
with col4:
    DashboardCard.metric_card("Title", "5", "Subtitle", "❌", "red")
```

### Form with Validation
```python
FormBuilder.section_header("Form Title", "Description")

with st.form("form_key"):
    col1, col2 = FormBuilder.form_row(2)
    with col1:
        field1 = FormBuilder.input_field("Field 1", "f1", required=True)
    with col2:
        field2 = FormBuilder.select_field("Field 2", ["Opt1", "Opt2"], "f2", required=True)
    
    submitted = FormBuilder.form_submit_button("Submit", "✓")
    
    if submitted:
        if not field1:
            Notifications.error_alert("Field 1 is required", "Validation Error")
        else:
            try:
                # Process data
                Notifications.success_alert("Data saved!", "Success")
            except Exception as e:
                Notifications.error_alert(str(e), "Error")
```

### Data Table with Search
```python
import pandas as pd

df = pd.DataFrame({...})
TableDisplay.display_data_table(df, "Table Title", searchable=True)
```

---

## Color Guide

| Color    | Hex Code | Use Case                    |
|----------|----------|-----------------------------|
| blue     | #667eea  | Info, general metrics       |
| green    | #28a745  | Success, active, positive   |
| red      | #dc3545  | Error, failed, critical     |
| orange   | #ff9800  | Warning, pending, attention |
| purple   | #764ba2  | Special, totals, highlights |
| teal     | #17a2b8  | Neutral info, secondary     |

---

## Component Cheat Sheet

### DashboardCard
```python
DashboardCard.metric_card(title, value, subtitle, icon, color)
DashboardCard.info_card(title, content, icon)
DashboardCard.status_badge(status, label)  # status: active/inactive/pending/failed/completed
```

### FormBuilder
```python
FormBuilder.section_header(title, description)
FormBuilder.input_field(label, key, placeholder, input_type, required)  # type: text/number/password
FormBuilder.select_field(label, options, key, required)
FormBuilder.date_field(label, key, required)
FormBuilder.textarea_field(label, key, placeholder, rows, required)
FormBuilder.form_row(num_columns)  # Returns columns
FormBuilder.form_submit_button(label, icon)
```

### Notifications
```python
Notifications.success_alert(message, title)
Notifications.error_alert(message, title)
Notifications.warning_alert(message, title)
Notifications.info_alert(message, title)
```

### TableDisplay
```python
TableDisplay.display_data_table(dataframe, title, searchable)
TableDisplay.display_stats_row(stats_dict)
```

---

## Search & Replace Patterns

### Replace Standard Inputs
```python
# OLD
st.text_input("Username")
st.text_input("Password", type="password")
st.number_input("Age", min_value=0)
st.selectbox("Role", ["Admin", "User"])
st.date_input("Date")
st.text_area("Notes")

# NEW
FormBuilder.input_field("Username", "username_key", required=True)
FormBuilder.input_field("Password", "password_key", input_type="password", required=True)
FormBuilder.input_field("Age", "age_key", input_type="number", required=True)
FormBuilder.select_field("Role", ["Admin", "User"], "role_key", required=True)
FormBuilder.date_field("Date", "date_key", required=True)
FormBuilder.textarea_field("Notes", "notes_key", rows=4)
```

### Replace Alerts
```python
# OLD
st.success("Success message")
st.error("Error message")
st.warning("Warning message")
st.info("Info message")

# NEW
Notifications.success_alert("Success message", "Success")
Notifications.error_alert("Error message", "Error")
Notifications.warning_alert("Warning message", "Warning")
Notifications.info_alert("Info message", "Info")
```

### Replace Dataframes
```python
# OLD
st.dataframe(df, use_container_width=True)

# NEW
TableDisplay.display_data_table(df, "Table Title", searchable=True)
```

---

## Icons Reference

Common emoji icons for different contexts:

```python
# Actions
"✓" "✔️" "✅"  # Success/Complete
"✗" "✖️" "❌"  # Cancel/Error
"➕" "+"       # Add/Create
"➖" "-"       # Remove
"✏️" "📝"     # Edit
"🗑️"          # Delete
"🔍" "🔎"     # Search
"⚙️"          # Settings
"🔄"          # Refresh/Sync

# Status
"✅"          # Active/Success
"⛔"          # Inactive/Blocked
"⏳"          # Pending/Loading
"⚠️"          # Warning
"ℹ️"          # Info

# Objects
"👤" "👥"     # User(s)
"📊" "📈"     # Charts/Data
"🛢️"          # Tank
"⛴️"          # Vessel
"🚚"          # Truck
"📦"          # Package
"📄" "📋"     # Document
"🔐" "🔒"     # Security
"📍"          # Location
"🏠"          # Home

# Operations
"📥"          # Receipt/Download
"📤"          # Dispatch/Upload
"💾"          # Save
"🔗"          # Link
"📧"          # Email
```

---

## Example Implementations

### Login Form
```python
from ui_components import FormBuilder, Notifications, apply_custom_css

def render_login():
    apply_custom_css()
    st.markdown("""<div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 2.5rem; border-radius: 12px; margin-bottom: 2rem; text-align: center;'>
        <h1 style='color: white; margin: 0;'>🔐 Login</h1></div>""", unsafe_allow_html=True)
    
    with st.form("login"):
        username = FormBuilder.input_field("Username", "user", required=True)
        password = FormBuilder.input_field("Password", "pass", input_type="password", required=True)
        submitted = FormBuilder.form_submit_button("Login", "🔐")
        
        if submitted:
            if authenticate(username, password):
                Notifications.success_alert("Welcome!", "Login Successful")
            else:
                Notifications.error_alert("Invalid credentials", "Login Failed")
```

### Dashboard Page
```python
from ui_components import DashboardCard, TableDisplay, apply_custom_css

def render_dashboard():
    apply_custom_css()
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        DashboardCard.metric_card("Users", "245", "Active", "👥", "blue")
    with col2:
        DashboardCard.metric_card("Transactions", "1,234", "Today", "📊", "green")
    with col3:
        DashboardCard.metric_card("Pending", "15", "Awaiting", "⏳", "orange")
    with col4:
        DashboardCard.metric_card("Errors", "3", "Last hour", "❌", "red")
    
    # Table
    df = get_data()
    TableDisplay.display_data_table(df, "Recent Activity", searchable=True)
```

### Settings Form
```python
from ui_components import FormBuilder, Notifications

def render_settings():
    FormBuilder.section_header("User Settings", "Update your preferences")
    
    with st.form("settings"):
        col1, col2 = FormBuilder.form_row(2)
        with col1:
            name = FormBuilder.input_field("Full Name", "name", required=True)
            email = FormBuilder.input_field("Email", "email", required=True)
        with col2:
            role = FormBuilder.select_field("Role", ["Admin", "User"], "role", required=True)
            location = FormBuilder.select_field("Location", ["HQ", "Branch"], "loc")
        
        notifications = st.checkbox("Enable email notifications")
        submitted = FormBuilder.form_submit_button("Save Settings", "💾")
        
        if submitted:
            save_settings(name, email, role, location, notifications)
            Notifications.success_alert("Settings saved successfully!", "Success")
```

---

**Quick Tip:** Copy these patterns and modify them for your specific needs!
