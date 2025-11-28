import streamlit as st

class DashboardCard:
    
    @staticmethod
    def metric_card(title, value, subtitle="", icon="📊", color="blue"):
        color_map = {
            "blue": "#2563eb",
            "green": "#22c55e",
            "red": "#ef4444",
            "orange": "#f59e0b",
            "purple": "#7c3aed",
            "teal": "#14b8a6"
        }
        accent = color_map.get(color, "#2563eb")
        st.markdown(f"""
        <div style="background: rgba(255,255,255,0.6); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
                    border: 1px solid rgba(0,0,0,0.08); border-radius: 14px; padding: 1.25rem; 
                    box-shadow: 0 6px 18px rgba(0,0,0,0.06);">
            <div style="display:flex; align-items:center; justify-content:space-between;">
                <p style="margin:0; color:#6b7280; font-size:.9rem; text-transform:uppercase; letter-spacing:.02em;">
                    {title}
                </p>
                <span style="font-size:1.2rem;">{icon}</span>
            </div>
            <h2 style="margin:.35rem 0 .25rem 0; color:{accent}; font-size:2rem; font-weight:800;">{value}</h2>
            {f"<p style='margin:0; color:#4b5563; font-size:.95rem;'>{subtitle}</p>" if subtitle else ""}
        </div>
        """, unsafe_allow_html=True)

    @staticmethod
    def info_card(title, content, icon="ℹ️"):
        st.markdown(f"""
        <div style="background: rgba(23,162,184,0.12); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
                    border: 1px solid rgba(23,162,184,0.35); border-radius: 14px; padding: 1.25rem;">
            <div style="display:flex; align-items:center; gap:.5rem;">
                <span>{icon}</span>
                <h3 style="margin:0; color:#117a8b; font-size:1.1rem;">{title}</h3>
            </div>
            <p style="margin:.45rem 0 0 0; color:#0c5460; line-height:1.6;">{content}</p>
        </div>
        """, unsafe_allow_html=True)

    @staticmethod
    def status_badge(status, label):
        status_colors = {
            "active": "#22c55e",
            "inactive": "#6b7280",
            "pending": "#f59e0b",
            "failed": "#ef4444",
            "completed": "#14b8a6"
        }
        bg = status_colors.get(status, "#2563eb")
        st.markdown(f"""
        <span style="display:inline-block; background:{bg}; color:white; padding:.35rem .75rem; 
                     border-radius:20px; font-size:.85rem; font-weight:600;">
            {label}
        </span>
        """, unsafe_allow_html=True)
