#!/usr/bin/env python3
"""
OTMS Reporting System Documentation PDF Generator

This script generates a comprehensive PDF documentation for the Dynamic Reporting System.
It creates professional documentation with proper formatting, tables, and code examples.
"""

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, ListFlowable, ListItem, Preformatted, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from datetime import datetime


class NumberedCanvas(canvas.Canvas):
    """Custom canvas for adding page numbers in footer."""
    
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []
    
    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()
    
    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)
    
    def draw_page_number(self, page_count):
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.grey)
        page_num = self._pageNumber
        text = f"Page {page_num} of {page_count}"
        self.drawRightString(7.5 * inch, 0.5 * inch, text)
        self.drawString(1 * inch, 0.5 * inch, "OTMS Dynamic Reporting System Documentation")


def create_styles():
    """Create custom paragraph styles for the document."""
    styles = getSampleStyleSheet()
    
    # Title style - 18pt bold
    styles.add(ParagraphStyle(
        name='DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        spaceAfter=20,
        textColor=colors.HexColor('#1a5276')
    ))
    
    # Section header - 14pt bold, blue color
    styles.add(ParagraphStyle(
        name='SectionHeader',
        parent=styles['Heading1'],
        fontSize=14,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#2980b9'),
        spaceBefore=20,
        spaceAfter=12,
        leftIndent=0
    ))
    
    # Subsection header - 12pt bold
    styles.add(ParagraphStyle(
        name='SubsectionHeader',
        parent=styles['Heading2'],
        fontSize=12,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#34495e'),
        spaceBefore=15,
        spaceAfter=8
    ))
    
    # Body text - 10pt
    styles.add(ParagraphStyle(
        name='DocBodyText',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica',
        alignment=TA_JUSTIFY,
        spaceBefore=6,
        spaceAfter=6,
        leading=14
    ))
    
    # Code block style - 9pt monospace
    styles.add(ParagraphStyle(
        name='CodeBlock',
        parent=styles['Code'],
        fontSize=9,
        fontName='Courier',
        backColor=colors.HexColor('#f4f4f4'),
        borderColor=colors.HexColor('#cccccc'),
        borderWidth=1,
        borderPadding=8,
        spaceBefore=8,
        spaceAfter=8,
        leftIndent=10,
        rightIndent=10
    ))
    
    # Bullet list item
    styles.add(ParagraphStyle(
        name='BulletItem',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica',
        spaceBefore=3,
        spaceAfter=3,
        leftIndent=20
    ))
    
    # Numbered list item
    styles.add(ParagraphStyle(
        name='NumberedItem',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica',
        spaceBefore=4,
        spaceAfter=4,
        leftIndent=25
    ))
    
    # Note/tip style
    styles.add(ParagraphStyle(
        name='NoteStyle',
        parent=styles['Normal'],
        fontSize=9,
        fontName='Helvetica-Oblique',
        textColor=colors.HexColor('#7f8c8d'),
        spaceBefore=6,
        spaceAfter=6,
        leftIndent=15,
        borderColor=colors.HexColor('#3498db'),
        borderWidth=2,
        borderPadding=5
    ))
    
    # Table of Contents entry
    styles.add(ParagraphStyle(
        name='TOCEntry',
        parent=styles['Normal'],
        fontSize=11,
        fontName='Helvetica',
        spaceBefore=6,
        spaceAfter=6
    ))
    
    return styles


def create_table_style():
    """Create a professional table style with alternating row colors."""
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2980b9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ])


def build_cover_page(styles):
    """Build the cover page elements."""
    elements = []
    
    # Add spacing for logo placeholder
    elements.append(Spacer(1, 1.5 * inch))
    
    # Logo placeholder
    logo_placeholder = Table(
        [['[ OTMS LOGO ]']],
        colWidths=[3 * inch],
        rowHeights=[1 * inch]
    )
    logo_placeholder.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#2980b9')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ecf0f1')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 14),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#7f8c8d')),
    ]))
    elements.append(logo_placeholder)
    
    elements.append(Spacer(1, 0.8 * inch))
    
    # Main title
    elements.append(Paragraph(
        "OTMS Dynamic Reporting System",
        styles['DocTitle']
    ))
    
    elements.append(Spacer(1, 0.3 * inch))
    
    # Subtitle
    subtitle_style = ParagraphStyle(
        name='Subtitle',
        parent=styles['Normal'],
        fontSize=14,
        fontName='Helvetica',
        alignment=TA_CENTER,
        textColor=colors.HexColor('#7f8c8d')
    )
    elements.append(Paragraph(
        "Complete Documentation &amp; User Guide",
        subtitle_style
    ))
    
    elements.append(Spacer(1, 1 * inch))
    
    # Version and date info
    info_data = [
        ['Version:', '1.0'],
        ['Date:', datetime.now().strftime('%B %d, %Y')],
        ['Document Type:', 'Technical Documentation'],
        ['Classification:', 'Internal Use']
    ]
    
    info_table = Table(info_data, colWidths=[2 * inch, 3 * inch])
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(info_table)
    
    elements.append(Spacer(1, 1.5 * inch))
    
    # Footer note
    footer_style = ParagraphStyle(
        name='FooterNote',
        parent=styles['Normal'],
        fontSize=9,
        fontName='Helvetica-Oblique',
        alignment=TA_CENTER,
        textColor=colors.HexColor('#95a5a6')
    )
    elements.append(Paragraph(
        "Oil Tank Management System - Confidential",
        footer_style
    ))
    
    elements.append(PageBreak())
    
    return elements


