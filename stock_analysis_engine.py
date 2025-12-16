"""
Stock Analysis Engine - Advanced Analytics and Custom Table Management
=======================================================================
A comprehensive engine for creating custom analytical tables, defining 
multi-table relationships, computed columns, and generating visualizations.

Features:
- Create custom analysis tables with flexible schema
- Define multi-table relationships with JOIN operations
- Computed columns using SQL expressions or Python formulas
- Data aggregation (SUM, AVG, COUNT, MIN, MAX, etc.)
- Multiple visualization types (line, bar, pie, scatter, area, etc.)
- Save analysis results to database
"""

import uuid
import json
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple, Union
from io import BytesIO

import pandas as pd
import numpy as np
from sqlalchemy import (
    Table, Column, MetaData, Integer, Float, String, Text, Date, DateTime,
    Boolean, inspect, func, and_, or_, case, cast, ForeignKey, create_engine
)
from sqlalchemy.exc import OperationalError, ProgrammingError, DatabaseError
from sqlalchemy.orm import Session

from db import get_session, flex_engine, engine
from logger import log_info, log_error, log_warning


# ==============================================================================
# CONSTANTS AND TYPE DEFINITIONS
# ==============================================================================

COLUMN_TYPES = {
    'text': {'sql': String(255), 'pd': 'object', 'label': 'Text'},
    'number': {'sql': Float, 'pd': 'float64', 'label': 'Number'},
    'integer': {'sql': Integer, 'pd': 'int64', 'label': 'Integer'},
    'date': {'sql': Date, 'pd': 'datetime64[ns]', 'label': 'Date'},
    'datetime': {'sql': DateTime, 'pd': 'datetime64[ns]', 'label': 'Date/Time'},
    'boolean': {'sql': Boolean, 'pd': 'bool', 'label': 'Yes/No'},
    'longtext': {'sql': Text, 'pd': 'object', 'label': 'Long Text'},
}

AGGREGATION_FUNCTIONS = {
    'sum': {'sql': func.sum, 'pd': 'sum', 'label': 'Sum'},
    'avg': {'sql': func.avg, 'pd': 'mean', 'label': 'Average'},
    'count': {'sql': func.count, 'pd': 'count', 'label': 'Count'},
    'min': {'sql': func.min, 'pd': 'min', 'label': 'Minimum'},
    'max': {'sql': func.max, 'pd': 'max', 'label': 'Maximum'},
    'first': {'sql': None, 'pd': 'first', 'label': 'First'},
    'last': {'sql': None, 'pd': 'last', 'label': 'Last'},
    'std': {'sql': None, 'pd': 'std', 'label': 'Std Dev'},
    'var': {'sql': None, 'pd': 'var', 'label': 'Variance'},
    'median': {'sql': None, 'pd': 'median', 'label': 'Median'},
}

JOIN_TYPES = {
    'inner': 'INNER JOIN',
    'left': 'LEFT OUTER JOIN',
    'right': 'RIGHT OUTER JOIN',
    'outer': 'FULL OUTER JOIN',
    'cross': 'CROSS JOIN',
}

CHART_TYPES = {
    'table': {'label': 'Data Table', 'icon': '📋', 'category': 'table'},
    'line': {'label': 'Line Chart', 'icon': '📈', 'category': 'trend'},
    'bar': {'label': 'Bar Chart', 'icon': '📊', 'category': 'comparison'},
    'bar_horizontal': {'label': 'Horizontal Bar', 'icon': '📊', 'category': 'comparison'},
    'area': {'label': 'Area Chart', 'icon': '📉', 'category': 'trend'},
    'pie': {'label': 'Pie Chart', 'icon': '🥧', 'category': 'composition'},
    'donut': {'label': 'Donut Chart', 'icon': '🍩', 'category': 'composition'},
    'scatter': {'label': 'Scatter Plot', 'icon': '⚪', 'category': 'correlation'},
    'histogram': {'label': 'Histogram', 'icon': '📊', 'category': 'distribution'},
    'heatmap': {'label': 'Heatmap', 'icon': '🔥', 'category': 'correlation'},
    'metric': {'label': 'Metric Card', 'icon': '🔢', 'category': 'kpi'},
    'gauge': {'label': 'Gauge', 'icon': '⏱️', 'category': 'kpi'},
}


# ==============================================================================
# SCHEMA MANAGER - Create and manage custom analysis tables
# ==============================================================================

