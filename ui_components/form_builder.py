import streamlit as st

class FormBuilder:
    
    @staticmethod
    def section_header(title, description=""):
        st.markdown(f"""
        <div style="margin: 2rem 0 1.25rem 0;">
            <div style="display:flex; align-items:center; gap:.6rem;">
                <span style="display:inline-block; width:12px; height:12px; border-radius:50%; 
                              background: linear-gradient(135deg, #667eea, #764ba2);"></span>
                <h3 style="margin:0; color:#1e3c72; font-size:1.25rem; font-weight:700;">{title}</h3>
            </div>
            {f"<p style='margin:.4rem 0 0 1.2rem; color:#4b5563; font-size:.95rem;'>{description}</p>" if description else ""}
        </div>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def input_field(label, key, placeholder="", input_type="text", required=False):
        """Create a styled input field"""
        st.markdown(f"""
        <label style="font-weight: 600; color: #333; display: block; margin-bottom: 0.5rem;">
            {label} {" <span style='color: red;'>*</span>" if required else ""}
        </label>
        """, unsafe_allow_html=True)
        
        if input_type == "text":
            return st.text_input("", key=key, placeholder=placeholder, label_visibility="collapsed")
        elif input_type == "number":
            return st.number_input("", key=key, label_visibility="collapsed")
        elif input_type == "password":
            return st.text_input("", key=key, type="password", placeholder=placeholder, label_visibility="collapsed")
    
    @staticmethod
    def select_field(label, options, key, required=False):
        """Create a styled select field"""
        st.markdown(f"""
        <label style="font-weight: 600; color: #333; display: block; margin-bottom: 0.5rem;">
            {label} {" <span style='color: red;'>*</span>" if required else ""}
        </label>
        """, unsafe_allow_html=True)
        return st.selectbox("", options, key=key, label_visibility="collapsed")
    
    @staticmethod
    def date_field(label, key, required=False, default_date=None):
        """Create a styled date field"""
        st. markdown(f"""
        <label style="font-weight: 600; color: #333; display: block; margin-bottom: 0.5rem;">
            {label} {" <span style='color: red;'>*</span>" if required else ""}
        </label>
        """, unsafe_allow_html=True)
        from datetime import date
        default_val = default_date or date.today()
        return st.date_input(
            "",
            key=key,
            value=default_val,
            label_visibility="collapsed",
            max_value=date.today()
        )
    
    @staticmethod
    def textarea_field(label, key, placeholder="", rows=4, required=False):
        """Create a styled textarea field"""
        st.markdown(f"""
        <label style="font-weight: 600; color: #333; display: block; margin-bottom: 0.5rem;">
            {label} {" <span style='color: red;'>*</span>" if required else ""}
        </label>
        """, unsafe_allow_html=True)
        return st.text_area("", key=key, placeholder=placeholder, height=rows*30, label_visibility="collapsed")
    
    @staticmethod
    def form_row(num_columns=2):
        """Create columns for form layout"""
        return st.columns(num_columns)
    
    @staticmethod
    def form_submit_button(label="Submit", icon="✓"):
        """Create a styled submit button"""
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            return st.form_submit_button(f"{icon} {label}", use_container_width=True)
