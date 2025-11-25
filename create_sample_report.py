# create_sample_report.py
"""
Utility script to create sample reports for testing
Run this once to populate the database with test reports
"""

import json
from datetime import datetime

from db import init_db, get_session
from models import ReportDefinition, ReportAccess


def create_sample_reports():
    """Create sample report definitions for testing"""
    
    init_db()
    
    with get_session() as session:
        # Check if sample reports already exist
        existing = session.query(ReportDefinition).filter(
            ReportDefinition.slug == 'tank_transactions_summary'
        ).first()
        
        if existing:
            print("✅ Sample reports already exist!")
            return
        
        print("Creating sample reports...")
        
        # ==========================================
        # REPORT 1: Tank Transactions Summary
        # ==========================================
        
        report1_config = {
            "report_type": "tank_transactions_summary",
            "data_source": {
                "table": "tank_transactions",
                "joins": []
            },
            "columns": [
                {"field": "date", "label": "Transaction Date", "type": "date"},
                {"field": "tank_name", "label": "Tank Name", "type": "string"},
                {"field": "operation", "label": "Operation Type", "type": "string"},
                {"field": "qty_bbls", "label": "Quantity (BBL)", "type": "numeric"},
                {"field": "dip_cm", "label": "Dip (cm)", "type": "numeric"},
                {"field": "water_cm", "label": "Water (cm)", "type": "numeric"},
                {"field": "remarks", "label": "Remarks", "type": "string"},
                {"field": "created_by", "label": "Created By", "type": "string"}
            ],
            "filters": [
                {"field": "location_id", "operator": "equals", "value": "user_location"},
                {"field": "date", "operator": "between", "value": "date_range"}
            ],
            "grouping": [],
            "sorting": [
                {"field": "date", "order": "desc"}
            ],
            "aggregations": {},
            "export_formats": ["csv", "xlsx", "pdf"]
        }
        
        report1 = ReportDefinition(
            location_id=None,  # Available to all locations
            name="Tank Transactions Summary",
            slug="tank_transactions_summary",
            config_json=json.dumps(report1_config),
            is_active=True,
            created_by="system",
            created_at=datetime.utcnow()
        )
        
        session.add(report1)
        session.flush()  # Get the ID
        
        # Grant access to all operational roles
        for role in ['manager', 'supervisor', 'operator', 'admin-operations', 'admin-it']:
            access1 = ReportAccess(
                report_id=report1.id,
                role=role,
                granted_by="system",
                granted_at=datetime.utcnow()
            )
            session.add(access1)
        
        print(f"✅ Created: {report1.name}")
        
        # ==========================================
        # REPORT 2: Tanker Dispatch Report
        # ==========================================
        
        report2_config = {
            "report_type": "tanker_dispatch_summary",
            "data_source": {
                "table": "tanker_transactions",
                "joins": []
            },
            "columns": [
                {"field": "transaction_date", "label": "Date", "type": "date"},
                {"field": "tanker_name", "label": "Tanker Name", "type": "string"},
                {"field": "convoy_no", "label": "Convoy No", "type": "string"},
                {"field": "cargo", "label": "Cargo", "type": "string"},
                {"field": "destination", "label": "Destination", "type": "string"},
                {"field": "compartment", "label": "Compartment", "type": "string"},
                {"field": "nsv_bbl", "label": "NSV (BBL)", "type": "numeric"},
                {"field": "created_by", "label": "Created By", "type": "string"}
            ],
            "filters": [
                {"field": "location_id", "operator": "equals", "value": "user_location"},
                {"field": "transaction_date", "operator": "between", "value": "date_range"}
            ],
            "grouping": [],
            "sorting": [
                {"field": "transaction_date", "order": "desc"}
            ],
            "aggregations": {},
            "export_formats": ["csv", "xlsx", "pdf"]
        }
        
        report2 = ReportDefinition(
            location_id=None,
            name="Tanker Dispatch Report",
            slug="tanker_dispatch_report",
            config_json=json.dumps(report2_config),
            is_active=True,
            created_by="system",
            created_at=datetime.utcnow()
        )
        
        session.add(report2)
        session.flush()
        
        # Grant access to all operational roles
        for role in ['manager', 'supervisor', 'operator', 'admin-operations', 'admin-it']:
            access2 = ReportAccess(
                report_id=report2.id,
                role=role,
                granted_by="system",
                granted_at=datetime.utcnow()
            )
            session.add(access2)
        
        print(f"✅ Created: {report2.name}")
        
        # ==========================================
        # REPORT 3: YADE Voyage Summary
        # ==========================================
        
        report3_config = {
            "report_type": "yade_voyage_summary",
            "data_source": {
                "table": "yade_voyages",
                "joins": []
            },
            "columns": [
                {"field": "date", "label": "Voyage Date", "type": "date"},
                {"field": "yade_name", "label": "YADE Barge", "type": "string"},
                {"field": "voyage_no", "label": "Voyage No", "type": "string"},
                {"field": "convoy_no", "label": "Convoy No", "type": "string"},
                {"field": "cargo", "label": "Cargo", "type": "string"},
                {"field": "destination", "label": "Destination", "type": "string"},
                {"field": "loading_berth", "label": "Loading Berth", "type": "string"},
                {"field": "created_by", "label": "Created By", "type": "string"}
            ],
            "filters": [
                {"field": "location_id", "operator": "equals", "value": "user_location"},
                {"field": "date", "operator": "between", "value": "date_range"}
            ],
            "grouping": [],
            "sorting": [
                {"field": "date", "order": "desc"}
            ],
            "aggregations": {},
            "export_formats": ["csv", "xlsx", "pdf"]
        }
        
        report3 = ReportDefinition(
            location_id=None,
            name="YADE Voyage Summary",
            slug="yade_voyage_summary",
            config_json=json.dumps(report3_config),
            is_active=True,
            created_by="system",
            created_at=datetime.utcnow()
        )
        
        session.add(report3)
        session.flush()
        
        # Grant access to all operational roles
        for role in ['manager', 'supervisor', 'operator', 'admin-operations', 'admin-it']:
            access3 = ReportAccess(
                report_id=report3.id,
                role=role,
                granted_by="system",
                granted_at=datetime.utcnow()
            )
            session.add(access3)
        
        print(f"✅ Created: {report3.name}")
        
        # ==========================================
        # REPORT 4: Daily Production Summary
        # ==========================================
        
        report4_config = {
            "report_type": "daily_production_summary",
            "data_source": {
                "table": "gpp_production",
                "joins": []
            },
            "columns": [
                {"field": "date", "label": "Date", "type": "date"},
                {"field": "okw_production", "label": "OKW Production", "type": "numeric"},
                {"field": "gpp1_production", "label": "GPP1 Production", "type": "numeric"},
                {"field": "gpp2_production", "label": "GPP2 Production", "type": "numeric"},
                {"field": "total_production", "label": "Total Production", "type": "numeric"},
                {"field": "gpp_closing_stock", "label": "Closing Stock", "type": "numeric"},
                {"field": "remarks", "label": "Remarks", "type": "string"}
            ],
            "filters": [
                {"field": "location_id", "operator": "equals", "value": "user_location"},
                {"field": "date", "operator": "between", "value": "date_range"}
            ],
            "grouping": [],
            "sorting": [
                {"field": "date", "order": "desc"}
            ],
            "aggregations": {},
            "export_formats": ["csv", "xlsx", "pdf"]
        }
        
        report4 = ReportDefinition(
            location_id=None,
            name="Daily Production Summary",
            slug="daily_production_summary",
            config_json=json.dumps(report4_config),
            is_active=True,
            created_by="system",
            created_at=datetime.utcnow()
        )
        
        session.add(report4)
        session.flush()
        
        # Grant access to all operational roles
        for role in ['manager', 'supervisor', 'operator', 'admin-operations', 'admin-it']:
            access4 = ReportAccess(
                report_id=report4.id,
                role=role,
                granted_by="system",
                granted_at=datetime.utcnow()
            )
            session.add(access4)
        
        print(f"✅ Created: {report4.name}")
        
        # Commit all changes
        session.commit()
        
        print("\n" + "="*50)
        print("✅ Successfully created 4 sample reports!")
        print("="*50)
        print("\nReports created:")
        print("1. Tank Transactions Summary")
        print("2. Tanker Dispatch Report")
        print("3. YADE Voyage Summary")
        print("4. Daily Production Summary")
        print("\nAll reports are accessible to:")
        print("- admin-operations")
        print("- admin-it")
        print("- manager")
        print("- supervisor")
        print("- operator")


if __name__ == "__main__":
    create_sample_reports()