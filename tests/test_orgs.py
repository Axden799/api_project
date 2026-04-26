"""
tests/test_orgs.py — Tests for Stage 4: Organizations

Covers:
  - Organization model (seat limits, is_at_seat_limit, set_plan)
  - Invitation model (is_expired, is_pending, create factory)
  - Create org route
  - Org dashboard visibility / access control
  - Invite route (send invite, duplicate invite)
  - Accept invite (logged-in and redirect-to-login flows)
  - Remove member
  - Change role
"""
import pytest
from datetime import datetime, timedelta
from app.extensions import db
from app.models import User, Organization, Membership, Invitation, PLAN_SEAT_LIMITS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_user(email='user@example.com', password='password123', verified=True):
    u = User(email=email)
    u.set_password(password)
    u.email_verified = verified
    db.session.add(u)
    db.session.commit()
    return u


def create_org(name='Test Org'):
    org = Organization(name=name)
    db.session.add(org)
    db.session.commit()
    return org


def add_member(user, org, role='member'):
    m = Membership(user_id=user.id, organization_id=org.id, role=role)
    db.session.add(m)
    db.session.commit()
    return m


def login(client, email='user@example.com', password='password123'):
    return client.post('/auth/login', data={'email': email, 'password': password},
                       follow_redirects=True)


# ---------------------------------------------------------------------------
# Organization model
# ---------------------------------------------------------------------------

class TestOrganizationModel:
    def test_seat_count_empty(self, app):
        with app.app_context():
            org = create_org()
            assert org.seat_count == 0

    def test_seat_count_with_members(self, app):
        with app.app_context():
            org = create_org()
            u1 = create_user('a@x.com')
            u2 = create_user('b@x.com')
            add_member(u1, org, 'owner')
            add_member(u2, org, 'member')
            assert org.seat_count == 2

    def test_is_at_seat_limit_false_when_under(self, app):
        with app.app_context():
            org = create_org()
            org.max_seats = 3
            u = create_user()
            add_member(u, org, 'owner')
            assert not org.is_at_seat_limit

    def test_is_at_seat_limit_true_when_full(self, app):
        with app.app_context():
            org = create_org()
            org.max_seats = 1
            u = create_user()
            add_member(u, org, 'owner')
            assert org.is_at_seat_limit

    def test_is_at_seat_limit_false_for_enterprise(self, app):
        with app.app_context():
            org = create_org()
            org.max_seats = None  # enterprise / unlimited
            for i in range(100):
                u = create_user(f'u{i}@x.com')
                add_member(u, org, 'member')
            assert not org.is_at_seat_limit

    def test_set_plan_updates_max_seats(self, app):
        with app.app_context():
            org = create_org()
            org.set_plan('basic')
            assert org.plan == 'basic'
            assert org.max_seats == PLAN_SEAT_LIMITS['basic']

    def test_set_plan_rejects_unknown_plan(self, app):
        with app.app_context():
            org = create_org()
            with pytest.raises(ValueError):
                org.set_plan('gold')


# ---------------------------------------------------------------------------
# Invitation model
# ---------------------------------------------------------------------------

class TestInvitationModel:
    def test_create_sets_token_and_expiry(self, app):
        with app.app_context():
            owner = create_user()
            org = create_org()
            inv = Invitation.create(
                organization_id=org.id,
                email='invite@example.com',
                role='member',
                invited_by_user_id=owner.id,
            )
            assert inv.token is not None
            assert len(inv.token) > 20
            assert inv.expires_at > datetime.utcnow()

    def test_is_pending_true_for_fresh_invite(self, app):
        with app.app_context():
            owner = create_user()
            org = create_org()
            inv = Invitation.create(
                organization_id=org.id,
                email='invite@example.com',
                role='member',
                invited_by_user_id=owner.id,
            )
            db.session.add(inv)
            db.session.commit()
            assert inv.is_pending

    def test_is_pending_false_when_accepted(self, app):
        with app.app_context():
            owner = create_user()
            org = create_org()
            inv = Invitation.create(
                organization_id=org.id,
                email='invite@example.com',
                role='member',
                invited_by_user_id=owner.id,
            )
            inv.accepted_at = datetime.utcnow()
            db.session.add(inv)
            db.session.commit()
            assert not inv.is_pending

    def test_is_expired_true_for_old_invite(self, app):
        with app.app_context():
            owner = create_user()
            org = create_org()
            inv = Invitation.create(
                organization_id=org.id,
                email='invite@example.com',
                role='member',
                invited_by_user_id=owner.id,
            )
            inv.expires_at = datetime.utcnow() - timedelta(hours=1)
            db.session.add(inv)
            db.session.commit()
            assert inv.is_expired
            assert not inv.is_pending


# ---------------------------------------------------------------------------
# Create org route
# ---------------------------------------------------------------------------

