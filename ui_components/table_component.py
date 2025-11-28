import streamlit as st
import pandas as pd

class TableDisplay:
    
    @staticmethod
    def display_data_table(dataframe, title="", searchable=False):
        if title:
            st.markdown(f"""
            <div style="display:flex; align-items:center; gap:.5rem; margin-bottom:.5rem;">
                <span style="width:10px; height:10px; border-radius:50%; background:#667eea; display:inline-block;"></span>
                <h3 style="margin:0; color:#1e3c72; font-size:1.1rem;">{title}</h3>
            </div>
            """, unsafe_allow_html=True)

        if searchable:
            search_term = st.text_input("🔍 Search", key=f"search_{title}")
            if search_term:
                mask = dataframe.astype(str).apply(lambda x: x.str.contains(search_term, case=False)).any(axis=1)
                dataframe = dataframe[mask]

        st.dataframe(dataframe, use_container_width=True, hide_index=True)

    @staticmethod
    def display_stats_row(stats_dict):
        cols = st.columns(len(stats_dict))
        for col, (label, value) in zip(cols, stats_dict.items()):
            with col:
                st.metric(label, value)
