import streamlit as st

class DashboardCard:
    """Reusable card component for displaying metrics"""
    
    @staticmethod
    def metric_card(title, value, subtitle="", icon="📊", color="blue"):
        """Display a professional metric card"""
        color_map = {
            "blue": "#667eea",
            "green": "#28a745",
            "red": "#dc3545",
            "orange": "#ff9800",
            "purple": "#764ba2",
            "teal": "#17a2b8"
        }
        border_color = color_map.get(color, "#667eea")
        
        st.markdown(f"""
        <div style="background: white; border-radius: 12px; padding: 1.5rem; 
                    box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-left: 5px solid {border_color};">
            <p style="color: #999; font-size: 0.9rem; margin: 0; text-transform: uppercase;">{title}</p>
            <h2 style="color: {border_color}; font-size: 2rem; margin: 0. 5rem 0; font-weight: 700;">{value}</h2>
            {f"<p style='color: #666; font-size: 0.85rem; margin: 0;'>{subtitle}</p>" if subtitle else ""}
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def info_card(title, content, icon="ℹ️"):
        """Display an information card"""
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #d1ecf1 0%, #bee5eb 100%); 
                    border-radius: 12px; padding: 1.5rem; border-left: 5px solid #17a2b8;">
            <h3 style="color: #117a8b; margin: 0 0 0. 5rem 0;">{title}</h3>
            <p style="color: #004085; margin: 0; line-height: 1.6;">{content}</p>
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def status_badge(status, label):
        """Display status badge"""
        status_colors = {
            "active": "#28a745",
            "inactive": "#6c757d",
            "pending": "#ffc107",
            "failed": "#dc3545",
            "completed": "#17a2b8"
        }
        bg_color = status_colors.get(status, "#667eea")
        st.markdown(f"""
        <span style="display: inline-block; background: {bg_color}; color: white; 
                     padding: 0.35rem 0.75rem; border-radius: 20px; font-size: 0.85rem; font-weight: 600;">
            {label}
        </span>
        """, unsafe_allow_html=True)