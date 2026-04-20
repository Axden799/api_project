"""
tests/test_auth.py — tests for registration, login, logout, and email verification.

Run with:  pytest
Run one class:  pytest tests/test_auth.py::TestUserModel
Run one test:   pytest tests/test_auth.py::TestUserModel::test_password_hashing
"""
from app.models import User
from app.auth.routes import generate_verification_token, verify_verification_token


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

    def test_register_redirects_to_login(self, client, db):
        response = client.post('/auth/register', data={
            'email': 'new@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
        }, follow_redirects=False)

        assert response.status_code == 302
        assert '/auth/login' in response.headers['Location']

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
