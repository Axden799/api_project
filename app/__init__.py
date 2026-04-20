import os
from flask import Flask
from config import config
from .extensions import db, login_manager, migrate


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    with app.app_context():
        from . import models  # noqa: F401 — registers tables with SQLAlchemy

    return app
