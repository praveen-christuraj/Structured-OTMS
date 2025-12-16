# OTMS Overview

## What OTMS is for

OTMS (Oil Terminal Management System) is a location-based operations application used to:

- Capture operational entries (tank, tanker, vessel/FSO, and YADE workflows)
- Produce operational views and reports (OTR, Material Balance, Reporting)
- Support configurable dashboards and analytics (Dashboard Customization, Stock Analysis)
- Enforce role-based access control and maintain a complete audit trail

## Navigation basics

- Use the left sidebar to navigate between pages.
- Most operational pages require an **Active Location** (selected on **Home**).
- Some pages are available only to administrators (Manage Users, Manage Locations, Location Settings, Customization pages).

## Core concepts

### Active Location
The **Active Location** is the location context used across pages for:
- loading assets and transactions
- applying per-location page visibility and configuration
- scoping reports/analytics

### Head Office vs Operating Location
- **Operating location:** Has assets (tanks) and creates transactions.
- **Head Office (HO):** Administrative hub that does not hold assets on-site. HO users typically switch the Active Location to view other locations.

See `Documentation/User_Manual/02_Locations_and_Head_Office.md`.

### Audit trail
Important actions are recorded in the **Audit Log**, including config changes and create/update/delete events for operational records.

See `Documentation/User_Manual/03_Audit_and_Logging.md`.

