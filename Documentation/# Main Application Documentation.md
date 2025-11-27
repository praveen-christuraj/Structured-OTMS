# Main Application Documentation

## 1. Overview
**File Name:** `app.py`
**Type:** Application Entry Point
**Purpose:** 
This file serves as the central controller for the OTMS (Oil/Operations Terminal Management System). It orchestrates the entire application lifecycle, including user authentication, session management, sidebar navigation, and page routing.

## 2. Architecture & Logic Flow
This file does not handle business logic (like saving data) directly. Instead, it acts as a "Traffic Cop":

1.  **Startup Initialization:**
    - Initializes the Database (`db.init_db`).
    - Checks/Creates a default Admin user (`ensure_default_admin_user`) if the DB is empty.
    - Injects global CSS styles (Glassmorphism UI).

2.  **Authentication Layer:**
    - Checks `st.session_state` for a logged-in user.
    - **If No User:** Renders the Login Page (`app_pages.login`).
    - **If User Exists:** Checks `SecurityManager` for session timeouts (30-minute sliding window).

3.  **Navigation Construction:**
    - Calls `get_pages(user, location_id)` to determine which sidebar buttons to show.
    - Filters pages based on:
        - **User Role:** (e.g., Admins see "Manage Users", Operators do not).
        - **Location Config:** (e.g., "Tanker Transactions" might be disabled for Location A).
        - **Module Existence:** Checks if the python file actually exists before showing the link.

4.  **Routing:**
    - Reads `st.session_state["current_page"]`.
    - Imports and executes the corresponding `render_*` function (e.g., `render_home_page()`).

## 3. Key Functions

### `main()`
- **Description:** The primary execution loop.
- **Logic:** Setup -> Auth Check -> Timeout Check -> Render Sidebar -> Render Active Page.

### `ensure_default_admin_user()`
- **Description:** Bootstraps the system.
- **Default Credentials:** `admin` / `Admin@123`
- **Trigger:** Runs only if `User` table count is 0.

### `get_pages(user, active_location_id)`
- **Description:** The core permission logic for the sidebar.
- **Returns:** A list of strings (Page Titles) that the specific user is allowed to click.

### `_render_sidebar_nav(...)`
- **Description:** Visual component.
- **Features:**
    - Displays Logo.
    - Displays User Profile (Name, Role, Location).
    - Renders Logout button with confirmation logic.
    - Renders Navigation buttons with "Active State" highlighting.

## 4. Dependencies
- **Streamlit:** Core framework.
- **Database:** `db`, `models`
- **Security:** `security`, `auth`, `permission_manager`
- **Configuration:** `location_config`
- **Pages:** Imports functions from `app_pages.*`