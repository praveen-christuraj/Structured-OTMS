"""
Home Page with Configurable Dashboard
Integrates location-based dashboard with customization support
"""

import streamlit as st
from datetime import date, datetime, timedelta
from db import get_session
from models import Location
from dashboard_utils import DashboardMetrics
from location_manager import LocationManager
from ui_components import DashboardCard, Notifications
# Dashboard imports
try:
    from dashboard_config import DashboardConfigManager
    from dashboard_widgets import DashboardRenderer
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False


def _load_locations():
    """Small helper to load all active locations."""
    with get_session() as session:
        locations = LocationManager. get_all_locations(session, active_only=True)
    return locations


def render_admin_it_home(user: dict):
    """Render Admin-IT special home page"""
    Notifications.success_alert(
        f"Welcome back, {user. get('full_name') or user.get('username')}!",
        "Login Successful"
    )
    st.markdown("""
    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 2rem; border-radius: 10px; margin-bottom: 2rem;'>
        <h1 style='color: white; margin: 0;'>🔧 System Administration</h1>
        <p style='color: rgba(255,255,255,0.9); margin: 0. 5rem 0 0 0;'>Admin-IT Dashboard</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"### Welcome, {user. get('full_name') or user.get('username')}!")
    st.caption("You have system administration access")
    
    st.markdown("---")
    st.markdown("### 🔐 Your Access")
    
    col1, col2 = st. columns(2)
    
    with col1:
        st.markdown("""
        **✅ You Can Access:**
        - 👥 Manage Users
        - 📜 Audit Log
        - 🕒 Login History
        - 💾 Backup & Recovery
        - ✅ My Tasks (Password Reset Requests)
        - 🔐 2FA Settings
        """)
    
    with col2:
        st. markdown("""
        **⛔ Restricted Access:**
        - All Operational Pages (Tank, Yade, Tanker Transactions)
        - All Reports (OTR, BCCR, Material Balance)
        - Location-specific Operations
        
        *Admin-IT is for system administration only*
        """)
    
    st.markdown("---")
    st.markdown("### 📌 Quick Links")
    
    quick_col1, quick_col2, quick_col3 = st. columns(3)
    
    with quick_col1:
        if st.button("👥", use_container_width=True, help="Manage Users"):
            st. session_state.page = "Manage Users"
            st.rerun()
    
    with quick_col2:
        if st.button("📜", use_container_width=True, help="View Audit Log"):
            st. session_state.page = "Audit Log"
            st.rerun()
    
    with quick_col3:
        if st. button("✅ My Tasks", use_container_width=True):
            st.session_state.page = "My Tasks"
            st.rerun()


def render_location_dashboard(selected_location_id: int, user: dict):
    """Render full operational dashboard for location"""
    
    if not DASHBOARD_AVAILABLE:
        st.error("Dashboard modules not available.  Please ensure dashboard_config.py and dashboard_widgets.py are installed.")
        return
    
    # Get location details
    with get_session() as s:
        loc = LocationManager.get_location_by_id(s, selected_location_id)
        if not loc:
            st.error("❌ Location not found.")
            return
        
        loc_name = getattr(loc, "name", "Location")
        loc_code = getattr(loc, "code", "")
    
    # Load dashboard config for header settings
    from dashboard_config import DashboardConfigManager
    config = DashboardConfigManager.load_config(selected_location_id)
    header_cfg = config.get("page_header", {
        "title": "{location_name} Dashboard",
        "subtitle": "Management Information System",
        "show_welcome": True,
        "show_datetime": True,
        "background_gradient_start": "#667eea",
        "background_gradient_end": "#764ba2"
    })
    
    # Replace {location_name} placeholder
    page_title = header_cfg.get("title", "{location_name} Dashboard").replace("{location_name}", loc_name)
    page_subtitle = header_cfg.get("subtitle", "Management Information System")
    
    # Build welcome and datetime sections
    additional_info = []
    if header_cfg.get("show_welcome", True):
        additional_info.append(f"Welcome back, <strong>{user['username']}</strong>")
    if header_cfg.get("show_datetime", True):
        additional_info.append(datetime.now().strftime('%A, %B %d, %Y - %I:%M %p'))
    
    info_text = " | ".join(additional_info) if additional_info else ""
    
    # Dashboard header - full width
    gradient_start = header_cfg.get("background_gradient_start", "#667eea")
    gradient_end = header_cfg.get("background_gradient_end", "#764ba2")
    
    st.markdown(
        f"""
        <div style='background: linear-gradient(135deg, {gradient_start} 0%, {gradient_end} 100%); 
                    padding: 2.5rem; border-radius: 10px; margin-bottom: 1rem; color: white;'>
            <h1 style='margin: 0; font-size: 2.5rem;'>{page_title}</h1>
            <p style='margin: 0.5rem 0 0 0; opacity: 0.9; font-size: 1.1rem;'>{page_subtitle}</p>
            {f"<p style='margin: 0.5rem 0 0 0; font-size: 0.95rem;'>{info_text}</p>" if info_text else ""}
        </div>
        """,
        unsafe_allow_html=True
    )
    c1, c2 = st.columns([0.9, 0.1])
    with c2:
        if st.button("🖨️", help="Export Dashboard to PDF", use_container_width=True):
            try:
                from logger import log_info
                log_info("Dashboard PDF export triggered")
            except Exception:
                pass
            try:
                import streamlit.components.v1 as components
                components.html(
                    """
                    <script>
                    (async function(){
                        function loadScript(src){
                            return new Promise(function(resolve, reject){
                                try {
                                    var s = document.createElement('script');
                                    s.src = src;
                                    s.onload = resolve;
                                    s.onerror = function(){ reject(new Error('Failed to load '+src)); };
                                    var doc2 = (window.parent && window.parent.document) ? window.parent.document : document;
                                    (doc2.body || doc2.head || doc2.documentElement).appendChild(s);
                                } catch(e){ reject(e); }
                            });
                        }
                        try {
                            var doc = (window.parent && window.parent.document) ? window.parent.document : document;
                            if (!window.parent.__otmsPdfLibsLoaded) {
                                await loadScript('https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js');
                                await loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');
                                window.parent.__otmsPdfLibsLoaded = true;
                            }
                            var target = doc.querySelector('[data-testid="stAppViewContainer"] .block-container')
                                || doc.querySelector('.block-container')
                                || doc.querySelector('main')
                                || doc.body;
                            var h2c = (window.parent && window.parent.html2canvas) ? window.parent.html2canvas : window.html2canvas;
                            await new Promise(function(r){ requestAnimationFrame(r); });
                            var canvas = await h2c(target, { scale: 1.5, useCORS: true, backgroundColor: '#ffffff' });
                            var imgData = canvas.toDataURL('image/png');
                            var jpdf = (window.parent && window.parent.jspdf) ? window.parent.jspdf : window.jspdf;
                            var jsPDF = jpdf.jsPDF || jpdf;
                            var pdf = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' });
                            var pageWidth = pdf.internal.pageSize.getWidth();
                            var pageHeight = pdf.internal.pageSize.getHeight();
                            var imgWidth = pageWidth;
                            var imgHeight = canvas.height * (imgWidth / canvas.width);
                            var y = 0;
                            pdf.addImage(imgData, 'PNG', 0, y, imgWidth, imgHeight);
                            var heightLeft = imgHeight - pageHeight;
                            while (heightLeft > 0) {
                                pdf.addPage();
                                y = heightLeft - imgHeight;
                                pdf.addImage(imgData, 'PNG', 0, y, imgWidth, imgHeight);
                                heightLeft -= pageHeight;
                            }
                            var blob = pdf.output('blob');
                            var url = ((window.parent || window).URL || URL).createObjectURL(blob);
                            (window.parent || window).open(url, '_blank');
                        } catch (err) {
                            console.error(err);
                            try { (window.parent || window).print(); } catch(e2) {}
                            alert('Failed to export dashboard to PDF. Print dialog opened as fallback.');
                        }
                    })();
                    </script>
                    """,
                    height=0
                );
            except Exception as e:
                st.error(f"PDF export failed: {e}")
            
    
    # Load dashboard configuration
    try:
        config = DashboardConfigManager.load_config(selected_location_id)
        
        # Render dashboard with section-based filters
        DashboardRenderer.render_dashboard_with_sections(config, selected_location_id, user)
    except Exception as e:
        st.error(f"Error rendering dashboard: {e}")
        import traceback
        st.code(traceback.format_exc())
        st.info("Falling back to basic summary view...")
        render_basic_summary(selected_location_id)
    
    st.markdown("---")

def render_basic_summary(selected_location_id: int):
    """Fallback basic summary if dashboard fails"""
    with get_session() as session:
        summary = DashboardMetrics.get_location_summary(session, selected_location_id)
    
    st.markdown("### 📊 Location Summary (last 7 days)")
    
    # Row 1 – tank counts using DashboardCard
    c1, c2, c3 = st.columns(3)
    with c1:
        DashboardCard. metric_card(
            "Total Tanks", 
            str(summary.get("total_tanks", 0)), 
            "All tanks", 
            "🛢️", 
            "blue"
        )
    with c2:
        DashboardCard.metric_card(
            "Active Tanks", 
            str(summary.get("active_tanks", 0)), 
            "Operating", 
            "✅", 
            "green"
        )
    with c3:
        DashboardCard. metric_card(
            "Inactive Tanks", 
            str(summary.get("inactive_tanks", 0)), 
            "Standby", 
            "⏸️", 
            "orange"
        )
    
    st.markdown("---")
    
    # Row 2 – activity using DashboardCard
    c4, c5, c6 = st.columns(3)
    with c4:
        DashboardCard.metric_card(
            "Tank Transactions", 
            str(summary.get("recent_transactions", 0)), 
            "This week", 
            "📝", 
            "purple"
        )
    with c5:
        DashboardCard.metric_card(
            "YADE Voyages", 
            str(summary.get("recent_voyages", 0)), 
            "In progress", 
            "⛴️", 
            "teal"
        )
    with c6:
        DashboardCard.metric_card(
            "Tanker Dispatches", 
            str(summary.get("recent_tanker_dispatches", 0)), 
            "Scheduled", 
            "🚚", 
            "blue"
        )
    
    st.markdown("---")
    
    # Row 3 – stock
    c7, c8 = st.columns(2)
    with c7:
        DashboardCard.metric_card(
            "Current Stock", 
            f"{summary.get('current_stock_bbl', 0):,} bbl", 
            "Available inventory", 
            "📦", 
            "green"
        )
    with c8:
        DashboardCard.metric_card(
            "Tanks with Stock", 
            str(summary.get("tanks_with_stock", 0)), 
            "Active storage", 
            "🗂️", 
            "blue"
        )

def render_home_page(active_location_id, user):
    """
    Main home page entry point:
    - Admin-IT gets special homepage
    - Other users get location selector and operational dashboard
    - If no locations exist, prompt to create one
    """
    
    # Special handling for Admin-IT
    if user and user.get("role") == "admin-it":
        render_admin_it_home(user)
        return
    
    st.markdown("### 🏠 Home")
    
    # 1) Load existing locations
    locations = _load_locations()
    
    if not locations:
        st.warning(
            "No locations found in the database. "
            "Please go to **Manage Locations** (left sidebar) to create your first location."
        )
        return
    
    # ===== Role / assignment logic =====
    role = (user or {}).get("role", "")
    role_lc = (role or "").lower()
    user_loc_id = (user or {}).get("location_id")
    is_admin = role_lc in ("admin-operations", "admin-it", "admin", "super-admin")
    
    # 2) Build label -> id mapping for the dropdown
    labels = [f"{loc.name} ({loc.code})" for loc in locations]
    id_by_label = {label: loc.id for label, loc in zip(labels, locations)}
    id_set = {loc.id for loc in locations}
    
    # Helper to get label by id
    def _label_for_location_id(loc_id: int) -> str:
        for loc in locations:
            if loc. id == loc_id:
                return f"{loc.name} ({loc. code})"
        return labels[0]  # fallback
    
    # Decide default selection
    if active_location_id and active_location_id in id_set:
        default_label = _label_for_location_id(active_location_id)
    elif user_loc_id and user_loc_id in id_set:
        # If user has assigned location and it's active, prefer that
        default_label = _label_for_location_id(user_loc_id)
        st.session_state["active_location_id"] = user_loc_id
        active_location_id = user_loc_id
    else:
        default_label = labels[0]
        st.session_state["active_location_id"] = locations[0].id
        active_location_id = locations[0].id

    if "__prev_active_location_id" not in st.session_state:
        st.session_state["__prev_active_location_id"] = active_location_id
    
    # 3) Render location selector (locked for non-admins with assignment)
    st.markdown("#### Select Active Location")
    
    if not is_admin and user_loc_id:
        # Non-admin tied to a location: lock the selector to their assigned location
        if user_loc_id in id_set:
            locked_label = _label_for_location_id(user_loc_id)
            st.info("You are assigned to a specific location by your administrator.")
            st.selectbox("Location", labels, index=labels.index(locked_label), disabled=True)
            selected_location_id = user_loc_id
            st.session_state["active_location_id"] = user_loc_id
        else:
            # Assigned location not active/visible → allow choosing, but inform
            st.warning(
                "Your assigned location is not currently active. "
                "Please contact an administrator.  For now, select from available locations."
            )
            selected_label = st.selectbox(
                "Location",
                labels,
                index=labels.index(default_label),
                help="This active location will be used across all other pages.",
            )
            selected_location_id = id_by_label[selected_label]
            prev_id = st.session_state.get("__prev_active_location_id")
            st.session_state["active_location_id"] = selected_location_id
            if prev_id != selected_location_id:
                st.session_state["__prev_active_location_id"] = selected_location_id
                st.rerun()
    else:
        # Admins (or users without an assigned location): free selection
        selected_label = st.selectbox(
            "Location",
            labels,
            index=labels.index(default_label),
            help="This active location will be used across all other pages.",
        )
        selected_location_id = id_by_label[selected_label]
        prev_id = st.session_state.get("__prev_active_location_id")
        st.session_state["active_location_id"] = selected_location_id
        if prev_id != selected_location_id:
            st.session_state["__prev_active_location_id"] = selected_location_id
            st.rerun()
    
    # 4) Render the full operational dashboard
    if DASHBOARD_AVAILABLE:
        render_location_dashboard(selected_location_id, user)
    else:
        # Fallback to basic summary
        st.info("Full dashboard not available. Showing basic summary.")
        render_basic_summary(selected_location_id)
    
    # Footer note
    st.caption(
        "💡 **Tip:** Use 'Dashboard Customization' (admin only) to configure widgets, "
        "charts, and data mappings for this location."
    )

# Main entry point (if this file is run directly for testing)
if __name__ == "__main__":
    # For testing purposes
    render_home_page(
        active_location_id=st.session_state.get("active_location_id"),
        user=st.session_state.get("auth_user")
    )
