# Asset Management

## Purpose

Asset Management is used to maintain master data such as:
- tanks (per location)
- vessels and vessel-to-location assignments
- FSO assignment to location
- tankers (master list)
- YADE barges (shared master list)
- ASTM Table 11 (density/volume conversion reference)

## Who can access

- Admin roles (per policy).

## Key notes

- Tanks are **per location** and are required before Tank Transactions can be used at that location.
- Vessels/FSO can be assigned to locations for operations workflows.
- Tankers and YADE barges may be shared master lists depending on configuration.

## Head Office behavior

If the Active Location is a **Head Office** location:
- tank creation and location-specific assignments are disabled
- switch Active Location to an operating terminal to manage assets

## Audit logging

- Creating/updating/deleting assets is recorded in the audit log.

