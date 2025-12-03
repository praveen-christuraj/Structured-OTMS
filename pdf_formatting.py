"""
PDF Formatting Utilities
Standardizes number formatting across all PDFs in the OTMS system.

Standard Rules:
- All quantities: 2 decimal places
- VCF only: 5 decimal places
"""

def format_pdf_number(value, field_name: str = "", decimal_places: int = None) -> str:
    """
    Format a number for PDF display with standardized decimal places.
    
    Args:
        value: The numeric value to format
        field_name: Name of the field (used to detect VCF)
        decimal_places: Override decimal places (if None, uses auto-detection)
    
    Returns:
        Formatted string with appropriate decimal places
    """
    try:
        num = float(value)
        
        # Auto-detect decimal places if not specified
        if decimal_places is None:
            # VCF gets 5 decimal places
            if field_name and 'vcf' in field_name.lower():
                decimal_places = 5
            else:
                # Everything else gets 2 decimal places
                decimal_places = 2
        
        # Format with comma separators and specified decimal places
        return f"{num:,.{decimal_places}f}"
    except (ValueError, TypeError):
        return "-"


def format_pdf_data_row(row_dict: dict, special_fields: dict = None) -> dict:
    """
    Format all numeric values in a row dictionary for PDF display.
    
    Args:
        row_dict: Dictionary of field names to values
        special_fields: Dict of field_name -> decimal_places for special formatting
    
    Returns:
        Dictionary with formatted string values
    """
    special_fields = special_fields or {}
    formatted = {}
    
    for key, value in row_dict.items():
        if isinstance(value, (int, float)):
            decimals = special_fields.get(key)
            formatted[key] = format_pdf_number(value, key, decimals)
        else:
            formatted[key] = str(value) if value is not None else ""
    
    return formatted
