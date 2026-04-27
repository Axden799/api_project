from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_required, current_user
from ..extensions import db, limiter


def _ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr)
from ..models import Organization, Membership, Invitation, PLAN_SEAT_LIMITS
from . import orgs_bp
from .forms import CreateOrgForm, InviteForm


# ---------------------------------------------------------------------------
# Create organization
# ---------------------------------------------------------------------------

@orgs_bp.route('/orgs/create', methods=['GET', 'POST'])
@login_required
def create():
    if not current_user.email_verified:
        flash('Please verify your email before creating an organization.', 'info')
        return redirect(url_for('dashboard.index'))

    form = CreateOrgForm()

    if form.validate_on_submit():
        org = Organization(name=form.name.data.strip())
        db.session.add(org)
        db.session.flush()  # gives org.id before commit

        membership = Membership(
            user_id=current_user.id,
            organization_id=org.id,
            role='owner',
        )
        db.session.add(membership)
        db.session.commit()

        current_app.logger.warning(
            f'ORG_CREATED: new organization  org="{org.name}"  '
            f'org_id={org.id}  owner={current_user.email}  ip={_ip()}'
        )

        flash(f'"{org.name}" created successfully.', 'success')
        return redirect(url_for('orgs.org_dashboard', org_id=org.id))

    return render_template('orgs/create.html', form=form)


# ---------------------------------------------------------------------------
# Org dashboard
# ---------------------------------------------------------------------------

@orgs_bp.route('/orgs/<int:org_id>')
@login_required
def org_dashboard(org_id):
    org = db.session.get(Organization, org_id)
    if org is None:
        flash('Organization not found.', 'error')
        return redirect(url_for('dashboard.index'))

    membership = Membership.query.filter_by(
        user_id=current_user.id,
        organization_id=org_id,
    ).first()
    if membership is None:
        flash('You are not a member of that organization.', 'error')
        return redirect(url_for('dashboard.index'))

    invite_form = InviteForm()
    return render_template(
        'orgs/dashboard.html',
        org=org,
        membership=membership,
        invite_form=invite_form,
        seat_limit=org.max_seats,
        PLAN_SEAT_LIMITS=PLAN_SEAT_LIMITS,
    )


# ---------------------------------------------------------------------------
# Send invite
# ---------------------------------------------------------------------------

@orgs_bp.route('/orgs/<int:org_id>/invite', methods=['POST'])
@login_required
@limiter.limit('5 per hour')
def invite(org_id):
    org = db.session.get(Organization, org_id)
    if org is None:
        flash('Organization not found.', 'error')
        return redirect(url_for('dashboard.index'))

    membership = Membership.query.filter_by(
        user_id=current_user.id,
        organization_id=org_id,
    ).first()
    if membership is None or membership.role not in ('owner', 'admin'):
        flash('Only owners and admins can send invitations.', 'error')
        return redirect(url_for('orgs.org_dashboard', org_id=org_id))

    if org.is_at_seat_limit:
        flash('Seat limit reached. Upgrade the plan before inviting more members.', 'error')
        return redirect(url_for('orgs.org_dashboard', org_id=org_id))

    form = InviteForm()
    if form.validate_on_submit():
        email = form.email.data.lower()
        role = form.role.data

        # If a pending invite already exists for this email, cancel it and
        # issue a fresh one. This lets owners resend without waiting 48 hours.
        # The old token stops working the moment it is deleted.
        existing = Invitation.query.filter_by(
            organization_id=org_id,
            email=email,
            accepted_at=None,
        ).first()
        resent = False
        if existing and existing.is_pending:
            db.session.delete(existing)
            db.session.flush()
            resent = True

        inv = Invitation.create(
            organization_id=org_id,
            email=email,
            role=role,
            invited_by_user_id=current_user.id,
        )
        db.session.add(inv)
        db.session.commit()

        accept_url = url_for('orgs.accept_invite', token=inv.token, _external=True)

        # Stub: print to terminal until SendGrid is configured
        print(f'\n{"="*60}')
        print(f'INVITE LINK for {email} to join "{org.name}" as {role}:')
        print(f'{accept_url}')
        print(f'{"="*60}\n')

        action = 'INVITE_RESENT' if resent else 'INVITE_SENT'
        current_app.logger.warning(
            f'{action}: invitation issued  org="{org.name}"  org_id={org_id}  '
            f'to={email}  role={role}  by={current_user.email}  ip={_ip()}'
        )

        flash(f'Invitation sent to {email}. Check the terminal for the link. Any previous invite link for this address is now invalid.', 'success')

    return redirect(url_for('orgs.org_dashboard', org_id=org_id))


# ---------------------------------------------------------------------------
# Accept invite
# ---------------------------------------------------------------------------

