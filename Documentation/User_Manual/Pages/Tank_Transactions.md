# Tank Transactions

## Purpose

Capture tank-related operational entries for the **Active Location**, including (depending on enabled tabs):
- Tank Entry (dip/water/temperature/quality and stock calculations)
- Meter Records
- Condensate Records
- Produced Water Records
- Production (if enabled)

Tab visibility is controlled by `Location Settings`.

## Who can access

- Operational roles (operator/supervisor/admin-operations) when enabled for the location.
- Managers are typically view-only.
- Admin-IT typically does not access operational pages.

## Head Office behavior

If the Active Location is **Head Office**:
- this page will ask you to switch Active Location to an operating terminal (HO has no tanks/assets).

## Before you start

1. Select the correct Active Location on `Home`
2. Ensure tanks exist for the location (`Asset Management → Tanks`)
3. Ensure required dropdown catalogs are configured (`Location Settings → Operations`)

## How to make a Tank Entry (typical)

1. Open `Tank Transactions`
2. Select the **Tank Entry** tab
3. Choose a tank and operation
4. Enter the required measurements (dip/water/temp/BS&W/etc. as configured)
5. Save the entry

## Deletion / approvals (if enabled)

Deletion may require approvals depending on role and your deployment policy.
Reference:
- `Documentation/DELETION_APPROVAL_QUICK_START.md`

## Custom Tabs

If your location has Custom Tabs configured, they appear as additional tabs on this page.
Reference:
- `Documentation/Custom_Tabs_Feature_Guide.txt`

