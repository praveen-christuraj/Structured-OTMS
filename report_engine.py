# report_engine.py
"""
Report Engine - Core logic for dynamic report generation
Handles query building, filtering, aggregation, and exports (CSV, XLSX, PDF)
"""

import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Any, Optional
import json
from io import BytesIO
import base64

from sqlalchemy import and_, or_, func, desc, asc
from sqlalchemy.orm import Session

from db import get_session
from models import (
    TankTransaction, Tank, Location, User, YadeVoyage, TankerTransaction,
    OTRRecord, FSOOperation, Vessel, VesselOperation, GPPProductionRecord,
    RiverDraftRecord, ProducedWaterRecord, OFSProductionEvacuationRecord
)


class ReportEngine:
    """
    Dynamic report generation engine.
    Builds queries from JSON configuration and exports data in multiple formats.
    """
    
    # Map of available data sources (tables)
    DATA_SOURCES = {
        'tank_transactions': TankTransaction,
        'tanker_transactions': TankerTransaction,
        'yade_voyages': YadeVoyage,
        'otr_records': OTRRecord,
        'fso_operations': FSOOperation,
        'gpp_production': GPPProductionRecord,
        'river_draft': RiverDraftRecord,
        'produced_water': ProducedWaterRecord,
        'ofs_production': OFSProductionEvacuationRecord,
        'tanks': Tank,
        'vessels': Vessel,
        'locations': Location,
    }
    
    # Map of operators for filters
    OPERATORS = {
        'equals': lambda col, val: col == val,
        'not_equals': lambda col, val: col != val,
        'greater_than': lambda col, val: col > val,
        'less_than': lambda col, val: col < val,
        'greater_equal': lambda col, val: col >= val,
        'less_equal': lambda col, val: col <= val,
        'contains': lambda col, val: col.like(f'%{val}%') if val and isinstance(val, str) else col.like('%'),
        'starts_with': lambda col, val: col.like(f'{val}%') if val and isinstance(val, str) else col.like('%'),
        'ends_with': lambda col, val: col.like(f'%{val}') if val and isinstance(val, str) else col.like('%'),
        'in': lambda col, val: col.in_(val) if val and isinstance(val, (list, tuple)) else col.in_([]),
        'between': lambda col, val: and_(col >= val[0], col <= val[1]) if val and isinstance(val, (list, tuple)) and len(val) >= 2 else col >= 0,
    }
    
    def __init__(self, report_config: Dict[str, Any]):
        """
        Initialize report engine with configuration.
        
        Args:
            report_config: JSON configuration from ReportDefinition.config_json
        """
        self.config = report_config
        self.data_source = report_config.get('data_source', {})
        self.columns = report_config.get('columns', [])
        self.filters = report_config.get('filters', [])
        self.grouping = report_config.get('grouping', [])
        self.sorting = report_config.get('sorting', [])
        self.aggregations = report_config.get('aggregations', {})
    
    def build_query(self, session: Session, user_filters: Dict[str, Any] = None):
        """
        Build SQLAlchemy query from configuration.
        
        Args:
            session: Database session
            user_filters: Runtime filters provided by user (e.g., date range)
        
        Returns:
            SQLAlchemy query object
        """
        # Get the primary table
        table_name = self.data_source.get('table')
        if not table_name or not isinstance(table_name, str):
            raise ValueError(f"Invalid or missing data source table: {table_name}")
        
        # Check if it's a standard table or custom table
        if table_name in self.DATA_SOURCES:
            primary_model = self.DATA_SOURCES[table_name]
        else:
            # Try to get custom table model
            try:
                from models import get_custom_table_model
                from logger import log_info, log_error
                
                log_info(f"Attempting to load custom table model for '{table_name}'")
                primary_model = get_custom_table_model(table_name)
                
                if not primary_model:
                    log_error(f"Custom table '{table_name}' not found in database")
                    raise ValueError(f"Custom table '{table_name}' not found in database. Please ensure the table exists.")
                    
                log_info(f"Successfully loaded model for custom table '{table_name}'")
            except ValueError:
                raise  # Re-raise ValueError as-is
            except Exception as e:
                from logger import log_error
                log_error(f"Error loading custom table '{table_name}': {str(e)}", exc_info=True)
                raise ValueError(f"Unknown data source: {table_name}. Error: {e}")
        
        # Start with base query anchored to primary model
        query = session.query(primary_model).select_from(primary_model)

        # Apply base location scoping if applicable
        base_loc_mode = self.data_source.get('base_location_mode')
        base_loc_id = self.data_source.get('base_location_id')
        if hasattr(primary_model, 'location_id'):
            if base_loc_mode == 'current' and isinstance(user_filters, dict) and user_filters.get('location_id') is not None:
                query = query.filter(primary_model.location_id == user_filters.get('location_id'))
            elif base_loc_mode == 'specific' and base_loc_id:
                query = query.filter(primary_model.location_id == base_loc_id)
        
        # Apply joins if specified (only for standard tables) using explicit ON clauses
        if table_name in self.DATA_SOURCES:
            joined_tables = set()
            joins = self.data_source.get('joins', [])
            for join_config in joins:
                join_table = join_config.get('table')
                if not join_table:
                    continue
                # avoid self-joins and duplicate joins that cause ambiguity
                if join_table == table_name or join_table in joined_tables:
                    continue
                # resolve join model (standard only for now)
                join_model = self.DATA_SOURCES.get(join_table)
                if not join_model:
                    continue

                # Build explicit ON clause from join_keys to avoid ambiguous joins
                join_keys = join_config.get('join_keys') or []
                conditions = []
                for jk in join_keys:
                    left_key = jk.get('primary')
                    right_key = jk.get('source')
                    if left_key and right_key and hasattr(primary_model, left_key) and hasattr(join_model, right_key):
                        conditions.append(getattr(primary_model, left_key) == getattr(join_model, right_key))

                if conditions:
                    join_type = (join_config.get('type') or join_config.get('join_type') or '').lower()
                    if join_type == 'left':
                        query = query.outerjoin(join_model, and_(*conditions))
                    else:
                        query = query.join(join_model, and_(*conditions))
                    joined_tables.add(join_table)
                # If no valid join keys, skip joining to prevent ambiguous JOIN errors
        
        # Apply predefined filters from config
        query = self._apply_filters(query, primary_model, self.filters, user_filters)
        
        return query
    
    def _apply_filters(self, query, model, filter_configs: List[Dict], user_filters: Dict = None):
        """
        Apply filters to query.
        
        Args:
            query: SQLAlchemy query
            model: Primary model class
            filter_configs: List of filter configurations
            user_filters: Runtime user-provided filters
        
        Returns:
            Filtered query
        """
        user_filters = user_filters or {}
        
        for filter_config in filter_configs:
            field = filter_config.get('field')
            if not field or not isinstance(field, str):
                continue  # Skip invalid field definitions
            
            operator = filter_config.get('operator', 'equals')
            value = filter_config.get('value')
            
            # Replace placeholder values with actual user input
            if isinstance(value, str) and value:
                if value == 'user_location' and 'location_id' in user_filters:
                    value = user_filters['location_id']
                elif value == 'date_range' and 'date_range' in user_filters:
                    value = user_filters['date_range']
                elif len(value) > 5 and value.startswith('user_') and value in user_filters:
                    value = user_filters[value]
            
            # Check if user provided override for this filter
            if field in user_filters:
                value = user_filters[field]
            
            # Skip if no value provided
            if value is None:
                continue
            
            # Get the column from model
            if hasattr(model, field):
                column = getattr(model, field)
                
                # Apply operator with validation
                if operator in self.OPERATORS:
                    try:
                        # Validate value type for specific operators
                        if operator == 'between':
                            if not isinstance(value, (list, tuple)) or len(value) < 2:
                                continue  # Skip invalid between filter
                        elif operator in ['contains', 'starts_with', 'ends_with']:
                            if not value or not isinstance(value, str):
                                continue  # Skip invalid string filter
                        elif operator == 'in':
                            if not isinstance(value, (list, tuple)):
                                continue  # Skip invalid in filter
                        
                        filter_func = self.OPERATORS[operator]
                        query = query.filter(filter_func(column, value))
                    except (IndexError, TypeError, AttributeError) as e:
                        # Skip filter if it causes an error
                        print(f"Warning: Skipping filter {field} with operator {operator}: {e}")
                        continue
        
        return query
    
    def execute_report(self, user_filters: Dict[str, Any] = None) -> pd.DataFrame:
        """
        Execute report and return results as pandas DataFrame.
        
        Args:
            user_filters: Runtime filters (date range, location, etc.)
        
        Returns:
            pandas DataFrame with report results
        """
        try:
            table_name = self.data_source.get('table')
            use_flex = bool(table_name and table_name not in self.DATA_SOURCES)
            if use_flex:
                from db import get_flex_session
                sess_ctx = get_flex_session()
            else:
                sess_ctx = get_session()
            with sess_ctx as session:
                query = self.build_query(session, user_filters)
                rows = query.all()

                # Collect primary and extra key fields required for merges
                primary_table = self.data_source.get('table')
                required_primary_fields = set()
                for col_config in self.columns:
                    for jk in col_config.get('join_keys', []) or []:
                        pf = jk.get('primary')
                        if pf:
                            required_primary_fields.add(pf)
                for rel in self.data_source.get('joins', []) or []:
                    for jk in rel.get('join_keys', []) or []:
                        pf = jk.get('primary')
                        if pf:
                            required_primary_fields.add(pf)

                # Build primary results
                results = []
                for row in rows:
                    row_dict = {}
                    # Extract fields from primary table columns
                    for col_config in self.columns:
                        # Only primary-source fields here; externals will be merged later
                        src_tbl = col_config.get('source_table', primary_table)
                        src_field = col_config.get('source_field') or col_config.get('field')
                        label_field = col_config.get('field')
                        label = col_config.get('label') or (label_field if isinstance(label_field, str) else (src_field or 'Unknown'))
                        col_type = col_config.get('type', 'string')
                        if src_tbl == primary_table and src_field and hasattr(row, src_field):
                            value = getattr(row, src_field)
                            if col_type == 'date' and isinstance(value, (date, datetime)):
                                value = value.strftime('%Y-%m-%d')
                            elif col_type == 'datetime' and isinstance(value, datetime):
                                value = value.strftime('%Y-%m-%d %H:%M:%S')
                            elif col_type == 'numeric' and value is not None:
                                try:
                                    value = float(value)
                                except Exception:
                                    pass
                            row_dict[label] = value
                    # Ensure required primary key fields present for merges
                    for pf in required_primary_fields:
                        if hasattr(row, pf):
                            row_dict[pf] = getattr(row, pf)
                    # Auto-include common join keys even if not selected
                    for pf in ['date', 'tx_date', 'record_date', 'location_id', 'tank_id', 'vessel_id']:
                        if hasattr(row, pf) and pf not in row_dict:
                            row_dict[pf] = getattr(row, pf)
                    results.append(row_dict)

                df = pd.DataFrame(results)

                # Apply grouping and aggregations if specified
                if self.grouping and self.aggregations:
                    df = self._apply_aggregations(df)
                
                # Merge external source columns
                df = self._merge_external_columns(df, user_filters)

                # Apply formula columns
                df = self._apply_formula_columns(df)

                # Apply runtime filters at DataFrame level (supports label-based fields)
                df = self._apply_runtime_filters_df(df, user_filters)

                # Apply sorting after filtering
                if self.sorting and not df.empty:
                    for sort_config in self.sorting:
                        field = sort_config.get('field')
                        order = sort_config.get('order', 'asc')
                        ascending = (order == 'asc')
                        if field in df.columns:
                            df = df.sort_values(by=field, ascending=ascending)

                # Keep only requested columns (plus any filter fields present)
                requested_labels = []
                for c in self.columns:
                    lbl = c.get('label') or c.get('field') or c.get('source_field')
                    if lbl and lbl not in requested_labels:
                        requested_labels.append(lbl)
                filter_fields = [f.get('field') for f in (self.filters or []) if f.get('field')]
                ordered_keep = []
                for col in requested_labels + filter_fields:
                    if col in df.columns and col not in ordered_keep:
                        ordered_keep.append(col)
                if ordered_keep:
                    df = df[ordered_keep]

                # Apply numeric decimal-place rounding per column config
                df = self._apply_decimal_places(df)

                return df
        except IndexError as e:
            raise ValueError(f"String index error in report execution. Check report configuration. Details: {str(e)}")
        except Exception as e:
            raise ValueError(f"Error executing report: {str(e)}")
    
    def _apply_aggregations(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply grouping and aggregations to DataFrame."""
        if df.empty:
            return df
        
        # Build aggregation dict
        agg_dict = {}
        for agg_name, agg_config in self.aggregations.items():
            field = agg_config.get('field')
            function = agg_config.get('function', 'sum')
            
            if field in df.columns:
                agg_dict[field] = function
        
        # Apply grouping
        if self.grouping and agg_dict:
            valid_groups = [g for g in self.grouping if g in df.columns]
            if valid_groups:
                df = df.groupby(valid_groups).agg(agg_dict).reset_index()
        
        return df

    def _merge_external_columns(self, df_primary: pd.DataFrame, user_filters: Dict[str, Any]) -> pd.DataFrame:
        primary_table = self.data_source.get('table')
        if df_primary is None or df_primary.empty:
            return df_primary
        external_cols = [c for c in self.columns if c.get('source_table') and c.get('source_table') != primary_table]
        if not external_cols:
            return df_primary

        relationship_map = {}
        for rel in self.data_source.get('joins', []) or []:
            tbl = rel.get('table')
            jks = rel.get('join_keys') or []
            if tbl and jks:
                relationship_map[tbl] = jks

        # Group external columns by source table to minimize queries
        from collections import defaultdict
        table_cols = defaultdict(list)
        for c in external_cols:
            table_cols[c['source_table']].append(c)

        from sqlalchemy import inspect
        from db import engine, flex_engine, get_flex_session

        def _pick_session(table_name: str):
            # Decide which engine has the table; default to primary
            if flex_engine:
                try:
                    if table_name in inspect(flex_engine).get_table_names():
                        return get_flex_session
                except Exception:
                    pass
            if engine:
                try:
                    if table_name in inspect(engine).get_table_names():
                        return get_session
                except Exception:
                    pass
            return get_session

        for src_table, cols in table_cols.items():
            sess_ctx = _pick_session(src_table)
            with sess_ctx() as session:
                # Build base query for source table
                src_model = None
                if src_table in self.DATA_SOURCES:
                    src_model = self.DATA_SOURCES[src_table]
                else:
                    from models import get_custom_table_model
                    src_model = get_custom_table_model(src_table)
                if not src_model:
                    continue
                q = session.query(src_model)
                # Reuse global filters when possible
                q = self._apply_filters(q, src_model, self.filters, user_filters)
                rows = q.all()
                # Build df for source with join keys and selected fields
                records = []
                # Aggregate map per field
                for r in rows:
                    rec = {}
                    # include join keys used by any col in this src_table
                    needed_jk = set()
                    # 1) Column-specific join keys
                    for c in cols:
                        for jk in c.get('join_keys', []) or []:
                            if jk.get('source'):
                                needed_jk.add(jk['source'])
                    for jk in relationship_map.get(src_table, []) or []:
                        if jk.get('source'):
                            needed_jk.add(jk['source'])
                    # Add the required source-side join fields to the record
                    for jkf in needed_jk:
                        if hasattr(r, jkf):
                            rec[jkf] = getattr(r, jkf)
                    for c in cols:
                        sf = c.get('source_field')
                        label = c.get('label') or sf
                        val = getattr(r, sf) if (sf and hasattr(r, sf)) else None
                        # Store raw; aggregation applied later via groupby after merge if needed, or pre-aggregate
                        rec[label] = val
                    records.append(rec)
                df_src = pd.DataFrame(records)
                # If any aggregations specified, apply grouping by join keys and aggregate label columns
                agg_map = {}
                for c in cols:
                    label = c.get('label') or c.get('source_field')
                    agg = c.get('aggregation')
                    if agg:
                        # map textual agg to pandas function
                        func_map = {'sum': 'sum', 'avg': 'mean', 'max': 'max', 'min': 'min'}
                        agg_map[label] = func_map.get(agg, 'sum')
                join_src_fields = []
                for c in cols:
                    for jk in c.get('join_keys', []) or []:
                        if jk.get('source') and jk['source'] not in join_src_fields:
                            join_src_fields.append(jk['source'])
                if agg_map and df_src is not None and not df_src.empty and join_src_fields:
                    df_src = df_src.groupby(join_src_fields).agg(agg_map).reset_index()

                # Perform left merge; auto-detect join keys when not provided
                src_col_names = [c.name for c in src_model.__table__.columns]
                auto_pairs_catalog = [
                    ('tx_date', 'tx_date'), ('date', 'date'), ('record_date', 'record_date'),
                    ('date', 'tx_date'), ('tx_date', 'date'), ('date', 'record_date'), ('record_date', 'date'),
                    ('location_id', 'location_id'), ('tank_id', 'tank_id'), ('vessel_id', 'vessel_id')
                ]
                for c in cols:
                    label = c.get('label') or c.get('source_field')
                    join_pairs = c.get('join_keys') or relationship_map.get(src_table) or []
                    # Keep only pairs that exist on both sides
                    join_pairs = [
                        jk for jk in (join_pairs or [])
                        if jk.get('primary') in df_primary.columns and jk.get('source') in df_src.columns
                    ]
                    left_on = [jk['primary'] for jk in join_pairs]
                    right_on = [jk['source'] for jk in join_pairs]
                    if not left_on or not right_on:
                        link_by = (c.get('link_by') or 'auto').lower().replace(' ', '')
                        def _pick(colnames, candidates):
                            for k in candidates:
                                if k in colnames:
                                    return k
                            return None
                        if link_by != 'auto':
                            l_date = _pick(list(df_primary.columns), ['tx_date','date','record_date'])
                            r_date = _pick(src_col_names, ['tx_date','date','record_date'])
                            l_loc = _pick(list(df_primary.columns), ['location_id'])
                            r_loc = _pick(src_col_names, ['location_id'])
                            l_tank = _pick(list(df_primary.columns), ['tank_id'])
                            r_tank = _pick(src_col_names, ['tank_id'])
                            if link_by == 'date' and l_date and r_date:
                                left_on, right_on = [l_date], [r_date]
                            elif link_by == 'date+location' and l_date and r_date and l_loc and r_loc:
                                left_on, right_on = [l_date, l_loc], [r_date, r_loc]
                            elif link_by == 'tank+date' and l_tank and r_tank and l_date and r_date:
                                left_on, right_on = [l_tank, l_date], [r_tank, r_date]
                        # Auto-detect pairs based on common keys/synonyms
                        auto_left_on, auto_right_on = [], []
                        left_cols = list(df_primary.columns)
                        for lo, ro in auto_pairs_catalog:
                            if lo in left_cols and ro in src_col_names:
                                auto_left_on.append(lo)
                                auto_right_on.append(ro)
                        left_on, right_on = auto_left_on, auto_right_on
                    # If still no join keys, fallback to broadcasting aggregated value for the column
                    if not left_on or not right_on or not all([lo in df_primary.columns for lo in left_on]):
                        agg = c.get('aggregation')
                        series = df_src[label] if label in df_src.columns else pd.Series([pd.NA])
                        if agg and not series.empty:
                            func_map = {'sum': 'sum', 'avg': 'mean', 'max': 'max', 'min': 'min'}
                            fn = func_map.get(agg, 'sum')
                            try:
                                val = getattr(series, fn)()
                            except Exception:
                                val = pd.NA
                        else:
                            val = series.iloc[0] if len(series) > 0 else pd.NA
                        df_primary[label] = val
                        continue
                    # Merge only the required label column plus join_src_fields to avoid duplication
                    keep_cols = list(set(right_on + [label]))
                    df_merge_src = df_src[keep_cols] if set(keep_cols).issubset(set(df_src.columns)) else df_src
                    mode = c.get('source_location_mode')
                    loc_id = c.get('source_location_id')
                    if mode == 'current' and isinstance(user_filters, dict):
                        cur_loc = user_filters.get('location_id')
                        if cur_loc is not None and 'location_id' in df_merge_src.columns:
                            df_merge_src = df_merge_src[df_merge_src['location_id'] == cur_loc]
                    elif mode == 'specific' and loc_id is not None:
                        if 'location_id' in df_merge_src.columns:
                            df_merge_src = df_merge_src[df_merge_src['location_id'] == loc_id]

                    # Normalize join column types for better matching (e.g., date strings vs datetime objects)
                    for lo in left_on:
                        if lo in df_primary.columns and pd.api.types.is_datetime64_any_dtype(df_primary[lo]):
                            df_primary[lo] = pd.to_datetime(df_primary[lo], errors='coerce').dt.strftime('%Y-%m-%d')
                        elif lo in df_primary.columns:
                            df_primary[lo] = df_primary[lo].astype(str)
                    for ro in right_on:
                        if ro in df_merge_src.columns and pd.api.types.is_datetime64_any_dtype(df_merge_src[ro]):
                            df_merge_src[ro] = pd.to_datetime(df_merge_src[ro], errors='coerce').dt.strftime('%Y-%m-%d')
                        elif ro in df_merge_src.columns:
                            df_merge_src[ro] = df_merge_src[ro].astype(str)

                    df_primary = df_primary.merge(
                        df_merge_src,
                        left_on=left_on,
                        right_on=right_on,
                        how='left',
                        suffixes=('', f'_{src_table}')
                    )
                    # Drop duplicate join columns brought from source to keep table tidy
                    for ro in right_on:
                        dup_col = f"{ro}_{src_table}"
                        if dup_col in df_primary.columns:
                            df_primary = df_primary.drop(columns=[dup_col])

        return df_primary

    def _apply_formula_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        for col_config in self.columns:
            formula = col_config.get('formula')
            label = col_config.get('label') or col_config.get('field')
            if not formula or not label:
                continue
            op = formula.get('operation')
            cols = formula.get('columns') or []
            if not cols:
                continue
            # Ensure columns exist
            if not all([c in df.columns for c in cols]):
                continue
            try:
                if op == 'sum':
                    df[label] = df[cols].sum(axis=1)
                elif op == 'subtract':
                    base = df[cols[0]]
                    for c in cols[1:]:
                        base = base - df[c]
                    df[label] = base
                elif op == 'multiply':
                    prod = df[cols[0]]
                    for c in cols[1:]:
                        prod = prod * df[c]
                    df[label] = prod
                elif op == 'divide':
                    denom = df[cols[1]] if len(cols) > 1 else 1
                    df[label] = df[cols[0]] / denom.replace(0, pd.NA)
                elif op == 'percentage':
                    denom = df[cols[1]] if len(cols) > 1 else 1
                    df[label] = (df[cols[0]] / denom.replace(0, pd.NA)) * 100
                elif op == 'maximum':
                    df[label] = df[cols].max(axis=1)
                elif op == 'minimum':
                    df[label] = df[cols].min(axis=1)
                elif op == 'average':
                    df[label] = df[cols].mean(axis=1)
            except Exception:
                # If formula fails, keep column as NA
                df[label] = pd.NA
        return df

    def _apply_runtime_filters_df(self, df: pd.DataFrame, user_filters: Dict[str, Any]) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        user_filters = user_filters or {}
        # Date range filter applied to common date-like columns
        if 'date_range' in user_filters and isinstance(user_filters['date_range'], (list, tuple)) and len(user_filters['date_range']) >= 2:
            start, end = user_filters['date_range'][0], user_filters['date_range'][1]
            # Prefer configured date/datetime columns (labels or raw fields) before falling back
            date_candidates = []
            try:
                for col_config in self.columns or []:
                    col_type = str(col_config.get('type', '')).lower()
                    if col_type in ('date', 'datetime'):
                        label = col_config.get('label') or col_config.get('field') or col_config.get('source_field')
                        for name in [label, col_config.get('field'), col_config.get('source_field')]:
                            if isinstance(name, str) and name not in date_candidates:
                                date_candidates.append(name)
            except Exception:
                pass
            for fallback in ['date', 'tx_date', 'record_date']:
                if fallback not in date_candidates:
                    date_candidates.append(fallback)
            try:
                start_dt = pd.to_datetime(start)
                end_dt = pd.to_datetime(end)
                if pd.isna(start_dt) or pd.isna(end_dt):
                    start_dt = None
                    end_dt = None
                elif start_dt > end_dt:
                    start_dt, end_dt = end_dt, start_dt
            except Exception:
                start_dt = None
                end_dt = None
            if start_dt is not None and end_dt is not None:
                for dc in date_candidates:
                    if dc not in df.columns:
                        continue
                    try:
                        series = pd.to_datetime(df[dc], errors='coerce')
                        mask = (series >= start_dt) & (series <= end_dt)
                        df = df[mask]
                        break
                    except Exception:
                        continue
        # Apply configured filters using label-based field names
        for fc in (self.filters or []):
            field = fc.get('field')
            operator = fc.get('operator', 'equals')
            if not isinstance(field, str) or field not in df.columns:
                continue
            value = user_filters.get(field)
            # Skip empty values to avoid filtering everything accidentally
            if value is None:
                continue
            if isinstance(value, str) and value.strip() == "":
                continue
            if isinstance(value, (list, tuple)) and len(value) == 0:
                continue
            try:
                if operator == 'equals':
                    df = df[df[field] == value]
                elif operator == 'not_equals':
                    df = df[df[field] != value]
                elif operator == 'greater_than':
                    df = df[pd.to_numeric(df[field], errors='coerce') > float(value)]
                elif operator == 'less_than':
                    df = df[pd.to_numeric(df[field], errors='coerce') < float(value)]
                elif operator == 'greater_equal':
                    df = df[pd.to_numeric(df[field], errors='coerce') >= float(value)]
                elif operator == 'less_equal':
                    df = df[pd.to_numeric(df[field], errors='coerce') <= float(value)]
                elif operator == 'contains' and isinstance(value, str):
                    df = df[df[field].astype(str).str.contains(value, na=False)]
                elif operator == 'starts_with' and isinstance(value, str):
                    df = df[df[field].astype(str).str.startswith(value)]
                elif operator == 'ends_with' and isinstance(value, str):
                    df = df[df[field].astype(str).str.endswith(value)]
                elif operator == 'in' and isinstance(value, (list, tuple)):
                    df = df[df[field].isin(value)]
                elif operator == 'between' and isinstance(value, (list, tuple)) and len(value) >= 2:
                    low, high = value[0], value[1]
                    series = pd.to_numeric(df[field], errors='coerce')
                    df = df[(series >= float(low)) & (series <= float(high))]
            except Exception:
                continue
        return df

    def _apply_column_formatting(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply formatting rules to columns based on configuration.

        This method processes formatting configurations for:
        - Number formatting (decimals, thousands separator)
        - Prefix/suffix
        - Conditional formatting (returns formatted strings)
        """
        if df is None or df.empty:
            return df

        for col_config in self.columns:
            formatting = col_config.get('formatting')
            if not formatting:
                continue

            label = col_config.get('label') or col_config.get('field')
            if label not in df.columns:
                continue

            try:
                col_type = col_config.get('type', 'string')

                if col_type == 'numeric':
                    decimal_places = formatting.get('decimal_places', 2)
                    thousands_sep = formatting.get('thousands_separator', False)
                    prefix = formatting.get('prefix', '')
                    suffix = formatting.get('suffix', '')

                    def format_number(val):
                        if pd.isna(val):
                            return ''
                        try:
                            num = float(val)
                            if thousands_sep:
                                formatted = f"{num:,.{decimal_places}f}"
                            else:
                                formatted = f"{num:.{decimal_places}f}"
                            return f"{prefix}{formatted}{suffix}"
                        except Exception:
                            return str(val)

                    df[f'{label}_formatted'] = df[label].apply(format_number)

            except Exception:
                continue

        return df

    def _apply_decimal_places(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Round numeric columns based on configured decimal_places so the preview
        and exports respect the Report Customization settings.
        """
        if df is None or df.empty:
            return df
        for col_config in self.columns:
            try:
                if str(col_config.get("type")).lower() != "numeric":
                    continue
                label = col_config.get("label") or col_config.get("field") or col_config.get("source_field")
                if not label or label not in df.columns:
                    continue
                dp = col_config.get("decimal_places")
                if dp is None:
                    continue
                dp = int(dp)
                df[label] = pd.to_numeric(df[label], errors="coerce").round(dp)
            except Exception:
                continue
        return df
    
    def export_csv(self, df: pd.DataFrame, filename: str = None) -> bytes:
        """
        Export DataFrame to CSV.
        
        Args:
            df: pandas DataFrame
            filename: Optional filename (not used, for consistency)
        
        Returns:
            CSV data as bytes
        """
        csv_buffer = BytesIO()
        df.to_csv(csv_buffer, index=False, encoding='utf-8')
        csv_buffer.seek(0)
        return csv_buffer.getvalue()
    
    def export_xlsx(self, df: pd.DataFrame, filename: str = None) -> bytes:
        """
        Export DataFrame to Excel (XLSX).
        
        Args:
            df: pandas DataFrame
            filename: Optional filename (not used, for consistency)
        
        Returns:
            Excel data as bytes
        """
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Report')
        excel_buffer.seek(0)
        return excel_buffer.getvalue()
    
    def export_pdf(self, df: pd.DataFrame, report_name: str = "Report", user_filters: Dict[str, Any] = None) -> bytes:
        """
        Export DataFrame to PDF.
        
        Args:
            df: pandas DataFrame
            report_name: Name of the report for title
            user_filters: Runtime filters (for calculating date-based averages)
        
        Returns:
            PDF data as bytes
        """
        from reportlab.lib.pagesizes import A4, A3, landscape, portrait
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.units import inch

        pdf_buffer = BytesIO()

        # PDF options from config (orientation/page size/logo flag)
        opts = {}
        try:
            opts = self.config.get("pdf_options", {}) if isinstance(self.config, dict) else {}
        except Exception:
            opts = {}
        orientation = (opts.get("orientation") or "landscape").lower()
        page_size_name = (opts.get("page_size") or "A4").upper()
        include_logo = bool(opts.get("include_logo", True))

        page_size_map = {"A4": A4, "A3": A3}
        base_size = page_size_map.get(page_size_name, A4)
        page_size = landscape(base_size) if orientation == "landscape" else portrait(base_size)

        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=page_size,
            leftMargin=18,
            rightMargin=18,
            topMargin=24,
            bottomMargin=24,
        )
        elements = []

        # Palette aligned with conventional reports
        header_bg = colors.HexColor("#0B3D91")
        header_text = colors.white
        table_header_bg = colors.HexColor("#1E3A8A")
        table_row_alt = colors.HexColor("#F3F4F6")
        table_grid = colors.HexColor("#D1D5DB")

        # Styles
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Heading1"], textColor=header_text))
        styles.add(ParagraphStyle(name="Meta", parent=styles["Normal"], textColor=header_text, fontSize=9))
        styles.add(ParagraphStyle(name="TableCell", parent=styles["Normal"], fontSize=9))

        # Header bar
        title_para = Paragraph(report_name or "Report", styles["ReportTitle"])
        meta_para = Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["Meta"])
        header_cells = [[title_para, meta_para]]
        header_table = Table(header_cells, colWidths=[doc.width * 0.6, doc.width * 0.4])
        header_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), header_bg),
                    ("TEXTCOLOR", (0, 0), (-1, -1), header_text),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(header_table)
        elements.append(Spacer(1, 0.2 * inch))

        # Optional logo placeholder (text badge) to keep consistent layout without needing image assets
        if include_logo:
            logo_para = Paragraph("<b>OTMS</b> | Operations Reporting", styles["Normal"])
            elements.append(logo_para)
            elements.append(Spacer(1, 0.1 * inch))

        # Subtitle line
        elements.append(Paragraph("Custom Report Output", styles["Normal"]))
        elements.append(Spacer(1, 0.15 * inch))
        
        # Prepare decimal formatting lookup for numeric columns
        decimals_lookup = {}
        try:
            for col_cfg in self.columns:
                lbl = col_cfg.get("label") or col_cfg.get("field") or col_cfg.get("source_field")
                if not lbl:
                    continue
                if str(col_cfg.get("type")).lower() == "numeric":
                    try:
                        # VCF gets 5 decimal places, everything else gets 2
                        if 'vcf' in lbl.lower():
                            decimals_lookup[lbl] = 5
                        else:
                            decimals_lookup[lbl] = int(col_cfg.get("decimal_places")) if col_cfg.get("decimal_places") is not None else 2
                    except Exception:
                        decimals_lookup[lbl] = 2
        except Exception:
            decimals_lookup = {}

        def _fmt_num(val, dp):
            try:
                v = float(val)
                if pd.isna(v):
                    return ""
                return f"{v:,.{dp}f}"
            except Exception:
                return "" if pd.isna(val) else str(val)

        # Make a display copy with formatted numeric columns
        df_display = df.copy()
        for col in list(df_display.columns):
            if col in decimals_lookup:
                dp = decimals_lookup[col]
                df_display[col] = df_display[col].apply(lambda x, d=dp: _fmt_num(x, d))

        # Prepare table data
        if df.empty:
            no_data = Paragraph("No data available for this report.", styles['Normal'])
            elements.append(no_data)
        else:
            # Limit columns if too many (PDF width limitation)
            max_cols = 12
            if len(df_display.columns) > max_cols:
                df_display = df_display.iloc[:, :max_cols]

            # Convert DataFrame to list of lists (stringify values for consistency)
            table_data = [list(map(str, df_display.columns.tolist()))]
            for row_vals in df_display.values.tolist():
                table_data.append([("" if v is None else str(v)) for v in row_vals])

            # Derive column widths evenly across available width
            col_count = len(df_display.columns)
            col_width = doc.width / col_count if col_count else doc.width
            col_widths = [col_width for _ in range(col_count)]

            table = Table(table_data, colWidths=col_widths, repeatRows=1)

            # Style the table using conventional palette
            style_cmds = [
                ("BACKGROUND", (0, 0), (-1, 0), table_header_bg),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, table_grid),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
            # Zebra striping for body rows
            for idx in range(1, len(table_data)):
                if idx % 2 == 0:
                    style_cmds.append(("BACKGROUND", (0, idx), (-1, idx), table_row_alt))

            table.setStyle(TableStyle(style_cmds))
            elements.append(table)

            # Totals / summary section in PDF when enabled
            show_totals = bool(self.config.get("show_totals", False)) if isinstance(self.config, dict) else False
            if show_totals:
                numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) or c in decimals_lookup]
                numeric_cols = [c for c in numeric_cols if c in df.columns]
                if numeric_cols:
                    elements.append(Spacer(1, 0.2 * inch))
                    elements.append(Paragraph("Summary (Totals)", styles["Normal"]))
                    summary_headers = ["Metric"] + numeric_cols
                    summary_rows = []
                    metrics = ["Total", "Average"]
                    
                    # Calculate number of days from date filter for proper daily average
                    num_days = 1  # default to 1 day if no filter applied
                    if user_filters and 'date_range' in user_filters and isinstance(user_filters['date_range'], (list, tuple)) and len(user_filters['date_range']) >= 2:
                        try:
                            start_date = user_filters['date_range'][0]
                            end_date = user_filters['date_range'][1]
                            if isinstance(start_date, date) and isinstance(end_date, date):
                                num_days = (end_date - start_date).days + 1  # +1 to include both start and end dates
                                if num_days < 1:
                                    num_days = 1
                        except Exception:
                            num_days = 1
                    
                    for metric in metrics:
                        row_vals = [metric]
                        for col in numeric_cols:
                            series = pd.to_numeric(df[col], errors="coerce")
                            val = ""
                            if metric == "Total":
                                val = series.sum(skipna=True)
                            elif metric == "Average":
                                total = series.sum(skipna=True)
                                val = total / num_days
                            dp = decimals_lookup.get(col, 2)
                            row_vals.append(_fmt_num(val, dp))
                        summary_rows.append(row_vals)

                    summary_table = Table([summary_headers] + summary_rows, repeatRows=1)
                    summary_style = [
                        ("BACKGROUND", (0, 0), (-1, 0), table_header_bg),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 9),
                        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                        ("GRID", (0, 0), (-1, -1), 0.5, table_grid),
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 9),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ]
                    for idx in range(1, len(summary_rows) + 1):
                        if idx % 2 == 0:
                            summary_style.append(("BACKGROUND", (0, idx), (-1, idx), table_row_alt))
                    summary_table.setStyle(TableStyle(summary_style))
                    elements.append(summary_table)
        
        # Build PDF
        # Footer with page numbers and report name
        def _footer(canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            footer_text = f"{report_name} - Page {canvas.getPageNumber()}"
            canvas.drawString(40, 20, footer_text)
            canvas.restoreState()

        doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()
    
    def get_pdf_base64(self, df: pd.DataFrame, report_name: str = "Report", user_filters: Dict[str, Any] = None) -> str:
        """
        Generate PDF and return as base64 string for iframe display.
        
        Args:
            df: pandas DataFrame
            report_name: Name of the report
            user_filters: Runtime filters (for calculating date-based averages)
        
        Returns:
            Base64 encoded PDF string
        """
        pdf_bytes = self.export_pdf(df, report_name, user_filters)
        return base64.b64encode(pdf_bytes).decode('utf-8')


def get_available_data_sources() -> List[str]:
    """Get list of available data sources for report building - includes ALL database tables."""
    from logger import log_info, log_error
    
    sources = []
    all_tables = []
    try:
        from sqlalchemy import inspect
        from db import engine, flex_engine
        if engine:
            inspector = inspect(engine)
            base_tables = inspector.get_table_names()
            sources.extend(base_tables)
            all_tables.extend(base_tables)
            log_info(f"Loaded {len(base_tables)} tables from primary database")
        if flex_engine:
            finsp = inspect(flex_engine)
            flex_tables = finsp.get_table_names()
            for t in flex_tables:
                if t not in sources:
                    sources.append(t)
            all_tables.extend([t for t in flex_tables if t not in all_tables])
            log_info(f"Loaded {len(flex_tables)} tables from flexible database")
        if not engine and not flex_engine:
            sources = list(ReportEngine.DATA_SOURCES.keys())
    except Exception as e:
        log_error(f"Could not load tables from databases: {str(e)}", exc_info=True)
        sources = list(ReportEngine.DATA_SOURCES.keys())
    
    # Add custom tab tables from location_config (in case they're not in DB yet)
    try:
        from location_config import get_all_custom_table_names
        from db import get_session
        
        with get_session() as session:
            custom_tables = get_all_custom_table_names(session)
            for ct in custom_tables:
                if ct not in sources:
                    sources.append(ct)
            log_info(f"Added {len([ct for ct in custom_tables if ct not in all_tables])} additional custom tables from location_config")
    except Exception as e:
        log_error(f"Could not load custom tables from location_config: {str(e)}")
    
    return sorted(sources)


def get_columns_for_source(source_name: str) -> List[Dict[str, str]]:
    """
    Get available columns for a data source.
    
    Args:
        source_name: Name of the data source
    
    Returns:
        List of column definitions with field name and type
    """
    from logger import log_info, log_error, log_warning
    
    model = None
    
    # Check if it's a standard data source
    if source_name in ReportEngine.DATA_SOURCES:
        model = ReportEngine.DATA_SOURCES[source_name]
        log_info(f"Loading columns for standard data source '{source_name}'")
    else:
        # Try to get custom table model
        try:
            from models import get_custom_table_model
            log_info(f"Attempting to load custom table '{source_name}'")
            model = get_custom_table_model(source_name)
            if model:
                log_info(f"Successfully loaded custom table model for '{source_name}'")
            else:
                log_warning(f"Custom table '{source_name}' not found")
        except Exception as e:
            log_error(f"Error loading custom table '{source_name}': {str(e)}", exc_info=True)
    
    if not model:
        try:
            from sqlalchemy import inspect
            from db import engine, flex_engine
            columns = []
            for eng in [engine, flex_engine]:
                if not eng:
                    continue
                insp = inspect(eng)
                try:
                    cols = insp.get_columns(source_name)
                except Exception:
                    cols = []
                if cols:
                    for c in cols:
                        t = str(c.get('type'))
                        if 'INT' in t:
                            field_type = 'numeric'
                        elif 'FLOAT' in t or 'DECIMAL' in t or 'NUMERIC' in t:
                            field_type = 'numeric'
                        elif 'DATE' in t and 'TIME' not in t:
                            field_type = 'date'
                        elif 'DATETIME' in t or 'TIMESTAMP' in t or 'TIME' in t:
                            field_type = 'datetime'
                        elif 'BOOL' in t:
                            field_type = 'boolean'
                        else:
                            field_type = 'string'
                        columns.append({
                            'field': c['name'],
                            'label': c['name'].replace('_', ' ').title(),
                            'type': field_type
                        })
                    return columns
            log_warning(f"No model found and inspector could not load columns for '{source_name}'")
            return []
        except Exception as e:
            log_error(f"Inspector fallback failed for '{source_name}': {str(e)}")
            return []
    
    columns = []
    
    try:
        for column in model.__table__.columns:
            col_type = str(column.type)
            if 'INT' in col_type:
                field_type = 'numeric'
            elif 'FLOAT' in col_type or 'DECIMAL' in col_type:
                field_type = 'numeric'
            elif 'DATE' in col_type and 'TIME' not in col_type:
                field_type = 'date'
            elif 'DATETIME' in col_type or 'TIMESTAMP' in col_type:
                field_type = 'datetime'
            elif 'BOOL' in col_type:
                field_type = 'boolean'
            else:
                field_type = 'string'
            columns.append({
                'field': column.name,
                'label': column.name.replace('_', ' ').title(),
                'type': field_type
            })
        log_info(f"Retrieved {len(columns)} columns for data source '{source_name}'")
    except Exception as e:
        log_error(f"Error extracting columns from model for '{source_name}': {str(e)}", exc_info=True)
    
    return columns
