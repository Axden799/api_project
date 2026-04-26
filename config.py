import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    RATELIMIT_STORAGE_URI = 'memory://'   # use Redis URL in production
    RATELIMIT_HEADERS_ENABLED = True      # expose X-RateLimit-* headers in responses


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///dev.db')


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'  # in-memory, leaves no file
    WTF_CSRF_ENABLED = False                        # disable CSRF for form submissions in tests
    RATELIMIT_ENABLED = False                       # disable rate limits so tests run freely


class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    RATELIMIT_STORAGE_URI = os.environ.get('REDIS_URL', 'memory://')
    SESSION_COOKIE_SECURE = True       # only send session cookie over HTTPS
    REMEMBER_COOKIE_SECURE = True      # only send remember me cookie over HTTPS
    SESSION_COOKIE_SAMESITE = 'Lax'   # block cookie from being sent on cross-site requests


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