def build_table_of_contents(styles):
    """Build the table of contents."""
    elements = []
    
    elements.append(Paragraph("Table of Contents", styles['DocTitle']))
    elements.append(Spacer(1, 0.3 * inch))
    
    toc_entries = [
        ("1. Overview", "3"),
        ("2. What We Built", "4"),
        ("3. System Architecture", "6"),
        ("4. Admin Guide", "8"),
        ("   4.1 Initial Setup", "8"),
        ("   4.2 User Management", "9"),
        ("   4.3 Location Configuration", "10"),
        ("   4.4 Report Definition", "11"),
        ("5. User Guide", "13"),
        ("   5.1 Running Reports", "13"),
        ("   5.2 Creating Custom Reports", "14"),
        ("   5.3 Export Options", "15"),
        ("6. Database Structure", "17"),
        ("7. Configuration Examples", "19"),
        ("8. Troubleshooting", "22"),
        ("9. Quick Reference Cards", "24"),
        ("10. Training Scenarios", "26"),
    ]
    
    toc_data = []
    for entry, page in toc_entries:
        if entry.startswith("   "):
            toc_data.append([f"    {entry.strip()}", page])
        else:
            toc_data.append([entry, page])
    
    toc_table = Table(toc_data, colWidths=[5 * inch, 1 * inch])
    toc_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#ecf0f1')),
    ]))
    elements.append(toc_table)
    
    elements.append(PageBreak())
    
    return elements


def build_overview_section(styles):
    """Build the Overview section."""
    elements = []
    
    elements.append(Paragraph("1. Overview", styles['SectionHeader']))
    
    elements.append(Paragraph(
        "The OTMS Dynamic Reporting System is a flexible, configuration-driven reporting framework "
        "designed for the Oil Tank Management System. It enables administrators to define custom "
        "reports through JSON configuration, allowing end users to generate, filter, and export "
        "operational data without requiring code changes.",
        styles['DocBodyText']
    ))
    
    elements.append(Paragraph("Key Features", styles['SubsectionHeader']))
    
    features = [
        "[CHECK] Dynamic Report Definitions - Create reports via JSON configuration",
        "[CHECK] Multiple Data Sources - Tank transactions, meters, voyages, FSO operations",
        "[CHECK] Flexible Filtering - Date ranges, locations, custom field filters",
        "[CHECK] Role-Based Access - Reports scoped to user permissions and locations",
        "[CHECK] Multiple Export Formats - CSV, Excel (XLSX), and PDF output",
        "[CHECK] Real-Time Preview - See data before exporting",
        "[CHECK] Aggregation Support - Sum, count, average with grouping",
        "[CHECK] Audit Trail - All report access is logged"
    ]
    
    for feature in features:
        elements.append(Paragraph(f"  {feature}", styles['BulletItem']))
    
    elements.append(Paragraph("Target Audience", styles['SubsectionHeader']))
    
    elements.append(Paragraph(
        "This documentation is intended for:",
        styles['DocBodyText']
    ))
    
    audiences = [
        "[ARROW] System Administrators - Setting up and configuring reports",
        "[ARROW] IT Staff - Technical maintenance and troubleshooting",
        "[ARROW] Managers - Understanding available reporting capabilities",
        "[ARROW] Operators - Running day-to-day reports"
    ]
    
    for audience in audiences:
        elements.append(Paragraph(f"  {audience}", styles['BulletItem']))
    
    elements.append(PageBreak())
    
    return elements


