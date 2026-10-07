from __future__ import annotations

from flask import Flask

from .admin import admin_bp
from .analytics import analytics_bp
from .categories import categories_bp
from .dashboards import dashboards_bp
from .forecast import forecast_bp
from .goals import goals_bp
from .health import health_bp
from .ingest import ingest_bp
from .metrics import metrics_bp
from .prices import prices_bp
from .receipts import receipts_bp
from .statements import statements_bp
from .tags import tags_bp
from .telemetry import telemetry_bp
from .transactions import transactions_bp
from .workstations import workstations_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(health_bp)
    app.register_blueprint(statements_bp)
    app.register_blueprint(ingest_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(receipts_bp)
    app.register_blueprint(prices_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(dashboards_bp)
    app.register_blueprint(workstations_bp)
    app.register_blueprint(forecast_bp)
    app.register_blueprint(goals_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(telemetry_bp)
