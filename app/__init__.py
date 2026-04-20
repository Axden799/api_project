import os
from flask import Flask
from config import config
from .extensions import db, login_manager, migrate


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Bind extensions to this app instance
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # Flask-Login — where to send unauthenticated users
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    with app.app_context():
        from . import models  # noqa: F401 — registers tables with SQLAlchemy

    # Register blueprints
    from .auth import auth_bp
    from .dashboard import dashboard_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp)

    return app
