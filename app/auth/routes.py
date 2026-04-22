from datetime import datetime, timezone
from urllib.parse import urlparse
from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from ..extensions import db
from ..models import User
from . import auth_bp
from .forms import (
    RegisterForm, LoginForm,
    ChangeEmailForm, ChangePasswordForm,
    ForgotPasswordForm, ResetPasswordForm,
)

RESEND_COOLDOWN_SECONDS = 60


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


# --- Email verification ---

def generate_verification_token(user_id):
    """
    Signs the user's ID with the app secret key using itsdangerous.
    Salt 'email-verify' scopes this token so it cannot be used on any
    other route that also uses _serializer() with a different salt.
    No database row is created — the signature itself is the proof.
    Expires after 24 hours (enforced on decode via max_age).
    """
    return _serializer().dumps(user_id, salt='email-verify')


def verify_verification_token(token, max_age=86400):
    """
    Decodes and verifies the token. Returns user_id if the signature is
    valid and the token is not older than max_age seconds, else None.
    """
    try:
        user_id = _serializer().loads(token, salt='email-verify', max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None
    return user_id


# --- Email change ---

def generate_email_change_token(user_id, new_email):
    """
    Signs a dict containing the user's ID and their requested new email.
    Embedding the new email in the token means we never need to store it
    in the database or rely on the session surviving across devices.
    Salt 'email-change' prevents this token from being accepted on any
    other route. Expires after 24 hours.
    """
    return _serializer().dumps({'user_id': user_id, 'new_email': new_email}, salt='email-change')


def verify_email_change_token(token, max_age=86400):
    """
    Decodes the token. Returns (user_id, new_email) if valid, else (None, None).
    """
    try:
        data = _serializer().loads(token, salt='email-change', max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None, None
    return data.get('user_id'), data.get('new_email')


# --- Password reset ---

def generate_reset_token(user):
    """
    Signs a dict containing the user's ID and a fingerprint of their current
    password hash (the last 8 characters of the bcrypt hash string).

    Why embed part of the password hash?
    bcrypt produces a completely different hash every time, even for the same
    password. So if the user resets their password — or an attacker somehow
    changes it — the fingerprint in the token no longer matches the new hash.
    The verify function checks this and rejects the token, making each reset
    link single-use by design.

    Salt 'password-reset' scopes this token. Expires after 1 hour (shorter
    than email tokens — a reset link in an inbox is higher risk).
    """
    data = {'id': user.id, 'chk': user.password_hash[-8:]}
    return _serializer().dumps(data, salt='password-reset')


def verify_reset_token(token, max_age=3600):
    """
    Decodes the token, looks up the user, and checks that the password
    fingerprint still matches the current hash.
    Returns the User object if everything is valid, else None.
    """
    try:
        data = _serializer().loads(token, salt='password-reset', max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None
    user = db.session.get(User, data.get('id'))
    if user is None:
        return None
    # Token is dead if the password has been changed since it was issued
    if user.password_hash[-8:] != data.get('chk'):
        return None
    return user


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

        session['verify_user_id'] = user.id
        return redirect(url_for('auth.verify_pending'))

    return render_template('auth/register.html', form=form)


@auth_bp.route('/verify-pending')
def verify_pending():
    """
    Shown immediately after registration.
    Also reachable by a logged-in user who hasn't verified yet.
    """
    if current_user.is_authenticated:
        if current_user.email_verified:
            return redirect(url_for('dashboard.index'))
        user = current_user
    else:
        user_id = session.get('verify_user_id')
        if not user_id:
            return redirect(url_for('auth.login'))
        user = db.session.get(User, user_id)
        if not user:
            return redirect(url_for('auth.login'))
        if user.email_verified:
            return redirect(url_for('auth.login'))

    # Calculate seconds remaining on cooldown so the template can show it
    cooldown_remaining = 0
    resend_at = session.get('verify_resend_at')
    if resend_at:
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(resend_at)).total_seconds()
        cooldown_remaining = max(0, int(RESEND_COOLDOWN_SECONDS - elapsed))

    return render_template(
        'auth/verify_pending.html',
        email=user.email,
        cooldown_remaining=cooldown_remaining,
    )


@auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    """
    Generates a fresh verification token and prints it to the terminal.
    Works whether or not the user is logged in.
    Enforces a 60-second cooldown via the session.
    """
    if current_user.is_authenticated:
        user = current_user
    else:
        user_id = session.get('verify_user_id')
        if not user_id:
            flash('Session expired. Please log in.', 'error')
            return redirect(url_for('auth.login'))
        user = db.session.get(User, user_id)
        if not user:
            flash('Account not found.', 'error')
            return redirect(url_for('auth.login'))

    if user.email_verified:
        flash('Your email is already verified.', 'info')
        return redirect(url_for('dashboard.index'))

    # Enforce cooldown
    resend_at = session.get('verify_resend_at')
    if resend_at:
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(resend_at)).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            remaining = int(RESEND_COOLDOWN_SECONDS - elapsed)
            flash(f'Please wait {remaining} seconds before requesting another link.', 'info')
            return redirect(url_for('auth.verify_pending'))

    token = generate_verification_token(user.id)
    verify_url = url_for('auth.verify_email', token=token, _external=True)

    print(f'\n{"="*60}')
    print(f'VERIFICATION LINK for {user.email}:')
    print(f'{verify_url}')
    print(f'{"="*60}\n')
    current_app.logger.info(f'Verification URL: {verify_url}')

    session['verify_resend_at'] = datetime.now(timezone.utc).isoformat()
    flash('A new verification link has been sent. Check the terminal.', 'success')

    next_page = url_for('auth.verify_pending') if not current_user.is_authenticated else url_for('dashboard.index')
    return redirect(next_page)


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

        # Consume a pending org invite if the user arrived via an invite link.
        from ..orgs.utils import process_pending_invite
        process_pending_invite(user)

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


@auth_bp.route('/settings')
@login_required
def settings():
    return render_template('auth/settings.html')


# ---------------------------------------------------------------------------
# Change email
# ---------------------------------------------------------------------------

@auth_bp.route('/change-email', methods=['GET', 'POST'])
@login_required
def change_email():
    form = ChangeEmailForm()

    if form.validate_on_submit():
        if not current_user.check_password(form.password.data):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('auth.change_email'))

        new_email = form.new_email.data.lower()

        # Generate a token that carries both the user ID and the new address.
        # We do NOT write the new email to the database yet — the user must
        # click the confirmation link first. This prevents typos from locking
        # them out and stops an attacker with brief session access from silently
        # hijacking the account.
        token = generate_email_change_token(current_user.id, new_email)
        confirm_url = url_for('auth.confirm_email_change', token=token, _external=True)

        print(f'\n{"="*60}')
        print(f'EMAIL CHANGE CONFIRMATION LINK for {current_user.email} → {new_email}:')
        print(f'{confirm_url}')
        print(f'{"="*60}\n')
        current_app.logger.info(f'Email change URL: {confirm_url}')

        flash(
            f'A confirmation link has been sent to {new_email}. '
            'Click it to complete the change. The link expires in 24 hours.',
            'info',
        )
        return redirect(url_for('auth.settings'))

    return render_template('auth/change_email.html', form=form)