def build_what_we_built_section(styles):
    """Build the What We Built section."""
    elements = []
    
    elements.append(Paragraph("2. What We Built", styles['SectionHeader']))
    
    elements.append(Paragraph("Core Components", styles['SubsectionHeader']))
    
    components = [
        ["Component", "Description", "Location"],
        ["Report Engine", "Core query builder and executor", "report_engine.py"],
        ["Report Definitions", "JSON-based report configurations", "Database table"],
        ["Report UI", "Streamlit interface for users", "app_pages/reports.py"],
        ["Export Handlers", "CSV, XLSX, PDF generators", "report_engine.py"],
        ["Data Sources", "SQLAlchemy model mappings", "models.py"],
    ]
    
    comp_table = Table(components, colWidths=[1.8 * inch, 2.8 * inch, 1.8 * inch])
    comp_table.setStyle(create_table_style())
    elements.append(comp_table)
    
    elements.append(Spacer(1, 0.3 * inch))
    
    elements.append(Paragraph("Supported Data Sources", styles['SubsectionHeader']))
    
    elements.append(Paragraph(
        "The reporting system can query the following operational data:",
        styles['DocBodyText']
    ))
    
    data_sources = [
        ["Data Source Key", "Model", "Description"],
        ["tank_transactions", "TankTransaction", "Daily tank dip records with volumes"],
        ["tanker_transactions", "TankerTransaction", "Tanker loading/unloading records"],
        ["yade_voyages", "YadeVoyage", "YADE vessel voyage data"],
        ["otr_records", "OTRRecord", "Oil Transfer Records"],
        ["fso_operations", "FSOOperation", "FSO vessel operations"],
        ["gpp_production", "GPPProductionRecord", "Gas Processing Plant production"],
        ["river_draft", "RiverDraftRecord", "River draft measurements"],
        ["produced_water", "ProducedWaterRecord", "Produced water disposal records"],
        ["ofs_production", "OFSProductionEvacuationRecord", "OFS production and evacuation"],
        ["tanks", "Tank", "Tank master data"],
        ["vessels", "Vessel", "Vessel master data"],
        ["locations", "Location", "Location master data"],
    ]
    
    ds_table = Table(data_sources, colWidths=[1.8 * inch, 2.2 * inch, 2.4 * inch])
    ds_table.setStyle(create_table_style())
    elements.append(ds_table)
    
    elements.append(Spacer(1, 0.3 * inch))
    
    elements.append(Paragraph("Filter Operators", styles['SubsectionHeader']))
    
    operators = [
        ["Operator", "Usage", "Example"],
        ["equals", "Exact match", 'status equals "active"'],
        ["not_equals", "Exclude value", 'type not_equals "test"'],
        ["greater_than", "Numeric comparison", "volume greater_than 1000"],
        ["less_than", "Numeric comparison", "volume less_than 500"],
        ["contains", "Substring search", 'name contains "Tank"'],
        ["starts_with", "Prefix match", 'code starts_with "TK"'],
        ["between", "Range filter", "date between [start, end]"],
        ["in", "Multiple values", 'status in ["active", "pending"]'],
    ]
    
    op_table = Table(operators, colWidths=[1.5 * inch, 2 * inch, 2.9 * inch])
    op_table.setStyle(create_table_style())
    elements.append(op_table)
    
    elements.append(PageBreak())
    
    return elements


def build_architecture_section(styles):
    """Build the Architecture section with text-based diagrams."""
    elements = []
    
    elements.append(Paragraph("3. System Architecture", styles['SectionHeader']))
    
    elements.append(Paragraph("High-Level Architecture", styles['SubsectionHeader']))
    
    arch_diagram = """
+------------------------------------------------------------------+
|                        OTMS APPLICATION                          |
+------------------------------------------------------------------+
|                                                                  |
|   +------------------+    +------------------+    +-----------+  |
|   |   Streamlit UI   |    |   Report Engine  |    |  Exports  |  |
|   | (app_pages/      |--->| (report_engine.  |--->| CSV/XLSX/ |  |
|   |  reports.py)     |    |  py)             |    | PDF       |  |
|   +------------------+    +------------------+    +-----------+  |
|            |                       |                             |
|            v                       v                             |
|   +------------------+    +------------------+                   |
|   | Report           |    | SQLAlchemy       |                   |
|   | Definitions      |    | ORM Models       |                   |
|   | (JSON Config)    |    | (models.py)      |                   |
|   +------------------+    +------------------+                   |
|                                    |                             |
|                                    v                             |
|                          +------------------+                    |
|                          |   SQLite/DB      |                    |
|                          |   (otms.db)      |                    |
|                          +------------------+                    |
|                                                                  |
+------------------------------------------------------------------+
"""
    
    elements.append(Preformatted(arch_diagram, styles['CodeBlock']))
    
    elements.append(Paragraph("Data Flow", styles['SubsectionHeader']))
    
    flow_diagram = """
+----------------+     +----------------+     +----------------+
| User Selects   |     | Engine Builds  |     | Query Executes |
| Report + Dates |--->| SQLAlchemy     |--->| Against DB     |
|                |     | Query          |     |                |
+----------------+     +----------------+     +----------------+
                                                      |
                                                      v
+----------------+     +----------------+     +----------------+
| User Downloads |     | Format Handler |     | DataFrame      |
| File           |<---| (CSV/XLSX/PDF) |<---| Created        |
|                |     |                |     |                |
+----------------+     +----------------+     +----------------+
"""
    
    elements.append(Preformatted(flow_diagram, styles['CodeBlock']))
    
    elements.append(Paragraph("Report Definition Structure", styles['SubsectionHeader']))
    
    json_example = """{
    "data_source": {
        "table": "tank_transactions",
        "joins": []
    },
    "columns": [
        {"field": "tx_date", "label": "Date", "type": "date"},
        {"field": "tank_name", "label": "Tank", "type": "string"},
        {"field": "gsv", "label": "GSV (bbl)", "type": "numeric"}
    ],
    "filters": [
        {"field": "location_id", "operator": "equals", "value": "user_location"}
    ],
    "sorting": [
        {"field": "tx_date", "order": "desc"}
    ],
    "grouping": [],
    "aggregations": {}
}"""
    
    elements.append(Preformatted(json_example, styles['CodeBlock']))
    
    elements.append(PageBreak())
    
    return elements


