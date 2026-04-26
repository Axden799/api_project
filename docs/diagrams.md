# Diagrams

All diagrams are written in [Mermaid](https://mermaid.js.org/) and render automatically on GitHub.

---

## 1. Entity-Relationship Diagram

Shows every database table, its columns, and the foreign key relationships between them.

```mermaid
erDiagram
    users {
        int id PK
        string email UK
        string password_hash
        boolean is_active
        boolean email_verified
        datetime created_at
    }

    organizations {
        int id PK
        string name
        string stripe_customer_id UK
        string stripe_subscription_id UK
        string plan
        int max_seats
        string status
        datetime created_at
    }

    memberships {
        int id PK
        int user_id FK
        int organization_id FK
        int invited_by_user_id FK
        string role
        datetime joined_at
    }

    invitations {
        int id PK
        int organization_id FK
        int invited_by_user_id FK
        string email
        string role
        string token UK
        datetime expires_at
        datetime accepted_at
    }

    users ||--o{ memberships : "belongs to orgs via"
    organizations ||--o{ memberships : "has members via"
    users ||--o{ memberships : "invited members via"
    organizations ||--o{ invitations : "has"
    users ||--o{ invitations : "sent"
```

---

## 2. User Flow — Registration to Joining an Organization

The complete path a new user takes from first visiting the site to becoming a member of an organization.

```mermaid
flowchart TD
    A([User visits site]) --> B[GET /auth/register]
    B --> C[Fill in email + password]
    C --> D{Form valid?}
    D -- No --> C
    D -- Yes --> E[Account created\nVerification link printed to terminal]
    E --> F[GET /auth/verify-pending\nCheck your email page]
    F --> G{Got the link?}
    G -- No --> H[Click Resend\nPOST /auth/resend-verification]
    H --> I{60s cooldown\npassed?}
    I -- No --> F
    I -- Yes --> E
    G -- Yes --> J[GET /auth/verify/token\nEmail verified]
    J --> K[GET /auth/login]
    K --> L[Submit email + password]
    L --> M{Credentials\nvalid?}
    M -- No --> L
    M -- Yes --> N[Session created\nGET /dashboard]
    N --> O{Has pending\ninvite in session?}
    O -- Yes --> P[process_pending_invite\nMembership created]
    P --> Q[Redirected to org dashboard]
    O -- No --> R{Email\nverified?}
    R -- No --> S[Warning shown\nCannot create or join orgs]
    R -- Yes --> T[Create org or\naccept invite normally]
    T --> Q
```

---

## 3. User Flow — Account Management

Actions an existing logged-in user can take to manage their account.

```mermaid
flowchart TD
    A([Logged-in user]) --> B[GET /auth/settings]

    B --> C[Change email]
    B --> D[Change password]

    C --> E[GET /auth/change-email\nEnter new email + current password]
    E --> F{Password\ncorrect?}
    F -- No --> E
    F -- Yes --> G[Token generated\nnew email embedded inside token]
    G --> H[Link printed to terminal\nfor new address]
    H --> I[GET /auth/confirm-email-change/token\nclicked from new inbox]
    I --> J{Token valid\nand not expired?}
    J -- No --> K[Error: link invalid]
    J -- Yes --> L{New email\nstill available?}
    L -- No --> M[Error: email taken]
    L -- Yes --> N[Email updated\nemail_verified reset to True]

    D --> O[GET /auth/change-password\nEnter current + new password]
    O --> P{Current password\ncorrect?}
    P -- No --> O
    P -- Yes --> Q[Password hash updated\nRedirect to settings]
```

---

## 4. User Flow — Forgot Password

The full reset flow for a logged-out user who cannot remember their password.

```mermaid
flowchart TD
    A([User cannot log in]) --> B[Click Forgot your password?\non login page]
    B --> C[GET /auth/forgot-password\nEnter email address]
    C --> D[POST /auth/forgot-password]
    D --> E{Account exists\nand is active?}
    E -- No --> F[Same generic response shown\nno hint that email was not found]
    E -- Yes --> G[Reset token generated\ncontains user ID + password hash fingerprint]
    G --> H[Link printed to terminal\nExpires in 1 hour]
    F --> I[User sees: if an account exists\na link has been sent]
    H --> I
    I --> J{User clicks\nreset link}
    J -- Link expired --> K[Error: link invalid\nRedirect to forgot-password]
    J -- Valid --> L[GET /auth/reset-password/token\nEnter new password form]
    L --> M[POST new password]
    M --> N{Token still valid?\nPassword unchanged since issued?}
    N -- No --> K
    N -- Yes --> O[Password hash updated\nOld token fingerprint no longer matches\nAll future use of old token blocked]
    O --> P[User logged in automatically\nRedirect to dashboard]
```

---

## 5. User Flow — Inviting a Member

How an owner or admin invites someone and how that person joins the org.

```mermaid
flowchart TD
    A([Owner or Admin]) --> B[GET /orgs/org_id\nOrg dashboard]
    B --> C{At seat limit?}
    C -- Yes --> D[Invite form hidden\nUpgrade plan prompt shown]
    C -- No --> E[Fill in email + role\nPOST /orgs/org_id/invite]
    E --> F{Pending invite\nalready exists for this email?}
    F -- Yes --> G[Blocked: duplicate invite]
    F -- No --> H[Invitation row created\ntoken + 48h expiry]
    H --> I[Link printed to terminal]

    I --> J([Invitee receives link])
    J --> K[GET /orgs/invite/token]
    K --> L{Token valid\nand pending?}
    L -- No --> M[Error: invalid or expired]
    L -- Yes --> N{User logged in?}
    N -- Yes --> O{Email matches\ninvite email?}
    N -- No --> P[Token stored in session\nRedirect to login]
    P --> Q[User logs in or registers]
    Q --> R[process_pending_invite fires\nafter successful login]
    R --> O
    O -- No --> S[Error: wrong email address]
    O -- Yes --> T{Org still\nunder seat limit?}
    T -- No --> U[Error: seat limit reached]
    T -- Yes --> V{Already a\nmember?}
    V -- Yes --> W[Info: already a member\nInvite marked accepted]
    V -- No --> X[Membership row created\nInvite accepted_at stamped]
    X --> Y[Redirect to org dashboard]
```

---

## 6. Invitation Lifecycle — State Diagram

The three states an invitation moves through.

```mermaid
stateDiagram-v2
    [*] --> Pending : Invitation.create() called\ntoken generated, expires_at set

    Pending --> Accepted : Invitee clicks link\naccepted_at stamped\nMembership row created

    Pending --> Expired : 48 hours pass\nno action taken

    Accepted --> [*]
    Expired --> [*] : New invite can now be sent\nto the same email
```

---

## 7. Sequence Diagram — Password Reset Token Exchange

Shows the exact sequence of messages between the browser, server, and database during a password reset.

```mermaid
sequenceDiagram
    actor User
    participant Browser
    participant Server
    participant DB

    User->>Browser: Clicks "Forgot your password?"
    Browser->>Server: GET /auth/forgot-password
    Server->>Browser: Render forgot_password.html

    User->>Browser: Submits email address
    Browser->>Server: POST /auth/forgot-password
    Server->>DB: SELECT * FROM users WHERE email = ?
    DB-->>Server: User row (or nothing)

    alt Email exists and account is active
        Server->>Server: generate_reset_token(user)\nsigns {id, chk} with SECRET_KEY + salt
        Server->>Server: Print reset URL to terminal
    end

    Server->>Browser: Render same "check your email" message\nregardless of whether email existed

    User->>Browser: Clicks reset link
    Browser->>Server: GET /auth/reset-password/token
    Server->>Server: verify_reset_token(token)\ndecodes {id, chk}
    Server->>DB: SELECT * FROM users WHERE id = ?
    DB-->>Server: User row
    Server->>Server: Check user.password_hash[-8:] == chk

    alt Token valid and fingerprint matches
        Server->>Browser: Render reset_password.html form
        User->>Browser: Submits new password
        Browser->>Server: POST /auth/reset-password/token
        Server->>DB: UPDATE users SET password_hash = ? WHERE id = ?
        DB-->>Server: OK
        Server->>Server: login_user(user)\nOld token now dead — hash fingerprint changed
        Server->>Browser: Redirect to /dashboard
    else Token expired or fingerprint mismatch
        Server->>Browser: Flash error, redirect to /auth/forgot-password
    end
```

---

## 8. Sequence Diagram — Email Change Token Exchange

```mermaid
sequenceDiagram
    actor User
    participant Browser
    participant Server
    participant DB

    User->>Browser: Goes to /auth/settings → Change email
    Browser->>Server: GET /auth/change-email
    Server->>Browser: Render change_email.html

    User->>Browser: Submits new email + current password
    Browser->>Server: POST /auth/change-email
    Server->>Server: check_password(current_password)

    alt Password incorrect
        Server->>Browser: Flash error, re-render form
    else Password correct
        Server->>DB: SELECT * FROM users WHERE email = new_email
        DB-->>Server: None (email available)
        Server->>Server: generate_email_change_token(user_id, new_email)\nsigns {user_id, new_email} — new email lives in token\nnot written to DB yet
        Server->>Server: Print confirmation URL to terminal
        Server->>Browser: Flash "check your new inbox", redirect to settings
    end

    User->>Browser: Clicks confirmation link in new inbox
    Browser->>Server: GET /auth/confirm-email-change/token
    Server->>Server: verify_email_change_token(token)\ndecodes {user_id, new_email}
    Server->>Server: Check user_id matches current_user.id

    alt Token valid and user matches
        Server->>DB: SELECT * FROM users WHERE email = new_email
        DB-->>Server: None (still available)
        Server->>DB: UPDATE users SET email = new_email, email_verified = True
        DB-->>Server: OK
        Server->>Browser: Flash success, redirect to settings
    else Token invalid, expired, or email now taken
        Server->>Browser: Flash error, redirect to settings
    end
```
