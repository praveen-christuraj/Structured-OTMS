# ==============================================================
# Project OTMS - System Brochure (Technical Edition)
# ==============================================================
# Generates:  OTMS_System_Brochure.pdf
# Location:   D:\Project OTMS-Rebuild\Documentation\
# Author:     Praveen Christuraj
# ==============================================================
# Requires:   pip install reportlab
# ==============================================================

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    Paragraph, Spacer, Image, PageBreak,
    Frame, PageTemplate, BaseDocTemplate, SimpleDocTemplate, Table, TableStyle
)
from datetime import datetime
import os

# --------------------------------------------------------------
# Configuration
# --------------------------------------------------------------
PROJECT_TITLE = "Oil Terminal Management System (OTMS)"
DOCUMENT_TYPE = "System Brochure (Technical Edition)"
AUTHOR_NAME = "Created by Praveen Christuraj"
LOGO_PATH = r"D:\Project OTMS-Rebuild\assets\logo.png"
OUTPUT_PDF = r"D:\Project OTMS-Rebuild\Documentation\OTMS_System_Brochure.pdf"

# --------------------------------------------------------------
# Styles
# --------------------------------------------------------------
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="SecTitle", fontSize=16, leading=20,
    fontName="Helvetica-Bold", textColor=colors.HexColor("#003366"),
    spaceBefore=10, spaceAfter=8))
styles.add(ParagraphStyle(
    name="SubTitle", fontSize=13, leading=18,
    fontName="Helvetica-Bold", textColor=colors.HexColor("#004b7a"),
    spaceAfter=6))
styles.add(ParagraphStyle(
    name="Body", fontSize=10.5, leading=14,
    fontName="Helvetica", spaceAfter=5))
styles.add(ParagraphStyle(
    name="Quote", fontSize=10, leading=13,
    leftIndent=8, rightIndent=8,
    backColor=colors.whitesmoke,
    fontName="Helvetica-Oblique", textColor=colors.HexColor("#333333")))
styles.add(ParagraphStyle(
    name="SmallNote", fontSize=8, leading=10,
    textColor=colors.gray, fontName="Helvetica-Oblique"))

# --------------------------------------------------------------
# Header / Footer with Blue Banner + Logo
# --------------------------------------------------------------
def header_footer(canvas, doc):
    canvas.saveState()
    w, h = A4

    # Blue banner background
    canvas.setFillColor(colors.HexColor("#003366"))
    canvas.rect(0, h - 20*mm, w, 20*mm, fill=1, stroke=0)

    # Header text
    canvas.setFont("Helvetica-Bold", 10)
    canvas.setFillColor(colors.white)
    canvas.drawString(25*mm, h - 12*mm, "Project OTMS – System Brochure")

    # Logo on right
    if os.path.exists(LOGO_PATH):
        try:
            canvas.drawImage(LOGO_PATH, w - 40*mm, h - 18*mm, 25*mm, 15*mm, mask="auto")
        except Exception:
            pass

    # Footer
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.gray)
    canvas.drawString(20*mm, 10*mm, AUTHOR_NAME)
    canvas.drawRightString(w - 20*mm, 10*mm, f"Page {doc.page}")
    canvas.restoreState()

# --------------------------------------------------------------
# Template Class
# --------------------------------------------------------------
class OTMSBrochure(BaseDocTemplate):
    """Legacy template (kept for potential advanced layouts).
    Currently we use SimpleDocTemplate for brochure generation to allow
    onFirstPage/onLaterPages callbacks directly. This class remains for
    future expansion (multiple frames, custom page templates)."""
    def __init__(self, filename, **kw):
        super().__init__(filename, pagesize=A4, **kw)
        frame = Frame(20*mm, 20*mm, A4[0] - 40*mm, A4[1] - 40*mm, id='normal')
        template = PageTemplate(id='brochure', frames=frame, onPage=header_footer)
        self.addPageTemplates([template])