def build_admin_guide_section(styles):
    """Build the Admin Guide section."""
    elements = []
    
    elements.append(Paragraph("4. Admin Guide", styles['SectionHeader']))
    
    # 4.1 Initial Setup
    elements.append(Paragraph("4.1 Initial Setup", styles['SubsectionHeader']))
    
    elements.append(Paragraph(
        "Follow these steps to set up the reporting system for your organization:",
        styles['DocBodyText']
    ))
    
    setup_steps = [
        "1. Log in as admin-operations (default: admin / Admin@123)",
        "2. Navigate to Manage Locations and create your operational locations",
        "3. Go to Manage Users to create user accounts with appropriate roles",
        "4. Access Location Settings to enable Reports for each location",
        "5. Create report definitions in the database (see Configuration Examples)",
        "6. Verify report access by logging in as different user roles"
    ]
    
    for step in setup_steps:
        elements.append(Paragraph(step, styles['NumberedItem']))
    
    elements.append(Spacer(1, 0.2 * inch))
    
    # 4.2 User Management
    elements.append(Paragraph("4.2 User Management", styles['SubsectionHeader']))
    
    elements.append(Paragraph(
        "The system supports multiple roles with different access levels:",
        styles['DocBodyText']
    ))
    
    roles_data = [
        ["Role", "Icon", "Report Access", "Can Create Reports"],
        ["admin-operations", "[BUILDING]", "All locations", "Yes"],
        ["admin-it", "[COMPUTER]", "All locations", "Yes"],
        ["manager", "[TIE]", "Assigned location", "No"],
        ["supervisor", "[PERSON]", "Assigned location", "No"],
        ["operator", "[WORKER]", "Assigned location", "No"],
    ]
    
    roles_table = Table(roles_data, colWidths=[1.5 * inch, 1 * inch, 1.8 * inch, 1.5 * inch])
    roles_table.setStyle(create_table_style())
    elements.append(roles_table)
    
    elements.append(Spacer(1, 0.2 * inch))
    
    elements.append(Paragraph("Creating a New User:", styles['SubsectionHeader']))
    
    user_steps = [
        "1. Go to Manage Users page",
        "2. Click 'Add New User' button",
        "3. Fill in username, password, full name",
        "4. Select appropriate role from dropdown",
        "5. Assign user to a location (required for non-admin roles)",
        "6. Click Save to create the user",
        "7. Share credentials securely with the new user"
    ]
    
    for step in user_steps:
        elements.append(Paragraph(step, styles['NumberedItem']))
    
    elements.append(PageBreak())
    
    # 4.3 Location Configuration
    elements.append(Paragraph("4.3 Location Configuration", styles['SubsectionHeader']))
    
    elements.append(Paragraph(
        "Each location can have different page visibility settings:",
        styles['DocBodyText']
    ))
    
    location_steps = [
        "1. Navigate to Location Settings",
        "2. Select the target location from the dropdown",
        "3. Toggle 'Reports' to ON to enable reporting for this location",
        "4. Configure other page visibility as needed",
        "5. Click Save to apply changes",
        "6. The sidebar will update to reflect the new settings"
    ]
    
    for step in location_steps:
        elements.append(Paragraph(step, styles['NumberedItem']))
    
    elements.append(Spacer(1, 0.2 * inch))
    
    # 4.4 Report Definition
    elements.append(Paragraph("4.4 Report Definition", styles['SubsectionHeader']))
    
    elements.append(Paragraph(
        "Reports are defined using JSON configuration stored in the database. "
        "Each report definition includes:",
        styles['DocBodyText']
    ))
    
    definition_parts = [
        "[DOT] data_source - The primary table and any joins",
        "[DOT] columns - Fields to display with labels and types",
        "[DOT] filters - Default filters and user-input placeholders",
        "[DOT] sorting - Default sort order",
        "[DOT] grouping - Fields to group by (for aggregations)",
        "[DOT] aggregations - Sum, count, average calculations"
    ]
    
    for part in definition_parts:
        elements.append(Paragraph(f"  {part}", styles['BulletItem']))
    
    elements.append(Paragraph(
        "[NOTE] Tip: Use 'user_location' as a filter value to automatically scope "
        "reports to the user's assigned location.",
        styles['NoteStyle']
    ))
    
    elements.append(PageBreak())
    
    return elements


