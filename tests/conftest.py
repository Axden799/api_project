"""
conftest.py — pytest fixtures shared across all test files.

pytest discovers this file automatically. Fixtures defined here are
available in every test file in the tests/ directory without importing them.
"""
import pytest
from app import create_app
from app.extensions import db as _db


@pytest.fixture
def app():
    """
    Creates the Flask app in testing mode.
    Uses an in-memory SQLite database — created fresh, destroyed after each test.
    """
    app = create_app('testing')

    with app.app_context():
        _db.create_all()   # create all tables before the test runs
        yield app          # test runs here
        _db.session.remove()
        _db.drop_all()     # wipe everything after the test finishes


@pytest.fixture
def client(app):
    """
    A test client that can send GET/POST requests to the app
    without needing a running server.
    """
    return app.test_client()


@pytest.fixture
def db(app):
    """
    Gives a test direct access to the database session —
    useful for inserting records and making assertions on the database.
    """
    return _db
