from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_session
from location_config import LocationConfig
from models import Location
from security import SecurityManager
from stock_analysis_engine import (
    AnalysisConfigManager,
    AnalyticsQueryBuilder,
    DataAnalyzer,
    VisualizationHelper,
)
from ui import header
from ui_components import TableDisplay


def _load_analysis_tabs(location_id: int) -> List[Dict[str, Any]]:
    with get_session() as session:
        return AnalysisConfigManager.load_analysis_tabs(session, int(location_id))


def _render_analysis_visualization(df: pd.DataFrame, viz: Dict[str, Any]) -> None:
    vtype = (viz.get("type") or "table").strip().lower()
    title = (viz.get("title") or "").strip()
    x_field = (viz.get("x_field") or "").strip()
    y_field = (viz.get("y_field") or "").strip()
    series_field = (viz.get("series_field") or "").strip()

    if title:
        st.markdown(f"#### {title}")

    if vtype == "table":
        TableDisplay.display_data_table(df, title="Data", searchable=True)
        return

    if vtype in {"line", "bar", "area"}:
        if not y_field or y_field not in df.columns:
            st.info("Configure a Metric field for this chart.")
            return

        if x_field and x_field not in df.columns:
            st.info("Configured X axis field is not present in the dataset.")
            return

        if series_field and series_field in df.columns and x_field:
            data = df.sort_values(by=x_field) if x_field else df
            if vtype == "line":
                fig = px.line(data, x=x_field, y=y_field, color=series_field, markers=True)
            elif vtype == "bar":
                fig = px.bar(data, x=x_field, y=y_field, color=series_field, barmode="group")
            else:
                fig = px.area(data, x=x_field, y=y_field, color=series_field)
            st.plotly_chart(fig, use_container_width=True)
            return

        data = df.copy()
        if x_field:
            data = data.sort_values(by=x_field)
            chart_df = data[[x_field, y_field]].set_index(x_field)
        else:
            chart_df = data[[y_field]]

        if vtype == "line":
            st.line_chart(chart_df)
        elif vtype == "bar":
            st.bar_chart(chart_df)
        else:
            st.area_chart(chart_df)
        return

    if vtype in {"pie", "donut"}:
        if not (x_field and y_field and x_field in df.columns and y_field in df.columns):
            st.info("Configure X axis field and Metric field for this chart.")
            return
        prepared = VisualizationHelper.prepare_chart_data(df, vtype, x_field=x_field, y_field=y_field)
        pie_df = prepared.get("data") if isinstance(prepared, dict) and prepared.get("data") is not None else df
        hole = 0.45 if vtype == "donut" else 0.0
        fig = px.pie(pie_df, names=x_field, values=y_field, hole=hole)
        st.plotly_chart(fig, use_container_width=True)
        return

    if vtype == "scatter":
        if not (x_field and y_field and x_field in df.columns and y_field in df.columns):
            st.info("Configure X axis field and Metric field for this chart.")
            return
        kwargs: Dict[str, Any] = {}
        if series_field and series_field in df.columns:
            kwargs["color"] = series_field
        fig = px.scatter(df, x=x_field, y=y_field, **kwargs)
        st.plotly_chart(fig, use_container_width=True)
        return

    if vtype == "histogram":
        col = y_field or x_field
        if not col or col not in df.columns:
            st.info("Configure a field for this histogram.")
            return
        fig = px.histogram(df, x=col)
        st.plotly_chart(fig, use_container_width=True)
        return

    if vtype == "metric":
        if not y_field or y_field not in df.columns:
            st.info("Configure Metric field for this widget.")
            return
        stats = DataAnalyzer.calculate_statistics(df, y_field)
        gain_loss = DataAnalyzer.calculate_gain_loss(df, y_field, date_column=(x_field or None))
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Records", f"{len(df):,}")
        with c2:
            total = stats.get("sum")
            st.metric("Total", f"{total:,.2f}" if total is not None else "N/A")
        with c3:
            change = gain_loss.get("absolute_change")
            st.metric("Net Change", f"{change:,.2f}" if change is not None else "N/A")
        return

    st.info(f"Unsupported widget type: {vtype}")


