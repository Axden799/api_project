from flask import render_template
from flask_login import login_required, current_user
from . import dashboard_bp


@dashboard_bp.route('/dashboard')
@login_required
def index():
    memberships = current_user.memberships
    return render_template('dashboard/index.html', memberships=memberships)