def build_user_guide_section(styles):
    """Build the User Guide section."""
    elements = []
    
    elements.append(Paragraph("5. User Guide", styles['SectionHeader']))
    
    # 5.1 Running Reports
    elements.append(Paragraph("5.1 Running Reports", styles['SubsectionHeader']))
    
    elements.append(Paragraph(
        "Follow these steps to run a report:",
        styles['DocBodyText']
    ))
    
    run_steps = [
        "1. Log in to OTMS with your credentials",
        "2. Click on 'Reports' in the sidebar navigation",
        "3. Select a report from the available reports dropdown",
        "4. Choose your date range using the date pickers",
        "5. Apply any additional filters if available",
        "6. Click 'Generate Report' to view the data",
        "7. Review the results in the data table",
        "8. Export using CSV, Excel, or PDF buttons"
    ]
    
    for step in run_steps:
        elements.append(Paragraph(step, styles['NumberedItem']))
    
    elements.append(Spacer(1, 0.2 * inch))
    
    # 5.2 Creating Custom Reports (Admin only)
    elements.append(Paragraph("5.2 Creating Custom Reports (Admin Only)", styles['SubsectionHeader']))
    
    elements.append(Paragraph(
        "Administrators can create new report definitions:",
        styles['DocBodyText']
    ))
    
    create_steps = [
        "1. Identify the data source (e.g., tank_transactions)",
        "2. Determine which columns to include",
        "3. Define any default filters",
        "4. Create the JSON configuration (see examples)",
        "5. Insert the report definition into the database",
        "6. Assign appropriate access permissions",
        "7. Test the report with different user roles"
    ]
    
    for step in create_steps:
        elements.append(Paragraph(step, styles['NumberedItem']))
    
    elements.append(Spacer(1, 0.2 * inch))
    
    # 5.3 Export Options
    elements.append(Paragraph("5.3 Export Options", styles['SubsectionHeader']))
    
    export_data = [
        ["Format", "Best For", "Features"],
        ["CSV", "Data analysis, imports", "Plain text, universal compatibility"],
        ["Excel (XLSX)", "Spreadsheet work", "Formatted, multiple sheets possible"],
        ["PDF", "Printing, sharing", "Fixed layout, professional appearance"],
    ]
    
    export_table = Table(export_data, colWidths=[1.5 * inch, 2 * inch, 2.9 * inch])
    export_table.setStyle(create_table_style())
    elements.append(export_table)
    
    elements.append(Spacer(1, 0.2 * inch))
    
    elements.append(Paragraph("Export Tips:", styles['SubsectionHeader']))
    
    tips = [
        "[STAR] CSV files can be opened in Excel, Google Sheets, or any text editor",
        "[STAR] PDF reports are limited to 10 columns for readability",
        "[STAR] Large datasets may take longer to generate - be patient",
        "[STAR] All exports are logged in the audit trail"
    ]
    
    for tip in tips:
        elements.append(Paragraph(f"  {tip}", styles['BulletItem']))
    
    elements.append(PageBreak())
    
    return elements


def build_database_section(styles):
    """Build the Database Structure section."""
    elements = []
    
    elements.append(Paragraph("6. Database Structure", styles['SectionHeader']))
    
    elements.append(Paragraph(
        "The reporting system uses the following key database tables:",
        styles['DocBodyText']
    ))
    
    # Report Definition Table
    elements.append(Paragraph("ReportDefinition Table", styles['SubsectionHeader']))
    
    report_def_cols = [
        ["Column", "Type", "Description"],
        ["id", "INTEGER", "Primary key"],
        ["name", "VARCHAR(100)", "Report display name"],
        ["description", "TEXT", "Report description"],
        ["config_json", "TEXT", "JSON configuration"],
        ["created_by", "INTEGER", "User ID who created"],
        ["created_at", "DATETIME", "Creation timestamp"],
        ["is_active", "BOOLEAN", "Whether report is active"],
        ["location_id", "INTEGER", "Optional location scope"],
    ]
    
    rd_table = Table(report_def_cols, colWidths=[1.5 * inch, 1.5 * inch, 3.4 * inch])
    rd_table.setStyle(create_table_style())
    elements.append(rd_table)
    
    elements.append(Spacer(1, 0.2 * inch))
    
    # Tank Transaction Table
    elements.append(Paragraph("TankTransaction Table (Example Data Source)", styles['SubsectionHeader']))
    
    tank_tx_cols = [
        ["Column", "Type", "Description"],
        ["id", "INTEGER", "Primary key"],
        ["location_id", "INTEGER", "Location reference"],
        ["tank_id", "INTEGER", "Tank reference"],
        ["tx_date", "DATE", "Transaction date"],
        ["dip_cm", "FLOAT", "Dip measurement in cm"],
        ["water_cm", "FLOAT", "Water measurement in cm"],
        ["tov", "FLOAT", "Total Observed Volume"],
        ["gov", "FLOAT", "Gross Observed Volume"],
        ["gsv", "FLOAT", "Gross Standard Volume"],
        ["nsv", "FLOAT", "Net Standard Volume"],
        ["api60", "FLOAT", "API gravity at 60F"],
        ["created_by", "INTEGER", "User who created"],
        ["created_at", "DATETIME", "Creation timestamp"],
    ]
    
    tt_table = Table(tank_tx_cols, colWidths=[1.5 * inch, 1.5 * inch, 3.4 * inch])
    tt_table.setStyle(create_table_style())
    elements.append(tt_table)
    
    elements.append(Spacer(1, 0.2 * inch))
    
    # Audit Log Table
    elements.append(Paragraph("AuditLog Table", styles['SubsectionHeader']))
    
    audit_cols = [
        ["Column", "Type", "Description"],
        ["id", "INTEGER", "Primary key"],
        ["timestamp", "DATETIME", "Event timestamp"],
        ["user_id", "INTEGER", "User who performed action"],
        ["username", "VARCHAR(50)", "Username for display"],
        ["action", "VARCHAR(50)", "Action type (CREATE, READ, etc.)"],
        ["resource_type", "VARCHAR(50)", "Type of resource accessed"],
        ["resource_id", "VARCHAR(100)", "ID of resource"],
        ["details", "TEXT", "Additional details"],
        ["ip_address", "VARCHAR(50)", "Client IP address"],
        ["success", "BOOLEAN", "Whether action succeeded"],
    ]
    
    al_table = Table(audit_cols, colWidths=[1.5 * inch, 1.5 * inch, 3.4 * inch])
    al_table.setStyle(create_table_style())
    elements.append(al_table)
    
    elements.append(PageBreak())
    
    return elements


