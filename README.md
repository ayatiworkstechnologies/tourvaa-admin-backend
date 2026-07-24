# Tourvaa Backend

FastAPI REST API powering the Tourvaa travel platform. Provides authentication, dynamic RBAC, tour CMS, bookings/payments/invoices, customer/supplier/agent/affiliate self-service portals, cancellations, supplier ledger & payouts, notifications, chatbot, website CMS, audit logging, and role-scoped dashboards.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Framework | FastAPI |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Database | MySQL (PyMySQL driver) |
| Authentication | JWT via python-jose |
| Password Hashing | Bcrypt via Passlib |
| Validation | Pydantic v2 |
| File Uploads | python-multipart |
| PDF Generation | ReportLab (invoices) |
| Email | SMTP (smtplib) |
| AI Chatbot | Anthropic SDK |

---

## Setup

### 1. Create and activate a virtual environment

```bash
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # macOS / Linux
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create `backend/.env`

```env
APP_NAME=Tourvaa Backend
APP_ENV=development
APP_DEBUG=true

DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/DATABASE_NAME

JWT_SECRET_KEY=replace_with_a_strong_random_secret_32_chars_minimum
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

API_BASE_URL=http://127.0.0.1:8000
FRONTEND_URL=http://localhost:3000
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000

SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your@email.com
SMTP_PASSWORD=your_smtp_password
SMTP_FROM_NAME=Tourvaa
SMTP_FROM_EMAIL=no-reply@yourdomain.com
SMTP_REPLY_TO=support@yourdomain.com
SMTP_USE_SSL=true
SMTP_STARTTLS=false
SMTP_TIMEOUT_SECONDS=20

MOBILE_DEEP_LINK_URL=tourvaa://reset-password

SUPER_ADMIN_NAME=Super Admin
SUPER_ADMIN_EMAIL=admin@tourvaa.com
SUPER_ADMIN_PASSWORD=replace_with_a_unique_strong_password
SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP=false

ANTHROPIC_API_KEY=sk-ant-...
```

> **Security:** Generate a strong JWT secret with `python -c "import secrets; print(secrets.token_hex(32))"`. Use a unique production super-admin password and keep `SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP=false` after bootstrap.

### 4. Create the MySQL database

Create the database named in `DATABASE_URL` before running migrations.

### 5. Run migrations

```bash
python -m alembic upgrade head
python -m alembic current
```

The current schema head is `20260724_0038`. Revision `0038` idempotently backfills `supplier_vehicles.vehicle_type`/`registration_number` for any database that was bootstrapped purely through the migration chain (these columns were added to the model without ever getting a migration -- see the troubleshooting section below). Revision `0037` adds supplier commission-request staging fields (`suppliers.commission_request_*`, mirroring the existing agent commission-request flow) and a `supplier_payouts.paid_by` audit column. Revision `0036` repairs verification metadata only for legacy supplier accounts that were already approved, active, and password-enabled.

Seed or synchronize roles and permissions without deleting application data:

```powershell
$env:PYTHONUTF8="1"
python -m scripts.reset_seed_admin_rbac
```

Never use `--reset` against a database containing data you need to retain.

### 6. Start the API

```bash
python -m scripts.dev_server
```

API runs at `http://127.0.0.1:8000`. Interactive docs at `http://127.0.0.1:8000/docs`.

The dev server scopes auto-reload to `app/` and `alembic/`, ignoring `venv/`, `backups/`, caches, tests, SQL dumps, and seed scripts. This prevents noisy shutdown/restart cycles while running database cleanup or seed commands. To run without reload:

```bash
python -m scripts.dev_server --no-reload
```

---

## Super-admin Bootstrap

Startup and the RBAC seed create the configured super-admin when it does not exist. Credentials come from `SUPER_ADMIN_EMAIL` and `SUPER_ADMIN_PASSWORD`; the seed command no longer prints the password.

For an existing super-admin, the password is changed from configuration only when `SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP=true`. Keep that setting `false` in production except during an intentional, controlled password recovery.

---

## Email Delivery

All SMTP sends go through `app/utils/mailer.py`. The mailer writes progress to `email_logs` with `sending`, `sent`, or `failed`, sends both plain-text and HTML bodies, and adds standard headers like `Date`, `Message-ID`, `Reply-To`, and `X-Mailer`.

