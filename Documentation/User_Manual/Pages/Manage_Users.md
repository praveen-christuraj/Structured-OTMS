# Manage Users

## Purpose

Create and manage users, including:
- roles (operator/supervisor/manager/admin-it/admin-operations)
- assigned location
- activation/deactivation
- password and 2FA policy flags
- export operations access flag (where used)

## Who can access

- Admin roles with management access.

## Create a new user

1. Open `Manage Users`
2. Fill in username, full name, and password
3. Choose a role
4. Assign a location (if applicable)
5. Set policy flags:
   - mandatory password change on first login
   - mandatory 2FA
6. Save

## Update an existing user

1. Select the user in **User Maintenance**
2. Update role/location/name and save

## Common admin actions

- Activate/deactivate a user account
- Reset 2FA for a user (when a device is lost)
- Force password reset / enforce password change

## Audit logging

- User creation, updates, activation changes, and security resets are recorded in the audit log.

## Related documentation

- `Documentation/ROLE_BASED_ACCESS_CONTROL.md`
- `Documentation/PASSWORD_2FA_MANAGEMENT_COMPLETE.md`