class AnalysisSchemaManager:
    """
    Manages the creation and modification of custom analysis tables in the database.
    """
    
    RESERVED_COLUMNS = ['id', 'location_id', 'created_by', 'created_at', 'updated_by', 'updated_at']
    
    @staticmethod
    def validate_table_name(table_name: str) -> Tuple[bool, str]:
        """
        Validate a table name for use in the database.
        
        Returns:
            (is_valid, error_message)
        """
        if not table_name:
            return False, "Table name is required"
        
        # Clean and normalize
        clean_name = table_name.strip().lower()
        
        # Check for valid characters
        if not re.match(r'^[a-z][a-z0-9_]*$', clean_name):
            return False, "Table name must start with a letter and contain only letters, numbers, and underscores"
        
        # Check length
        if len(clean_name) < 3:
            return False, "Table name must be at least 3 characters"
        if len(clean_name) > 63:
            return False, "Table name must be less than 64 characters"
        
        # Check for reserved words
        reserved = ['select', 'insert', 'update', 'delete', 'drop', 'create', 'alter', 'table', 'index']
        if clean_name in reserved:
            return False, f"'{clean_name}' is a reserved word"
        
        return True, ""
    
    @staticmethod
    def validate_column_definition(col_def: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate a column definition.
        
        Returns:
            (is_valid, error_message)
        """
        name = col_def.get('name', '').strip()
        if not name:
            return False, "Column name is required"
        
        if not re.match(r'^[a-z][a-z0-9_]*$', name.lower()):
            return False, f"Invalid column name '{name}'"
        
        if name.lower() in AnalysisSchemaManager.RESERVED_COLUMNS:
            return False, f"'{name}' is a reserved column name"
        
        col_type = col_def.get('type', 'text')
        if col_type not in COLUMN_TYPES:
            return False, f"Invalid column type '{col_type}'"
        
        return True, ""
    
    @staticmethod
    def create_analysis_table(
        table_name: str,
        columns: List[Dict[str, Any]],
        location_id: int,
        include_audit_columns: bool = True
    ) -> Tuple[bool, str]:
        """
        Create a new analysis table in the database.
        
        Args:
            table_name: Name for the new table
            columns: List of column definitions
            location_id: Location ID for the table
            include_audit_columns: Whether to include created_at, updated_at, etc.
        
        Returns:
            (success, message)
        """
        # Validate table name
        is_valid, error = AnalysisSchemaManager.validate_table_name(table_name)
        if not is_valid:
            return False, error
        
        clean_name = table_name.strip().lower().replace(' ', '_')
        
        # Validate columns
        for col in columns:
            is_valid, error = AnalysisSchemaManager.validate_column_definition(col)
            if not is_valid:
                return False, error
        
        if not flex_engine:
            return False, "Database engine not available"
        
        try:
            # Check if table exists
            inspector = inspect(flex_engine)
            if clean_name in inspector.get_table_names():
                return False, f"Table '{clean_name}' already exists"
            
            # Build column definitions
            from models import Base
            metadata = Base.metadata
            
            table_columns = [
                Column('id', Integer, primary_key=True, autoincrement=True),
                Column('location_id', Integer, nullable=False),
            ]
            
            if include_audit_columns:
                table_columns.extend([
                    Column('created_by', String(64), nullable=True),
                    Column('created_at', DateTime, server_default=func.now()),
                    Column('updated_by', String(64), nullable=True),
                    Column('updated_at', DateTime, onupdate=func.now()),
                ])
            
            # Add custom columns
            for col_def in columns:
                col_name = col_def.get('name', '').strip().lower().replace(' ', '_')
                col_type = col_def.get('type', 'text')
                nullable = col_def.get('nullable', True)
                default = col_def.get('default', None)
                
                if col_name in [c.name for c in table_columns]:
                    continue  # Skip duplicates
                
                sql_type = COLUMN_TYPES.get(col_type, COLUMN_TYPES['text'])['sql']
                col = Column(col_name, sql_type, nullable=nullable, default=default)
                table_columns.append(col)
            
            # Create table
            new_table = Table(clean_name, metadata, *table_columns)
            metadata.create_all(flex_engine)
            
            log_info(f"✅ Created analysis table '{clean_name}' with {len(table_columns)} columns")
            return True, f"Table '{clean_name}' created successfully"
            
        except Exception as e:
            log_error(f"Failed to create analysis table '{clean_name}': {str(e)}", exc_info=True)
            return False, f"Failed to create table: {str(e)}"
    
    @staticmethod
    def drop_analysis_table(table_name: str) -> Tuple[bool, str]:
        """
        Drop an analysis table from the database.
        
        Returns:
            (success, message)
        """
        if not flex_engine:
            return False, "Database engine not available"
        
        try:
            inspector = inspect(flex_engine)
            if table_name not in inspector.get_table_names():
                return True, "Table does not exist"  # Already gone
            
            metadata = MetaData()
            table = Table(table_name, metadata, autoload_with=flex_engine)
            table.drop(flex_engine)
            
            log_info(f"✅ Dropped analysis table '{table_name}'")
            return True, f"Table '{table_name}' dropped successfully"
            
        except Exception as e:
            log_error(f"Failed to drop table '{table_name}': {str(e)}", exc_info=True)
            return False, f"Failed to drop table: {str(e)}"
    
    @staticmethod
    def get_table_columns(table_name: str) -> List[Dict[str, Any]]:
        """
        Get column information for a table.
        
        Returns:
            List of column definitions
        """
        columns = []
        
        for eng in [flex_engine, engine]:
            if not eng:
                continue
            try:
                inspector = inspect(eng)
                if table_name not in inspector.get_table_names():
                    continue
                
                for col in inspector.get_columns(table_name):
                    col_type = 'text'
                    sql_type = str(col['type']).upper()
                    
                    if 'INT' in sql_type:
                        col_type = 'integer'
                    elif 'FLOAT' in sql_type or 'REAL' in sql_type or 'NUMERIC' in sql_type:
                        col_type = 'number'
                    elif 'DATE' in sql_type and 'TIME' not in sql_type:
                        col_type = 'date'
                    elif 'DATETIME' in sql_type or 'TIMESTAMP' in sql_type:
                        col_type = 'datetime'
                    elif 'BOOL' in sql_type:
                        col_type = 'boolean'
                    elif 'TEXT' in sql_type:
                        col_type = 'longtext'
                    
                    columns.append({
                        'name': col['name'],
                        'type': col_type,
                        'nullable': col.get('nullable', True),
                        'primary_key': col.get('primary_key', False),
                        'sql_type': sql_type,
                    })
                
                return columns
                
            except Exception as e:
                log_warning(f"Error getting columns for '{table_name}': {str(e)}")
                continue
        
        return columns
    
    @staticmethod
    def add_column_to_table(table_name: str, column_def: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Add a new column to an existing analysis table.
        
        Returns:
            (success, message)
        """
        is_valid, error = AnalysisSchemaManager.validate_column_definition(column_def)
        if not is_valid:
            return False, error
        
        if not flex_engine:
            return False, "Database engine not available"
        
        col_name = column_def.get('name', '').strip().lower()
        col_type = column_def.get('type', 'text')
        
        try:
            inspector = inspect(flex_engine)
            if table_name not in inspector.get_table_names():
                return False, f"Table '{table_name}' does not exist"
            
            # Check if column already exists
            existing_cols = [c['name'] for c in inspector.get_columns(table_name)]
            if col_name in existing_cols:
                return False, f"Column '{col_name}' already exists"
            
            # Get SQL type
            sql_type_mapping = {
                'text': 'VARCHAR(255)',
                'number': 'FLOAT',
                'integer': 'INTEGER',
                'date': 'DATE',
                'datetime': 'DATETIME',
                'boolean': 'BOOLEAN',
                'longtext': 'TEXT',
            }
            sql_type = sql_type_mapping.get(col_type, 'VARCHAR(255)')
            
            # Execute ALTER TABLE
            with flex_engine.connect() as conn:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sql_type}")
                conn.commit()
            
            log_info(f"✅ Added column '{col_name}' to table '{table_name}'")
            return True, f"Column '{col_name}' added successfully"
            
        except Exception as e:
            log_error(f"Failed to add column '{col_name}' to '{table_name}': {str(e)}", exc_info=True)
            return False, f"Failed to add column: {str(e)}"


