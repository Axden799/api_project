import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from config import config
from .extensions import db, login_manager, migrate, csrf, limiter


def _configure_logging(app):
    """
    Set up a rotating file logger for the application.

    Always active — development, testing, and production all write logs.

    Test runs write to logs/test.log so they stay separate from development
    and production logs. Development and production both write to logs/app.log.

    Each file rotates at 1 MB and keeps up to 10 backups (~11 MB cap per file).
    """
    os.makedirs('logs', exist_ok=True)

    log_file = 'logs/test.log' if app.testing else 'logs/app.log'

    handler = RotatingFileHandler(
        log_file,
        maxBytes=1_000_000,   # rotate after 1 MB
        backupCount=10,       # keep up to 10 rotated files
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
