# twofa_settings.py
from __future__ import annotations

import time
from typing import Any, Dict

import streamlit as st

from db import get_session
from ui import header
from twofa import TwoFactorAuth
from security import SecurityManager
from auth import AuthManager
from models import User
from logger import log_error


def _clear_2fa_session_states() -> None:
    """Helper to clear any temporary 2FA setup state from session."""
    for key in [
        "2fa_setup",
        "2fa_backup_codes_ready",
        "backup_codes_visible",
        "new_backup_codes",
    ]:
        st.session_state.pop(key, None)


def render_twofa_settings_page(active_location_id: int | None, user: Dict[str, Any] | None) -> None:
    """Render the Two-Factor Authentication Settings page."""
    header("Two-Factor Authentication Settings")

    if not user:
        st.error("Please login to access this page.")
        st.stop()

    try:
        from ip_service import IPService
        ip_val = st.session_state.get("last_login_ip")
        ua_val = st.session_state.get("last_login_useragent")
        if ip_val or ua_val:
            loc = IPService.get_location_from_ip(ip_val or "127.0.0.1")
            dev = IPService.parse_user_agent(ua_val or "")
            flag = IPService.get_flag_emoji(loc.get("country") or "Unknown")
            st.caption(
                f"IP: {ip_val or 'N/A'} • {flag} {loc.get('city')}, {loc.get('country')} • {dev.get('device_type')} • {dev.get('browser')} • {dev.get('os')}"
            )
    except Exception:
        pass

    st.markdown("### 🔐 Two-Factor Authentication (2FA)")
    st.caption("Add an extra layer of security to your account")

    # -------- Check current 2FA status --------
    try:
        with get_session() as s:
            is_2fa_enabled = TwoFactorAuth.is_enabled(s, user["id"])
    except Exception as ex:
        log_error(f"Failed to check 2FA status for user {user.get('username')}: {ex}", exc_info=True)
        st.error(f"Failed to load 2FA status: {ex}")
        return

    if is_2fa_enabled:
        st.success("✅ **2FA is ENABLED** for your account")
    else:
        st.warning("⚠️ **2FA is DISABLED** — Your account is less secure")

    st.markdown("---")

    # =====================================================
    #  A) ENABLE 2FA (if currently disabled)
    # =====================================================
    if not is_2fa_enabled:
        st.markdown("#### Enable 2FA")

        st.info(
            """
**How it works:**

1. **Recommended:** Download **Microsoft Authenticator** app  
   - iOS: App Store → search **"Microsoft Authenticator"**  
   - Android: Play Store → search **"Microsoft Authenticator"**
2. Open the app → tap **"+"** → select **"Other account"** → **scan the QR code**
3. Enter the 6-digit code to verify
4. **Save your backup codes** in a safe place!

*Also works with: Google Authenticator, Authy, 1Password, etc.*
            """
        )

        if st.button("🔐 Enable 2FA", key="enable_2fa_btn", type="primary"):
            try:
                with get_session() as s:
                    secret, backup_codes, provisioning_uri = TwoFactorAuth.enable_2fa(s, user["id"])

                st.session_state["2fa_setup"] = {
                    "secret": secret,
                    "backup_codes": backup_codes,
                    "provisioning_uri": provisioning_uri,
                }
                st.rerun()

            except Exception as ex:
                log_error(f"Failed to enable 2FA for user {user.get('username')}: {ex}", exc_info=True)
                st.error(f"Failed to start 2FA setup: {ex}")

        # ---------- 2FA setup flow after clicking "Enable 2FA" ----------
        setup = st.session_state.get("2fa_setup")
        if setup:
            st.markdown("---")
            st.markdown("#### Step 1: Scan QR Code")

            try:
                qr_image = TwoFactorAuth.generate_qr_code(setup["provisioning_uri"])
                col1, col2, col3 = st.columns([0.2, 0.6, 0.2])
                with col2:
                    st.image(qr_image, caption="Scan this with Microsoft Authenticator", width=300)
            except Exception as ex:
                log_error(f"Failed to generate 2FA QR code for {user.get('username')}: {ex}", exc_info=True)
                st.error(f"Failed to generate QR code: {ex}")
                return

            with st.expander("🔢 Can't scan? Enter manually"):
                st.code(setup["secret"], language=None)
                st.caption(f"Account: {user['username']}")
                st.caption(f"Issuer: {getattr(TwoFactorAuth, 'ISSUER_NAME', 'OTMS')}")

            st.markdown("#### Step 2: Verify Code")

            # Use a form for the code entry
            with st.form("verify_2fa_setup"):
                verification_code = st.text_input(
                    "Enter the 6-digit code from your app",
                    max_chars=6,
                    placeholder="000000",
                    key="2fa_verify_code",
                )
                verify_btn = st.form_submit_button("✅ Verify & Enable", type="primary")

            if verify_btn:
                if not verification_code or len(verification_code) != 6 or not verification_code.isdigit():
                    st.error("Please enter a valid 6-digit code.")
                else:
                    try:
                        with get_session() as s:
                            success = TwoFactorAuth.verify_and_enable(s, user["id"], verification_code)

                        if success:
                            st.success("✅ 2FA enabled successfully!")

                            # Store backup codes in session for one-time display
                            st.session_state["2fa_backup_codes_ready"] = setup["backup_codes"]
                            st.session_state.pop("2fa_setup", None)

                            # Log audit
                            with get_session() as s:
                                SecurityManager.log_audit(
                                    s,
                                    user["username"],
                                    "2FA_ENABLED",
                                    user_id=user["id"],
                                    location_id=user.get("location_id"),
                                    details="User enabled 2FA",
                                )

                            st.rerun()
                        else:
                            st.error("❌ Invalid code. Please try again.")

                    except Exception as ex:
                        log_error(f"Failed to verify 2FA for {user.get('username')}: {ex}", exc_info=True)
                        st.error(f"Verification failed: {ex}")

        # ---------- Show backup codes immediately after successful setup ----------
        if st.session_state.get("2fa_backup_codes_ready"):
            backup_codes = st.session_state["2fa_backup_codes_ready"]

            st.markdown("---")
            st.markdown("#### 🔐 IMPORTANT: Save Your Backup Codes")
            st.warning("Store these codes in a safe place. You'll need them if you lose your device.")

            backup_codes_text = "\n".join(backup_codes)
            st.code(backup_codes_text, language=None)

            st.download_button(
                "⬇️ Download Backup Codes",
                data=backup_codes_text,
                file_name=f"otms_backup_codes_{user['username']}.txt",
                mime="text/plain",
                key="download_backup_codes_initial",
            )

            if st.button("✅ I've Saved My Backup Codes - Continue", key="finish_2fa_setup"):
                st.session_state.pop("2fa_backup_codes_ready", None)
                st.success("Setup complete! You can now use 2FA to login.")
                time.sleep(1)
                st.rerun()

        return  # nothing else for not-enabled state

    # =====================================================
    #  B) MANAGE 2FA (already enabled)
    # =====================================================
    st.markdown("#### Manage 2FA")

    tab1, tab2, tab3 = st.tabs(["Backup Codes", "Regenerate Codes", "Disable 2FA"])

    # -------- TAB 1: View backup codes --------
    with tab1:
        st.markdown("##### Your Backup Codes")
        st.caption("Use these codes if you lose access to your authenticator app.")

        try:
            with get_session() as s:
                backup_codes = TwoFactorAuth.get_backup_codes(s, user["id"])
        except Exception as ex:
            log_error(f"Failed to load backup codes for {user.get('username')}: {ex}", exc_info=True)
            st.error(f"Failed to load backup codes: {ex}")
            backup_codes = []

        if backup_codes:
            st.info(f"You have **{len(backup_codes)}** unused backup codes.")

            if "backup_codes_visible" not in st.session_state:
                st.session_state["backup_codes_visible"] = False

            if not st.session_state["backup_codes_visible"]:
                if st.button("👁️ Show Backup Codes", key="btn_show_backup_codes", type="primary"):
                    st.session_state["backup_codes_visible"] = True
                    st.rerun()
            else:
                st.code("\n".join(backup_codes), language=None)
                backup_codes_text = "\n".join(backup_codes)

                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        "⬇️ Download Codes",
                        data=backup_codes_text,
                        file_name=f"otms_backup_codes_{user['username']}.txt",
                        mime="text/plain",
                        key="download_existing_backup_codes",
                        use_container_width=True,
                    )
                with col2:
                    if st.button("🙈 Hide Codes", key="btn_hide_backup_codes", use_container_width=True):
                        st.session_state["backup_codes_visible"] = False
                        st.rerun()
        else:
            st.warning("⚠️ No backup codes remaining. Generate new ones in the next tab.")

    # -------- TAB 2: Regenerate backup codes --------
    with tab2:
        st.markdown("##### Regenerate Backup Codes")
        st.warning("⚠️ This will **invalidate** all your old backup codes.")

        st.markdown(
            """
**When should you regenerate backup codes?**

- You've used most of your backup codes  
- You suspect your codes may have been compromised  
- You want to refresh your codes for security
            """
        )

        if "new_backup_codes" not in st.session_state:
            st.session_state["new_backup_codes"] = None

        if st.session_state["new_backup_codes"] is None:
            if st.button("🔐 Generate New Backup Codes", key="btn_regen_backup_codes", type="primary"):
                try:
                    with get_session() as s:
                        new_codes = TwoFactorAuth.regenerate_backup_codes(s, user["id"])
                    st.session_state["new_backup_codes"] = new_codes

                    # Log audit
                    with get_session() as s:
                        SecurityManager.log_audit(
                            s,
                            user["username"],
                            "2FA_BACKUP_CODES_REGENERATED",
                            user_id=user["id"],
                            location_id=user.get("location_id"),
                        )

                    st.rerun()
                except Exception as ex:
                    log_error(f"Failed to regenerate backup codes for {user.get('username')}: {ex}", exc_info=True)
                    st.error(f"Failed to regenerate codes: {ex}")

        if st.session_state["new_backup_codes"] is not None:
            new_codes = st.session_state["new_backup_codes"]

            st.success("✅ New backup codes generated!")
            st.warning("⚠️ **IMPORTANT:** Save these codes now. Old codes are no longer valid.")

            st.code("\n".join(new_codes), language=None)

            col1, col2 = st.columns(2)
            with col1:
                new_codes_text = "\n".join(new_codes)
                st.download_button(
                    "⬇️ Download New Codes",
                    data=new_codes_text,
                    file_name=f"otms_backup_codes_{user['username']}_new.txt",
                    mime="text/plain",
                    key="download_new_backup_codes",
                    use_container_width=True,
                )
            with col2:
                if st.button("✅ Done - Clear", key="btn_clear_new_backup_codes", use_container_width=True):
                    st.session_state["new_backup_codes"] = None
                    st.rerun()

    # -------- TAB 3: Disable 2FA --------
    with tab3:
        st.markdown("##### Disable 2FA")
        st.error("⚠️ **Warning:** Disabling 2FA makes your account less secure.")

        st.markdown(
            """
**Why you might disable 2FA:**

- Switching to a new phone  
- Lost access to authenticator app  
- Technical issues  

**Important:** You can re-enable 2FA anytime after disabling.
            """
        )

        st.markdown("---")
        st.markdown("**To disable 2FA, please:**")
        st.markdown("1. Enter your current password")
        st.markdown("2. Confirm by typing your username")

        with st.form("disable_2fa_form"):
            current_pwd = st.text_input(
                "Current Password",
                type="password",
                key="disable_2fa_pwd",
                placeholder="Enter your password",
            )
            confirm_username = st.text_input(
                f"Type your username ({user['username']}) to confirm",
                key="disable_2fa_username",
                placeholder="Type username here",
            )
            disable_btn = st.form_submit_button("🚫 Disable 2FA", type="primary")

        if disable_btn:
            if not current_pwd:
                st.error("⚠️ Please enter your password.")
            elif confirm_username.strip() != user["username"]:
                st.error(f"⚠️ Username confirmation does not match. Expected: {user['username']}")
            else:
                try:
                    with get_session() as s:
                        db_user = s.query(User).filter(User.id == user["id"]).one_or_none()

                        if db_user and AuthManager.verify_password(current_pwd, db_user.password_hash):
                            TwoFactorAuth.disable_2fa(s, user["id"])

                            st.success("✅ 2FA disabled successfully.")

                            SecurityManager.log_audit(
                                s,
                                user["username"],
                                "2FA_DISABLED",
                                user_id=user["id"],
                                location_id=user.get("location_id"),
                                details="User disabled 2FA",
                            )

                            _clear_2fa_session_states()
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("❌ Invalid password.")
                except Exception as ex:
                    log_error(f"Failed to disable 2FA for {user.get('username')}: {ex}", exc_info=True)
                    st.error(f"Failed to disable 2FA: {ex}")
