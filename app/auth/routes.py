from urllib.parse import urlparse
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from ..extensions import db
from ..models import User
from . import auth_bp
from .forms import RegisterForm, LoginForm


# ---------------------------------------------------------------------------
# Token helpers for email verification
# ---------------------------------------------------------------------------

def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def generate_verification_token(user_id):
    """Sign the user's ID with the app secret. No database storage needed."""
    return _serializer().dumps(user_id, salt='email-verify')


def verify_verification_token(token, max_age=86400):
    """
    Decode and verify the token. Returns the user_id if valid, None otherwise.
    max_age is in seconds — 86400 = 24 hours.
    """
    try:
        user_id = _serializer().loads(token, salt='email-verify', max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None
    return user_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = RegisterForm()

    if form.validate_on_submit():
        user = User(email=form.email.data.lower())
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        token = generate_verification_token(user.id)
        verify_url = url_for('auth.verify_email', token=token, _external=True)

        # Stub: print to terminal until SendGrid is configured
        print(f'\n{"="*60}')
        print(f'VERIFICATION LINK for {user.email}:')
        print(f'{verify_url}')
        print(f'{"="*60}\n')
        current_app.logger.info(f'Verification URL: {verify_url}')

        flash('Account created. Check the terminal for your verification link.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()

        if user is None or not user.check_password(form.password.data):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('auth.login'))

        if not user.is_active:
            flash('This account has been deactivated.', 'error')
            return redirect(url_for('auth.login'))

        login_user(user, remember=form.remember_me.data)

        # Redirect to the page they were originally trying to reach, if any.
        # urlparse check prevents open-redirect attacks — only allow relative URLs.
        next_page = request.args.get('next')
        if next_page and urlparse(next_page).netloc != '':
            next_page = None

        return redirect(next_page or url_for('dashboard.index'))

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/verify/<token>')
def verify_email(token):
    user_id = verify_verification_token(token)

    if user_id is None:
        flash('The verification link is invalid or has expired.', 'error')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, user_id)

    if user is None:
        flash('Account not found.', 'error')
        return redirect(url_for('auth.login'))

    if user.email_verified:
        flash('Email already verified. Please log in.', 'info')
        return redirect(url_for('auth.login'))

    user.email_verified = True
    db.session.commit()

    flash('Email verified successfully. You can now log in.', 'success')
    return redirect(url_for('auth.login'))
