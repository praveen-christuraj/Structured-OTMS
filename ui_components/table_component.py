import streamlit as st
import pandas as pd

class TableDisplay:
    """Professional table display component"""
    
    @staticmethod
    def display_data_table(dataframe, title="", searchable=False):
        """Display a professional data table"""
        if title:
            st.markdown(f"<h3 style='color: #1e3c72;'>{title}</h3>", unsafe_allow_html=True)
        
        if searchable:
            search_term = st.text_input("🔍 Search", key=f"search_{title}")
            if search_term:
                mask = dataframe. astype(str).apply(lambda x: x.str.contains(search_term, case=False)). any(axis=1)
                dataframe = dataframe[mask]
        
        st.dataframe(dataframe, use_container_width=True, hide_index=True)
    
    @staticmethod
    def display_stats_row(stats_dict):
        """Display statistics in a row"""
        cols = st.columns(len(stats_dict))
        for col, (label, value) in zip(cols, stats_dict.items()):
            with col:
                st.metric(label, value)