# ==============================================================================
# QUERY BUILDER - Build complex analytical queries
# ==============================================================================

class AnalyticsQueryBuilder:
    """
    Builds SQL queries from analysis configurations.
    Supports multi-table joins, computed columns, aggregations, and filters.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize query builder with configuration.
        
        Config structure:
        {
            "source_tables": [
                {"name": "table1", "alias": "t1"},
                {"name": "table2", "alias": "t2"}
            ],
            "joins": [
                {
                    "left_table": "t1",
                    "left_field": "id",
                    "right_table": "t2",
                    "right_field": "table1_id",
                    "type": "inner"
                }
            ],
            "columns": [
                {"source": "t1.field1", "alias": "Field 1"},
                {"source": "t2.field2", "alias": "Field 2"},
                {"formula": "t1.quantity * t2.price", "alias": "Total", "type": "computed"}
            ],
            "filters": [...],
            "group_by": [...],
            "aggregations": {...},
            "order_by": [...]
        }
        """
        self.config = config
        self.source_tables = config.get('source_tables', [])
        self.joins = config.get('joins', [])
        self.columns = config.get('columns', [])
        self.filters = config.get('filters', [])
        self.group_by = config.get('group_by', [])
        self.aggregations = config.get('aggregations', {})
        self.order_by = config.get('order_by', [])
        self.limit = config.get('limit')
        self.runtime_filters = config.get('runtime_filters') or {}
    
    def execute(self, user_filters: Dict[str, Any] = None) -> pd.DataFrame:
        """
        Execute the query and return results as a DataFrame.
        
        Args:
            user_filters: Runtime filters from user input
        
        Returns:
            pandas DataFrame with query results
        """
        try:
            sql = self.build_sql(user_filters)
            log_info(f"Executing analytics query: {sql[:200]}...")
            
            # Try flex engine first, then primary
            for eng in [flex_engine, engine]:
                if not eng:
                    continue
                try:
                    df = pd.read_sql(sql, eng)
                    log_info(f"Query returned {len(df)} rows")
                    return df
                except Exception:
                    continue
            
            return pd.DataFrame()
            
        except Exception as e:
            log_error(f"Error executing analytics query: {str(e)}", exc_info=True)
            raise
    
    def build_sql(self, user_filters: Dict[str, Any] = None) -> str:
        """
        Build the SQL query string.
        
        Returns:
            SQL query string
        """
        parts = []
        
        # SELECT clause
        select_cols = self._build_select_columns()
        parts.append(f"SELECT {select_cols}")
        
        # FROM clause
        from_clause = self._build_from_clause()
        parts.append(f"FROM {from_clause}")
        
        # JOIN clauses
        join_clauses = self._build_join_clauses()
        if join_clauses:
            parts.append(join_clauses)
        
        # WHERE clause
        where_clause = self._build_where_clause(user_filters)
        if where_clause:
            parts.append(f"WHERE {where_clause}")
        
        # GROUP BY clause
        if self.group_by:
            group_cols = ', '.join(self.group_by)
            parts.append(f"GROUP BY {group_cols}")
        
        # ORDER BY clause
        if self.order_by:
            order_cols = ', '.join([
                f"{o.get('field')} {o.get('direction', 'ASC')}"
                for o in self.order_by
            ])
            parts.append(f"ORDER BY {order_cols}")
        
        # LIMIT clause
        if self.limit and isinstance(self.limit, int):
            parts.append(f"LIMIT {self.limit}")
        
        return '\n'.join(parts)
    
    def _build_select_columns(self) -> str:
        """Build SELECT column list."""
        cols = []
        
        for col in self.columns:
            if col.get('type') == 'computed' and col.get('formula'):
                expr = f"({col['formula']}) AS [{col.get('alias', 'computed')}]"
            elif col.get('aggregation'):
                agg = col['aggregation'].upper()
                source = col.get('source', '*')
                alias = col.get('alias', f'{agg}_{source}')
                expr = f"{agg}({source}) AS [{alias}]"
            else:
                source = col.get('source')
                alias = col.get('alias')
                if alias and alias != source:
                    expr = f"{source} AS [{alias}]"
                else:
                    expr = source
            cols.append(expr)
        
        return ', '.join(cols) if cols else '*'
    
    def _build_from_clause(self) -> str:
        """Build FROM clause with table aliases."""
        if not self.source_tables:
            return ""
        
        primary = self.source_tables[0]
        table_name = primary.get('name')
        alias = primary.get('alias', table_name)
        
        if alias and alias != table_name:
            return f"{table_name} AS {alias}"
        return table_name
    
    def _build_join_clauses(self) -> str:
        """Build JOIN clauses."""
        joins = []
        
        for join in self.joins:
            join_type = JOIN_TYPES.get(join.get('type', 'inner'), 'INNER JOIN')
            right_table = join.get('right_table')
            right_alias = join.get('right_alias', right_table)
            left_field = join.get('left_field')
            right_field = join.get('right_field')
            left_table = join.get('left_table')
            
            if right_alias and right_alias != right_table:
                table_ref = f"{right_table} AS {right_alias}"
            else:
                table_ref = right_table
                right_alias = right_table

            # Support composite join keys via join['conditions']
            on_parts: List[str] = []
            for cond in (join.get('conditions') or []):
                cond_left_table = cond.get('left_table') or left_table
                cond_right_table = cond.get('right_table') or right_alias
                cond_left_field = cond.get('left_field') or cond.get('left')
                cond_right_field = cond.get('right_field') or cond.get('right')
                if not cond_left_table or not cond_right_table or not cond_left_field or not cond_right_field:
                    continue
                on_parts.append(f"{cond_left_table}.{cond_left_field} = {cond_right_table}.{cond_right_field}")

            # Backward compatible single-key join
            if not on_parts and left_table and left_field and right_alias and right_field:
                on_parts.append(f"{left_table}.{left_field} = {right_alias}.{right_field}")

            if not on_parts:
                continue

            on_clause = " AND ".join(on_parts)
            joins.append(f"{join_type} {table_ref} ON {on_clause}")
        
        return '\n'.join(joins)

    @staticmethod
    def _sql_literal(value: Any) -> str:
        """Convert a Python value into a safe SQL literal."""
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (datetime, date)):
            return f"'{value.isoformat()}'"
        text = str(value)
        text = text.replace("'", "''")
        return f"'{text}'"

    def _primary_table_name(self) -> Optional[str]:
        if not self.source_tables:
            return None
        return self.source_tables[0].get("name")

    def _primary_alias(self) -> Optional[str]:
        if not self.source_tables:
            return None
        primary = self.source_tables[0]
        return primary.get("alias") or primary.get("name")

    def _default_location_field(self) -> str:
        alias = self._primary_alias()
        return f"{alias}.location_id" if alias else "location_id"

    def _default_date_field(self) -> Optional[str]:
        table_name = self._primary_table_name()
        alias = self._primary_alias()
        if table_name:
            try:
                cols = AnalysisSchemaManager.get_table_columns(table_name)
                col_names = {str(c.get("name", "")).lower() for c in (cols or [])}
                for candidate in ["tx_date", "date", "record_date", "created_at", "updated_at"]:
                    if candidate in col_names:
                        return f"{alias}.{candidate}" if alias else candidate
            except Exception:
                pass
        return f"{alias}.tx_date" if alias else "tx_date"

    def _build_where_clause(self, user_filters: Dict[str, Any] = None) -> str:
        """Build WHERE clause combining configured and runtime filters."""
        conditions = []
        
        # Add configured filters
        for f in self.filters:
            cond = self._build_filter_condition(f)
            if cond:
                conditions.append(cond)
        
        # Add runtime filters (location/date) with configurable field mapping
        if user_filters:
            runtime_cfg = self.runtime_filters if isinstance(self.runtime_filters, dict) else {}

            loc_field = (runtime_cfg.get("location_field") or "").strip() or self._default_location_field()
            date_field = runtime_cfg.get("date_field")
            if isinstance(date_field, str):
                date_field = date_field.strip() or None
            if date_field is None:
                date_field = self._default_date_field()

            loc_value = user_filters.get("location_id")
            if loc_value not in (None, "") and loc_field:
                try:
                    conditions.append(f"{loc_field} = {int(loc_value)}")
                except Exception:
                    pass

            date_from = user_filters.get("date_from")
            if date_from not in (None, "") and date_field:
                conditions.append(f"{date_field} >= {self._sql_literal(date_from)}")

            date_to = user_filters.get("date_to")
            if date_to not in (None, "") and date_field:
                conditions.append(f"{date_field} <= {self._sql_literal(date_to)}")
        
        return ' AND '.join(conditions) if conditions else ''
    
    def _build_filter_condition(self, filter_def: Dict[str, Any]) -> str:
        """Build a single filter condition."""
        field = filter_def.get('field')
        operator = filter_def.get('operator', 'equals')
        value = filter_def.get('value')
        
        if not field:
            return ''
        
        op_map = {
            'equals': '=',
            'not_equals': '!=',
            'greater_than': '>',
            'less_than': '<',
            'greater_equal': '>=',
            'less_equal': '<=',
            'contains': 'LIKE',
            'starts_with': 'LIKE',
            'ends_with': 'LIKE',
            'is_null': 'IS NULL',
            'is_not_null': 'IS NOT NULL',
            'in': 'IN',
        }
        
        sql_op = op_map.get(operator, '=')
        
        if operator == 'is_null':
            return f"{field} IS NULL"
        elif operator == 'is_not_null':
            return f"{field} IS NOT NULL"
        elif operator == 'contains':
            return f"{field} LIKE '%{value}%'"
        elif operator == 'starts_with':
            return f"{field} LIKE '{value}%'"
        elif operator == 'ends_with':
            return f"{field} LIKE '%{value}'"
        elif operator == 'in' and isinstance(value, list):
            values = ', '.join([f"'{v}'" if isinstance(v, str) else str(v) for v in value])
            return f"{field} IN ({values})"
        elif isinstance(value, str):
            return f"{field} {sql_op} '{value}'"
        elif isinstance(value, (int, float)):
            return f"{field} {sql_op} {value}"
        elif isinstance(value, (date, datetime)):
            return f"{field} {sql_op} '{value}'"
        
        return ''


