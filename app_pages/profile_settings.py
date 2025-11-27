# app_pages/profile_settings.py
"""
User Profile Settings Page
Allows users to:
- Change their password
- Setup/manage 2FA
- View password expiry status
- Request password reset (forgot password)
"""

import streamlit as st
from datetime import datetime, timedelta
from db import get_session
from models import User
from auth import AuthManager
from twofa import TwoFactorAuth
from security import SecurityManager
from task_manager import TaskManager


def check_password_expiry(user: User) -> dict:
    """
    Check if user's password has expired or is expiring soon
    
    Returns:
        dict with keys: expired, days_until_expiry, message, severity
    """
    # Admins with password_never_expires can skip
    if user.password_never_expires:
        return {
            "expired": False,
            "days_until_expiry": None,
            "message": "Your password never expires (admin privilege)",
            "severity": "info"
        }
    
    if not user.password_changed_at:
        # Password never changed - must change now
        return {
            "expired": True,
            "days_until_expiry": 0,
            "message": "⚠️ You must change your password immediately",
            "severity": "error"
        }
    
    expiry_days = user.password_expiry_days or 30
    password_age = (datetime.utcnow() - user.password_changed_at).days
    days_until_expiry = expiry_days - password_age
    
    if days_until_expiry <= 0:
        return {
            "expired": True,
            "days_until_expiry": days_until_expiry,
            "message": f"❌ Your password expired {abs(days_until_expiry)} days ago. Please change it immediately.",
            "severity": "error"
        }
    elif days_until_expiry <= 7:
        return {
            "expired": False,
            "days_until_expiry": days_until_expiry,
            "message": f"⚠️ Your password expires in {days_until_expiry} days. Please change it soon.",
            "severity": "warning"
        }
    else:
        return {
            "expired": False,
            "days_until_expiry": days_until_expiry,
            "message": f"✅ Your password expires in {days_until_expiry} days",
            "severity": "success"
        }


def render_password_change_section(user_dict: dict):
    """Render password change form"""
    st.markdown("### 🔐 Change Password")
    
    with get_session() as session:
        user = session.query(User).filter(User.id == user_dict["id"]).first()
        if not user:
            st.error("User not found")
            return
        
        # Check password expiry status
        expiry_status = check_password_expiry(user)
        
        if expiry_status["severity"] == "error":
            st.error(expiry_status["message"])
        elif expiry_status["severity"] == "warning":
            st.warning(expiry_status["message"])
        else:
            st.info(expiry_status["message"])
    
    with st.form("change_password_form"):
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password", 
                                     help="Must be at least 8 characters")
        confirm_password = st.text_input("Confirm New Password", type="password")
        
        submitted = st.form_submit_button("Change Password", type="primary")
        
        if submitted:
            if not current_password or not new_password or not confirm_password:
                st.error("All fields are required")
                return
            
            if new_password != confirm_password:
                st.error("New passwords do not match")
                return
            
            if len(new_password) < 8:
                st.error("Password must be at least 8 characters long")
                return
            
            if new_password == current_password:
                st.error("New password must be different from current password")
                return
            
            try:
                with get_session() as session:
                    user = session.query(User).filter(User.id == user_dict["id"]).first()
                    
                    # Verify current password
                    if not AuthManager.verify_password(current_password, user.password_hash):
                        st.error("Current password is incorrect")
                        return
                    
                    # Update password
                    user.password_hash = AuthManager.hash_password(new_password)
                    user.password_changed_at = datetime.utcnow()
                    user.must_change_password = False
                    user.force_password_change = False
                    
                    # Log the change
                    SecurityManager.log_audit(
                        session,
                        user_dict["username"],
                        "UPDATE",
                        resource_type="User",
                        resource_id=str(user.id),
                        details="Password changed via profile settings",
                        user_id=user.id,
                        location_id=user_dict.get("location_id"),
                        success=True
                    )
                    
                    session.commit()
                    st.success("✅ Password changed successfully!")
                    
                    # Clear enforcement flags
                    if "must_change_password" in st.session_state:
                        del st.session_state["must_change_password"]
                    if "password_expired" in st.session_state:
                        del st.session_state["password_expired"]
                    
                    st.balloons()
                    
            except Exception as e:
                st.error(f"Failed to change password: {str(e)}")