def build_configuration_examples(styles):
    """Build the Configuration Examples section."""
    elements = []
    
    elements.append(Paragraph("7. Configuration Examples", styles['SectionHeader']))
    
    # Example 1: Daily Tank Summary
    elements.append(Paragraph("Example 1: Daily Tank Summary Report", styles['SubsectionHeader']))
    
    example1 = """{
    "data_source": {
        "table": "tank_transactions",
        "joins": []
    },
    "columns": [
        {"field": "tx_date", "label": "Date", "type": "date"},
        {"field": "tank_name", "label": "Tank", "type": "string"},
        {"field": "dip_cm", "label": "Dip (cm)", "type": "numeric"},
        {"field": "gov", "label": "GOV (bbl)", "type": "numeric"},
        {"field": "gsv", "label": "GSV (bbl)", "type": "numeric"},
        {"field": "nsv", "label": "NSV (bbl)", "type": "numeric"},
        {"field": "api60", "label": "API@60F", "type": "numeric"}
    ],
    "filters": [
        {"field": "location_id", "operator": "equals", "value": "user_location"},
        {"field": "tx_date", "operator": "between", "value": "date_range"}
    ],
    "sorting": [
        {"field": "tx_date", "order": "desc"},
        {"field": "tank_name", "order": "asc"}
    ],
    "grouping": [],
    "aggregations": {}
}"""
    
    elements.append(Preformatted(example1, styles['CodeBlock']))
    
    elements.append(Spacer(1, 0.2 * inch))
    
    # Example 2: Monthly Production Summary
    elements.append(Paragraph("Example 2: Monthly Production Summary with Aggregation", styles['SubsectionHeader']))
    
    example2 = """{
    "data_source": {
        "table": "tank_transactions",
        "joins": []
    },
    "columns": [
        {"field": "tank_name", "label": "Tank", "type": "string"},
        {"field": "gsv", "label": "Total GSV (bbl)", "type": "numeric"},
        {"field": "nsv", "label": "Total NSV (bbl)", "type": "numeric"}
    ],
    "filters": [
        {"field": "location_id", "operator": "equals", "value": "user_location"},
        {"field": "tx_date", "operator": "between", "value": "date_range"}
    ],
    "sorting": [
        {"field": "tank_name", "order": "asc"}
    ],
    "grouping": ["tank_name"],
    "aggregations": {
        "total_gsv": {"field": "gsv", "function": "sum"},
        "total_nsv": {"field": "nsv", "function": "sum"}
    }
}"""
    
    elements.append(Preformatted(example2, styles['CodeBlock']))
    
    elements.append(Spacer(1, 0.2 * inch))
    
    # Example 3: FSO Operations Report
    elements.append(Paragraph("Example 3: FSO Operations Report", styles['SubsectionHeader']))
    
    example3 = """{
    "data_source": {
        "table": "fso_operations",
        "joins": []
    },
    "columns": [
        {"field": "operation_date", "label": "Date", "type": "date"},
        {"field": "vessel_name", "label": "Vessel", "type": "string"},
        {"field": "operation_type", "label": "Operation", "type": "string"},
        {"field": "volume_loaded", "label": "Volume (bbl)", "type": "numeric"},
        {"field": "status", "label": "Status", "type": "string"}
    ],
    "filters": [
        {"field": "location_id", "operator": "equals", "value": "user_location"},
        {"field": "operation_date", "operator": "between", "value": "date_range"},
        {"field": "status", "operator": "in", "value": ["completed", "pending"]}
    ],
    "sorting": [
        {"field": "operation_date", "order": "desc"}
    ],
    "grouping": [],
    "aggregations": {}
}"""
    
    elements.append(Preformatted(example3, styles['CodeBlock']))
    
    elements.append(PageBreak())
    
    return elements