def _render_analysis_tab(location_id: int, tab_cfg: Dict[str, Any], user: Optional[Dict[str, Any]]) -> None:
    tab_id = str(tab_cfg.get("id") or "")
    tab_desc = (tab_cfg.get("description") or "").strip()
    if tab_desc:
        st.caption(tab_desc)

    runtime = tab_cfg.get("runtime_filters") or {}
    date_field = (runtime.get("date_field") or "").strip()

    user_filters: Dict[str, Any] = {"location_id": int(location_id)}
    if date_field:
        end = pd.Timestamp.today().date()
        start = end - pd.Timedelta(days=30)
        picked = st.date_input(
            "Date range",
            value=(start, end),
            key=f"sa_tab_{tab_id}_date",
        )
        if isinstance(picked, (list, tuple)) and len(picked) == 2:
            user_filters["date_from"] = picked[0]
            user_filters["date_to"] = picked[1]

    try:
        qb = AnalyticsQueryBuilder(tab_cfg)
        df = qb.execute(user_filters)
    except Exception as ex:
        st.error(f"Failed to execute analysis query: {ex}")
        try:
            SecurityManager.log_audit(
                session=None,
                username=(user or {}).get("username", "system"),
                action="STOCK_ANALYSIS_ERROR",
                resource_type="StockAnalysisTab",
                resource_id=tab_id or None,
                details=f"Failed to execute analysis tab '{tab_cfg.get('name') or tab_cfg.get('title') or ''}': {ex}",
                user_id=(user or {}).get("id"),
                location_id=int(location_id),
                ip_address=str(st.session_state.get("client_ip") or "N/A"),
                success=False,
            )
        except Exception:
            pass
        return

    if df.empty:
        st.info("No data found for current filters.")
        return

    visualizations = tab_cfg.get("visualizations") or []
    if not visualizations:
        TableDisplay.display_data_table(df, title="Data", searchable=True)
        return

    for viz in visualizations:
        if not isinstance(viz, dict):
            continue
        _render_analysis_visualization(df, viz)
        st.markdown("---")


def render_stock_analysis_page(active_location_id: Optional[int], user: Optional[Dict[str, Any]]):
    header("Stock Analysis")

    if not user:
        st.error("Please login to access this page")
        st.stop()

    if not active_location_id:
        st.error("No active location selected")
        st.stop()

    try:
        _user_role = st.session_state.get("auth_user", {}).get("role")
        _loc_id = st.session_state.get("active_location_id")
        if _user_role not in ["admin-operations", "manager"] and _loc_id:
            with get_session() as _s:
                _cfg = LocationConfig.get_config(_s, int(_loc_id))
            if _cfg.get("page_access", {}).get("Stock Analysis") is False:
                st.caption("Stock Analysis Access: ⛔ Denied")
                st.stop()
    except Exception:
        pass

    with get_session() as session:
        loc = session.query(Location).get(int(active_location_id))
    if not loc:
        st.error("Location not found.")
        st.stop()

    st.info(f"Active Location: {loc.name} ({loc.code})")

    view_key = f"_audit_view_stock_analysis_{active_location_id}"
    if not st.session_state.get(view_key):
        try:
            SecurityManager.log_audit(
                session=None,
                username=(user or {}).get("username", "system"),
                action="VIEW",
                resource_type="StockAnalysis",
                resource_id=str(active_location_id),
                details=f"Viewed Stock Analysis for {loc.name} ({loc.code})",
                user_id=(user or {}).get("id"),
                location_id=int(active_location_id),
                ip_address=str(st.session_state.get("client_ip") or "N/A"),
                success=True,
            )
        except Exception:
            pass
        st.session_state[view_key] = True

    analysis_tabs = _load_analysis_tabs(int(active_location_id))
    if not analysis_tabs:
        st.info("No Stock Analysis tabs configured for this location. Ask an administrator to use Stock Analysis Customization.")
        return

    tab_titles = [(t.get("name") or t.get("title") or "Analysis").strip() or "Analysis" for t in analysis_tabs]
    st_tabs = st.tabs(tab_titles)
    for idx, tab_cfg in enumerate(analysis_tabs):
        with st_tabs[idx]:
            _render_analysis_tab(int(active_location_id), tab_cfg, user)
