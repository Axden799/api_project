from datetime import datetime
from flask import session, flash
from ..extensions import db
from ..models import Invitation, Membership


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
        flash('The invitation link is invalid or has expired.', 'error')
        return

    if invite.email.lower() != user.email.lower():
        flash('This invitation was sent to a different email address.', 'error')
        return

    # Check the org is not already full
    org = invite.organization
    if org.is_at_seat_limit:
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

    flash(f'You have joined "{org.name}" as {invite.role}.', 'success')
