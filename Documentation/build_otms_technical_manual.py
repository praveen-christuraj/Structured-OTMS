# ==============================================================
# Project OTMS - Technical Documentation Manual Builder
# ==============================================================
# Generates:  OTMS_Technical_Manual.pdf
# Location:   D:\Project OTMS-Rebuild\Documentation\
# Author:     Praveen Christuraj
# ==============================================================
# Requires:  pip install reportlab
# ==============================================================

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    Paragraph, Spacer, PageBreak, Frame, PageTemplate, BaseDocTemplate, Image, NextPageTemplate
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
import os

# --------------------------------------------------------------
# Configuration
# --------------------------------------------------------------
PROJECT_TITLE = "Oil Terminal Management System (OTMS)"
DOCUMENT_TYPE = "Technical Documentation Manual"
AUTHOR_NAME = "Created by Praveen Christuraj"
LOGO_PATH = r"D:\Project OTMS-Rebuild\assets\logo.png"
OUTPUT_PDF = r"D:\Project OTMS-Rebuild\Documentation\OTMS_Technical_Manual.pdf"

# --------------------------------------------------------------
# Styles
# --------------------------------------------------------------
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='SectionTitle', fontSize=16, leading=20,
                          spaceAfter=10, textColor=colors.darkblue, fontName='Helvetica-Bold'))
styles.add(ParagraphStyle(name='SubTitle', fontSize=13, leading=16,
                          spaceAfter=8, textColor=colors.HexColor('#004b7a'), fontName='Helvetica-Bold'))
styles.add(ParagraphStyle(name='BodyText2', fontSize=10.5, leading=14,
                          spaceAfter=6, fontName='Helvetica'))
styles.add(ParagraphStyle(name='CodeBlock', fontSize=9, leading=12,
                          backColor=colors.whitesmoke, fontName='Courier', leftIndent=6, rightIndent=6))
styles.add(ParagraphStyle(name='SmallNote', fontSize=8, leading=10,
                          textColor=colors.gray, fontName='Helvetica-Oblique'))

