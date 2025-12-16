# Customization Concepts (Admin)

OTMS supports deep per-location customization. This section explains where each type of customization lives.

## Location Settings

Use `Location Settings` to control:
- which pages are enabled/disabled for a location
- which Tank Transactions tabs are visible
- operations catalogs used by dropdowns (destinations, berths, etc.)

## Dashboard Customization

Use `Dashboard Customization` to:
- configure dashboard widgets and layout per location
- map visuals and cards to data sources

## Page Customization

Use `Page Customization` to:
- define dynamic tables (Produced Water, Production, etc.)
- create and manage Custom Tabs for Tank Transactions and Tanker Transactions
- configure YADE Tracking tables/columns/filters

Reference:
- `Documentation/Custom_Tabs_Feature_Guide.txt`
- `Documentation/Custom_Table_Editing_System.txt`
- `Documentation/Custom_Column_Calculations_Guide.txt`

## Report Customization

Use `Report Customization` to:
- create configurable reports based on available data sources
- include custom tab tables as sources

## Stock Analysis Customization

Use `Stock Analysis Customization` to:
- create analytics tabs per location by joining database tables
- define calculated output columns
- add widgets (charts, KPIs)
- optionally materialize results into a physical database table