class TestCreateOrgRoute:
    def test_redirect_if_not_logged_in(self, client):
        r = client.get('/orgs/create', follow_redirects=False)
        assert r.status_code == 302
        assert '/auth/login' in r.headers['Location']

    def test_redirect_if_email_not_verified(self, client, app):
        with app.app_context():
            create_user(verified=False)
        login(client)
        r = client.get('/orgs/create', follow_redirects=True)
        assert b'verify your email' in r.data.lower()

    def test_get_form_renders(self, client, app):
        with app.app_context():
            create_user()
        login(client)
        r = client.get('/orgs/create')
        assert r.status_code == 200
        assert b'Create' in r.data

    def test_creates_org_and_owner_membership(self, client, app):
        with app.app_context():
            create_user()
        login(client)
        r = client.post('/orgs/create', data={'name': 'My Company'}, follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            org = Organization.query.filter_by(name='My Company').first()
            assert org is not None
            m = Membership.query.filter_by(organization_id=org.id).first()
            assert m is not None
            assert m.role == 'owner'

    def test_empty_name_rejected(self, client, app):
        with app.app_context():
            create_user()
        login(client)
        r = client.post('/orgs/create', data={'name': ''}, follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            assert Organization.query.count() == 0


# ---------------------------------------------------------------------------
# Org dashboard
# ---------------------------------------------------------------------------

class TestOrgDashboard:
    def test_non_member_cannot_view(self, client, app):
        with app.app_context():
            create_user()
            org = create_org()
            org_id = org.id
        login(client)
        r = client.get(f'/orgs/{org_id}', follow_redirects=True)
        assert b'not a member' in r.data.lower()

    def test_member_can_view(self, client, app):
        with app.app_context():
            u = create_user()
            org = create_org()
            add_member(u, org, 'owner')
            org_id = org.id
        login(client)
        r = client.get(f'/orgs/{org_id}')
        assert r.status_code == 200
        assert b'Test Org' in r.data


# ---------------------------------------------------------------------------
# Invite route
# ---------------------------------------------------------------------------

class TestInviteRoute:
    def _setup(self, app):
        with app.app_context():
            owner = create_user('owner@x.com')
            org = create_org()
            add_member(owner, org, 'owner')
            return org.id

    def test_member_cannot_invite(self, client, app):
        with app.app_context():
            u = create_user()
            org = create_org()
            add_member(u, org, 'member')
            org_id = org.id
        login(client)
        r = client.post(f'/orgs/{org_id}/invite',
                        data={'email': 'new@x.com', 'role': 'member'},
                        follow_redirects=True)
        assert b'owners and admins' in r.data.lower()

    def test_owner_can_invite(self, client, app):
        org_id = self._setup(app)
        login(client, 'owner@x.com')
        r = client.post(f'/orgs/{org_id}/invite',
                        data={'email': 'newmember@x.com', 'role': 'member'},
                        follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            inv = Invitation.query.filter_by(email='newmember@x.com').first()
            assert inv is not None
            assert inv.is_pending

    def test_resend_cancels_old_invite_and_issues_new_one(self, client, app):
        org_id = self._setup(app)
        login(client, 'owner@x.com')
        client.post(f'/orgs/{org_id}/invite',
                    data={'email': 'dup@x.com', 'role': 'member'})
        with app.app_context():
            first_token = Invitation.query.filter_by(email='dup@x.com').first().token

        client.post(f'/orgs/{org_id}/invite',
                    data={'email': 'dup@x.com', 'role': 'member'},
                    follow_redirects=True)
        with app.app_context():
            invites = Invitation.query.filter_by(email='dup@x.com').all()
            # Only one invite row should exist — the new one
            assert len(invites) == 1
            # The token must have changed — old link is dead
            assert invites[0].token != first_token
            assert invites[0].is_pending

    def test_invite_blocked_when_at_seat_limit(self, client, app):
        with app.app_context():
            owner = create_user('owner@x.com')
            org = create_org()
            org.max_seats = 1
            db.session.commit()
            add_member(owner, org, 'owner')
            org_id = org.id
        login(client, 'owner@x.com')
        r = client.post(f'/orgs/{org_id}/invite',
                        data={'email': 'extra@x.com', 'role': 'member'},
                        follow_redirects=True)
        assert b'seat limit' in r.data.lower()


# ---------------------------------------------------------------------------
# Accept invite
# ---------------------------------------------------------------------------

class TestAcceptInvite:
    def _make_invite(self, app, email='invitee@x.com', role='member'):
        with app.app_context():
            owner = create_user('owner@x.com')
            org = create_org()
            add_member(owner, org, 'owner')
            inv = Invitation.create(
                organization_id=org.id,
                email=email,
                role=role,
                invited_by_user_id=owner.id,
            )
            db.session.add(inv)
            db.session.commit()
            return inv.token, org.id

    def test_invalid_token_shows_error(self, client):
        r = client.get('/orgs/invite/badtoken', follow_redirects=True)
        assert b'invalid or has expired' in r.data.lower()

    def test_logged_out_user_stored_in_session_and_redirected(self, client, app):
        token, _ = self._make_invite(app)
        r = client.get(f'/orgs/invite/{token}', follow_redirects=False)
        assert r.status_code == 302
        assert '/auth/login' in r.headers['Location']

    def test_accept_invite_as_logged_in_user(self, client, app):
        token, org_id = self._make_invite(app)
        with app.app_context():
            create_user('invitee@x.com')
        login(client, 'invitee@x.com')
        r = client.get(f'/orgs/invite/{token}', follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            inv = Invitation.query.filter_by(token=token).first()
            assert inv.accepted_at is not None
            u = User.query.filter_by(email='invitee@x.com').first()
            m = Membership.query.filter_by(user_id=u.id, organization_id=org_id).first()
            assert m is not None
            assert m.role == 'member'

    def test_wrong_email_cannot_accept(self, client, app):
        token, org_id = self._make_invite(app, email='invitee@x.com')
        with app.app_context():
            create_user('wrong@x.com')
        login(client, 'wrong@x.com')
        r = client.get(f'/orgs/invite/{token}', follow_redirects=True)
        assert b'different email address' in r.data.lower()
        with app.app_context():
            u = User.query.filter_by(email='wrong@x.com').first()
            m = Membership.query.filter_by(user_id=u.id, organization_id=org_id).first()
            assert m is None

    def test_accept_via_login_flow(self, client, app):
        token, org_id = self._make_invite(app, email='invitee@x.com')
        with app.app_context():
            create_user('invitee@x.com')
        # Visit invite link while logged out → stores token in session
        client.get(f'/orgs/invite/{token}')
        # Log in → process_pending_invite fires
        login(client, 'invitee@x.com')
        with app.app_context():
            u = User.query.filter_by(email='invitee@x.com').first()
            m = Membership.query.filter_by(user_id=u.id, organization_id=org_id).first()
            assert m is not None


# ---------------------------------------------------------------------------
# Remove member
# ---------------------------------------------------------------------------

class TestRemoveMember:
    def _setup(self, app):
        with app.app_context():
            owner = create_user('owner@x.com')
            member = create_user('member@x.com')
            org = create_org()
            add_member(owner, org, 'owner')
            add_member(member, org, 'member')
            return org.id, member.id

    def test_owner_can_remove_member(self, client, app):
        org_id, member_id = self._setup(app)
        login(client, 'owner@x.com')
        r = client.post(f'/orgs/{org_id}/members/{member_id}/remove', follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            m = Membership.query.filter_by(user_id=member_id, organization_id=org_id).first()
            assert m is None

    def test_member_cannot_remove_others(self, client, app):
        org_id, member_id = self._setup(app)
        login(client, 'member@x.com')
        with app.app_context():
            owner_id = User.query.filter_by(email='owner@x.com').first().id
        r = client.post(f'/orgs/{org_id}/members/{owner_id}/remove', follow_redirects=True)
        assert b'owners and admins' in r.data.lower()

    def test_owner_cannot_remove_self(self, client, app):
        with app.app_context():
            owner = create_user('owner@x.com')
            org = create_org()
            add_member(owner, org, 'owner')
            org_id = org.id
            owner_id = owner.id
        login(client, 'owner@x.com')
        r = client.post(f'/orgs/{org_id}/members/{owner_id}/remove', follow_redirects=True)
        assert b'owner cannot be removed' in r.data.lower()


# ---------------------------------------------------------------------------
# Change role
# ---------------------------------------------------------------------------

class TestChangeRole:
    def _setup(self, app):
        with app.app_context():
            owner = create_user('owner@x.com')
            member = create_user('member@x.com')
            org = create_org()
            add_member(owner, org, 'owner')
            add_member(member, org, 'member')
            return org.id, member.id

    def test_owner_can_promote_to_admin(self, client, app):
        org_id, member_id = self._setup(app)
        login(client, 'owner@x.com')
        r = client.post(
            f'/orgs/{org_id}/members/{member_id}/role',
            data={'role': 'admin'},
            follow_redirects=True,
        )
        assert r.status_code == 200
        with app.app_context():
            m = Membership.query.filter_by(user_id=member_id, organization_id=org_id).first()
            assert m.role == 'admin'

    def test_non_owner_cannot_change_role(self, client, app):
        org_id, member_id = self._setup(app)
        login(client, 'member@x.com')
        with app.app_context():
            owner_id = User.query.filter_by(email='owner@x.com').first().id
        r = client.post(
            f'/orgs/{org_id}/members/{owner_id}/role',
            data={'role': 'member'},
            follow_redirects=True,
        )
        assert b'only the owner' in r.data.lower()

    def test_invalid_role_rejected(self, client, app):
        org_id, member_id = self._setup(app)
        login(client, 'owner@x.com')
        r = client.post(
            f'/orgs/{org_id}/members/{member_id}/role',
            data={'role': 'superadmin'},
            follow_redirects=True,
        )
        assert b'invalid role' in r.data.lower()
