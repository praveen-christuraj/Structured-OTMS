import streamlit as st

class Notifications:
    """Professional notification/alert component"""
    
    @staticmethod
    def success_alert(message, title="Success"):
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); 
                    border-left: 5px solid #28a745; border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
            <p style="color: #155724; margin: 0; font-weight: 600;">✅ {title}</p>
            <p style="color: #155724; margin: 0. 5rem 0 0 0;">{message}</p>
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def error_alert(message, title="Error"):
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%); 
                    border-left: 5px solid #dc3545; border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
            <p style="color: #721c24; margin: 0; font-weight: 600;">❌ {title}</p>
            <p style="color: #721c24; margin: 0.5rem 0 0 0;">{message}</p>
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def warning_alert(message, title="Warning"):
        st. markdown(f"""
        <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%); 
                    border-left: 5px solid #ffc107; border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
            <p style="color: #856404; margin: 0; font-weight: 600;">⚠️ {title}</p>
            <p style="color: #856404; margin: 0.5rem 0 0 0;">{message}</p>
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def info_alert(message, title="Info"):
        st. markdown(f"""
        <div style="background: linear-gradient(135deg, #d1ecf1 0%, #bee5eb 100%); 
                    border-left: 5px solid #17a2b8; border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
            <p style="color: #0c5460; margin: 0; font-weight: 600;">ℹ️ {title}</p>
            <p style="color: #0c5460; margin: 0.5rem 0 0 0;">{message}</p>
        </div>
        """, unsafe_allow_html=True)