def build_troubleshooting_section(styles):
    """Build the Troubleshooting section."""
    elements = []
    
    elements.append(Paragraph("8. Troubleshooting", styles['SectionHeader']))
    
    elements.append(Paragraph("Common Issues and Solutions", styles['SubsectionHeader']))
    
    issues = [
        ["Issue", "Possible Cause", "Solution"],
        [
            "Reports page not visible",
            "Reports disabled for location",
            "Admin: Enable in Location Settings"
        ],
        [
            "No data in report",
            "Date range has no records",
            "Expand date range or verify data exists"
        ],
        [
            "Report shows error",
            "Invalid JSON configuration",
            "Check report definition syntax"
        ],
        [
            "Export button not working",
            "Browser blocking download",
            "Check browser popup settings"
        ],
        [
            "PDF export fails",
            "reportlab not installed",
            "Run: pip install reportlab"
        ],
        [
            "Session expired",
            "30-minute timeout reached",
            "Log in again; activity resets timer"
        ],
        [
            "Access denied",
            "Insufficient role permissions",
            "Contact admin for role upgrade"
        ],
        [
            "Slow report generation",
            "Large date range selected",
            "Narrow date range or add filters"
        ],
    ]
    
    issues_table = Table(issues, colWidths=[2 * inch, 2.2 * inch, 2.2 * inch])
    issues_table.setStyle(create_table_style())
    elements.append(issues_table)
    
    elements.append(Spacer(1, 0.3 * inch))
    
    elements.append(Paragraph("Error Messages Reference", styles['SubsectionHeader']))
    
    errors = [
        ["Error Message", "Meaning", "Action"],
        [
            "Unknown data source: X",
            "Invalid table name in config",
            "Use valid table from DATA_SOURCES"
        ],
        [
            "String index error",
            "Filter configuration issue",
            "Check filter field names and operators"
        ],
        [
            "No locations found",
            "No locations in database",
            "Create location in Manage Locations"
        ],
        [
            "Permission denied",
            "Role cannot access feature",
            "Request appropriate permissions"
        ],
    ]
    
    errors_table = Table(errors, colWidths=[2.2 * inch, 2 * inch, 2.2 * inch])
    errors_table.setStyle(create_table_style())
    elements.append(errors_table)
    
    elements.append(Spacer(1, 0.3 * inch))
    
    elements.append(Paragraph("Diagnostic Steps", styles['SubsectionHeader']))
    
    diagnostic_steps = [
        "1. Check the browser console for JavaScript errors (F12)",
        "2. Verify the database file exists (otms.db)",
        "3. Check application logs in the logs/ directory",
        "4. Confirm user role and location assignment",
        "5. Test with a known-working report definition",
        "6. Restart the Streamlit application if needed"
    ]
    
    for step in diagnostic_steps:
        elements.append(Paragraph(step, styles['NumberedItem']))
    
    elements.append(PageBreak())
    
    return elements


def build_quick_reference_section(styles):
    """Build the Quick Reference Cards section."""
    elements = []
    
    elements.append(Paragraph("9. Quick Reference Cards", styles['SectionHeader']))
    
    # Role Quick Reference
    elements.append(Paragraph("Role Permissions Quick Reference", styles['SubsectionHeader']))
    
    role_ref = [
        ["Capability", "Operator", "Supervisor", "Manager", "Admin-IT", "Admin-Ops"],
        ["View Reports", "Yes", "Yes", "Yes", "Yes", "Yes"],
        ["Export Data", "Yes", "Yes", "Yes", "Yes", "Yes"],
        ["Create Reports", "No", "No", "No", "Yes", "Yes"],
        ["Manage Users", "No", "No", "No", "Yes", "Yes"],
        ["Location Settings", "No", "No", "No", "Yes", "Yes"],
        ["View Audit Log", "No", "No", "Yes", "Yes", "Yes"],
        ["All Locations", "No", "No", "No", "Yes", "Yes"],
    ]
    
    role_table = Table(role_ref, colWidths=[1.5 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch, 1 * inch])
    role_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2980b9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
    ]))
    elements.append(role_table)
    
    elements.append(Spacer(1, 0.3 * inch))
    
    # Keyboard Shortcuts (if applicable)
    elements.append(Paragraph("Navigation Quick Reference", styles['SubsectionHeader']))
    
    nav_ref = [
        ["Action", "Steps"],
        ["Login", "Enter username + password, click Login"],
        ["Select Location", "Home page -> Location dropdown"],
        ["Run Report", "Reports -> Select report -> Set dates -> Generate"],
        ["Export CSV", "Generate report -> Click 'Download CSV'"],
        ["Export Excel", "Generate report -> Click 'Download Excel'"],
        ["Export PDF", "Generate report -> Click 'Download PDF'"],
        ["Logout", "Click Logout in sidebar -> Confirm"],
    ]
    
    nav_table = Table(nav_ref, colWidths=[1.8 * inch, 4.6 * inch])
    nav_table.setStyle(create_table_style())
    elements.append(nav_table)
    
    elements.append(Spacer(1, 0.3 * inch))
    
    # Data Types Reference
    elements.append(Paragraph("Column Types Reference", styles['SubsectionHeader']))
    
    types_ref = [
        ["Type", "Description", "Format Example"],
        ["string", "Text values", '"Tank-001"'],
        ["numeric", "Numbers (integer or decimal)", "1234.56"],
        ["date", "Date only", "2024-01-15"],
        ["datetime", "Date and time", "2024-01-15 14:30:00"],
        ["boolean", "True/False", "True"],
    ]
    
    types_table = Table(types_ref, colWidths=[1.3 * inch, 2.5 * inch, 2.6 * inch])
    types_table.setStyle(create_table_style())
    elements.append(types_table)
    
    elements.append(PageBreak())
    
    return elements


