from flask import Blueprint

orgs_bp = Blueprint('orgs', __name__)

from . import routes  # noqa: F401, E402
