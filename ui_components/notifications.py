import streamlit as st

class Notifications:
    
    @staticmethod
    def success_alert(message, title="Success"):
        st.markdown(f"""
        <div style="background: rgba(34,197,94,0.12); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
                    border: 1px solid rgba(34,197,94,0.35); border-radius: 12px; padding: 1rem; margin-bottom: 1rem;">
            <p style="color: #166534; margin: 0; font-weight: 700;">✅ {title}</p>
            <p style="color: #166534; margin: .45rem 0 0 0;">{message}</p>
        </div>
        """, unsafe_allow_html=True)

    @staticmethod
    def error_alert(message, title="Error"):
        st.markdown(f"""
        <div style="background: rgba(239,68,68,0.12); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
                    border: 1px solid rgba(239,68,68,0.35); border-radius: 12px; padding: 1rem; margin-bottom: 1rem;">
            <p style="color: #7f1d1d; margin: 0; font-weight: 700;">❌ {title}</p>
            <p style="color: #7f1d1d; margin: .45rem 0 0 0;">{message}</p>
        </div>
        """, unsafe_allow_html=True)

    @staticmethod
    def warning_alert(message, title="Warning"):
        st.markdown(f"""
        <div style="background: rgba(245,158,11,0.12); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
                    border: 1px solid rgba(245,158,11,0.35); border-radius: 12px; padding: 1rem; margin-bottom: 1rem;">
            <p style="color: #78350f; margin: 0; font-weight: 700;">⚠️ {title}</p>
            <p style="color: #78350f; margin: .45rem 0 0 0;">{message}</p>
        </div>
        """, unsafe_allow_html=True)

    @staticmethod
    def info_alert(message, title="Info"):
        st.markdown(f"""
        <div style="background: rgba(20,184,166,0.12); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
                    border: 1px solid rgba(20,184,166,0.35); border-radius: 12px; padding: 1rem; margin-bottom: 1rem;">
            <p style="color: #0f766e; margin: 0; font-weight: 700;">ℹ️ {title}</p>
            <p style="color: #0f766e; margin: .45rem 0 0 0;">{message}</p>
        </div>
        """, unsafe_allow_html=True)
