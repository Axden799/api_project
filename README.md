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
1. Token generated with `itsdangerous` — signed, no database storage needed
2. Token expires after 24 hours
3. Clicking the link sets `email_verified = True` on the User row

### Create an Organization (not yet built)
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
| GET | `/dashboard` | Yes | Main app view (placeholder) |

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
| `tests/test_auth.py` | User model, tokens, register, login, logout, verification |

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
│   │   ├── forms.py         RegisterForm, LoginForm
│   │   └── routes.py        register, login, logout, verify_email
│   ├── dashboard/
│   │   ├── __init__.py      Blueprint definition
│   │   └── routes.py        placeholder dashboard (login required)
│   ├── orgs/                not yet built
│   └── billing/             not yet built
├── app/templates/
│   ├── base.html            shared layout, nav, flash messages
│   ├── auth/
│   │   ├── login.html
│   │   └── register.html
│   └── dashboard/
│       └── index.html
├── migrations/              auto-managed by Flask-Migrate
├── tests/
│   ├── conftest.py          pytest fixtures
│   └── test_auth.py         25 auth tests
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
| 3 — Auth | Done | Register, login, logout, email verification, tests |
| 4 — Orgs | Not started | Create org, invite members, manage team |
| 5 — Billing | Not started | Stripe checkout, webhook, customer portal |
| 6 — Email | Not started | SendGrid integration, real verification emails |