# --------------------------------------------------------------
# Header / Footer
# --------------------------------------------------------------
def header_footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    # Header line
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(colors.gray)
    canvas.drawString(20 * mm, height - 10 * mm, "Project OTMS – Technical Manual")
    # Footer
    canvas.setFillColor(colors.gray)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(20 * mm, 10 * mm, AUTHOR_NAME)
    canvas.drawRightString(width - 20 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()

# --------------------------------------------------------------
# Document Template
# --------------------------------------------------------------
class OTMSManual(BaseDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, pagesize=A4, **kw)
        frame = Frame(20*mm, 20*mm, A4[0]-40*mm, A4[1]-40*mm, id='normal')
        cover_template = PageTemplate(id='cover', frames=frame, onPage=build_cover)
        manual_template = PageTemplate(id='manual', frames=frame, onPage=header_footer)
        self.addPageTemplates([cover_template, manual_template])

# --------------------------------------------------------------
# Cover Page
# --------------------------------------------------------------
def build_cover(canvas, doc):
    canvas.saveState()
    width, height = A4
    # background
    canvas.setFillColor(colors.whitesmoke)
    canvas.rect(0, 0, width, height, fill=1, stroke=0)
    # Logo
    if os.path.exists(LOGO_PATH):
        logo_w = 90 * mm
        logo_h = 90 * mm
        x = (width - logo_w) / 2
        y = height - 160 * mm
        canvas.drawImage(LOGO_PATH, x, y, logo_w, logo_h, mask='auto')
    # Title
    canvas.setFont("Helvetica-Bold", 22)
    canvas.setFillColor(colors.HexColor("#003366"))
    canvas.drawCentredString(width/2, height - 190*mm, PROJECT_TITLE)
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawCentredString(width/2, height - 205*mm, DOCUMENT_TYPE)
    # Author / date
    canvas.setFont("Helvetica", 10)
    canvas.setFillColor(colors.black)
    canvas.drawCentredString(width/2, 60*mm, AUTHOR_NAME)
    canvas.drawCentredString(width/2, 50*mm, f"Generated on {datetime.now():%Y-%m-%d}")
    canvas.restoreState()

# --------------------------------------------------------------
# Utility functions
# --------------------------------------------------------------
def add_section(flow, title, content, level=1):
    """Adds a section title and body paragraph(s)."""
    if level == 1:
        flow.append(Spacer(1, 10))
        flow.append(Paragraph(title, styles['SectionTitle']))
    elif level == 2:
        flow.append(Paragraph(title, styles['SubTitle']))
    else:
        flow.append(Paragraph(f"<b>{title}</b>", styles['BodyText2']))

    if isinstance(content, list):
        for c in content:
            flow.append(Paragraph(c, styles['BodyText2']))
    else:
        flow.append(Paragraph(content, styles['BodyText2']))
    flow.append(Spacer(1, 4))

def add_code(flow, code_text):
    """Adds a formatted code block."""
    flow.append(Paragraph(f"<pre>{code_text}</pre>", styles['CodeBlock']))
    flow.append(Spacer(1, 4))

def add_note(flow, text):
    flow.append(Paragraph(text, styles['SmallNote']))

# --------------------------------------------------------------
# Main builder
# --------------------------------------------------------------
def build_otms_manual():
    doc = OTMSManual(OUTPUT_PDF)
    story = []

    # Cover page rendered by 'cover' template; switch to 'manual' for subsequent pages
    story.append(Spacer(1, 1))
    story.append(NextPageTemplate('manual'))
    story.append(PageBreak())

    # Table of Contents placeholder
    story.append(Paragraph("Table of Contents", styles['SectionTitle']))
    toc_items = [
        "1. Executive Summary",
        "2. System Architecture Overview",
        "3. Core Components",
        "4. Helper Modules",
        "5. Data Models & ORM Layer",
        "6. Operational Pages",
        "7. Calculations & Conversions",
        "8. Dashboard & Reporting Engine",
        "9. Security & Audit Framework",
        "10. Automation & Backup System",
        "11. Utility & Support Tools",
        "12. Configuration & Setup Scripts",
        "13. Appendices and Future Roadmap"
    ]
    for item in toc_items:
        story.append(Paragraph(item, styles['BodyText2']))
    story.append(PageBreak())

    # ---------- Section 1 ----------
    add_section(story, "1. Executive Summary",
        [
            "The Oil Terminal Management System (OTMS) is an integrated Streamlit-based operational platform "
            "developed to manage real-time oil terminal and tank-farm operations across multiple locations. "
            "It centralizes all field activities—from tank transactions to YADE and FSO operations—within a secure, auditable environment.",
            "Project OTMS consolidates 41 independent Python modules into a cohesive ecosystem providing data integrity, "
            "calculation accuracy, and enterprise-level reporting."
        ])
# ==============================================================
#  PART 2 — Fill all sections and generate PDF
# ==============================================================

def populate_sections(story):
    # ---------- Section 2 ----------
    add_section(story, "2. System Architecture Overview",
        [
            "OTMS follows a modular architecture. Each feature page is isolated into its own Python file, "
            "with shared logic encapsulated in core helpers. The main entry point `main_app.py` controls routing, "
            "authentication, and session management.",
            "All operational pages (Tank, Tanker, YADE, FSO, Vessel, etc.) are stored in the `app_pages/` folder. "
            "Each exposes a `render_*` function that the main app invokes based on sidebar selection.",
            "Configuration modules (`location_config`, `dashboard_config`, `fso_config`) hold per-location and "
            "per-dashboard settings, allowing location-aware control of visibility and behavior."
        ])
    add_code(story, "if page == 'Tank Transactions':\n    render_tank_transactions_page(sess, user, location_id)")

    # ---------- Section 3 ----------
    add_section(story, "3. Core Components",
        [
            "• `db.py` – creates SQLAlchemy sessions and manages local SQLite ↔ SQL Server bridge.",
            "• `security.py` – handles authentication, session expiry, audit logging, and password policy.",
            "• `permission_manager.py` – defines role-based access for operators, supervisors, managers, and admins.",
            "• `auth.py` – login / logout endpoints and credential verification.",
            "• `task_manager.py` – scheduler for background jobs like auto-backup and reconciliation.",
            "• `recycle_bin.py` – safe archival of deleted objects with restore support.",
            "• `logger.py` – central error logger with timestamped file output."
        ])
    add_code(story,
        "from db import get_session\n"
        "with get_session() as s:\n"
        "    SecurityManager.log_audit(s, user, 'UPDATE', resource_type='Tank', resource_id='T001')")

    # ---------- Section 4 ----------
    add_section(story, "4. Helper Modules",
        [
            "Helper utilities keep calculations and presentation reusable:",
            "• `utils_calc.py` – contains full API ↔ Density ↔ VCF ↔ LT conversion formulas.",
            "• `unique_id_generator.py` – produces IDs like AGGU-20250109-0001 to guarantee daily uniqueness.",
            "• `timezone_utils.py` – converts UTC ↔ Africa/Lagos time for audit consistency.",
            "• `ui.py` – shared Streamlit header layout.",
            "• `get_browser_info.py`, `ip_service.py`, `health_check.py` – diagnostic utilities."
        ])
    add_code(story,
        "def calculate_vcf(api60, temp_f):\n"
        "    temp_diff = temp_f - 60.0\n"
        "    rho60 = (141.5 * 999.012) / (api60 + 131.5)\n"
        "    alpha = 341.0957 / (rho60 ** 2)\n"
        "    return round(math.exp(-alpha*temp_diff - 0.8*alpha*alpha*temp_diff*temp_diff), 5)")

    # ---------- Section 5 ----------
    add_section(story, "5. Data Models & ORM Layer",
        [
            "`models.py` defines over 40 ORM classes such as Tank, TankTransaction, TankerTransaction, YadeVoyage, "
            "FSOOperation, and AuditLog. Relationships are declared with SQLAlchemy to ensure referential integrity.",
            "Each table includes `created_by`, `updated_by`, and timestamp fields for audit purposes."
        ])
    add_code(story, "class Tank(Base):\n    __tablename__ = 'tanks'\n    id = Column(Integer, primary_key=True)\n    name = Column(String)\n    capacity_bbl = Column(Float)")

    # ---------- Section 6 ----------
    add_section(story, "6. Operational Pages",
        [
            "Every operational page corresponds to a workflow:",
            "• Tank Transactions – records dip readings and computes TOV/GOV/GSV/NSV/LT/MT.",
            "• Tanker Transactions – manages truck loading bays, destinations, and seal grids.",
            "• YADE Transactions – handles barge voyages and auto-generates TOA PDFs.",
            "• FSO Operations – controls floating-storage receipts, exports, and variances.",
            "• Vessel Operations – logs shuttle vessel loading and discharging activities."
        ])
    add_code(story,
        "if st.session_state.get('auth_user')['role'] == 'admin-it':\n"
        "    st.error('🚫 Access Denied: Admin-IT users do not have operational access.')")

    # ---------- Section 7 ----------
    add_section(story, "7. Calculations & Conversions",
        [
            "Core formulas implemented in `utils_calc.py`:",
            "• Density @ 60 °F = SG × Water60;  SG = 141.5 / (API + 131.5)",
            "• API from Density = 141.5 / SG − 131.5",
            "• VCF = exp(−αΔT − 0.8α²ΔT²),  where α = 341.0957 / ρ₆₀²",
            "• LT = NSV × Table 11 Factor;  MT = LT × 1.01605",
            "• NSV = GSV − (GSV × BS&W %)"
        ])
    add_code(story,
        "def compute_all_for_tank_tx(...):\n"
        "    TOV = tank_volume_from_dip_cm(sess, tank_name, dip_cm)\n"
        "    FW  = free_water_from_water_cm(sess, tank_name, water_cm)\n"
        "    GOV = TOV - FW\n"
        "    api60 = api_observed_to_api60(api_obs, sample_temp_f)\n"
        "    vcf = calculate_vcf(api60, tank_temp_f)\n"
        "    GSV = round(GOV * vcf, 0)")

    # ---------- Section 8 ----------
    add_section(story, "8. Dashboard & Reporting Engine",
        [
            "OTMS dashboards are dynamic: layout, cards, and colors are stored in `dashboard_config.py` as JSON.",
            "`dashboard_utils.py` and `dashboard_widgets.py` render KPIs, trends, and tank visuals.",
            "`report_engine.py` and `report_customization.py` allow managers to design new reports directly from the UI."
        ])
    add_code(story, "report = ReportEngine(session).generate('daily_tank_summary', start, end)")

    # ---------- Section 9 ----------
    add_section(story, "9. Security & Audit Framework",
        [
            "Security stack:",
            "• Role-based access from `permission_manager.py`.",
            "• Two-Factor Auth (TOTP) via `twofa.py` – compatible with Google Authenticator.",
            "• `SecurityManager.log_audit()` records all CRUD events.",
            "• Session timeout enforcement for inactivity.",
            "All actions are traceable by user, timestamp, and location."
        ])
    add_code(story,
        "if TwoFactorAuth.verify_token(session, user.id, token):\n"
        "    login_success()\n"
        "else:\n"
        "    st.error('Invalid 2FA code')")

    # ---------- Section 10 ----------
    add_section(story, "10. Automation & Backup System",
        [
            "`backup_manager.py` and `backup_scheduler.py` automate daily database dumps with retention policies. "
            "`task_manager.py` runs scheduled housekeeping and notification tasks."
        ])
    add_code(story, "BackupManager.create_backup('D:/Project OTMS-Rebuild/backups')")

    # ---------- Section 11 ----------
    add_section(story, "11. Utility & Support Tools",
        [
            "Diagnostics and support scripts include:",
            "• `health_check.py` – verifies DB connectivity and disk space.",
            "• `ip_service.py` – resolves client IPs for audit context.",
            "• `get_browser_info.py` – fetches browser User-Agent for session logs."
        ])
    add_code(story, "ua = get_browser_user_agent()\nlogger.info(f'Browser: {ua}')")

    # ---------- Section 12 ----------
    add_section(story, "12. Configuration & Setup Scripts",
        [
            "Initial setup utilities:",
            "• `setup_fso_permissions.py` – pre-grants FSO page access to specific sites (Agge, Utapate, Lagos).",
            "• `location_manager.py` and `location_config.py` – CRUD for location data and settings.",
            "• `material_balance_config.py` and `material_balance_calculator.py` – define reconciliation logic."
        ])
    add_code(story, "if __name__ == '__main__':\n    print('🔧 Setting up FSO permissions...')\n    setup_fso_permissions()")

    # ---------- Section 13 ----------
    add_section(story, "13. Appendices and Future Roadmap",
        [
            "Appendix A – Database Schema Overview (ER diagram available in Power BI dashboards).",
            "Appendix B – Role Matrix: Operator < Supervisor < Manager < Admin-Ops < Admin-IT.",
            "Appendix C – Future Enhancements: REST API gateway, mobile views, cloud sync scheduler, and live sensor feeds.",
            "",
            "Thank you for using Project OTMS — a complete terminal management solution crafted by Praveen Christuraj."
        ])
    add_note(story, "End of Technical Manual")
    story.append(PageBreak())

# --------------------------------------------------------------
# Build and save
# --------------------------------------------------------------
def finalize_otms_manual():
    doc = OTMSManual(OUTPUT_PDF)
    story = []
    # use cover template then switch to manual
    story.append(Spacer(1, 1))
    story.append(NextPageTemplate('manual'))
    story.append(PageBreak())
    # fill all
    populate_sections(story)
    # compile
    doc.build(story)
    print(f'✅ OTMS Technical Manual generated successfully → {OUTPUT_PDF}')

if __name__ == "__main__":
    finalize_otms_manual()
