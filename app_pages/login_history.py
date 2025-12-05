# login_history.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import streamlit as st
import pandas as pd

from db import get_session
from ui import header
from action_logger_utils import log_export_action
from logger import log_error
from models import User, LoginAttempt
from security import SecurityManager

# Optional IP / timezone helpers
try:
    from ip_service import IPService
except Exception:  # pragma: no cover - if service not present
    class _DummyIPService:
        @staticmethod
        def get_flag_emoji(country: str | None) -> str:
            return "🏳️"
    IPService = _DummyIPService()  # type: ignore

try:
    from timezone_utils import utc_to_local, format_local_datetime, get_local_time  # type: ignore
    TIMEZONE_AVAILABLE = True
except Exception:
    TIMEZONE_AVAILABLE = False


def render_login_history_page(
    active_location_id: int | None,
    user: Dict[str, Any] | None,
) -> None:
    """Render the Login History & Security Monitoring page."""
    header("Login History & Security Monitoring")

    if not user:
        st.error("Please login to access this page.")
        st.stop()

    st.markdown("### 🔐 Login Activity Monitor")

    # =====================================================
    #  FILTERS
    # =====================================================
    col1, col2, col3, col4 = st.columns(4)

    # ----- User filter -----
    with col1:
        with get_session() as s:
            if user["role"] in ["admin-operations", "manager"]:
                all_users: List[User] = s.query(User).order_by(User.username.asc()).all()
                user_options = ["All"] + [u.username for u in all_users]
            else:
                user_options = [user["username"]]

        filter_user = st.selectbox(
            "User",
            user_options,
            key="login_history_user_filter",
        )

    # ----- Success filter -----
    with col2:
        filter_success = st.selectbox(
            "Status",
            ["All", "Success", "Failed"],
            key="login_history_status_filter",
        )

    # ----- Time period -----
    with col3:
        filter_days = st.selectbox(
            "Time Period",
            ["Last 7 days", "Last 30 days", "Last 90 days", "All time"],
            key="login_history_days_filter",
        )

    # ----- 2FA filter -----
    with col4:
        filter_2fa = st.selectbox(
            "2FA Used",
            ["All", "Yes", "No"],
            key="login_history_2fa_filter",
        )

    # =====================================================
    #  QUERY DATA
    # =====================================================
    try:
        with get_session() as s:
            query = s.query(LoginAttempt).order_by(LoginAttempt.timestamp.desc())

            if filter_user != "All":
                query = query.filter(LoginAttempt.username == filter_user)

            if filter_success == "Success":
                query = query.filter(LoginAttempt.success == True)  # noqa: E712
            elif filter_success == "Failed":
                query = query.filter(LoginAttempt.success == False)  # noqa: E712

            if filter_2fa == "Yes":
                query = query.filter(LoginAttempt.two_factor_used == True)  # type: ignore[attr-defined]
            elif filter_2fa == "No":
                query = query.filter(LoginAttempt.two_factor_used == False)  # type: ignore[attr-defined]

            if filter_days != "All time":
                days_map = {
                    "Last 7 days": 7,
                    "Last 30 days": 30,
                    "Last 90 days": 90,
                }
                days = days_map[filter_days]
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                query = query.filter(LoginAttempt.timestamp >= cutoff_date)

            attempts: List[LoginAttempt] = query.limit(500).all()

    except Exception as ex:
        log_error(f"Failed to load login history: {ex}", exc_info=True)
        st.error(f"Failed to load login history: {ex}")

        import traceback
        with st.expander("🔍 Error details"):
            st.code(traceback.format_exc())
        return

    # =====================================================
    #  STATISTICS + TABLE
    # =====================================================
    if not attempts:
        st.info("ℹ️ No login attempts found matching the filters.")

        if TIMEZONE_AVAILABLE:
            current_time = get_local_time()
            st.caption(
                f"⏱️ Current Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')} "
                "(Nigeria Time - WAT)"
            )
        else:
            st.caption(
                f"⏱️ Current Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} (UTC)"
            )
        return

    total_attempts = len(attempts)
    successful_logins = sum(1 for a in attempts if a.success)
    failed_logins = total_attempts - successful_logins
    unique_ips = len({a.ip_address for a in attempts if a.ip_address})

    two_fa_logins = sum(
        1 for a in attempts if getattr(a, "two_factor_used", False)
    )

    st.markdown("---")

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Total Attempts", total_attempts)
    with m2:
        success_pct = (successful_logins / total_attempts * 100) if total_attempts else 0
        st.metric("Successful", successful_logins, delta=f"{success_pct:.1f}%")
    with m3:
        fail_pct = (failed_logins / total_attempts * 100) if total_attempts else 0
        st.metric("Failed", failed_logins, delta=f"{fail_pct:.1f}%", delta_color="inverse")
    with m4:
        st.metric("Unique IPs", unique_ips)
    with m5:
        twofa_pct = (two_fa_logins / successful_logins * 100) if successful_logins else 0
        st.metric("2FA Used", two_fa_logins, delta=f"{twofa_pct:.1f}%")

    st.markdown("---")

    # ---------- Table ----------
    st.markdown("#### 🔐 Recent Login Attempts")

    if TIMEZONE_AVAILABLE:
        st.caption("⏱️ Showing times in **Nigeria Time (WAT - UTC+1)**")
    else:
        st.caption("⏱️ Showing times in **UTC** (install `pytz` for local time).")

    display_rows: List[Dict[str, Any]] = []

    for attempt in attempts[:100]:
        ip_country = getattr(attempt, "ip_country", None) or "Unknown"
        ip_city = getattr(attempt, "ip_city", None) or "Unknown"
        device_type = getattr(attempt, "device_type", None) or "Unknown"
        browser = getattr(attempt, "browser", None) or "Unknown"
        os_name = getattr(attempt, "os", None) or "Unknown"
        two_factor_used = getattr(attempt, "two_factor_used", False)

        flag = IPService.get_flag_emoji(ip_country)

        if attempt.timestamp:
            if TIMEZONE_AVAILABLE:
                timestamp_str = format_local_datetime(  # type: ignore[name-defined]
                    attempt.timestamp,
                    "%Y-%m-%d %H:%M:%S",
                )
            else:
                timestamp_str = attempt.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            timestamp_str = "N/A"

        display_rows.append(
            {
                "Timestamp": timestamp_str,
                "User": attempt.username,
                "Status": "✅ Success" if attempt.success else "❌ Failed",
                "IP Address": attempt.ip_address or "N/A",
                "Location": f"{flag} {ip_city}, {ip_country}",
                "Device": device_type,
                "Browser": browser,
                "OS": os_name,
                "2FA": "✅" if two_factor_used else "✖️",
                "Reason": attempt.failure_reason or "N/A",
            }
        )

    df = pd.DataFrame(display_rows)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=600,
        column_config={
            "Timestamp": st.column_config.TextColumn("Timestamp", width="medium"),
            "User": st.column_config.TextColumn("User", width="small"),
            "Status": st.column_config.TextColumn("Status", width="small"),
            "IP Address": st.column_config.TextColumn("IP Address", width="medium"),
            "Location": st.column_config.TextColumn("Location", width="medium"),
            "Device": st.column_config.TextColumn("Device", width="small"),
            "Browser": st.column_config.TextColumn("Browser", width="small"),
            "OS": st.column_config.TextColumn("OS", width="small"),
            "2FA": st.column_config.TextColumn("2FA", width="small"),
            "Reason": st.column_config.TextColumn("Reason", width="medium"),
        },
    )

    # ---------- Security alerts ----------
    recent_failures = [a for a in attempts[:50] if not a.success]
    if len(recent_failures) >= 5:
        st.warning(
            f"⚠️ **Security Alert:** {len(recent_failures)} failed login attempts in recent history."
        )

    if filter_user != "All":
        user_ips = {
            a.ip_address
            for a in attempts[:50]
            if a.username == filter_user and a.ip_address
        }
        if len(user_ips) > 3:
            st.warning(
                f"⚠️ **Multiple IPs Detected:** User '{filter_user}' logged in from "
                f"{len(user_ips)} different IP addresses."
            )

    st.markdown("---")

    # ---------- Download & refresh ----------
    col_download, col_refresh = st.columns([0.8, 0.2])
    with col_download:
        csv_data = df.to_csv(index=False)
        st.download_button(
            "⬇️ Download Login History (CSV)",
            data=csv_data,
            file_name=f"login_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
            on_click=lambda: log_export_action("LoginHistory", "CSV", len(df), st.session_state.get("auth_user"), st.session_state.get("active_location_id"))
        )
    with col_refresh:
        if st.button("🔄", use_container_width=True, help="Refresh"):
            st.rerun()

    # ---------- Additional insights ----------
    st.markdown("---")
    st.markdown("#### 🔐 Login Insights")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 📍 Top Login Locations")
        location_counts: Dict[str, int] = {}
        for a in attempts[:100]:
            country = getattr(a, "ip_country", None) or "Unknown"
            flag = IPService.get_flag_emoji(country)
            key = f"{flag} {country}"
            location_counts[key] = location_counts.get(key, 0) + 1

        for loc, count in sorted(location_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            st.caption(f"{loc}: {count} attempts")

    with c2:
        st.markdown("##### 💻 Top Devices")
        device_counts: Dict[str, int] = {}
        for a in attempts[:100]:
            device = getattr(a, "device_type", None) or "Unknown"
            device_counts[device] = device_counts.get(device, 0) + 1

        for dev, count in sorted(device_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            st.caption(f"{dev}: {count} attempts")
