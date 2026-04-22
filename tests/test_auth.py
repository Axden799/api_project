"""
tests/test_auth.py — tests for registration, login, logout, and email verification.

Run with:  pytest
Run one class:  pytest tests/test_auth.py::TestUserModel
Run one test:   pytest tests/test_auth.py::TestUserModel::test_password_hashing
"""
from datetime import datetime, timezone, timedelta
from app.models import User
from app.auth.routes import (
    generate_verification_token, verify_verification_token,
    generate_email_change_token, verify_email_change_token,
    generate_reset_token, verify_reset_token,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_user(db, email='user@example.com', password='password123', verified=False):
    """Insert a User row and return it. Reused across multiple tests."""
    user = User(email=email, email_verified=verified)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

class TestUserModel:

    def test_password_is_hashed(self, db):
        user = create_user(db)
        assert user.password_hash != 'password123'

    def test_correct_password_accepted(self, db):
        user = create_user(db)
        assert user.check_password('password123') is True

    def test_wrong_password_rejected(self, db):
        user = create_user(db)
        assert user.check_password('wrongpassword') is False

    def test_new_user_is_active(self, db):
        user = create_user(db)
        assert user.is_active is True

    def test_new_user_email_not_verified(self, db):
        user = create_user(db)
        assert user.email_verified is False


# ---------------------------------------------------------------------------
# Verification token
# ---------------------------------------------------------------------------

class TestVerificationToken:

    def test_token_encodes_user_id(self, app):
        with app.app_context():
            token = generate_verification_token(42)
            assert verify_verification_token(token) == 42

    def test_tampered_token_returns_none(self, app):
        with app.app_context():
            token = generate_verification_token(1)
            bad_token = token[:-4] + 'xxxx'
            assert verify_verification_token(bad_token) is None

    def test_garbage_string_returns_none(self, app):
        with app.app_context():
            assert verify_verification_token('notavalidtoken') is None


# ---------------------------------------------------------------------------
# Register route
# ---------------------------------------------------------------------------

class TestRegisterRoute:

    def test_register_page_loads(self, client):
        response = client.get('/auth/register')
        assert response.status_code == 200
        assert b'Create Account' in response.data

    def test_register_creates_user(self, client, db):
        response = client.post('/auth/register', data={
            'email': 'new@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
        }, follow_redirects=True)

        assert response.status_code == 200
        user = User.query.filter_by(email='new@example.com').first()
        assert user is not None

    def test_register_redirects_to_verify_pending(self, client, db):
        response = client.post('/auth/register', data={
            'email': 'new@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/auth/verify-pending' in response.headers['Location']

    def test_duplicate_email_rejected(self, client, db):
        create_user(db, email='taken@example.com')

        response = client.post('/auth/register', data={
            'email': 'taken@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'already exists' in response.data

    def test_password_mismatch_rejected(self, client):
        response = client.post('/auth/register', data={
            'email': 'new@example.com',
            'password': 'password123',
            'confirm_password': 'different456',
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'must match' in response.data

    def test_short_password_rejected(self, client):
        response = client.post('/auth/register', data={
            'email': 'new@example.com',
            'password': 'short',
            'confirm_password': 'short',
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'at least 8 characters' in response.data

    def test_email_stored_as_lowercase(self, client, db):
        client.post('/auth/register', data={
            'email': 'UPPER@EXAMPLE.COM',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        user = User.query.filter_by(email='upper@example.com').first()
        assert user is not None


# ---------------------------------------------------------------------------
# Login route
# ---------------------------------------------------------------------------

class TestLoginRoute:

    def test_login_page_loads(self, client):
        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'Sign In' in response.data

    def test_valid_credentials_redirect_to_dashboard(self, client, db):
        create_user(db)
        response = client.post('/auth/login', data={
            'email': 'user@example.com',
            'password': 'password123',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/dashboard' in response.headers['Location']

    def test_wrong_password_rejected(self, client, db):
        create_user(db)
        response = client.post('/auth/login', data={
            'email': 'user@example.com',
            'password': 'wrongpassword',
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Invalid email or password' in response.data

    def test_nonexistent_email_rejected(self, client):
        response = client.post('/auth/login', data={
            'email': 'nobody@example.com',
            'password': 'password123',
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'Invalid email or password' in response.data

    def test_inactive_user_cannot_login(self, client, db):
        user = create_user(db)
        user.is_active = False
        db.session.commit()

        response = client.post('/auth/login', data={
            'email': 'user@example.com',
            'password': 'password123',
        }, follow_redirects=True)

        assert response.status_code == 200
        assert b'deactivated' in response.data


# ---------------------------------------------------------------------------
# Email verification route
# ---------------------------------------------------------------------------

class TestVerifyEmailRoute:

    def test_valid_token_verifies_email(self, client, db, app):
        user = create_user(db)
        with app.app_context():
            token = generate_verification_token(user.id)

        response = client.get(f'/auth/verify/{token}', follow_redirects=True)

        assert response.status_code == 200
        assert b'verified' in response.data
        assert db.session.get(User, user.id).email_verified is True

    def test_invalid_token_rejected(self, client):
        response = client.get('/auth/verify/badtoken', follow_redirects=True)
        assert response.status_code == 200
        assert b'invalid or has expired' in response.data

    def test_already_verified_user_handled(self, client, db, app):
        user = create_user(db, verified=True)
        with app.app_context():
            token = generate_verification_token(user.id)

        response = client.get(f'/auth/verify/{token}', follow_redirects=True)
        assert response.status_code == 200
        assert b'already verified' in response.data


# ---------------------------------------------------------------------------
# Logout route
# ---------------------------------------------------------------------------

class TestLogoutRoute:

    def test_logout_requires_login(self, client):
        response = client.post('/auth/logout', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.headers['Location']

    def test_logout_redirects_to_login(self, client, db):
        create_user(db)
        client.post('/auth/login', data={
            'email': 'user@example.com',
            'password': 'password123',
        })
        response = client.post('/auth/logout', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.headers['Location']


# ---------------------------------------------------------------------------
# Verify pending page
# ---------------------------------------------------------------------------

class TestVerifyPendingRoute:

    def test_register_redirects_to_verify_pending(self, client):
        response = client.post('/auth/register', data={
            'email': 'new@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
        }, follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/verify-pending' in response.headers['Location']

    def test_verify_pending_page_loads_after_register(self, client):
        client.post('/auth/register', data={
            'email': 'new@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        response = client.get('/auth/verify-pending')
        assert response.status_code == 200
        assert b'Check your email' in response.data
        assert b'new@example.com' in response.data

    def test_verify_pending_without_session_redirects_to_login(self, client):
        response = client.get('/auth/verify-pending', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.headers['Location']

    def test_verified_user_redirected_from_verify_pending(self, client, db):
        create_user(db, verified=True)
        client.post('/auth/login', data={
            'email': 'user@example.com',
            'password': 'password123',
        })
        response = client.get('/auth/verify-pending', follow_redirects=False)
        assert response.status_code == 302
        assert '/dashboard' in response.headers['Location']


# ---------------------------------------------------------------------------
# Resend verification
# ---------------------------------------------------------------------------

class TestResendVerificationRoute:

    def test_resend_without_session_redirects_to_login(self, client):
        response = client.post('/auth/resend-verification', follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.headers['Location']

    def test_resend_sends_new_link(self, client):
        client.post('/auth/register', data={
            'email': 'new@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        response = client.post('/auth/resend-verification', follow_redirects=True)
        assert response.status_code == 200
        assert b'new verification link' in response.data

    def test_resend_cooldown_blocks_immediate_retry(self, client):
        client.post('/auth/register', data={
            'email': 'new@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        client.post('/auth/resend-verification')
        response = client.post('/auth/resend-verification', follow_redirects=True)
        assert b'Please wait' in response.data

    def test_resend_for_already_verified_user(self, client, db):
        create_user(db, verified=True)
        client.post('/auth/login', data={
            'email': 'user@example.com',
            'password': 'password123',
        })
        response = client.post('/auth/resend-verification', follow_redirects=True)
        assert b'already verified' in response.data

    def test_resend_works_when_logged_in(self, client, db):
        create_user(db, verified=False)
        client.post('/auth/login', data={
            'email': 'user@example.com',
            'password': 'password123',
        })
        response = client.post('/auth/resend-verification', follow_redirects=True)
        assert response.status_code == 200
        assert b'new verification link' in response.data


# ---------------------------------------------------------------------------
# Change email
# ---------------------------------------------------------------------------

class TestChangeEmailRoute:

    def test_change_email_requires_login(self, client):
        r = client.get('/auth/change-email', follow_redirects=False)
        assert r.status_code == 302
        assert '/auth/login' in r.headers['Location']

    def test_wrong_password_rejected(self, client, db):
        create_user(db, verified=True)
        client.post('/auth/login', data={'email': 'user@example.com', 'password': 'password123'})
        r = client.post('/auth/change-email', data={
            'new_email': 'new@example.com',
            'password': 'wrongpassword',
        }, follow_redirects=True)
        assert b'incorrect' in r.data.lower()

    def test_duplicate_email_rejected(self, client, db):
        create_user(db, email='user@example.com', verified=True)
        create_user(db, email='taken@example.com')
        client.post('/auth/login', data={'email': 'user@example.com', 'password': 'password123'})
        r = client.post('/auth/change-email', data={
            'new_email': 'taken@example.com',
            'password': 'password123',
        }, follow_redirects=True)
        assert b'already exists' in r.data.lower()

    def test_valid_request_generates_token(self, client, db, app):
        create_user(db, verified=True)
        client.post('/auth/login', data={'email': 'user@example.com', 'password': 'password123'})
        r = client.post('/auth/change-email', data={
            'new_email': 'new@example.com',
            'password': 'password123',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'confirmation link' in r.data.lower()

    def test_email_change_token_encodes_new_email(self, app):
        with app.app_context():
            token = generate_email_change_token(1, 'new@example.com')
            user_id, new_email = verify_email_change_token(token)
            assert user_id == 1
            assert new_email == 'new@example.com'

    def test_tampered_email_change_token_rejected(self, app):
        with app.app_context():
            token = generate_email_change_token(1, 'new@example.com')
            bad = token[:-4] + 'xxxx'
            user_id, new_email = verify_email_change_token(bad)
            assert user_id is None
            assert new_email is None

    def test_confirm_link_updates_email(self, client, db, app):
        create_user(db, verified=True)
        client.post('/auth/login', data={'email': 'user@example.com', 'password': 'password123'})
        with app.app_context():
            user = User.query.filter_by(email='user@example.com').first()
            token = generate_email_change_token(user.id, 'new@example.com')
        r = client.get(f'/auth/confirm-email-change/{token}', follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            u = User.query.filter_by(email='new@example.com').first()
            assert u is not None
            assert u.email_verified is True

    def test_confirm_link_invalid_token_rejected(self, client, db):
        create_user(db, verified=True)
        client.post('/auth/login', data={'email': 'user@example.com', 'password': 'password123'})
        r = client.get('/auth/confirm-email-change/badtoken', follow_redirects=True)
        assert b'invalid or has expired' in r.data.lower()


# ---------------------------------------------------------------------------
# Change password (logged in)
# ---------------------------------------------------------------------------

class TestChangePasswordRoute:

    def test_change_password_requires_login(self, client):
        r = client.get('/auth/change-password', follow_redirects=False)
        assert r.status_code == 302
        assert '/auth/login' in r.headers['Location']

    def test_wrong_current_password_rejected(self, client, db):
        create_user(db)
        client.post('/auth/login', data={'email': 'user@example.com', 'password': 'password123'})
        r = client.post('/auth/change-password', data={
            'current_password': 'wrongpassword',
            'new_password': 'newpassword123',
            'confirm_new_password': 'newpassword123',
        }, follow_redirects=True)
        assert b'incorrect' in r.data.lower()

    def test_password_mismatch_rejected(self, client, db):
        create_user(db)
        client.post('/auth/login', data={'email': 'user@example.com', 'password': 'password123'})
        r = client.post('/auth/change-password', data={
            'current_password': 'password123',
            'new_password': 'newpassword123',
            'confirm_new_password': 'different456',
        }, follow_redirects=True)
        assert b'must match' in r.data.lower()

    def test_valid_change_updates_password(self, client, db):
        create_user(db)
        client.post('/auth/login', data={'email': 'user@example.com', 'password': 'password123'})
        r = client.post('/auth/change-password', data={
            'current_password': 'password123',
            'new_password': 'newpassword123',
            'confirm_new_password': 'newpassword123',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'Password changed' in r.data
        with db.session.begin_nested():
            u = User.query.filter_by(email='user@example.com').first()
            assert u.check_password('newpassword123')
            assert not u.check_password('password123')

    def test_old_password_no_longer_works_after_change(self, client, db):
        create_user(db)
        client.post('/auth/login', data={'email': 'user@example.com', 'password': 'password123'})
        client.post('/auth/change-password', data={
            'current_password': 'password123',
            'new_password': 'newpassword123',
            'confirm_new_password': 'newpassword123',
        })
        client.post('/auth/logout')
        r = client.post('/auth/login', data={
            'email': 'user@example.com',
            'password': 'password123',
        }, follow_redirects=True)
        assert b'Invalid email or password' in r.data


# ---------------------------------------------------------------------------
# Forgot / reset password
# ---------------------------------------------------------------------------

class TestForgotPasswordRoute:

    def test_page_loads(self, client):
        r = client.get('/auth/forgot-password')
        assert r.status_code == 200
        assert b'Reset' in r.data

    def test_unknown_email_shows_generic_message(self, client):
        r = client.post('/auth/forgot-password', data={
            'email': 'nobody@example.com',
        }, follow_redirects=True)
        assert b'if an account' in r.data.lower()

    def test_known_email_shows_same_generic_message(self, client, db):
        create_user(db)
        r = client.post('/auth/forgot-password', data={
            'email': 'user@example.com',
        }, follow_redirects=True)
        assert b'if an account' in r.data.lower()

    def test_forgot_password_link_on_login_page(self, client):
        r = client.get('/auth/login')
        assert b'Forgot your password' in r.data


class TestResetPasswordRoute:

    def test_invalid_token_rejected(self, client):
        r = client.get('/auth/reset-password/badtoken', follow_redirects=True)
        assert b'invalid or has expired' in r.data.lower()

    def test_valid_token_shows_form(self, client, db, app):
        user = create_user(db)
        with app.app_context():
            u = User.query.filter_by(email='user@example.com').first()
            token = generate_reset_token(u)
        r = client.get(f'/auth/reset-password/{token}')
        assert r.status_code == 200
        assert b'New Password' in r.data

    def test_reset_updates_password_and_logs_in(self, client, db, app):
        create_user(db)
        with app.app_context():
            u = User.query.filter_by(email='user@example.com').first()
            token = generate_reset_token(u)
        r = client.post(f'/auth/reset-password/{token}', data={
            'new_password': 'resetpassword123',
            'confirm_new_password': 'resetpassword123',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert b'Password reset successfully' in r.data

    def test_token_invalid_after_password_change(self, client, db, app):
        create_user(db)
        with app.app_context():
            u = User.query.filter_by(email='user@example.com').first()
            token = generate_reset_token(u)
        # Use the token once — this logs the user in on success
        client.post(f'/auth/reset-password/{token}', data={
            'new_password': 'resetpassword123',
            'confirm_new_password': 'resetpassword123',
        })
        # Log out so the route doesn't short-circuit to dashboard
        client.post('/auth/logout')
        # Try to use the token again — password hash has changed so token is dead
        r = client.get(f'/auth/reset-password/{token}', follow_redirects=True)
        assert b'invalid or has expired' in r.data.lower()

    def test_reset_token_fingerprint_helpers(self, app, db):
        with app.app_context():
            user = User(email='t@x.com')
            user.set_password('original')
            db.session.add(user)
            db.session.commit()
            token = generate_reset_token(user)
            assert verify_reset_token(token) is not None
            user.set_password('changed')
            db.session.commit()
            assert verify_reset_token(token) is None
