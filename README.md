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

MOBILE_DEEP_LINK_URL=tourvaa://reset-password

SUPER_ADMIN_NAME=Super Admin
SUPER_ADMIN_EMAIL=admin@tourvaa.com
SUPER_ADMIN_PASSWORD=Admin@123
SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP=false

ANTHROPIC_API_KEY=sk-ant-...
```

> **Security:** Generate a strong JWT secret with `python -c "import secrets; print(secrets.token_hex(32))"` and keep `SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP=false` in production.

### 4. Create the MySQL database

Create the database named in `DATABASE_URL` before running migrations.

### 5. Run migrations

```bash
python -m alembic upgrade head
```

### 6. Start the API

```bash
uvicorn app.main:app --reload
```

API runs at `http://127.0.0.1:8000`. Interactive docs at `http://127.0.0.1:8000/docs`.

---

## Default Login

Seeded automatically on first startup:

| Field | Value |
| --- | --- |
| Email | `admin@tourvaa.com` |
| Password | `Admin@123` |

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

Seven built-in roles:

| Slug | Description |
| --- | --- |
| `super-admin` | Full platform access, no permission checks |
| `admin` | Full access via permissions |
| `sub-admin` | Access only to explicitly assigned permission modules |
| `supplier` | Own tours and bookings only |
| `agent-reseller` | Own bookings and clients only |
| `customer` | Own bookings and profile only |
| `affiliate` | Own referrals and commissions only |

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
uvicorn app.main:app --reload

# Run all tests (read-only - safe against a live DB)
venv\Scripts\python -m pytest tests/ -v

# Include destructive/write tests (creates, updates, deletes real records)
TOURVAA_WRITE_TESTS=1 venv\Scripts\python -m pytest tests/ -v

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
- [ ] Change default super admin password
- [ ] Point `DATABASE_URL` to production MySQL
- [ ] Run `alembic upgrade head` against production before first deploy
- [ ] Configure real SMTP credentials
- [ ] Set `ALLOWED_ORIGINS` to production frontend domains
- [ ] Set `APP_ENV=production` and `APP_DEBUG=false`