# ==============================================================================
# DATA ANALYZER - Perform analysis operations on data
# ==============================================================================

class DataAnalyzer:
    """
    Performs various analytical operations on DataFrames.
    """
    
    @staticmethod
    def compute_column(
        df: pd.DataFrame,
        formula: str,
        column_name: str,
        result_type: str = 'number'
    ) -> pd.DataFrame:
        """
        Add a computed column to a DataFrame using a formula.
        
        Args:
            df: Source DataFrame
            formula: Python expression or formula string
            column_name: Name for the new column
            result_type: Expected result type
        
        Returns:
            DataFrame with new computed column
        """
        try:
            result = df.copy()
            
            # Replace column references with df['column']
            expr = formula
            for col in df.columns:
                pattern = rf'\b{col}\b'
                expr = re.sub(pattern, f"df['{col}']", expr)
            
            # Evaluate expression
            result[column_name] = eval(expr)
            
            return result
            
        except Exception as e:
            log_error(f"Error computing column '{column_name}': {str(e)}")
            raise
    
    @staticmethod
    def aggregate(
        df: pd.DataFrame,
        group_by: List[str],
        aggregations: Dict[str, str]
    ) -> pd.DataFrame:
        """
        Perform aggregation on a DataFrame.
        
        Args:
            df: Source DataFrame
            group_by: List of columns to group by
            aggregations: Dict of {column: aggregation_function}
        
        Returns:
            Aggregated DataFrame
        """
        if not group_by or not aggregations:
            return df
        
        try:
            agg_dict = {}
            for col, agg_func in aggregations.items():
                if col in df.columns:
                    pd_func = AGGREGATION_FUNCTIONS.get(agg_func, {}).get('pd', 'sum')
                    agg_dict[col] = pd_func
            
            if not agg_dict:
                return df
            
            result = df.groupby(group_by, as_index=False).agg(agg_dict)
            return result
            
        except Exception as e:
            log_error(f"Error aggregating data: {str(e)}")
            raise
    
    @staticmethod
    def calculate_statistics(df: pd.DataFrame, column: str) -> Dict[str, Any]:
        """
        Calculate comprehensive statistics for a numeric column.
        
        Returns:
            Dict with statistics
        """
        stats = {
            'count': 0,
            'sum': None,
            'mean': None,
            'median': None,
            'std': None,
            'min': None,
            'max': None,
            'q1': None,
            'q3': None,
            'variance': None,
        }
        
        if column not in df.columns:
            return stats
        
        try:
            series = pd.to_numeric(df[column], errors='coerce').dropna()
            
            if len(series) == 0:
                return stats
            
            stats['count'] = len(series)
            stats['sum'] = float(series.sum())
            stats['mean'] = float(series.mean())
            stats['median'] = float(series.median())
            stats['std'] = float(series.std()) if len(series) > 1 else 0
            stats['min'] = float(series.min())
            stats['max'] = float(series.max())
            stats['q1'] = float(series.quantile(0.25))
            stats['q3'] = float(series.quantile(0.75))
            stats['variance'] = float(series.var()) if len(series) > 1 else 0
            
            return stats
            
        except Exception as e:
            log_warning(f"Error calculating statistics for '{column}': {str(e)}")
            return stats
    
    @staticmethod
    def calculate_gain_loss(df: pd.DataFrame, value_column: str, date_column: str = None) -> Dict[str, Any]:
        """
        Calculate gain/loss between first and last values.
        
        Returns:
            Dict with gain/loss information
        """
        result = {
            'first_value': None,
            'last_value': None,
            'absolute_change': None,
            'percent_change': None,
            'direction': 'unchanged',
        }
        
        if value_column not in df.columns or len(df) == 0:
            return result
        
        try:
            data = df.copy()
            
            # Sort by date if available
            if date_column and date_column in data.columns:
                data = data.sort_values(date_column)
            
            series = pd.to_numeric(data[value_column], errors='coerce').dropna()
            
            if len(series) < 2:
                return result
            
            first = float(series.iloc[0])
            last = float(series.iloc[-1])
            change = last - first
            
            result['first_value'] = first
            result['last_value'] = last
            result['absolute_change'] = change
            
            if first != 0:
                result['percent_change'] = (change / abs(first)) * 100
            
            if change > 0:
                result['direction'] = 'gain'
            elif change < 0:
                result['direction'] = 'loss'
            
            return result
            
        except Exception as e:
            log_warning(f"Error calculating gain/loss: {str(e)}")
            return result
    
    @staticmethod
    def pivot_data(
        df: pd.DataFrame,
        index: List[str],
        columns: str,
        values: str,
        aggfunc: str = 'sum'
    ) -> pd.DataFrame:
        """
        Create a pivot table from the DataFrame.
        
        Returns:
            Pivoted DataFrame
        """
        try:
            pd_func = AGGREGATION_FUNCTIONS.get(aggfunc, {}).get('pd', 'sum')
            
            pivot = pd.pivot_table(
                df,
                index=index,
                columns=columns,
                values=values,
                aggfunc=pd_func,
                fill_value=0
            ).reset_index()
            
            return pivot
            
        except Exception as e:
            log_error(f"Error creating pivot table: {str(e)}")
            raise


