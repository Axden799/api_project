# SaaS Auth Template

App template for handling accounts. Users create an account with an email and password. Each account can belong to multiple organizations as a member or admin.

---

## Accounts

- Anyone can register with an email and password
- Email verification is required before accessing any organization
- A single account can belong to multiple organizations simultaneously
- Within each organization, the account holds a specific role

---

## Organizations

An organization represents a company or team. It has its own plan, billing, and member list.

### Roles

| Role | Description |
|---|---|
| **Owner** | The user who created the org. Responsible for billing. Can manage members, admins, and org settings. One per org, transferable. |
| **Admin** | Can invite members, manage roles, and access all app features. No billing access. No limit on how many admins an org can have. |
| **Member** | Standard access to app features. Cannot manage the org or its members. |

### Plans & Seat Limits

Each organization is tied to a subscription plan. The plan determines how many total users (owner + admins + members combined) the org can have.

| Plan | Max Seats | Billing |
|---|---|---|
| Free | 3 | No charge |
| Basic | 10 | Flat monthly fee |
| Pro | 50 | Flat monthly fee |
| Enterprise | Unlimited | Custom |

When an org reaches its seat limit, the owner is prompted to upgrade before additional invites can be sent.

### Invitations

Owners and admins can invite new users by email. The system generates a secure, time-limited token and sends it to the invitee. The invitee clicks the link and either:

- Creates a new account → automatically added to the org with the assigned role
- Logs into an existing account → added to the org with the assigned role

---

## Core Flows

### Register
1. User submits email and password
2. Verification link printed to terminal (SendGrid not yet configured)
3. User clicks link → email verified → account active
4. Redirected to login

### Login
1. User submits email and password
2. Credentials validated
3. Session created → redirected to dashboard

### Email Verification
1. Token generated with `itsdangerous` — signed with app secret, no database storage needed
2. Token expires after 24 hours
3. Clicking the link sets `email_verified = True` on the User row
4. If the link is lost, user can request a resend (60-second cooldown)

### Change Email
1. Logged-in user submits new address and current password
2. Password verified before anything is changed
3. Token generated containing both user ID and new email address — new email is not written to the database yet
4. User clicks link sent to the new address → email updated, `email_verified` reset to True
5. Holding the change in a token until confirmed prevents typos from locking the user out

### Change Password (logged in)
1. Logged-in user submits current password, new password, confirmation
2. Current password verified before the hash is updated
3. Prevents silent takeover from an unlocked browser session

### Forgot Password
1. User submits their email address
2. Same response shown whether or not the email exists (prevents account enumeration)
3. Token generated containing user ID and a fingerprint of the current password hash
4. Token expires after 1 hour
5. User clicks reset link → sets new password → logged in automatically
6. Token is single-use: changing the password changes the hash fingerprint, making the old token invalid

### Create an Organization
1. User creates an org, automatically becomes its Owner
2. Owner selects a plan → redirected to Stripe Checkout
3. Payment confirmed → org activated

### Invite a User (not yet built)
1. Owner or admin enters an email and selects a role
2. Invite email sent with a secure token (expires in 48 hours)
3. Recipient clicks link → creates or logs into account → joined to org

---

## Data Model

```
User
├── id
├── email                    unique, indexed
├── password_hash            bcrypt via werkzeug
├── is_active                soft deactivation — never hard delete
├── email_verified
└── created_at

Organization
├── id
├── name
├── stripe_customer_id       null until payment set up
├── stripe_subscription_id   null on free plan
├── plan                     free | basic | pro | enterprise
├── max_seats                set automatically by plan
├── status                   active | cancelled | past_due
└── created_at

Membership                   links a user to an org with a role
├── id
├── user_id                  FK → users
├── organization_id          FK → organizations
├── role                     owner | admin | member
├── joined_at
└── invited_by_user_id       FK → users (nullable — null for org creator)

Invitation                   pending invite tokens
├── id
├── organization_id          FK → organizations
├── email
├── role                     role assigned on acceptance
├── token                    secrets.token_urlsafe(32), unique
├── expires_at               48 hours from creation
├── accepted_at              null until used — enforces single-use
└── invited_by_user_id       FK → users
```

---

## Routes

| Method | URL | Auth required | Description |
|---|---|---|---|
| GET | `/auth/register` | No | Registration form |
| POST | `/auth/register` | No | Create account, send verification link |
| GET | `/auth/login` | No | Login form |
| POST | `/auth/login` | No | Validate credentials, create session |
| POST | `/auth/logout` | Yes | Clear session |
| GET | `/auth/verify/<token>` | No | Verify email address |
| GET | `/auth/verify-pending` | No | "Check your email" page shown after registration |
| POST | `/auth/resend-verification` | No | Resend verification link (60-second cooldown) |
| GET | `/auth/settings` | Yes | Account settings page |
| GET/POST | `/auth/change-email` | Yes | Request email address change |
| GET | `/auth/confirm-email-change/<token>` | Yes | Confirm new email via link |
| GET/POST | `/auth/change-password` | Yes | Change password (requires current password) |
| GET/POST | `/auth/forgot-password` | No | Request password reset link |
| GET/POST | `/auth/reset-password/<token>` | No | Set new password via reset link |
| GET | `/dashboard` | Yes | Main app view — lists user's organizations |
| GET | `/orgs/create` | Yes | Create organization form |
| POST | `/orgs/create` | Yes | Create org, make current user owner |
| GET | `/orgs/<id>` | Yes | Org dashboard — members, invite form |
| POST | `/orgs/<id>/invite` | Yes (owner/admin) | Send invite, print link to terminal |
| GET | `/orgs/invite/<token>` | No | Accept invite link |
| POST | `/orgs/<id>/members/<id>/remove` | Yes (owner/admin) | Remove a member |
| POST | `/orgs/<id>/members/<id>/role` | Yes (owner only) | Change a member's role |