def render_2fa_section(user_dict: dict):
    """Render 2FA setup/management section"""
    st.markdown("### 🔒 Two-Factor Authentication (2FA)")
    
    with get_session() as session:
        user = session.query(User).filter(User.id == user_dict["id"]).first()
        if not user:
            st.error("User not found")
            return
        
        if user.totp_enabled:
            st.success("✅ 2FA is currently **ENABLED**")
            
            if user.force_2fa:
                st.info("ℹ️ 2FA is mandatory for your account and cannot be disabled")
            else:
                if st.button("🔓 Disable 2FA", type="secondary"):
                    user.totp_enabled = False
                    user.totp_secret = None
                    user.backup_codes = None
                    
                    SecurityManager.log_audit(
                        session,
                        user_dict["username"],
                        "UPDATE",
                        resource_type="User",
                        resource_id=str(user.id),
                        details="2FA disabled via profile settings",
                        user_id=user.id,
                        location_id=user_dict.get("location_id"),
                        success=True
                    )
                    
                    session.commit()
                    st.success("2FA has been disabled")
                    st.rerun()
        
        else:
            st.warning("⚠️ 2FA is currently **DISABLED**")
            
            if user.force_2fa:
                st.error("❌ 2FA is mandatory for your account. Please set it up now!")
            else:
                st.info("ℹ️ 2FA is recommended for enhanced security")
            
            if st.button("🔐 Setup 2FA Now", type="primary"):
                st.session_state["show_2fa_setup"] = True
                st.rerun()
    
    # 2FA Setup Flow
    if st.session_state.get("show_2fa_setup"):
        st.markdown("---")
        st.markdown("#### 📱 Setup Two-Factor Authentication")
        
        with get_session() as session:
            user = session.query(User).filter(User.id == user_dict["id"]).first()
            
            # Generate new secret if not in session
            if "temp_totp_secret" not in st.session_state:
                st.session_state["temp_totp_secret"] = TwoFactorAuth.generate_secret()
            
            secret = st.session_state["temp_totp_secret"]
            
            # Generate QR code
            qr_code = TwoFactorAuth.generate_qr_code(
                secret,
                user.username,
                issuer="OTMS"
            )
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.markdown("**Step 1:** Scan this QR code with your authenticator app")
                st.image(qr_code, width=250)
                
                st.markdown("**Or enter this code manually:**")
                st.code(secret)
            
            with col2:
                st.markdown("**Step 2:** Enter the 6-digit code from your app")
                
                with st.form("verify_2fa_setup"):
                    verification_code = st.text_input("6-Digit Code", max_chars=6)
                    verify_btn = st.form_submit_button("Verify & Enable 2FA")
                    
                    if verify_btn:
                        if TwoFactorAuth.verify_totp(secret, verification_code):
                            # Generate backup codes
                            backup_codes = TwoFactorAuth.generate_backup_codes()
                            
                            # Save to database
                            user.totp_secret = secret
                            user.totp_enabled = True
                            user.backup_codes = ",".join(backup_codes)
                            
                            SecurityManager.log_audit(
                                session,
                                user_dict["username"],
                                "UPDATE",
                                resource_type="User",
                                resource_id=str(user.id),
                                details="2FA enabled via profile settings",
                                user_id=user.id,
                                location_id=user_dict.get("location_id"),
                                success=True
                            )
                            
                            session.commit()
                            
                            st.success("✅ 2FA enabled successfully!")
                            
                            # Clear enforcement flag
                            if "must_setup_2fa" in st.session_state:
                                del st.session_state["must_setup_2fa"]
                            
                            # Show backup codes
                            st.warning("⚠️ **IMPORTANT: Save these backup codes in a safe place!**")
                            st.info("Each backup code can be used once if you lose access to your authenticator app")
                            
                            for i, code in enumerate(backup_codes, 1):
                                st.code(f"{i}. {code}")
                            
                            # Clear temp data
                            del st.session_state["temp_totp_secret"]
                            del st.session_state["show_2fa_setup"]
                            
                            if st.button("Continue"):
                                st.rerun()
                        else:
                            st.error("❌ Invalid code. Please try again.")
        
        if st.button("❌ Cancel 2FA Setup"):
            del st.session_state["temp_totp_secret"]
            del st.session_state["show_2fa_setup"]
            st.rerun()