@orgs_bp.route('/orgs/invite/<token>')
def accept_invite(token):
    invite = Invitation.query.filter_by(token=token).first()

    if invite is None or not invite.is_pending:
        current_app.logger.warning(
            f'INVITE_INVALID: bad or expired token used  ip={_ip()}'
        )
        flash('This invitation link is invalid or has expired.', 'error')
        return redirect(url_for('auth.login'))

    if current_user.is_authenticated:
        # User is already logged in — process immediately via the util
        from .utils import process_pending_invite
        session['pending_invite_token'] = token
        process_pending_invite(current_user)
        # If the join succeeded, send them to the org; otherwise back to dashboard
        fresh_membership = Membership.query.filter_by(
            user_id=current_user.id,
            organization_id=invite.organization_id,
        ).first()
        if fresh_membership:
            return redirect(url_for('orgs.org_dashboard', org_id=invite.organization_id))
        return redirect(url_for('dashboard.index'))

    # Not logged in — stash the token and send them to login
    session['pending_invite_token'] = token
    flash('Please log in (or create an account) to accept the invitation.', 'info')
    return redirect(url_for('auth.login'))


# ---------------------------------------------------------------------------
# Remove member (owner / admin only)
# ---------------------------------------------------------------------------

@orgs_bp.route('/orgs/<int:org_id>/members/<int:user_id>/remove', methods=['POST'])
@login_required
def remove_member(org_id, user_id):
    org = db.session.get(Organization, org_id)
    if org is None:
        flash('Organization not found.', 'error')
        return redirect(url_for('dashboard.index'))

    actor = Membership.query.filter_by(
        user_id=current_user.id, organization_id=org_id
    ).first()
    if actor is None or actor.role not in ('owner', 'admin'):
        flash('Only owners and admins can remove members.', 'error')
        return redirect(url_for('orgs.org_dashboard', org_id=org_id))

    target = Membership.query.filter_by(
        user_id=user_id, organization_id=org_id
    ).first()
    if target is None:
        flash('Member not found.', 'error')
        return redirect(url_for('orgs.org_dashboard', org_id=org_id))

    # Admins cannot remove the owner or other admins
    if actor.role == 'admin' and target.role in ('owner', 'admin'):
        flash('Admins can only remove regular members.', 'error')
        return redirect(url_for('orgs.org_dashboard', org_id=org_id))

    # Owner cannot remove themselves
    if target.role == 'owner':
        flash('The owner cannot be removed. Transfer ownership first.', 'error')
        return redirect(url_for('orgs.org_dashboard', org_id=org_id))

    removed_email = target.user.email
    removed_role = target.role
    db.session.delete(target)
    db.session.commit()

    current_app.logger.warning(
        f'MEMBER_REMOVED: member removed from org  org="{org.name}"  org_id={org_id}  '
        f'removed={removed_email}  removed_role={removed_role}  '
        f'by={current_user.email}  by_role={actor.role}  ip={_ip()}'
    )

    flash('Member removed.', 'success')
    return redirect(url_for('orgs.org_dashboard', org_id=org_id))


# ---------------------------------------------------------------------------
# Change member role (owner only)
# ---------------------------------------------------------------------------

@orgs_bp.route('/orgs/<int:org_id>/members/<int:user_id>/role', methods=['POST'])
@login_required
def change_role(org_id, user_id):
    org = db.session.get(Organization, org_id)
    if org is None:
        flash('Organization not found.', 'error')
        return redirect(url_for('dashboard.index'))

    actor = Membership.query.filter_by(
        user_id=current_user.id, organization_id=org_id
    ).first()
    if actor is None or actor.role != 'owner':
        flash('Only the owner can change member roles.', 'error')
        return redirect(url_for('orgs.org_dashboard', org_id=org_id))

    target = Membership.query.filter_by(
        user_id=user_id, organization_id=org_id
    ).first()
    if target is None:
        flash('Member not found.', 'error')
        return redirect(url_for('orgs.org_dashboard', org_id=org_id))

    if target.role == 'owner':
        flash('Cannot change the owner\'s role directly. Transfer ownership instead.', 'error')
        return redirect(url_for('orgs.org_dashboard', org_id=org_id))

    new_role = request.form.get('role')
    if new_role not in ('admin', 'member'):
        flash('Invalid role.', 'error')
        return redirect(url_for('orgs.org_dashboard', org_id=org_id))

    old_role = target.role
    target.role = new_role
    db.session.commit()

    current_app.logger.warning(
        f'ROLE_CHANGED: member role updated  org="{org.name}"  org_id={org_id}  '
        f'member={target.user.email}  old_role={old_role}  new_role={new_role}  '
        f'by={current_user.email}  ip={_ip()}'
    )

    flash('Role updated.', 'success')
    return redirect(url_for('orgs.org_dashboard', org_id=org_id))