---

## Local Development

### First-time setup

```bash
# Clone the repo
git clone https://github.com/Axden799/api_project.git
cd api_project

# Create and activate the virtual environment
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Create your environment file
cp .env.example .env

# Generate a secret key and paste it into .env as SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Initialize the database (first time only)

```bash
flask db init
flask db migrate -m "initial tables"
flask db upgrade
```

### Run the app

```bash
source venv/bin/activate        # if not already activated
flask run
```

App runs at http://127.0.0.1:5000

> **Email:** SendGrid is not yet configured. When you register, the verification
> link is printed to the terminal instead of sent by email. Copy it into your
> browser to verify.

### Every time you change models.py

```bash
flask db migrate -m "describe what changed"
flask db upgrade
```

---

## Testing

Tests use an in-memory SQLite database and run independently of your development database. CSRF is disabled in test mode so form submissions work without tokens.

### Run all tests

```bash
source venv/bin/activate
pytest
```

### Run with detail

```bash
pytest -v                                        # show each test name
pytest tests/test_auth.py -v                     # one file
pytest tests/test_auth.py::TestLoginRoute -v     # one class
pytest tests/test_auth.py::TestLoginRoute::test_wrong_password_rejected  # one test
```

### Test files

| File | What it covers |
|---|---|
| `tests/conftest.py` | Shared fixtures: app, client, db |
| `tests/test_auth.py` | User model, tokens, register, login, logout, verification, resend, change email, change password, forgot/reset password |
| `tests/test_orgs.py` | Org model, invitation model, create org, invite, accept, remove, change role |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| ORM | Flask-SQLAlchemy |
| Migrations | Flask-Migrate |
| Auth | Flask-Login, Werkzeug |
| Forms & CSRF | Flask-WTF |
| Tokens | itsdangerous, secrets |
| Payments | Stripe (not yet integrated) |
| Email | SendGrid (not yet integrated — stubbed to terminal) |
| Database (dev) | SQLite |
| Database (prod) | PostgreSQL |
| Testing | pytest |

---

## Project Structure

```
api_project/
├── app/
│   ├── __init__.py          application factory — creates app, registers blueprints
│   ├── extensions.py        db, login_manager, migrate (created unbound, avoids circular imports)
│   ├── models.py            User, Organization, Membership, Invitation
│   ├── auth/
│   │   ├── __init__.py      Blueprint definition
│   │   ├── forms.py         RegisterForm, LoginForm, ChangeEmailForm, ChangePasswordForm, ForgotPasswordForm, ResetPasswordForm
│   │   └── routes.py        register, login, logout, verify_email, verify_pending, resend_verification, settings, change_email, confirm_email_change, change_password, forgot_password, reset_password
│   ├── dashboard/
│   │   ├── __init__.py      Blueprint definition
│   │   └── routes.py        placeholder dashboard (login required)
│   ├── orgs/
│   │   ├── __init__.py      Blueprint definition
│   │   ├── forms.py         CreateOrgForm, InviteForm
│   │   ├── routes.py        create, org_dashboard, invite, accept_invite, remove_member, change_role
│   │   └── utils.py         process_pending_invite — consumes session invite token after login
│   └── billing/             not yet built
├── app/templates/
│   ├── base.html            shared layout, nav, flash messages
│   ├── auth/
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── verify_pending.html
│   │   ├── settings.html
│   │   ├── change_email.html
│   │   ├── change_password.html
│   │   ├── forgot_password.html
│   │   └── reset_password.html
│   ├── dashboard/
│   │   └── index.html       shows org list with links
│   └── orgs/
│       ├── create.html
│       └── dashboard.html   member list, role controls, invite form
├── migrations/              auto-managed by Flask-Migrate
├── tests/
│   ├── conftest.py          pytest fixtures
│   ├── test_auth.py         25 auth tests
│   └── test_orgs.py         33 org tests
├── .env                     secrets — not committed
├── .env.example             safe template for .env
├── config.py                DevelopmentConfig, TestingConfig, ProductionConfig
├── pytest.ini               tells pytest where to find the app
├── requirements.txt
├── run.py                   entry point
└── README.md
```

---

## Build Progress

| Stage | Status | Description |
|---|---|---|
| 1 — Skeleton | Done | App factory, config, extensions, run.py |
| 2 — Models | Done | User, Organization, Membership, Invitation + migrations |
| 3 — Auth | Done | Register, login, logout, email verification, resend verification, change email, change password, forgot/reset password, tests |
| 4 — Orgs | Done | Create org, invite members, manage team |
| 5 — Billing | Not started | Stripe checkout, webhook, customer portal |
| 6 — Email | Not started | SendGrid integration, real verification emails |
