from datetime import datetime, timedelta
import secrets
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db, login_manager


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLAN_SEAT_LIMITS = {
    'free': 3,
    'basic': 10,
    'pro': 50,
    'enterprise': None,  # None = unlimited
}

ROLES = ('owner', 'admin', 'member')
PLANS = tuple(PLAN_SEAT_LIMITS.keys())


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # A user can belong to many orgs — accessed via memberships
    memberships = db.relationship(
        'Membership',
        back_populates='user',
        foreign_keys='Membership.user_id',
        lazy='select',
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

class Organization(db.Model):
    __tablename__ = 'organizations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    stripe_customer_id = db.Column(db.String(120), unique=True, nullable=True)
    stripe_subscription_id = db.Column(db.String(120), unique=True, nullable=True)
    plan = db.Column(db.String(20), nullable=False, default='free')
    max_seats = db.Column(db.Integer, nullable=True, default=3)
    status = db.Column(db.String(20), nullable=False, default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    memberships = db.relationship(
        'Membership',
        back_populates='organization',
        cascade='all, delete-orphan',
        lazy='select',
    )
    invitations = db.relationship(
        'Invitation',
        back_populates='organization',
        cascade='all, delete-orphan',
        lazy='select',
    )

    @property
    def seat_count(self):
        """Number of active members currently in this org."""
        return len(self.memberships)

    @property
    def is_at_seat_limit(self):
        """True if the org cannot accept any more members."""
        if self.max_seats is None:
            return False  # enterprise / unlimited
        return self.seat_count >= self.max_seats

    def set_plan(self, plan_name):
        """Update plan and sync max_seats from the constants table."""
        if plan_name not in PLAN_SEAT_LIMITS:
            raise ValueError(f'Unknown plan: {plan_name}')
        self.plan = plan_name
        self.max_seats = PLAN_SEAT_LIMITS[plan_name]

    def __repr__(self):
        return f'<Organization {self.name}>'


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

class Membership(db.Model):
    __tablename__ = 'memberships'
    __table_args__ = (
        # A user can only have one membership per org
        db.UniqueConstraint('user_id', 'organization_id', name='uq_user_org'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='member')
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Nullable — first owner of an org was not invited by anyone
    invited_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Two FK columns both point at users — foreign_keys disambiguates them
    user = db.relationship(
        'User',
        back_populates='memberships',
        foreign_keys=[user_id],
    )
    organization = db.relationship(
        'Organization',
        back_populates='memberships',
    )
    invited_by = db.relationship(
        'User',
        foreign_keys=[invited_by_user_id],
    )

    def __repr__(self):
        return f'<Membership user={self.user_id} org={self.organization_id} role={self.role}>'


# ---------------------------------------------------------------------------
# Invitation
# ---------------------------------------------------------------------------

class Invitation(db.Model):
    __tablename__ = 'invitations'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='member')
    token = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    accepted_at = db.Column(db.DateTime, nullable=True)
    invited_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    organization = db.relationship('Organization', back_populates='invitations')
    invited_by = db.relationship('User', foreign_keys=[invited_by_user_id])

    @staticmethod
    def generate_token():
        """Cryptographically random URL-safe token."""
        return secrets.token_urlsafe(32)

    @property
    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    @property
    def is_pending(self):
        """True if the invite has not been accepted and has not expired."""
        return self.accepted_at is None and not self.is_expired

    @classmethod
    def create(cls, organization_id, email, role, invited_by_user_id, hours_valid=48):
        """Factory method — builds a ready-to-save Invitation."""
        return cls(
            organization_id=organization_id,
            email=email,
            role=role,
            invited_by_user_id=invited_by_user_id,
            token=cls.generate_token(),
            expires_at=datetime.utcnow() + timedelta(hours=hours_valid),
        )

    def __repr__(self):
        return f'<Invitation {self.email} org={self.organization_id} pending={self.is_pending}>'