Admins can inspect recent delivery attempts through:

```bash
GET /api/email-logs?status=failed
GET /api/email-logs?search=user@example.com
```

For production inbox delivery, configure the SMTP account and DNS for the same sender domain:

- `SMTP_FROM_EMAIL` should be a real mailbox or verified sender on your domain.
- SPF must include the SMTP provider.
- DKIM must be enabled in the SMTP provider and published in DNS.
- DMARC should exist for the domain, starting with `p=none` while testing.
- `SMTP_REPLY_TO` should be a monitored support address.
- Use `SMTP_USE_SSL=true` for port `465`, or `SMTP_USE_SSL=false` and `SMTP_STARTTLS=true` for port `587`.

Code can record send progress, but inbox vs spam is ultimately decided by DNS authentication, domain reputation, message content, and recipient behavior.

---

## Project Structure

Layer-based architecture - code is organized by technical concern rather than by feature module:

```text
app/
├── main.py                    Entry point, middleware + router registration
├── seed.py                    First-run super admin / role / permission seeding
├── config/                    Pydantic settings (reads .env)
├── database/                  SQLAlchemy engine and session
├── auth/
│   ├── security.py            JWT encode/decode, password hashing
│   └── permissions.py         get_current_user, permission-check dependencies
├── middleware/
│   ├── cors.py                CORS configuration
│   └── error_handlers.py      Global exception handlers
├── api/
│   └── router.py              Aggregates and mounts all routers under /api
├── routers/                   One file per resource - HTTP layer only (request/response, no business logic)
├── schemas/                   Pydantic request/response models, one file per resource
├── services/                  Business logic, one file per resource - called by routers
├── models/                    SQLAlchemy ORM models, one file per resource
└── utils/                     Shared helpers: money, pagination, response envelope,
                                rate limiting, mailer, ImageKit client, invoice PDF
                                generation, notification triggers, crypto, misc operations
```

Each resource (e.g. `bookings`) follows the same four-file pattern: `routers/bookings.py` → `services/bookings.py` → `schemas/bookings.py` → `models/bookings.py`.

Resources currently implemented: `auth`, `users`, `roles`, `permissions`, `dashboard`, `customers` (+ `customers_portal` self-service), `suppliers` (+ ledger, payouts), `agents`, `affiliates` (+ tracking), `cms` (+ geo, geo-seed), `tours` (+ `tour_versions`), `bookings` (+ `booking_calendar`), `cancellations`, `payments` (+ `payments_gateway`), `invoices`, `checkout`, `notifications`, `chatbot`, `email_templates`, `settings`, `admin_modules`, `profile`, `uploads`, `private_documents`, `sessions`, `reports`, `audit`, `website_cms`, `client` (public/external API), `public`.

---

## API Endpoints

All endpoints are mounted under `/api`. Full interactive reference: `/docs` (Swagger) or `/redoc`.

### Auth - `/api/auth`

| Method | Path | Description |
| --- | --- | --- |
| POST | `/register` | User registration |
| POST | `/register/supplier` | Supplier self-registration |
| POST | `/register/agent` | Agent self-registration |
| POST | `/login` | Login (rate limited: 10/min) |
| GET | `/me` | Current user session |
| POST | `/forgot-password` | Request password reset (rate limited: 5/5min) |
| POST | `/reset-password` | Reset password with token |
| GET | `/reset-password/validate` | Validate reset token |
| POST | `/refresh-token` | Refresh JWT access token |
| POST | `/verify-email` | Verify email address |
| GET | `/login-history` | User login history |
| POST | `/force-logout` | Force logout other sessions |

### Admin user account lifecycle

