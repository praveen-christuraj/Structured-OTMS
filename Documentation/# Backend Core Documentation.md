# Backend Core Documentation

## 1. Database Module (`db.py`)

### Overview
**File Name:** `db.py`
**Purpose:** 
This module acts as the Data Access Layer. It configures the SQLAlchemy connection, manages database sessions, and handles lightweight schema migrations (adding columns to existing tables) without external tools like Alembic.

### Configuration
- **Default DB:** SQLite (`otms.db`)
- **Environment Variable:** `DB_URL` (can be overridden in `.env`).
- **Settings:** `check_same_thread=False` is used for SQLite to allow multi-threaded access in Streamlit.

### Key Functions

#### `get_session()`
- **Description:** Creates and returns a new database session.
- **Usage:** Used in `with get_session() as session:` blocks throughout the app.
- **Returns:** `sqlalchemy.orm.Session`

#### `init_db()`
- **Description:** Initializes the database.
- **Logic:** 
  1. Creates tables defined in `models.py` if they don't exist.
  2. Calls `_ensure_schema_updates()` to patch existing tables.

#### `_ensure_schema_updates()`
- **Description:** Internal utility for "Hot-Fix" migrations.
- **Purpose:** Checks existing tables for missing columns (e.g., `supervisor_code_hash` in `users` or `net_rece_disp_bbls` in `otr_records`) and runs `ALTER TABLE` commands if they are missing. This ensures the app works even if the database file is from an older version.

---

## 2. Authentication Module (`auth.py`)

### Overview
**File Name:** `auth.py`
**Purpose:** 
Handles User Identity and Access Management (IAM). It bridges the gap between the UI login form and the Database `User` model. It enforces Role-Based Access Control (RBAC) logic regarding Locations.

### Logic Rules
1.  **Admins/Managers:** Are global users (Location ID is `None`).
2.  **Supervisors/Operators:** Must be tied to a specific Location ID.
3.  **Password Storage:** Uses `bcrypt` hashing.

### Key Functions (Class: `AuthManager`)

#### `authenticate(session, username, password, ...)`
- **Description:** Validates credentials against the database.
- **Logic:**
  1. Checks if account is locked via `SecurityManager`.
  2. Verifies password hash.
  3. Updates `last_login` timestamp.
  4. Logs the attempt.
- **Returns:** User Dictionary (safe for session state) or `None`.

#### `create_user(...)`
- **Description:** Registers a new user.
- **Validation:** Enforces role constraints (e.g., "Supervisors must have a supervisor code").
- **Returns:** Dictionary representation of the new user.

#### `transfer_user_to_location(session, user_id, new_location_id)`
- **Description:** Moves a non-admin user from one site to another.
- **Constraint:** Cannot transfer Admins (as they are already global).

#### `can_access_location(user_dict, location_id)`
- **Description:** Authorization check.
- **Logic:** 
  - Returns `True` if user is Admin/Manager.
  - Returns `True` if user's assigned location matches `location_id`.
  - Returns `False` otherwise.

#### `set_supervisor_code(session, user_id, new_code)`
- **Description:** Sets a hashed override code for a specific supervisor, allowing them to approve sensitive transactions.

---

## 3. Security Module (`security.py`)

### Overview
**File Name:** `security.py`
**Purpose:** 
Enforces security policies (Password strength, Brute-force protection, Session timeouts) and maintains the Audit Trail.

### Security Policies (Constants)
- **Min Password Length:** 8 characters
- **Max Failed Attempts:** 5 (locks account)
- **Lockout Duration:** 30 minutes
- **Session Timeout:** 30 minutes (sliding window)
- **Password Expiry:** 90 days

### Key Functions (Class: `SecurityManager`)

#### `log_audit(session, username, action, ...)`
- **Description:** The central logging function for compliance.
- **Features:** 
  - Captures Actor, Action, Resource (Target), and Timestamp.
  - Handles timezone conversion if `timezone_utils` is present.
  - Writes to `audit_log` table.

#### `validate_password_strength(password)`
- **Description:** Enforces complexity rules using Regex.
- **Rules:** Requires Uppercase, Lowercase, Number, and Special Character.

#### `is_session_expired(user_dict)`
- **Description:** Checks if the user has been idle longer than `SESSION_TIMEOUT_MINUTES`.

#### `verify_supervisor_code(code, supervisor_username)`
- **Description:** Validates a transaction override code.
- **Logic:** 
  - If `supervisor_username` is provided, verifies against that specific user's hashed code.
  - Fallback: Checks against environment variable `SUPERVISOR_CODE`.

#### `log_login_attempt(...)`
- **Description:** Detailed logging for security analysis.
- **Features:** Captures IP Address, User Agent, Device Type, and Failure Reason (if any).

### Dependencies
- **Internal:** `db`, `models`
- **External:** `bcrypt` (hashing), `sqlalchemy`
- **Optional:** `ip_service` (for geo-locating IP addresses in logs)