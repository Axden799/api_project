import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from config import config
from .extensions import db, login_manager, migrate, csrf, limiter


def _configure_logging(app):
    """
    Set up a rotating file logger for the application.

    Files are written to logs/app.log. A new file is started once the
    current one reaches 1 MB; up to 10 rotated files are kept before the
    oldest is deleted. The total footprint is therefore capped at ~11 MB.

    Only active outside debug/testing mode — in dev, Flask's own debug
    output is sufficient; in tests, logs would clutter pytest output.
    """
    os.makedirs('logs', exist_ok=True)

    handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=1_000_000,   # rotate after 1 MB
        backupCount=10,       # keep app.log.1 … app.log.10
    )
    handler.setLevel(logging.WARNING)

    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s %(name)s: %(message)s  '
        '[%(filename)s:%(lineno)d]'
    )
    handler.setFormatter(formatter)

    app.logger.addHandler(handler)
    app.logger.setLevel(logging.WARNING)


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Bind extensions to this app instance
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    # Flask-Login — where to send unauthenticated users
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    if not app.debug and not app.testing:
        _configure_logging(app)

    with app.app_context():
        from . import models  # noqa: F401 — registers tables with SQLAlchemy

    # Register blueprints
    from .auth import auth_bp
    from .dashboard import dashboard_bp
    from .orgs import orgs_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(orgs_bp)

    return app
