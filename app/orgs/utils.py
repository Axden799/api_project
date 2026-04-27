from datetime import datetime
from flask import session, flash, request, current_app
from ..extensions import db
from ..models import Invitation, Membership


def _ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)


def process_pending_invite(user):
    """
    Called immediately after a user logs in or registers.
    If there is a pending invite token stored in the session, consume it:
      - Validate it is still pending
      - Check the invite email matches the user's email
      - Create a Membership row
      - Mark the invite as accepted
    Clears the session key whether the invite is used or not.
    """
    token = session.pop('pending_invite_token', None)
    if token is None:
        return

    invite = Invitation.query.filter_by(token=token).first()

    if invite is None or not invite.is_pending:
        current_app.logger.warning(
            f'INVITE_ACCEPT_FAILED: invalid or expired token  '
            f'user={user.email}  ip={_ip()}'
        )
        flash('The invitation link is invalid or has expired.', 'error')
        return

    if invite.email.lower() != user.email.lower():
        current_app.logger.warning(
            f'INVITE_ACCEPT_FAILED: email mismatch  '
            f'invite_email={invite.email}  user={user.email}  ip={_ip()}'
        )
        flash('This invitation was sent to a different email address.', 'error')
        return

    # Check the org is not already full
    org = invite.organization
    if org.is_at_seat_limit:
        current_app.logger.warning(
            f'INVITE_ACCEPT_FAILED: seat limit reached  '
            f'org="{org.name}"  org_id={org.id}  user={user.email}  ip={_ip()}'
        )
        flash(
            f'"{org.name}" has reached its seat limit. Ask the owner to upgrade the plan.',
            'error',
        )
        return

    # Make sure the user is not already a member
    existing = Membership.query.filter_by(
        user_id=user.id,
        organization_id=org.id,
    ).first()
    if existing:
        flash(f'You are already a member of "{org.name}".', 'info')
        invite.accepted_at = datetime.utcnow()
        db.session.commit()
        return

    membership = Membership(
        user_id=user.id,
        organization_id=org.id,
        role=invite.role,
        invited_by_user_id=invite.invited_by_user_id,
    )
    invite.accepted_at = datetime.utcnow()

    db.session.add(membership)
    db.session.commit()

    current_app.logger.warning(
        f'INVITE_ACCEPTED: user joined org  org="{org.name}"  org_id={org.id}  '
        f'user={user.email}  role={invite.role}  ip={_ip()}'
    )

    flash(f'You have joined "{org.name}" as {invite.role}.', 'success')