# ==============================================================================
# ANALYSIS RESULT WRITER - Save analysis results to database
# ==============================================================================

class AnalysisResultWriter:
    """
    Writes analysis results back to the database.
    """
    
    @staticmethod
    def save_to_table(
        df: pd.DataFrame,
        table_name: str,
        location_id: int,
        username: str,
        if_exists: str = 'append'
    ) -> Tuple[bool, str, int]:
        """
        Save a DataFrame to a database table.
        
        Args:
            df: DataFrame to save
            table_name: Target table name
            location_id: Location ID
            username: User performing the save
            if_exists: 'append', 'replace', or 'fail'
        
        Returns:
            (success, message, rows_affected)
        """
        if df.empty:
            return False, "No data to save", 0
        
        if not flex_engine:
            return False, "Database engine not available", 0
        
        try:
            # Add metadata columns
            save_df = df.copy()
            save_df['location_id'] = location_id
            save_df['created_by'] = username
            save_df['created_at'] = datetime.utcnow()
            
            # Check if table exists
            inspector = inspect(flex_engine)
            existing_tables = set(inspector.get_table_names())

            to_sql_mode = if_exists

            # Ensure "replace" keeps our standard schema (id/location/audit cols)
            if table_name in existing_tables and if_exists == "replace":
                success, msg = AnalysisSchemaManager.drop_analysis_table(table_name)
                if not success:
                    return False, msg, 0
                existing_tables.discard(table_name)
                to_sql_mode = "append"

            if table_name not in existing_tables:
                if if_exists == 'fail':
                    return False, f"Table '{table_name}' does not exist", 0
                # Create table with schema from DataFrame
                columns = []
                reserved_cols = {c.lower() for c in AnalysisSchemaManager.RESERVED_COLUMNS}
                for col in save_df.columns:
                    col_name = str(col)
                    if col_name.lower() in reserved_cols:
                        continue
                    dtype = str(save_df[col].dtype)
                    if 'int' in dtype:
                        col_type = 'integer'
                    elif 'float' in dtype:
                        col_type = 'number'
                    elif 'datetime' in dtype:
                        col_type = 'datetime'
                    else:
                        col_type = 'text'
                    columns.append({'name': col_name, 'type': col_type})

                success, msg = AnalysisSchemaManager.create_analysis_table(
                    table_name, columns, location_id
                )
                if not success:
                    return False, msg, 0
            
            # Write data
            rows = save_df.to_sql(
                table_name,
                flex_engine,
                if_exists=to_sql_mode,
                index=False,
                method='multi'
            )
            
            log_info(f"✅ Saved {len(save_df)} rows to table '{table_name}'")
            return True, f"Saved {len(save_df)} rows to '{table_name}'", len(save_df)
            
        except Exception as e:
            log_error(f"Error saving to table '{table_name}': {str(e)}", exc_info=True)
            return False, f"Error saving data: {str(e)}", 0
    
    @staticmethod
    def clear_table_data(table_name: str, location_id: int = None) -> Tuple[bool, str]:
        """
        Clear data from a table, optionally filtered by location.
        
        Returns:
            (success, message)
        """
        if not flex_engine:
            return False, "Database engine not available"
        
        try:
            inspector = inspect(flex_engine)
            if table_name not in inspector.get_table_names():
                return False, f"Table '{table_name}' does not exist"
            
            with flex_engine.connect() as conn:
                if location_id:
                    conn.execute(f"DELETE FROM {table_name} WHERE location_id = {location_id}")
                else:
                    conn.execute(f"DELETE FROM {table_name}")
                conn.commit()
            
            log_info(f"✅ Cleared data from table '{table_name}'")
            return True, f"Data cleared from '{table_name}'"
            
        except Exception as e:
            log_error(f"Error clearing table '{table_name}': {str(e)}", exc_info=True)
            return False, f"Error clearing data: {str(e)}"