These endpoints require `update-users`:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/users/{user_id}/activate` | Complete first-time admin activation after registration requirements are satisfied |
| POST | `/api/users/{user_id}/deactivate` | Set the account inactive, record a reason, and revoke existing sessions |
| POST | `/api/users/{user_id}/reactivate` | Restore a previously deactivated account without changing its role or supplier operational approval |

Account state is intentionally separate from supplier operational approval:

- Email verification and password creation control whether a portal account is eligible for activation.
- `account_status=ACTIVE` and `is_active=true` allow sign-in.
- `suppliers.approval_status=APPROVED` unlocks supplier operational modules.
- Deactivation sets both the user and role profile inactive and increments `token_version`.
- Reactivation restores sign-in, activates the role profile, records history/audit data, and leaves supplier approval unchanged.
- The last active super-admin cannot be deactivated.

### Self-service portals

| Base Path | Description |
| --- | --- |
| `/api/customer/*` | Profile, travellers, bookings, cancellations, invoices, payments, messages, change-password |
| `/api/suppliers/me/*` | Profile, vehicles CRUD, commission requests |
| `/api/supplier/*` | Booking accept/decline/complete/cancel/postpone/notify, status history, messages |
| `/api/agents/me` | Profile |
| `/api/agent/*` | Messages (bookings/customers/invoices reuse the shared admin endpoints, row-scoped by role server-side) |

### Bookings - `/api/bookings`

Calculate-price, assign-supplier, cancel-request, calendar-event get/download, calendar-sync, status-history, payment-link, communications + replies, export, status updates.

#### Core booking lifecycle

1. A new booking starts in `pending_payment`.
2. Payment authorization creates an active hold. An assigned booking moves to `pending_supplier_acceptance`; an unassigned booking moves to `payment_authorized`.
3. Supplier acceptance confirms the booking, captures authorized funds, generates the invoice, updates the supplier ledger, and notifies the admin and customer.
4. Supplier decline marks the booking as `declined`, voids active payment holds or refunds captured funds, releases reserved calendar seats, and sends notifications.
5. Supplier decisions are idempotent and final: retrying the same decision is safe, while reversing an accepted or declined decision returns HTTP `409`.

A paid booking with a pending supplier decision remains `pending_supplier_acceptance`; payment synchronization cannot bypass supplier approval.

### Payments - `/api/payments`

Authorize, capture, void, refund, status updates, gateway test/simulate, gateway status, per-customer listing.

### Invoices - `/api/invoices`

Generate, generate-pdf, email, download (GST invoice PDF with tour name, traveller names, and payment method), detail/list.

### Dashboard - `/api/dashboard`

| Method | Path | Description | Auth |
| --- | --- | --- | --- |
| GET | `/me` | Role-specific profile, sidebar, modules, approval status | All roles |
| GET | `/summary` | Stats cards scoped to caller's role | All roles |
| GET | `/charts` | Chart data scoped to caller's role | All roles |
| GET | `/recent-activities` | Activity log scoped to caller's role | All roles |
| GET | `/alerts` | Alerts scoped to caller's role | All roles |
| GET | `/bookings` | Booking analytics | Admin+ |
| GET | `/revenue` | Revenue analytics | Admin+ |
| GET | `/payments` | Payment summary | Admin+ |
| GET | `/reports` | Reports summary | Admin+ |

### CMS - `/api`

Countries, cities, tour categories, tour subcategories, tours (CRUD + pricing + calendar + discounts + versions), CMS geo reference data, popular tours, website CMS content blocks.

### Customers / Suppliers / Agents / Affiliates (admin side)

Standard CRUD + approve/reject/partial-approve + block/unblock + markup/discount/commission settings + communications, under `/api/customers`, `/api/suppliers`, `/api/agents`, `/api/affiliates`.

### Other Modules

| Module | Base Path | Description |
| --- | --- | --- |
| Roles | `/api/roles` | Role CRUD + permission assignment |
| Permissions | `/api/permissions` | Permission CRUD |
| Settings | `/api/settings` | General / system / payment / API integration settings |
| Email Templates | `/api/email-templates` | CRUD |
| Cancellations | `/api/cancellations` | Cancellation requests + refund workflow |
| Supplier Ledger | `/api/supplier-ledger` | Ledger entries, payouts |
| Notifications | `/api/notifications` | List, mark-all-read, retry, push subscribe/broadcast |
| Sessions | `/api/sessions` | Active sessions, revoke, force-logout, expire-inactive |
| Reports | `/api/reports` | Snapshot reporting |
| Audit | `/api/audit-logs` | Audit log listing + export |
| Chatbot | `/api/chatbot` | AI assistant (Anthropic-backed) |
| Profile | `/api/profile` | View / update profile, change password |
| Uploads | `/api/uploads` | Profile images, admin assets |
| Private Documents | `/api/private-documents` | Signed/authenticated document access |
| Checkout | `/api/checkout` | Public booking checkout flow |
| Client API | `/api/client` | Public/external client API |
| Public | `/api/public` | Public-facing settings and content |

---

## Roles & Permissions

Six built-in roles:

| Slug | Description |
| --- | --- |
| `super-admin` | Full platform access, no permission checks |
| `admin` | Full access via permissions |
| `sub-admin` | Access only to explicitly assigned permission modules |
| `supplier` | Own tours and bookings only |
| `agent-reseller` | Own bookings and clients only |
| `customer` | Own bookings and profile only |

Permission format: `{module}.{action}` (e.g. `dashboard.view`, `bookings.view`) or legacy `view-{module}` - both supported via `expand_permission_slugs()`.

---

## Tests

37+ test modules, ~390+ test functions, run against a live dev server at `http://127.0.0.1:8000/api`.

Install the development test dependencies once:

```bash
pip install -r requirements-dev.txt
```

```bash
# Start the server first (separate terminal)
python -m scripts.dev_server

# Run all tests (read-only - safe against a live DB)
venv\Scripts\python -m pytest tests/ -v

# Include destructive/write tests (PowerShell; creates, updates, deletes records)
$env:TOURVAA_WRITE_TESTS="1"
venv\Scripts\python -m pytest tests/ -v

# Run a specific test file
venv\Scripts\python -m pytest tests/test_35_customer_portal.py -v
```

Audit the complete OpenAPI surface for duplicate routes, route shadowing, and server errors without changing real records:

```bash
venv\Scripts\python scripts/audit_api.py

# Also exercise every GET endpoint using the configured super-admin account
venv\Scripts\python scripts/audit_api.py --authenticated-reads
```

Coverage by area: core health & auth (`test_01`–`test_03`), dashboard & settings (`test_04`–`test_05`), customers/suppliers/agents/affiliates admin CRUD (`test_06`–`test_09`), geo & tour CMS (`test_10`–`test_18`), uploads (`test_19`), bookings/payments/invoices/communications (`test_20`–`test_24`), notifications/reports/sessions (`test_25`), handover guards & state machine (`test_26`), geo reference & public settings (`test_27`–`test_28`), chatbot (`test_29`), cancellations & payouts (`test_30`–`test_32`), website CMS & tour versions (`test_33`–`test_34`), and self-service portals for customer/supplier/agent (`test_35`–`test_37`).

Write/destructive tests are gated behind `TOURVAA_WRITE_TESTS=1` so a default run never mutates data.

---

## Production Checklist

- [ ] Set `JWT_SECRET_KEY` to a strong random secret (32+ chars)
- [ ] Set `SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP=false`
- [ ] Set a unique super-admin password and verify the admin login
- [ ] Point `DATABASE_URL` to production MySQL
- [ ] Back up the database, run `alembic upgrade head`, and confirm `alembic current` reports `20260724_0038`
- [ ] Run the RBAC seed without `--reset`
- [ ] Configure real SMTP credentials
- [ ] Set `ALLOWED_ORIGINS` to production frontend domains
- [ ] Set `APP_ENV=production` and `APP_DEBUG=false`

### First Production Database Cleanup

Use this only when preparing an existing database for first production use. The cleanup keeps migrations, the configured active super-admin, RBAC, geo reference data, app/payment/API settings, email templates, and tour category masters. It removes transactional, portal-user, catalogue, communication, audit, and session data, then runs the RBAC seed again.

1. Confirm `.env` points to the intended production database and `SUPER_ADMIN_EMAIL` belongs to the active `super-admin`.

2. Apply migrations and confirm the schema is current:

   ```powershell
   python -m alembic upgrade head
   python -m alembic current
   ```

3. Preview the cleanup plan. This is a dry run and does not change rows:

   ```powershell
   python -m scripts.prepare_live_database
   ```

4. Review the printed `PRESERVE COMPLETELY`, `PRESERVE FILTERED`, and `CLEAR` sections.

5. Execute only after the dry-run inventory is approved:

   ```powershell
   python -m scripts.prepare_live_database --execute --backup --confirm PREPARE-LIVE
   ```

The execution command creates a SQL backup under `backups/` before clearing data. It fails closed unless both `--backup` and `--confirm PREPARE-LIVE` are present.

After cleanup, start the API normally. Startup also seeds RBAC and email templates when the schema is ready:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

To resync RBAC later without clearing production data:

```powershell
python -m scripts.reset_seed_admin_rbac
```

---

## Live/Production Troubleshooting

### A live endpoint returns 500 with a generic message

`app/middleware/error_handlers.py`'s catch-all handler always returns `{"status": "error", "message": "An unexpected error occurred. Please try again later."}` for any unhandled exception, on purpose — the client never sees internals. That means the JSON response alone never tells you the real cause. Before guessing:

1. **Read the real traceback from the server logs**, not the HTTP response. The handler does `logger.exception(...)` before returning the generic body, so the actual exception (including the SQL error, if any) is in stdout/stderr wherever the process logs to (PM2: `pm2 logs tourvaa-admin-backend --err --lines 100`, or the log files directly, e.g. `/root/.pm2/logs/tourvaa-admin-backend-error.log`).
2. **If the traceback mentions a missing table or column** (`Table '...' doesn't exist`, `Unknown column '...'`), the deployed database schema is behind the deployed code — the app was updated but `alembic upgrade head` was not run against the database this environment actually points at. Run `python -m alembic current` and compare it against the latest revision in `alembic/versions/` (or `python -m alembic heads`); if they differ, back up the database and run `python -m alembic upgrade head`.
3. **`alembic current` already reports `head` but the column is still missing anyway** (this happened for real with `supplier_vehicles.vehicle_type`/`registration_number` — see revision `0038`): that means a column was added directly to a SQLAlchemy model in `app/models/` without a migration ever being written for it. Any database bootstrapped purely by running the migration chain from scratch will be missing it forever, no matter how many times you run `alembic upgrade head`, because there is nothing in the migration history that adds it. `alembic current` reporting `head` only proves every *known* migration ran -- it says nothing about whether the models and the migration history have actually stayed in sync. The fix is a new migration (guard each `op.add_column` with an inspector `_has_column` check like `0038` does, so it's safe to run against environments that already have the column some other way, e.g. local dev DBs that were bootstrapped differently).
4. **This is a recurring failure class in this codebase, not a one-off**: several endpoints call a shared serializer (e.g. `serialize_supplier`) that reads a relationship or column added by a migration newer than the one applied to that environment's database. The fix is always the same — apply the pending migration — not a code change, unless the endpoint needs a defensive fallback to degrade gracefully while a migration rollout is in progress (see `_approval_history()` in `app/services/suppliers.py` for the pattern: catch `sqlalchemy.exc.SQLAlchemyError` around the specific lazy-loaded relationship, log it, and return an empty/degraded value instead of letting the whole request 500).
5. **Confirm the fix live** by re-requesting the endpoint and checking the access log for `200` instead of `500` (PM2: `pm2 logs tourvaa-admin-backend --out --lines 30`).

### PM2: `OSError: [Errno 98] Address already in use` / a process keeps crash-looping

This means two PM2-managed processes are trying to bind the same port — almost always a duplicate app entry, `pm2 start` run a second time without deleting the first, or `ecosystem.config.js` misconfigured (e.g. `instances` set higher than intended in fork mode). Diagnose before restarting anything:

```bash
pm2 list                                   # look for more than one entry for this app, or unexpected restart counts
pm2 describe tourvaa-admin-backend         # confirms script path, port, exec mode, instance count
cat ecosystem.config.js                    # check for a duplicate `apps:` entry or `instances` > 1 in fork mode
```

Once you know which process id is the stale/duplicate one:

```bash
pm2 delete <id>                            # remove the duplicate/zombie entry, not the one actually serving traffic
pm2 restart tourvaa-admin-backend          # restart the real app cleanly
pm2 save                                   # persist the corrected process list so a server reboot doesn't resurrect the duplicate
```

Verify with `pm2 list` that exactly one process remains for this app and its status is `online` with a low/zero restart count before moving on.