def render_forgot_password_section(user_dict: dict):
    """Render forgot password / reset request section"""
    st.markdown("### 🔑 Forgot Password / Reset Request")
    
    st.info(
        "If you've forgotten your password or are unable to change it, "
        "you can request a password reset from the administrators."
    )
    
    with st.form("forgot_password_form"):
        reason = st.text_area(
            "Reason for Reset Request (optional)",
            help="Explain why you need a password reset",
            height=100
        )
        
        reset_2fa = st.checkbox(
            "Also reset 2FA",
            help="Check this if you've also lost access to your 2FA device"
        )
        
        submitted = st.form_submit_button("🚨 Send Reset Request to Admins")
        
        if submitted:
            try:
                with get_session() as session:
                    # Create password reset task
                    task = TaskManager.create_password_reset_request(
                        user=user_dict,
                        reason=reason or "User requested password reset via profile settings",
                        session=session
                    )
                    
                    # If 2FA reset is also requested, add to metadata
                    if reset_2fa:
                        from models import Task
                        task_obj = session.query(Task).filter(Task.id == task["id"]).first()
                        if task_obj:
                            import json
                            metadata = json.loads(task_obj.metadata_json or "{}")
                            metadata["reset_2fa"] = True
                            task_obj.metadata_json = json.dumps(metadata)
                            session.commit()
                
                st.success(
                    f"✅ Password reset request sent! Task ID: {task['id']}\n\n"
                    "Administrators (Admin-IT and Admin-Operations) have been notified. "
                    "You will be contacted once your request is processed."
                )
                
            except Exception as e:
                st.error(f"Failed to send reset request: {str(e)}")


def render_supervisor_code_section(user_dict: dict):
    """Render supervisor code management (for supervisors only)"""
    if user_dict.get("role") != "supervisor":
        return
    
    st.markdown("### 🔐 Supervisor Code")
    
    with get_session() as session:
        user = session.query(User).filter(User.id == user_dict["id"]).first()
        
        if user.supervisor_code_hash:
            st.success("✅ Supervisor code is set")
            if user.supervisor_code_set_at:
                st.caption(f"Last updated: {user.supervisor_code_set_at.strftime('%Y-%m-%d %H:%M')}")
        else:
            st.warning("⚠️ Supervisor code is not set")
    
    with st.form("change_supervisor_code_form"):
        st.info("Supervisor code is used to approve deletion requests from operators")
        
        current_code = st.text_input("Current Supervisor Code", type="password")
        new_code = st.text_input("New Supervisor Code", type="password")
        confirm_code = st.text_input("Confirm New Supervisor Code", type="password")
        
        submitted = st.form_submit_button("Update Supervisor Code")
        
        if submitted:
            if not new_code or not confirm_code:
                st.error("Both fields are required")
                return
            
            if new_code != confirm_code:
                st.error("Codes do not match")
                return
            
            if len(new_code) < 4:
                st.error("Supervisor code must be at least 4 characters")
                return
            
            try:
                with get_session() as session:
                    user = session.query(User).filter(User.id == user_dict["id"]).first()
                    
                    # Verify current code if it exists
                    if user.supervisor_code_hash and current_code:
                        if not AuthManager.verify_password(current_code, user.supervisor_code_hash):
                            st.error("Current supervisor code is incorrect")
                            return
                    
                    # Update code
                    user.supervisor_code_hash = AuthManager.hash_password(new_code)
                    user.supervisor_code_set_at = datetime.utcnow()
                    
                    SecurityManager.log_audit(
                        session,
                        user_dict["username"],
                        "UPDATE",
                        resource_type="User",
                        resource_id=str(user.id),
                        details="Supervisor code updated via profile settings",
                        user_id=user.id,
                        location_id=user_dict.get("location_id"),
                        success=True
                    )
                    
                    session.commit()
                    st.success("✅ Supervisor code updated successfully!")
                    
            except Exception as e:
                st.error(f"Failed to update supervisor code: {str(e)}")


def render():
    """Main render function for profile settings page"""
    st.title("👤 Profile Settings")
    
    # Get current user
    user = st.session_state.get("auth_user")
    if not user:
        st.error("You must be logged in to access profile settings")
        st.stop()
    
    # Display user info
    st.markdown(f"**Username:** {user.get('username')}")
    st.markdown(f"**Full Name:** {user.get('full_name')}")
    st.markdown(f"**Role:** {user.get('role')}")
    
    if user.get("location"):
        st.markdown(f"**Location:** {user['location'].get('name')} ({user['location'].get('code')})")
    else:
        st.markdown("**Location:** Not assigned")
    
    st.markdown("---")
    
    # Tabs for different settings
    tab1, tab2, tab3 = st.tabs(["🔐 Password", "🔒 2FA", "🔑 Account Recovery"])
    
    with tab1:
        render_password_change_section(user)
        
        # Supervisor code section (only for supervisors)
        if user.get("role") == "supervisor":
            st.markdown("---")
            render_supervisor_code_section(user)
    
    with tab2:
        render_2fa_section(user)
    
    with tab3:
        render_forgot_password_section(user)


if __name__ == "__main__":
    render()