def build_training_scenarios(styles):
    """Build the Training Scenarios section."""
    elements = []
    
    elements.append(Paragraph("10. Training Scenarios", styles['SectionHeader']))
    
    elements.append(Paragraph(
        "Use these scenarios to practice using the reporting system:",
        styles['DocBodyText']
    ))
    
    # Scenario 1
    elements.append(Paragraph("Scenario 1: Daily Operations Report", styles['SubsectionHeader']))
    
    elements.append(Paragraph(
        "[CLIPBOARD] Objective: Generate a daily tank transaction report for your location",
        styles['DocBodyText']
    ))
    
    scenario1_steps = [
        "1. Log in with your operator credentials",
        "2. Navigate to the Reports page from the sidebar",
        "3. Select 'Daily Tank Summary' from the report dropdown",
        "4. Set the date range to yesterday's date",
        "5. Click Generate Report",
        "6. Review the data for accuracy",
        "7. Export to PDF for the daily handover file",
        "8. Verify the PDF opens correctly"
    ]
    
    for step in scenario1_steps:
        elements.append(Paragraph(step, styles['NumberedItem']))
    
    elements.append(Spacer(1, 0.2 * inch))
    
    # Scenario 2
    elements.append(Paragraph("Scenario 2: Monthly Summary for Management", styles['SubsectionHeader']))
    
    elements.append(Paragraph(
        "[CLIPBOARD] Objective: Create a monthly production summary with totals",
        styles['DocBodyText']
    ))
    
    scenario2_steps = [
        "1. Log in with manager credentials",
        "2. Go to Reports page",
        "3. Select 'Monthly Production Summary'",
        "4. Set date range to the previous month",
        "5. Generate the report",
        "6. Note the aggregated totals by tank",
        "7. Export to Excel for further analysis",
        "8. Create charts from the Excel data"
    ]
    
    for step in scenario2_steps:
        elements.append(Paragraph(step, styles['NumberedItem']))
    
    elements.append(Spacer(1, 0.2 * inch))
    
    # Scenario 3
    elements.append(Paragraph("Scenario 3: Admin - Create New Report (Advanced)", styles['SubsectionHeader']))
    
    elements.append(Paragraph(
        "[CLIPBOARD] Objective: Define a custom report for FSO operations",
        styles['DocBodyText']
    ))
    
    scenario3_steps = [
        "1. Log in as admin-operations",
        "2. Review the Configuration Examples section of this document",
        "3. Identify required columns from the fso_operations table",
        "4. Create JSON configuration following the template",
        "5. Insert the report definition into the database",
        "6. Test the report with different date ranges",
        "7. Verify role-based access works correctly",
        "8. Document the new report for users"
    ]
    
    for step in scenario3_steps:
        elements.append(Paragraph(step, styles['NumberedItem']))
    
    elements.append(Spacer(1, 0.3 * inch))
    
    # Practice Exercises
    elements.append(Paragraph("Practice Exercises", styles['SubsectionHeader']))
    
    exercises = [
        ["Exercise", "Skill Practiced", "Difficulty"],
        ["Export same report in all 3 formats", "Export functionality", "Easy"],
        ["Run report with different date ranges", "Filtering", "Easy"],
        ["Compare data across two locations", "Multi-location access", "Medium"],
        ["Identify missing data in a report", "Data validation", "Medium"],
        ["Create a custom aggregation report", "Report configuration", "Advanced"],
    ]
    
    exercises_table = Table(exercises, colWidths=[2.8 * inch, 2 * inch, 1.6 * inch])
    exercises_table.setStyle(create_table_style())
    elements.append(exercises_table)
    
    elements.append(Spacer(1, 0.5 * inch))
    
    # Final note
    elements.append(Paragraph(
        "[INFO] For additional support, contact your system administrator or refer to "
        "the online help resources available within the application.",
        styles['NoteStyle']
    ))
    
    return elements


def generate_pdf():
    """Generate the complete documentation PDF."""
    output_file = "OTMS_Reporting_System_Documentation.pdf"
    
    # Create the document
    doc = SimpleDocTemplate(
        output_file,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch
    )
    
    # Create styles
    styles = create_styles()
    
    # Build all sections
    elements = []
    
    # Cover page
    elements.extend(build_cover_page(styles))
    
    # Table of Contents
    elements.extend(build_table_of_contents(styles))
    
    # Main sections
    elements.extend(build_overview_section(styles))
    elements.extend(build_what_we_built_section(styles))
    elements.extend(build_architecture_section(styles))
    elements.extend(build_admin_guide_section(styles))
    elements.extend(build_user_guide_section(styles))
    elements.extend(build_database_section(styles))
    elements.extend(build_configuration_examples(styles))
    elements.extend(build_troubleshooting_section(styles))
    elements.extend(build_quick_reference_section(styles))
    elements.extend(build_training_scenarios(styles))
    
    # Build the PDF with numbered pages
    doc.build(elements, canvasmaker=NumberedCanvas)
    
    return output_file


if __name__ == "__main__":
    generate_pdf()
    print("✅ Documentation PDF generated: OTMS_Reporting_System_Documentation.pdf")