# --------------------------------------------------------------
# Cover Page
# --------------------------------------------------------------
def build_cover(canvas, doc):
    w, h = A4
    canvas.saveState()

    # Background
    canvas.setFillColor(colors.HexColor("#f2f6fa"))
    canvas.rect(0, 0, w, h, fill=1, stroke=0)

    # Logo
    if os.path.exists(LOGO_PATH):
        canvas.drawImage(LOGO_PATH, w/2 - 45*mm, h - 160*mm, 90*mm, 70*mm, mask="auto")

    # Title
    canvas.setFont("Helvetica-Bold", 24)
    canvas.setFillColor(colors.HexColor("#003366"))
    canvas.drawCentredString(w/2, h - 190*mm, PROJECT_TITLE)

    # Subtitle
    canvas.setFont("Helvetica-Bold", 14)
    canvas.setFillColor(colors.black)
    canvas.drawCentredString(w/2, h - 205*mm, DOCUMENT_TYPE)

    # Author / date
    canvas.setFont("Helvetica", 10)
    canvas.drawCentredString(w/2, 60*mm, AUTHOR_NAME)
    canvas.drawCentredString(w/2, 50*mm, f"Generated on {datetime.now():%Y-%m-%d}")
    canvas.restoreState()

# --------------------------------------------------------------
# Utilities
# --------------------------------------------------------------
def add_section(flow, title, text_blocks):
    flow.append(Spacer(1, 10))
    flow.append(Paragraph(title, styles["SecTitle"]))
    for t in text_blocks:
        flow.append(Paragraph(t, styles["Body"]))
    flow.append(Spacer(1, 4))

def add_subsection(flow, title, text_blocks):
    flow.append(Spacer(1, 6))
    flow.append(Paragraph(title, styles["SubTitle"]))
    for t in text_blocks:
        flow.append(Paragraph(t, styles["Body"]))
    flow.append(Spacer(1, 4))

def add_quote(flow, text):
    flow.append(Paragraph(text, styles["Quote"]))
    flow.append(Spacer(1, 5))

def add_placeholder(flow, label="Insert Diagram / Screenshot Here"):
    tbl = Table([[label]], colWidths=[160*mm], rowHeights=[40*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.gray),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONT", (0,0), (-1,-1), "Helvetica-Oblique"),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.gray)
    ]))
    flow.append(tbl)
    flow.append(Spacer(1, 10))

