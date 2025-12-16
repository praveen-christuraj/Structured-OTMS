# Stock Analysis Customization

## Purpose

Build a strong analytics engine for Stock Analysis per location by defining:
- analytics tabs (each tab = one analysis)
- datasets produced by joining multiple database tables
- selected output columns and computed columns
- optional widgets (charts/metrics/tables)
- optional materialization (write results into a new database table)

## Who can access

- Admin roles (per policy).

## How to create a new Stock Analysis tab (step-by-step)

1. Set the Active Location on `Home` (this is the location you are configuring)
2. Open `Stock Analysis Customization`
3. Select **New analysis tab**
4. Fill **Tab Info** (name/description/active)
5. Build the dataset:
   - choose the **primary table**
   - add additional tables with aliases
   - define joins (how tables relate)
6. Define output columns:
   - pick source fields (`alias.column`)
   - add computed columns (formula)
7. Add widgets (optional):
   - widget title
   - chart type
   - x-axis field (category/date)
   - metric field (numeric value)
8. Preview to validate results
9. Save

## Materialize (optional)

Use materialization when you want a physical database table for:
- reuse in reporting
- performance
- exporting a stable dataset

## Deleting a tab

- The tab configuration can be deleted.
- Optionally, the materialized table can also be dropped.

## Related page

- `Documentation/User_Manual/Pages/Stock_Analysis.md`