# ==============================================================================
# ANALYSIS CONFIGURATION MANAGER - Save/Load analysis definitions
# ==============================================================================

class AnalysisConfigManager:
    """
    Manages saving and loading analysis configurations.
    """
    
    CONFIG_PAGE = 'stock_analysis'
    
    @staticmethod
    def save_analysis_tab(
        session: Session,
        location_id: int,
        tab_config: Dict[str, Any]
    ) -> Tuple[bool, str, str]:
        """
        Save an analysis tab configuration.
        
        Tab config structure:
        {
            "id": "uuid",
            "name": "Tab Name",
            "table_name": "analysis_table_name",
            "description": "Description",
            "columns": [...],
            "source_tables": [...],
            "joins": [...],
            "filters": [...],
            "aggregations": {...},
            "visualizations": [...],
            "active": true
        }
        """
        from location_config import LocationConfig, get_page_section_config, set_page_section_config
        
        try:
            # Load existing tabs
            existing = get_page_section_config(
                session, location_id, 
                page=AnalysisConfigManager.CONFIG_PAGE, 
                section='analysis_tabs'
            ) or {}
            
            tabs = existing.get('tabs', [])
            
            # Ensure tab has ID
            tab_id = tab_config.get('id') or str(uuid.uuid4())
            tab_config['id'] = tab_id
            tab_config['updated_at'] = datetime.utcnow().isoformat()
            
            # Update or add
            updated = False
            for i, t in enumerate(tabs):
                if t.get('id') == tab_id:
                    tabs[i] = tab_config
                    updated = True
                    break
            
            if not updated:
                tab_config['created_at'] = datetime.utcnow().isoformat()
                tabs.append(tab_config)
            
            # Save
            set_page_section_config(
                session, location_id,
                page=AnalysisConfigManager.CONFIG_PAGE,
                section='analysis_tabs',
                cfg={'tabs': tabs}
            )
            
            log_info(f"✅ Saved analysis tab '{tab_config.get('name')}' for location {location_id}")
            return True, f"Tab '{tab_config.get('name')}' saved successfully", tab_id
            
        except Exception as e:
            log_error(f"Error saving analysis tab: {str(e)}", exc_info=True)
            return False, f"Error saving tab: {str(e)}", ""
    
    @staticmethod
    def load_analysis_tabs(session: Session, location_id: int, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        Load all analysis tab configurations for a location.
        
        Returns:
            List of tab configurations
        """
        from location_config import get_page_section_config, set_page_section_config
        
        try:
            config = get_page_section_config(
                session, location_id,
                page=AnalysisConfigManager.CONFIG_PAGE,
                section='analysis_tabs'
            ) or {}
            
            tabs = config.get('tabs', [])
            
            # Filter and validate
            valid_tabs = []
            cleaned_tabs = []
            dirty = False
            seen_ids = set()
            for t in tabs:
                if not isinstance(t, dict):
                    dirty = True
                    continue

                tab_id = t.get('id')
                if not tab_id or tab_id in seen_ids:
                    t['id'] = str(uuid.uuid4())
                    dirty = True
                seen_ids.add(t.get('id'))

                if not t.get('name'):
                    t['name'] = 'Unnamed Tab'
                    dirty = True

                cleaned_tabs.append(t)
                if include_inactive or t.get('active', True):
                    valid_tabs.append(t)

            # Persist repairs (missing/duplicate IDs, missing names)
            if dirty:
                set_page_section_config(
                    session,
                    location_id,
                    page=AnalysisConfigManager.CONFIG_PAGE,
                    section='analysis_tabs',
                    cfg={'tabs': cleaned_tabs},
                )
            
            return valid_tabs
            
        except Exception as e:
            log_error(f"Error loading analysis tabs: {str(e)}", exc_info=True)
            return []
    
    @staticmethod
    def delete_analysis_tab(
        session: Session,
        location_id: int,
        tab_id: str,
        drop_table: bool = False
    ) -> Tuple[bool, str]:
        """
        Delete an analysis tab configuration.
        
        Args:
            session: Database session
            location_id: Location ID
            tab_id: Tab ID to delete
            drop_table: Whether to also drop the associated database table
        
        Returns:
            (success, message)
        """
        from location_config import get_page_section_config, set_page_section_config
        
        try:
            config = get_page_section_config(
                session, location_id,
                page=AnalysisConfigManager.CONFIG_PAGE,
                section='analysis_tabs'
            ) or {}
            
            tabs = config.get('tabs', [])
            
            # Find and remove
            removed_tab = None
            new_tabs = []
            for t in tabs:
                if t.get('id') == tab_id:
                    removed_tab = t
                else:
                    new_tabs.append(t)
            
            if not removed_tab:
                return False, "Tab not found"
            
            # Drop table if requested
            if drop_table and removed_tab.get('table_name'):
                table_name = removed_tab['table_name']
                success, msg = AnalysisSchemaManager.drop_analysis_table(table_name)
                if not success:
                    log_warning(f"Could not drop table '{table_name}': {msg}")
            
            # Save updated config
            set_page_section_config(
                session, location_id,
                page=AnalysisConfigManager.CONFIG_PAGE,
                section='analysis_tabs',
                cfg={'tabs': new_tabs}
            )
            
            log_info(f"✅ Deleted analysis tab '{removed_tab.get('name')}' for location {location_id}")
            return True, f"Tab '{removed_tab.get('name')}' deleted successfully"
            
        except Exception as e:
            log_error(f"Error deleting analysis tab: {str(e)}", exc_info=True)
            return False, f"Error deleting tab: {str(e)}"


# ==============================================================================
# VISUALIZATION HELPER - Prepare data for charts
# ==============================================================================

class VisualizationHelper:
    """
    Helper methods for preparing visualization data.
    """
    
    @staticmethod
    def prepare_chart_data(
        df: pd.DataFrame,
        chart_type: str,
        x_field: str = None,
        y_field: str = None,
        series_field: str = None
    ) -> Dict[str, Any]:
        """
        Prepare data for visualization based on chart type.
        
        Returns:
            Dict with prepared data and chart configuration
        """
        if df.empty:
            return {'data': None, 'config': {}}
        
        data = df.copy()
        config = {'type': chart_type}
        
        try:
            if chart_type in ['line', 'bar', 'area']:
                if x_field and x_field in data.columns:
                    data = data.sort_values(by=x_field)
                config['x'] = x_field
                config['y'] = y_field
                
            elif chart_type in ['pie', 'donut']:
                if x_field and y_field:
                    # Aggregate for pie chart
                    pie_data = data.groupby(x_field)[y_field].sum().reset_index()
                    data = pie_data
                config['labels'] = x_field
                config['values'] = y_field
                
            elif chart_type == 'scatter':
                config['x'] = x_field
                config['y'] = y_field
                if series_field:
                    config['color'] = series_field
                    
            elif chart_type == 'histogram':
                config['column'] = y_field or x_field
                
            elif chart_type == 'heatmap':
                config['x'] = x_field
                config['y'] = y_field
                config['values'] = series_field
            
            return {'data': data, 'config': config}
            
        except Exception as e:
            log_error(f"Error preparing chart data: {str(e)}")
            return {'data': data, 'config': config}
    
    @staticmethod
    def get_chart_options() -> List[Dict[str, str]]:
        """
        Get list of available chart types.
        
        Returns:
            List of chart type definitions
        """
        return [
            {'value': key, **val}
            for key, val in CHART_TYPES.items()
        ]


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_all_database_tables() -> List[str]:
    """
    Get list of all tables from both primary and flex databases.
    
    Returns:
        Sorted list of table names
    """
    tables = []
    
    for eng in [engine, flex_engine]:
        if not eng:
            continue
        try:
            inspector = inspect(eng)
            for t in inspector.get_table_names():
                if t not in tables:
                    tables.append(t)
        except Exception as e:
            log_warning(f"Error getting tables: {str(e)}")
    
    return sorted(tables)


def get_table_info(table_name: str) -> Dict[str, Any]:
    """
    Get comprehensive information about a table.
    
    Returns:
        Dict with table schema info
    """
    info = {
        'name': table_name,
        'exists': False,
        'columns': [],
        'primary_keys': [],
        'foreign_keys': [],
        'row_count': None,
    }
    
    for eng in [flex_engine, engine]:
        if not eng:
            continue
        try:
            inspector = inspect(eng)
            if table_name not in inspector.get_table_names():
                continue
            
            info['exists'] = True
            info['columns'] = AnalysisSchemaManager.get_table_columns(table_name)
            
            # Get primary keys
            pk = inspector.get_pk_constraint(table_name)
            info['primary_keys'] = pk.get('constrained_columns', []) if pk else []
            
            # Get foreign keys
            fks = inspector.get_foreign_keys(table_name)
            info['foreign_keys'] = [
                {
                    'columns': fk.get('constrained_columns', []),
                    'referred_table': fk.get('referred_table'),
                    'referred_columns': fk.get('referred_columns', []),
                }
                for fk in fks
            ]
            
            # Get row count
            try:
                with eng.connect() as conn:
                    result = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
                    info['row_count'] = result.scalar()
            except Exception:
                pass
            
            return info
            
        except Exception as e:
            log_warning(f"Error getting info for '{table_name}': {str(e)}")
    
    return info


def execute_raw_sql(sql: str, params: Dict[str, Any] = None) -> pd.DataFrame:
    """
    Execute a raw SQL query and return results as DataFrame.
    
    USE WITH CAUTION - only for read operations.
    """
    for eng in [flex_engine, engine]:
        if not eng:
            continue
        try:
            if params:
                return pd.read_sql(sql, eng, params=params)
            return pd.read_sql(sql, eng)
        except Exception:
            continue
    
    return pd.DataFrame()