@auth_bp.route('/confirm-email-change/<token>')
@login_required
def confirm_email_change(token):
    """
    The user clicks this link from their new inbox.
    We decode the token (which carries both user_id and new_email),
    verify the user matches, write the new email, and re-verify the account.
    """
    user_id, new_email = verify_email_change_token(token)

    if user_id is None or new_email is None:
        flash('The confirmation link is invalid or has expired.', 'error')
        return redirect(url_for('auth.settings'))

    if user_id != current_user.id:
        flash('This confirmation link does not belong to your account.', 'error')
        return redirect(url_for('auth.settings'))

    # Final duplicate check at commit time — another account may have taken
    # this address in the time between request and confirmation.
    if User.query.filter_by(email=new_email).first():
        flash('That email address is already in use.', 'error')
        return redirect(url_for('auth.settings'))

    current_user.email = new_email
    current_user.email_verified = True
    db.session.commit()

    flash('Email address updated successfully.', 'success')
    return redirect(url_for('auth.settings'))


# ---------------------------------------------------------------------------
# Change password (logged in)
# ---------------------------------------------------------------------------

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()

    if form.validate_on_submit():
        # Require the current password before accepting a new one.
        # Without this, anyone who finds an unlocked browser can permanently
        # take over the account by setting a new password.
        if not current_user.check_password(form.current_password.data):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('auth.change_password'))

        current_user.set_password(form.new_password.data)
        db.session.commit()

        flash('Password changed successfully.', 'success')
        return redirect(url_for('auth.settings'))

    return render_template('auth/change_password.html', form=form)


# ---------------------------------------------------------------------------
# Forgot password (logged out)
# ---------------------------------------------------------------------------

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = ForgotPasswordForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()

        # Always show the same message whether or not the email exists.
        # Showing "email not found" lets attackers enumerate which addresses
        # have accounts in the system.
        if user and user.is_active:
            token = generate_reset_token(user)
            reset_url = url_for('auth.reset_password', token=token, _external=True)

            print(f'\n{"="*60}')
            print(f'PASSWORD RESET LINK for {user.email}:')
            print(f'{reset_url}')
            print(f'{"="*60}\n')
            current_app.logger.info(f'Password reset URL: {reset_url}')

        flash(
            'If an account with that email exists, a reset link has been sent. '
            'Check your email.',
            'info',
        )
        return redirect(url_for('auth.forgot_password'))

    return render_template('auth/forgot_password.html', form=form)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    # Decode the token and retrieve the user in one step.
    # verify_reset_token also checks that the password fingerprint still
    # matches — if the password was already changed, this returns None.
    user = verify_reset_token(token)

    if user is None:
        flash('The reset link is invalid or has expired.', 'error')
        return redirect(url_for('auth.forgot_password'))

    form = ResetPasswordForm()

    if form.validate_on_submit():
        user.set_password(form.new_password.data)
        db.session.commit()

        # Log the user in immediately — no need to make them sign in again
        # after just proving ownership via the token.
        login_user(user)
        flash('Password reset successfully. You are now logged in.', 'success')
        return redirect(url_for('dashboard.index'))

    return render_template('auth/reset_password.html', form=form)


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
