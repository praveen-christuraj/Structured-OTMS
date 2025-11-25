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
        if table_name not in self.DATA_SOURCES:
            raise ValueError(f"Unknown data source: {table_name}")
        
        primary_model = self.DATA_SOURCES[table_name]
        
        # Start with base query
        query = session.query(primary_model)
        
        # Apply joins if specified
        joins = self.data_source.get('joins', [])
        for join_config in joins:
            join_table = join_config.get('table')
            if join_table in self.DATA_SOURCES:
                join_model = self.DATA_SOURCES[join_table]
                query = query.join(join_model)
        
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
            with get_session() as session:
                query = self.build_query(session, user_filters)
                
                # Execute query and convert to list of dicts
                results = []
                for row in query.all():
                    row_dict = {}
                    for col_config in self.columns:
                        field = col_config.get('field')
                        if not field:
                            continue  # Skip columns without field definition
                        
                        label = col_config.get('label', field if isinstance(field, str) else 'Unknown')
                        
                        # Get value from row
                        if hasattr(row, field):
                            value = getattr(row, field)
                            
                            # Format based on type
                            col_type = col_config.get('type', 'string')
                            if col_type == 'date' and isinstance(value, (date, datetime)):
                                value = value.strftime('%Y-%m-%d')
                            elif col_type == 'datetime' and isinstance(value, datetime):
                                value = value.strftime('%Y-%m-%d %H:%M:%S')
                            elif col_type == 'numeric' and value is not None:
                                value = float(value)
                            
                            row_dict[label] = value
                        else:
                            row_dict[label] = None
                    
                    results.append(row_dict)
                
                # Convert to DataFrame
                df = pd.DataFrame(results)
                
                # Apply grouping and aggregations if specified
                if self.grouping and self.aggregations:
                    df = self._apply_aggregations(df)
                
                # Apply sorting
                if self.sorting and not df.empty:
                    for sort_config in self.sorting:
                        field = sort_config.get('field')
                        order = sort_config.get('order', 'asc')
                        ascending = (order == 'asc')
                        if field in df.columns:
                            df = df.sort_values(by=field, ascending=ascending)
                
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
    
    def export_pdf(self, df: pd.DataFrame, report_name: str = "Report") -> bytes:
        """
        Export DataFrame to PDF.
        
        Args:
            df: pandas DataFrame
            report_name: Name of the report for title
        
        Returns:
            PDF data as bytes
        """
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.units import inch
        
        pdf_buffer = BytesIO()
        
        # Use landscape for wider tables
        doc = SimpleDocTemplate(pdf_buffer, pagesize=landscape(A4))
        elements = []
        
        # Add title
        styles = getSampleStyleSheet()
        title = Paragraph(f"<b>{report_name}</b>", styles['Heading1'])
        elements.append(title)
        elements.append(Spacer(1, 0.2 * inch))
        
        # Add generation date
        gen_date = Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
                            styles['Normal'])
        elements.append(gen_date)
        elements.append(Spacer(1, 0.3 * inch))
        
        # Prepare table data
        if df.empty:
            no_data = Paragraph("No data available for this report.", styles['Normal'])
            elements.append(no_data)
        else:
            # Limit columns if too many (PDF width limitation)
            max_cols = 10
            if len(df.columns) > max_cols:
                df = df.iloc[:, :max_cols]
            
            # Convert DataFrame to list of lists
            table_data = [df.columns.tolist()] + df.values.tolist()
            
            # Create table
            table = Table(table_data)
            
            # Style the table
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
            
            elements.append(table)
        
        # Build PDF
        doc.build(elements)
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()
    
    def get_pdf_base64(self, df: pd.DataFrame, report_name: str = "Report") -> str:
        """
        Generate PDF and return as base64 string for iframe display.
        
        Args:
            df: pandas DataFrame
            report_name: Name of the report
        
        Returns:
            Base64 encoded PDF string
        """
        pdf_bytes = self.export_pdf(df, report_name)
        return base64.b64encode(pdf_bytes).decode('utf-8')


def get_available_data_sources() -> List[str]:
    """Get list of available data sources for report building."""
    return list(ReportEngine.DATA_SOURCES.keys())


def get_columns_for_source(source_name: str) -> List[Dict[str, str]]:
    """
    Get available columns for a data source.
    
    Args:
        source_name: Name of the data source
    
    Returns:
        List of column definitions with field name and type
    """
    if source_name not in ReportEngine.DATA_SOURCES:
        return []
    
    model = ReportEngine.DATA_SOURCES[source_name]
    columns = []
    
    for column in model.__table__.columns:
        col_type = str(column.type)
        
        # Map SQL types to our types
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
    
    return columns