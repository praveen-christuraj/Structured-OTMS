# Page Customization

## Purpose

Page Customization lets administrators configure **location-specific** UI and dynamic data structures without changing code, including:
- dynamic tables (Produced Water / Production / Meter configuration, depending on build)
- Custom Tabs on Tank Transactions and Tanker Transactions
- YADE Tracking customization (tables, columns, filters)

## Who can access

- Admin roles with management access.

## Custom Tabs (Tank / Tanker Transactions)

Use this feature to create new tabs with your own columns.
Each custom tab can create its own database table and become available for reporting.

Reference:
- `Documentation/Custom_Tabs_Feature_Guide.txt`
- `Documentation/Custom_Tabs_Quick_Reference.txt`

## Dynamic tables and calculated columns

You can define:
- column headers and data types
- required fields
- computed columns using formulas (where enabled)

Reference:
- `Documentation/Custom_Table_Editing_System.txt`
- `Documentation/Custom_Column_Calculations_Guide.txt`

## Audit logging

- Creating/updating/deleting custom tabs and dynamic table definitions is recorded in the audit log.