# --------------------------------------------------------------
# Build Base + Table of Contents
# --------------------------------------------------------------
def build_base_brochure():
    # Use SimpleDocTemplate so we can supply onFirstPage/onLaterPages directly
    doc = SimpleDocTemplate(OUTPUT_PDF, pagesize=A4)
    story = []
    # Cover will be rendered via onFirstPage callback during final build

    # Table of contents page
    story.append(Paragraph("Table of Contents", styles["SecTitle"]))
    toc = [
        "1. Executive Summary",
        "2. Architecture Overview",
        "3. Core Components",
        "4. Helper Modules",
        "5. Database & ORM Layer",
        "6. Operational Pages",
        "7. Calculations & Conversions",
        "8. Dashboard & Reporting",
        "9. Security & Audit Framework",
        "10. Automation & Backup",
        "11. Utilities & Diagnostics",
        "12. Configuration & Setup",
        "13. Future Roadmap",
        "14. Appendices"
    ]
    for i in toc:
        story.append(Paragraph(i, styles["Body"]))
    story.append(PageBreak())

    # Next: populate() will fill sections
    return doc, story

    # ----------------------------------------------------------
    # 1. Executive Summary
    # ----------------------------------------------------------
    add_section(flow, "1. Executive Summary", [
        "Project OTMS (Oil Terminal Management System) is a unified, multi-module software "
        "platform engineered to manage terminal operations, inventory control, and reconciliation "
        "across onshore and offshore locations. It provides complete visibility into product "
        "movements—from flow-station intake to tank-farm storage, vessel export, and FSO out-turns.",
        
        "Built on Python and Streamlit, OTMS combines industrial accuracy with modern web technology. "
        "It eliminates the fragmentation between spreadsheets, manual logs, and individual operator "
        "records by creating a single, auditable source of truth for every operational event.",
        
        "Every transaction—whether a dip reading, a tanker dispatch, or a YADE voyage—is stored "
        "with user metadata, timestamps, and 2FA-protected audit trails. The system enforces "
        "real-time calculations using ASTM and API tables to guarantee that measurements and "
        "mass-balance computations remain consistent across all assets."
    ])

    add_subsection(flow, "Objectives of Project OTMS", [
        "• Achieve end-to-end digitalization of oil-terminal operations.",
        "• Provide a uniform interface for Tank, YADE, FSO, and Vessel activities.",
        "• Minimize human error through auto-calculated API60, VCF, LT, and NSV values.",
        "• Enable supervisors and managers to review, approve, and audit transactions remotely.",
        "• Supply structured data for dashboards, regulatory reporting, and monthly reconciliations."
    ])

    add_subsection(flow, "System Highlights", [
        "• Multi-location architecture with location-specific configuration control.",
        "• Role-based access management with Two-Factor Authentication.",
        "• Built-in backup, recycle-bin recovery, and automation scheduler.",
        "• Integration-ready REST/SQL layer for future cloud deployment.",
        "• Consistent unit conversion and computation using standardized ASTM formulas."
    ])

    add_quote(flow,
        "“OTMS transforms legacy terminal paperwork into a digital, secure, and analytical "
        "environment—bridging operational reliability with managerial insight.”"
    )

    add_placeholder(flow, "Insert Overview Diagram of OTMS Architecture Here")
    # ----------------------------------------------------------
    # 2. System Architecture Overview
    # ----------------------------------------------------------
    add_section(flow, "2. System Architecture Overview", [
        "OTMS is designed as a modular, service-oriented application where each page or function "
        "operates as an independent Python module. The heart of the system—`main_app.py`—acts as "
        "the central controller responsible for routing, authentication, and session management.",
        "All operational components (Tank, Tanker, YADE, FSO, Vessel, Dashboard, Reporting, etc.) "
        "reside in the `app_pages/` directory. Each file defines a `render_*` function which is "
        "invoked by the main controller based on user selection from the Streamlit sidebar.",
        "Configuration, such as location-specific settings or dashboard layout, is stored in JSON "
        "structures managed by `location_config.py` and `dashboard_config.py`."
    ])

    add_subsection(flow, "Technology Stack", [
        "• **Frontend / UI** – Streamlit 1.x framework.",
        "• **Backend / Logic** – Python 3 with SQLAlchemy ORM.",
        "• **Database** – SQLite local DB with optional SQL Server / NeonDB cloud sync.",
        "• **Reporting** – ReportLab PDF generator and Power BI integration.",
        "• **Authentication** – Custom security layer with 2FA via `pyotp`."
    ])

    add_subsection(flow, "Execution Flow", [
        "1. User logs in → credentials verified via `auth.py` and `security.py`.",
        "2. Sidebar populates pages allowed by `permission_manager.py`.",
        "3. Selected page calls its respective render function.",
        "4. Data read/written through `db.get_session()` context manager.",
        "5. Every commit triggers `SecurityManager.log_audit()` to ensure traceability."
    ])

    add_placeholder(flow, "Insert Architecture Flow Diagram Here")
    # ----------------------------------------------------------
    # 3. Core Components
    # ----------------------------------------------------------
    add_section(flow, "3. Core Components", [
        "`db.py` establishes SQLAlchemy sessions and manages connection pooling. "
        "`security.py` defines the `SecurityManager` responsible for authentication, "
        "session timeout, and audit logging. `permission_manager.py` governs page visibility "
        "per user role, while `auth.py` handles login validation and password hashing."
    ])

    add_subsection(flow, "Authentication and Roles", [
        "• Operator – restricted to entry pages only.",
        "• Supervisor – approves and reviews operator entries.",
        "• Manager – has full control within assigned locations.",
        "• Admin-Operations – oversees all sites and reporting.",
        "• Admin-IT – system configuration and user administration only."
    ])

    add_subsection(flow, "Audit & Logging", [
        "Every insert, update, or delete event is captured with timestamp, username, and location ID. "
        "Audit data is stored in the `AuditLog` table and surfaced via the Audit Log page. "
        "Critical failures are logged using the `logger` module with file-based persistence."
    ])
    # ----------------------------------------------------------
    # 4. Helper Modules
    # ----------------------------------------------------------
    add_section(flow, "4. Helper Modules", [
        "Helper files provide the reusable logic that powers calculations, IDs, "
        "and consistent formatting across all pages."
    ])

    add_subsection(flow, "Calculation Utilities (`utils_calc.py`)", [
        "Implements ASTM/API equations for Density↔API↔VCF↔LT conversions, including:",
        "• Linear interpolation for calibration tables.",
        "• API60 and Density-15 °C normalization.",
        "• VCF computation using Table 6A constants.",
        "• LT and MT derivation using Table 11 factors."
    ])

    add_subsection(flow, "Miscellaneous Utilities", [
        "• `unique_id_generator.py` – creates daily sequential IDs such as *AGGU-20250109-0001*.",
        "• `timezone_utils.py` – ensures all timestamps align to *Africa/Lagos* (UTC + 1).",
        "• `ui.py` – defines consistent page headers with logged-in user pills.",
        "• `get_browser_info.py` / `ip_service.py` – capture client agent & IP for audit trails."
    ])
    # ----------------------------------------------------------
    # 5. Database & ORM Layer
    # ----------------------------------------------------------
    add_section(flow, "5. Database & ORM Layer", [
        "The `models.py` module defines all ORM entities used throughout OTMS. "
        "Each class corresponds to a database table and includes standard audit columns "
        "(`created_by`, `updated_by`, timestamps). Relationships maintain referential integrity "
        "with cascade deletes disabled for safety."
    ])

    add_subsection(flow, "Major Entities", [
        "• Tank, TankTransaction, CalibrationTank",
        "• Tanker, TankerTransaction",
        "• YADE Voyage, Dip, SampleParam, SealDetail",
        "• FSO Operation, Vessel Operation",
        "• AuditLog, RecycleBin, User, Location, DashboardConfig"
    ])

    add_placeholder(flow, "Insert ER Diagram of Database Schema Here")
    # ----------------------------------------------------------
    # 6. Operational Pages
    # ----------------------------------------------------------
    add_section(flow, "6. Operational Pages", [
        "Each major operational activity is encapsulated in its own module under `app_pages/`. "
        "All follow a consistent pattern: page header → access validation → location check → data entry form → save → audit."
    ])

    add_subsection(flow, "Tank Transactions", [
        "Captures dip & water readings, computes TOV, GOV, GSV, NSV, LT and MT in real time. "
        "Supports tabbed views for Production, Receipt, and Draining operations."
    ])

    add_subsection(flow, "Tanker Transactions", [
        "Handles road tanker logistics – loading bays, destinations, operations, and seal tracking. "
        "Features a grid layout for multiple manhole seals per compartment."
    ])

    add_subsection(flow, "YADE Transactions / TOA", [
        "Manages barge voyages including before/after dips and sample parameters. "
        "Automatically generates *Transshipment Order & Advice (TOA)* PDFs using ReportLab templates."
    ])

    add_subsection(flow, "FSO Operations", [
        "Records floating-storage receipts and exports, computes variances, and produces out-turn reports "
        "for each export vessel. Permission scope limited to Agge, Utapate (OML-13), and Lagos locations."
    ])

    add_subsection(flow, "Vessel Operations", [
        "Logs shuttle vessel activities, including opening/closing dips and cargo reconciliation. "
        "Provides audit-ready PDF summaries for export documentation."
    ])
    # ----------------------------------------------------------
    # 7. Calculations & Conversions
    # ----------------------------------------------------------
    add_section(flow, "7. Calculations & Conversions", [
        "OTMS adheres strictly to ASTM and API standards for volume and mass conversions."
    ])

    add_subsection(flow, "Key Formulas", [
        "• **Density @ 60 °F = SG × Water60** (SG = 141.5 / (API + 131.5))",
        "• **API from Density = 141.5 / SG − 131.5**",
        "• **VCF = exp(−αΔT − 0.8α²ΔT²)** where α = 341.0957 / ρ₆₀²",
        "• **LT = NSV × Table 11 factor**, **MT = LT × 1.01605**"
    ])

    add_subsection(flow, "Computation Workflow", [
        "1. Retrieve tank calibration curve from database.",
        "2. Interpolate total & water dip → TOV / FW.",
        "3. Compute API@60 from observed sample readings.",
        "4. Determine VCF based on tank temperature.",
        "5. Derive GSV, NSV, LT, and MT sequentially.",
        "6. Store rounded values (0 decimal) for reconciliation consistency."
    ])
    # ----------------------------------------------------------
    # 8. Dashboard & Reporting
    # ----------------------------------------------------------
    add_section(flow, "8. Dashboard & Reporting", [
        "Dynamic dashboards give managers instant insight into production, evacuation, and losses. "
        "Dashboard configuration files store grid layouts, KPI cards, and chart types per location."
    ])

    add_subsection(flow, "Dashboard Engine", [
        "• `dashboard_config.py` – saves user-defined layouts in JSON.",
        "• `dashboard_utils.py` – renders KPIs, trend graphs, and tank visuals.",
        "• `dashboard_widgets.py` – implements reusable card components."
    ])

    add_subsection(flow, "Reporting", [
        "`report_engine.py` generates tabular or graphical reports from database views. "
        "Managers can design new templates via the Report Customization UI. "
        "All reports include date filters, export options (PDF, Excel), and location tagging."
    ])

    add_placeholder(flow, "Insert Dashboard Screenshot Placeholder Here")
    # ----------------------------------------------------------
    # 9. Security & Audit Framework
    # ----------------------------------------------------------
    add_section(flow, "9. Security & Audit Framework", [
        "Security in OTMS is multi-layered: user authentication, role validation, "
        "two-factor verification, and detailed audit trails."
    ])

    add_subsection(flow, "Two-Factor Authentication", [
        "Implemented via `twofa.py` using TOTP (Time-based One-Time Password) protocol. "
        "Users scan a QR code with Microsoft / Google Authenticator and verify tokens before access."
    ])

    add_subsection(flow, "Audit Logging", [
        "Every page operation triggers `SecurityManager.log_audit()` with username, action, "
        "resource type and ID, and timestamp. Logs are accessible through the Audit Log page and exportable to CSV/PDF."
    ])

    add_subsection(flow, "Role Enforcement", [
        "`permission_manager.py` dynamically hides or disables pages depending on role "
        "and active location configuration, preventing unauthorized data entry."
    ])
    # ----------------------------------------------------------
    # 10. Automation & Backup
    # ----------------------------------------------------------
    add_section(flow, "10. Automation & Backup", [
        "`backup_manager.py` performs scheduled backups, while `backup_scheduler.py` "
        "automatically triggers them based on frequency rules stored in the database."
    ])

    add_subsection(flow, "Backup Retention", [
        "Backups are timestamped and rotated based on defined retention limits. "
        "Operators can initiate manual backups via the UI, ensuring zero data loss."
    ])

    add_subsection(flow, "Task Scheduling", [
        "`task_manager.py` uses Python’s internal schedulers to run periodic jobs – "
        "reconciliations, report generation, and auto-notifications."
    ])
    # ----------------------------------------------------------
    # 11. Utilities & Diagnostics
    # ----------------------------------------------------------
    add_section(flow, "11. Utilities & Diagnostics", [
        "Diagnostic modules help maintain system health and capture runtime information."
    ])

    add_subsection(flow, "Monitoring Tools", [
        "• `health_check.py` – verifies database connectivity, disk space, and permissions.",
        "• `ip_service.py` – detects client network details for audits.",
        "• `get_browser_info.py` – records browser user-agent string during login.",
        "• `logger.py` – writes errors with timestamps to persistent log files."
    ])
    # ----------------------------------------------------------
    # 12. Configuration & Setup
    # ----------------------------------------------------------
    add_section(flow, "12. Configuration & Setup", [
        "Configuration scripts initialize system defaults and manage location-specific settings."
    ])

    add_subsection(flow, "Location Setup", [
        "`location_manager.py` and `location_config.py` store operation lists, page-visibility flags, "
        "and other site-level parameters."
    ])

    add_subsection(flow, "FSO Permission Setup", [
        "`setup_fso_permissions.py` enables the FSO-Operations page automatically for Agge, Utapate (OML-13), and Lagos locations."
    ])

    add_subsection(flow, "Material Balance Configuration", [
        "`material_balance_config.py` defines reconciliation logic, while "
        "`material_balance_calculator.py` computes variances for monthly reports."
    ])
    # ----------------------------------------------------------
    # 13. Future Roadmap
    # ----------------------------------------------------------
    add_section(flow, "13. Future Roadmap", [
        "Planned enhancements for upcoming OTMS releases include:"
    ])

    add_subsection(flow, "Development Targets", [
        "• REST API for integration with external ERP and SCADA systems.",
        "• Real-time sensor data ingestion (IoT dip gauges).",
        "• Cloud synchronization via NeonDB or Azure SQL.",
        "• Enhanced Power BI dashboards with live auto-refresh.",
        "• Mobile responsive UI for on-field data entry."
    ])

    add_quote(flow, "“The roadmap ensures that OTMS continues evolving into a fully digital oil-terminal ecosystem.”")
    # ----------------------------------------------------------
    # 14. Appendices
    # ----------------------------------------------------------
    add_section(flow, "14. Appendices", [
        "Appendix A – Database Schema Overview",
        "Appendix B – Role Hierarchy and Access Matrix",
        "Appendix C – File Structure and Dependencies",
        "Appendix D – Power BI Dashboard Integration Guide"
    ])

    add_subsection(flow, "Closing Note", [
        "Project OTMS represents years of operational experience translated into software. "
        "It was conceived and engineered by Praveen Christuraj to deliver precision, compliance, and efficiency "
        "for every barrel handled within terminal operations."
    ])

    add_quote(flow, "End of Document – Oil Terminal Management System (OTMS) Brochure © Praveen Christuraj")

def populate_sections(flow):
    add_section(flow, "1. Executive Summary", [
        "This section introduces the purpose, scope, and vision of Project OTMS.",
        "It explains how OTMS integrates field operations, tank management, and reporting "
        "into a unified system supporting multiple locations."
    ])

    add_subsection(flow, "Business Benefits", [
        "• Centralized data for all locations",
        "• 100 % audit compliance and traceability",
        "• Real-time volume reconciliation with ±0.1 % accuracy",
        "• Extensible design ready for cloud synchronization"
    ])

    # Add more sections in the same pattern…

def build_full_brochure():
    doc, story = build_base_brochure()
    populate_sections(story)
    # Build with cover + header/footer
    doc.build(story, onFirstPage=build_cover, onLaterPages=header_footer)
    print(f'✅ OTMS System Brochure generated successfully → {OUTPUT_PDF}')

if __name__ == "__main__":
    build_full_brochure()

