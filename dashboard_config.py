# dashboard_config.py
"""
Dashboard Configuration Manager
Handles dashboard layout, widget configuration, and data mappings
"""

import json
from typing import Dict, List, Any, Optional
from datetime import date, datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from db import Base, get_session
import streamlit as st


class DashboardConfig(Base):
    """Store dashboard configuration"""
    __tablename__ = "dashboard_configs"
    
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    config_name = Column(String(200), nullable=False)
    config_type = Column(String(50), default="location")  # location, global, custom
    layout_config = Column(Text)  # JSON string
    is_active = Column(Boolean, default=True)
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DashboardWidget(Base):
    """Store individual widget configurations"""
    __tablename__ = "dashboard_widgets"
    
    id = Column(Integer, primary_key=True)
    config_id = Column(Integer, ForeignKey("dashboard_configs.id"), nullable=False)
    widget_type = Column(String(50), nullable=False)  # card, tank, chart, table
    widget_name = Column(String(200), nullable=False)
    position = Column(Integer, default=0)
    row_position = Column(Integer, default=0)
    col_position = Column(Integer, default=0)
    width = Column(Integer, default=1)  # column span
    data_source = Column(String(200))  # which data to display
    data_mapping = Column(Text)  # JSON for field mappings
    style_config = Column(Text)  # JSON for styling
    is_visible = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DashboardConfigManager:
    """Manage dashboard configurations"""
    
    @staticmethod
    def get_default_config() -> Dict:
        """Return default dashboard configuration"""
        return {
            "page_header": {
                "title": "{location_name} Dashboard",
                "subtitle": "Management Information System",
                "show_welcome": True,
                "show_datetime": True,
                "background_gradient_start": "#667eea",
                "background_gradient_end": "#764ba2"
            },
            "sections": [
                {
                    "id": "summary_cards",
                    "name": "Summary Statistics",
                    "type": "summary_cards",
                    "enabled": True,
                    "order": 1,
                    "date_filter": {
                        "enabled": True,
                        "type": "single",  # single or range
                        "label": "Dashboard Date"
                    }
                },
                {
                    "id": "tank_visuals",
                    "name": "Tank Stock Levels",
                    "type": "tank_visuals",
                    "enabled": True,
                    "order": 2,
                    "date_filter": {
                        "enabled": True,
                        "type": "single",
                        "label": "As of Date"
                    }
                },
                {
                    "id": "monthly_data",
                    "name": "Monthly Data",
                    "type": "monthly_data",
                    "enabled": True,
                    "order": 3,
                    "date_filter": {
                        "enabled": True,
                        "type": "single",
                        "label": "Month"
                    }
                },
                {
                    "id": "trend_chart",
                    "name": "Production & Evacuation Trend",
                    "type": "trend_chart",
                    "enabled": True,
                    "order": 4,
                    "date_filter": {
                        "enabled": True,
                        "type": "range",
                        "label": "Date Range",
                        "default_days": 30
                    }
                }
            ],
            "layout": {
                "summary_cards": {
                    "enabled": True,
                    "columns": 6,
                    "cards": [
                        {
                            "name": "Production",
                            "data_source": "material_balance",
                            "field": "Receipt",
                            "unit": "bbls",
                            "color": "#667eea",
                            "show_delta": True
                        },
                        {
                            "name": "Evacuation",
                            "data_source": "material_balance",
                            "field": "Dispatch",
                            "unit": "bbls",
                            "color": "#667eea",
                            "show_delta": False
                        },
                        {
                            "name": "FSO Receipt",
                            "data_source": "fso_operations",
                            "field": "net_receipt_dispatch",
                            "unit": "bbls",
                            "color": "#667eea",
                            "show_delta": False
                        },
                        {
                            "name": "FSO Stock",
                            "data_source": "fso_operations",
                            "field": "closing_stock",
                            "unit": "bbls",
                            "color": "#667eea",
                            "show_delta": False
                        },
                        {
                            "name": "Ullage Available",
                            "data_source": "calculated",
                            "calculation": "ullage",
                            "unit": "bbls",
                            "color": "#667eea",
                            "show_delta": False
                        },
                        {
                            "name": "Pumpable Stock",
                            "data_source": "calculated",
                            "calculation": "pumpable",
                            "unit": "bbls",
                            "color": "#667eea",
                            "show_delta": False
                        }
                    ]
                },
                "tank_visuals": {
                    "enabled": True,
                    "columns": 5,
                    "tanks": [],  # List of tank configurations with data source mappings
                    "default_data_source": "otr",  # otr, tank_transaction, material_balance
                    "default_field": "nsv_bbl",
                    "show_status_selector": False,  # Show tank status dropdown
                    "pumpable_config": {
                        "enabled": True,
                        "pumpable_statuses": ["IDLE", "READY", "DISPATCHING"],  # Statuses that are pumpable
                        "pumpable_factor": 0.85  # Multiply by 0.85 for pumpable calculation
                    },
                    "style": {
                        "height": 200,
                        "border_radius": 10,
                        "show_status": True,
                        "show_percentage": True,
                        "color_scheme": "dynamic"  # dynamic, static
                    }
                },
                "monthly_data": {
                    "enabled": True,
                    "columns": 4,
                    "cards": [
                        {
                            "name": "Production",
                            "data_source": "material_balance",
                            "field": "Receipt",
                            "aggregation": "sum",
                            "show_average": True
                        },
                        {
                            "name": "Evacuation",
                            "data_source": "material_balance",
                            "field": "Dispatch",
                            "aggregation": "sum",
                            "show_average": True
                        },
                        {
                            "name": "Export",
                            "data_source": "fso_operations",
                            "field": "net_receipt_dispatch",
                            "aggregation": "sum",
                            "show_average": True
                        },
                        {
                            "name": "Vessel Status",
                            "data_source": "manual",
                            "show_average": False
                        }
                    ]
                },
                "trend_chart": {
                    "enabled": True,
                    "chart_type": "line",
                    "series": [
                        {
                            "name": "Production",
                            "data_source": "material_balance",
                            "field": "Receipt",
                            "color": "#8B4513"
                        },
                        {
                            "name": "Evacuation",
                            "data_source": "material_balance",
                            "field": "Dispatch",
                            "color": "#006400"
                        }
                    ],
                    "show_markers": True,
                    "show_labels": True,
                    "show_totals_card": True
                }
            },
            "styles": {
                "card": {
                    "background": "#ffffff",
                    "border_radius": 10,
                    "border_color": "#667eea",
                    "border_width": 4,
                    "padding": "1rem",
                    "shadow": "0 2px 8px rgba(0,0,0,0.1)"
                },
                "value": {
                    "font_size": "1.6rem",
                    "font_weight": "bold",
                    "color": "#667eea"
                },
                "label": {
                    "font_size": "0.8rem",
                    "font_weight": "bold",
                    "color": "#666666",
                    "text_transform": "uppercase"
                }
            }
        }
    
    @staticmethod
    def save_config(location_id: int, config_name: str, config_data: Dict, user: str) -> bool:
        """Save dashboard configuration"""
        try:
            with get_session() as s:
                # Check if config exists
                existing = s.query(DashboardConfig).filter(
                    DashboardConfig.location_id == location_id,
                    DashboardConfig.config_name == config_name
                ).first()
                
                if existing:
                    existing.layout_config = json.dumps(config_data)
                    existing. updated_at = datetime.utcnow()
                else:
                    new_config = DashboardConfig(
                        location_id=location_id,
                        config_name=config_name,
                        layout_config=json.dumps(config_data),
                        created_by=user
                    )
                    s.add(new_config)
                
                s.commit()
                return True
        except Exception as e:
            st.error(f"Error saving configuration: {e}")
            return False
    
    @staticmethod
    def load_config(location_id: int, config_name: str = "default") -> Dict:
        """Load dashboard configuration"""
        try:
            with get_session() as s:
                config = s.query(DashboardConfig).filter(
                    DashboardConfig.location_id == location_id,
                    DashboardConfig.config_name == config_name,
                    DashboardConfig. is_active == True
                ). first()
                
                if config and config.layout_config:
                    return json.loads(config. layout_config)
                else:
                    return DashboardConfigManager.get_default_config()
        except Exception:
            return DashboardConfigManager.get_default_config()
    
    @staticmethod
    def get_all_configs(location_id: int) -> List[Dict]:
        """Get all configurations for a location"""
        try:
            with get_session() as s:
                configs = s. query(DashboardConfig).filter(
                    DashboardConfig.location_id == location_id
                ).all()
                
                return [
                    {
                        "id": c.id,
                        "name": c.config_name,
                        "is_active": c.is_active,
                        "created_by": c.created_by,
                        "created_at": c.created_at,
                        "updated_at": c.updated_at
                    }
                    for c in configs
                ]
        except Exception:
            return []
    
    @staticmethod
    def delete_config(config_id: int) -> bool:
        """Delete a dashboard configuration"""
        try:
            with get_session() as s:
                config = s.query(DashboardConfig).filter(
                    DashboardConfig. id == config_id
                ).first()
                
                if config:
                    s.delete(config)
                    s.commit()
                    return True
                return False
        except Exception:
            return False