from __future__ import annotations

import logging
import threading

from flask import Flask
from flask_cors import CORS

from .adapters.inbound.http import register_blueprints
from .adapters.inbound.http.errors import register_error_handlers
from .config.container import Container
from .config.settings import Settings, get_settings

logging.basicConfig(level=logging.INFO)


def create_app(settings: Settings | None = None) -> Flask:
    """Application factory: builds the container and wires HTTP adapters.

    Bootstrap (schema creation + seeding) runs on the first request rather than
    here, because it opens the single-writer DuckDB cube. Under the Flask dev
    reloader the parent process imports this module to resolve ``app`` but never
    serves a request, so deferring keeps it from taking the cube's file lock and
    locking out the child that actually serves traffic.
    """
    settings = settings or get_settings()
    container = Container(settings)

    app = Flask(__name__)
    app.extensions["container"] = container

    CORS(app, origins=settings.cors_origin_list, supports_credentials=True)

    register_blueprints(app)
    register_error_handlers(app)

    bootstrap_lock = threading.Lock()
    bootstrapped = False

    @app.before_request
    def _bootstrap_once() -> None:
        nonlocal bootstrapped
        if bootstrapped:
            return
        with bootstrap_lock:
            if not bootstrapped:
                container.bootstrap()
                bootstrapped = True

    return app


# Expose a module-level app for `flask --app tomin.main run`.
app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
