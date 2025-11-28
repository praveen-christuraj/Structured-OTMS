import streamlit as st

def setup_page_config():
    """Configure page layout and theme"""
    pass

def apply_custom_css():
    """Apply professional custom CSS styling with glassy design"""
    st.markdown("""
    <style>
    /* -------- Buttons (glassy style) -------- */
    .stButton > button {
        background: rgba(255, 255, 255, 0.6) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        color: #374151 !important;
        border: 1.5px solid rgba(0, 0, 0, 0.12) !important;
        border-radius: 12px !important;
        padding: 0.7rem 1.4rem !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        cursor: pointer !important;
        transition: all 0.25s ease !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08) !important;
    }
    
    .stButton > button:hover {
        background: rgba(255, 255, 255, 0.85) !important;
        border: 1.5px solid rgba(0, 0, 0, 0.18) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12) !important;
    }
    
    /* Primary buttons */
    .stButton > button[kind="primary"],
    div[data-testid="stButton"] button[kind="primary"] {
        background: rgba(37, 99, 235, 0.15) !important;
        backdrop-filter: blur(12px) !important;
        border: 1.5px solid rgba(37, 99, 235, 0.35) !important;
        color: #2563eb !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 20px rgba(37, 99, 235, 0.2) !important;
    }
    
    .stButton > button[kind="primary"]:hover,
    div[data-testid="stButton"] button[kind="primary"]:hover {
        background: rgba(37, 99, 235, 0.25) !important;
        border: 1.5px solid rgba(37, 99, 235, 0.5) !important;
        box-shadow: 0 8px 28px rgba(37, 99, 235, 0.3) !important;
    }
    
    /* Secondary buttons */
    .stButton > button[kind="secondary"] {
        background: rgba(255, 255, 255, 0.5) !important;
        backdrop-filter: blur(12px) !important;
        border: 1.5px solid rgba(0, 0, 0, 0.1) !important;
        color: #6b7280 !important;
    }
    
    /* -------- Tabs (glassy style) -------- */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: transparent !important;
        border-bottom: 1px solid rgba(0, 0, 0, 0.08) !important;
        padding-bottom: 0 !important;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: rgba(255, 255, 255, 0.4) !important;
        backdrop-filter: blur(10px) !important;
        -webkit-backdrop-filter: blur(10px) !important;
        border: 1.5px solid rgba(0, 0, 0, 0.08) !important;
        border-radius: 10px 10px 0 0 !important;
        padding: 0.6rem 1.2rem !important;
        color: #6b7280 !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(255, 255, 255, 0.6) !important;
        border: 1.5px solid rgba(0, 0, 0, 0.15) !important;
    }
    
    .stTabs [aria-selected="true"] {
        background: rgba(37, 99, 235, 0.12) !important;
        backdrop-filter: blur(12px) !important;
        border: 1.5px solid rgba(37, 99, 235, 0.4) !important;
        border-bottom: 2px solid #2563eb !important;
        color: #2563eb !important;
        font-weight: 700 !important;
        box-shadow: 0 -2px 12px rgba(37, 99, 235, 0.15) !important;
    }
    
    /* -------- Input fields (glassy style) -------- */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > select,
    .stNumberInput > div > div > input,
    .stDateInput > div > div > input,
    .stTextArea > div > div > textarea {
        background: rgba(255, 255, 255, 0.7) !important;
        backdrop-filter: blur(10px) !important;
        -webkit-backdrop-filter: blur(10px) !important;
        border: 1.5px solid rgba(0, 0, 0, 0.12) !important;
        border-radius: 10px !important;
        padding: 0.7rem !important;
        color: #1f2937 !important;
        transition: all 0.2s ease !important;
    }
    
    .stTextInput > div > div > input:focus,
    .stSelectbox > div > div > select:focus,
    .stNumberInput > div > div > input:focus,
    .stDateInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        background: rgba(255, 255, 255, 0.9) !important;
        border: 1.5px solid rgba(37, 99, 235, 0.4) !important;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1) !important;
    }
    
    /* -------- Containers and cards -------- */
    div[data-testid="stExpander"] {
        background: rgba(255, 255, 255, 0.6) !important;
        backdrop-filter: blur(12px) !important;
        border: 1.5px solid rgba(0, 0, 0, 0.1) !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06) !important;
    }
    
    /* -------- DataFrames -------- */
    .stDataFrame {
        background: rgba(255, 255, 255, 0.7) !important;
        backdrop-filter: blur(10px) !important;
        border: 1.5px solid rgba(0, 0, 0, 0.1) !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06) !important;
    }
    
    /* -------- Alerts (glassy style) -------- */
    div[data-testid="stAlert"] {
        background: rgba(255, 255, 255, 0.7) !important;
        backdrop-filter: blur(12px) !important;
        border-radius: 12px !important;
        border: 1.5px solid rgba(0, 0, 0, 0.1) !important;
    }
    
    /* -------- Form containers -------- */
    div[data-testid="stForm"] {
        background: rgba(255, 255, 255, 0.5) !important;
        backdrop-filter: blur(10px) !important;
        border: 1.5px solid rgba(0, 0, 0, 0.08) !important;
        border-radius: 12px !important;
        padding: 1.5rem !important;
    }
    
    /* -------- Checkboxes and Radio buttons -------- */
    .stCheckbox, .stRadio {
        background: rgba(255, 255, 255, 0.4) !important;
        backdrop-filter: blur(8px) !important;
        border-radius: 8px !important;
        padding: 0.5rem !important;
    }
    
    /* -------- Metric containers -------- */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.6) !important;
        backdrop-filter: blur(12px) !important;
        border: 1.5px solid rgba(0, 0, 0, 0.1) !important;
        border-radius: 12px !important;
        padding: 1rem !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06) !important;
    }
    </style>
    """, unsafe_allow_html=True)