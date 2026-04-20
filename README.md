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

## Data Model

```
User
├── id
├── email
├── password_hash
├── is_active
├── email_verified
└── created_at

Organization
├── id
├── name
├── stripe_customer_id
├── stripe_subscription_id
├── plan                     (free, basic, pro, enterprise)
├── max_seats                (set by plan)
├── status                   (active, cancelled, past_due)
└── created_at

Membership               links a user to an org with a role
├── id
├── user_id
├── organization_id
├── role                     (owner, admin, member)
├── joined_at
└── invited_by_user_id

Invitation               pending invite tokens
├── id
├── organization_id
├── email
├── role                     (role the invitee will receive on acceptance)
├── token
├── expires_at
├── accepted_at
└── invited_by_user_id
```

---

## Core Flows

### Register
1. User submits email and password
2. Verification email sent
3. User confirms email → account active
4. Redirected to dashboard — no orgs yet

### Create an Organization
1. User creates an org, automatically becomes its Owner
2. Owner selects a plan → redirected to Stripe Checkout
3. Payment confirmed → org activated

### Invite a User
1. Owner or admin enters an email and selects a role
2. Invite email sent with a secure token (expires in 48 hours)
3. Recipient clicks link → creates or logs into account → joined to org

### Join an Org (existing user)
1. Click invite link → prompted to log in
2. After login → added to org with the assigned role

---

## Local Development

### First-time setup

```bash
# Clone the repo
git clone <repo-url>
cd api_project

# Create and activate the virtual environment
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Create your environment file
cp .env.example .env
# Open .env and set SECRET_KEY to a random string:
# python3 -c "import secrets; print(secrets.token_hex(32))"
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

### Every time you change models.py

```bash
flask db migrate -m "describe what changed"
flask db upgrade
```

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
| Payments | Stripe |
| Email | SendGrid or Resend |
| Database (dev) | SQLite |
| Database (prod) | PostgreSQL |

---

## Project Structure

```
api_project/
├── app/
│   ├── __init__.py          application factory
│   ├── models.py            User, Organization, Membership, Invitation
│   ├── auth/                register, login, logout, email verification
│   ├── orgs/                create org, invite members, manage team
│   ├── billing/             Stripe checkout, webhook handler, portal
│   └── dashboard/           main app views (protected)
├── migrations/
├── tests/
├── .env
├── config.py
└── run.py
```
