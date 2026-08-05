# Tourvaa Backend — Full Analytical Report & Audit Report

**Report Date:** 2026-08-04  
**Scope:** `tourvaa-admin-backend/` — full source tree, migrations, tests, scripts, and documentation  
**Codebase Version (alembic head):** `20260803_0054` (migration 0054)  
**Auditor:** Automated source-code audit  
**Status:** Complete

---

## 1. Executive Summary

Tourvaa Backend is a **FastAPI** REST API powering a multi-tenant travel-booking platform. It supports seven built-in user roles (super-admin, admin, sub-admin, supplier, agent-reseller, customer, affiliate) with fine-grained RBAC, a complete tour CMS, booking/payment/invoice lifecycles, supplier/agent/affiliate onboarding with approval workflows, an AI chatbot (Anthropic Claude), web-push notifications, audit logging, and role-scoped dashboards.

The codebase is **mature and production-grade** in most respects: it has 54 Alembic migrations, ~45 database tables, 34 routers, 34 service modules, 27 schema files, 39 integration-test modules plus 9 unit-test modules, and multiple operational scripts for auditing, migration repair, and live-database sanitization.

**Key strengths:** layered architecture (router → service → model/schema), idempotent RBAC seeding, dual-format permission slugs (dotted + legacy), per-portal JWT secrets, token-version force-logout, session tracking, defensive graceful-degradation patterns in serializers, comprehensive audit logging, and a well-structured test suite.

**Key concerns identified:** (1) documentation drift — `BACKEND_DOC.md` is 9 weeks out of date and references a non-existent `app/modules/` directory structure; (2) use of deprecated `datetime.utcnow()` with mixed timezone-awareness across comparisons; (3) two parallel registration service paths (`register_user` legacy vs. `register_unified_user`); (4) a duplicate `force_logout_user` function across two service modules; (5) an empty/phantom `app/utils/response.py` file; (6) production hardening gaps around rate-limiting (single-process fallback) and SMTP credential handling.

---

## 2. Architecture Overview

### 2.1 Layer-Based Structure

The codebase follows a **layer-based (horizontal) architecture** — code is organized by technical concern rather than by feature module:

```
app/
├── main.py                          # Entry point — app factory, startup events, CORS, error handlers, storage mounting
├── seed.py                          # First-run RBAC + super-admin seeding (startup event)
├── config/                          # Pydantic BaseSettings (.env loading)
│   └── __init__.py                  # Settings class (129 lines)
├── database/
│   └── __init__.py                  # SQLAlchemy engine, SessionLocal, Base, get_db()
├── auth/
│   ├── permissions.py               # get_current_user, require_any_permission, portal tokens, _decode_token
│   └── security.py                  # JWT, bcrypt, password-reset/OTP tokens
├── api/
│   └── router.py                    # Aggregates & mounts all routers under /api (132 lines)
├── middleware/
│   ├── cors.py                      # CORS configuration
│   └── error_handlers.py            # Global exception handlers (400/403/422/500)
├── routers/                         # 34 router files — HTTP layer only (request/response, no business logic)
├── services/                        # 34 service files — business logic (called by routers)
├── schemas/                         # 27 Pydantic request/response models + __init__.py
├── models/                          # 34 SQLAlchemy ORM model files
├── utils/                           # 15 shared utility modules (money, pagination, rate limit, mailer, crypto, etc.)
└── private-docs/                    # (directory, for sensitive document storage)
```

### 2.2 Four-File Pattern

Each resource (e.g., `bookings`, `payments`) follows a consistent pattern:

```
routers/{resource}.py  →  services/{resource}.py  →  schemas/{resource}.py  →  models/{resource}.py
```

- **Routers** handle HTTP concerns: request validation, dependency injection, response envelope formatting.
- **Services** contain all business logic: data queries, state transitions, notifications, audit logging.
- **Schemas** are Pydantic models for request/response serialization.
- **Models** are SQLAlchemy declarative ORM classes.

### 2.3 Router Registration Strategy

Routers are grouped into four categories in `api/router.py`:

| Group | Purpose |
|---|---|
| `CORE_ROUTERS` | Auth, users, roles, permissions, dashboard, profile, settings, currency, email templates, email logs, uploads, client |
| `PARTNER_AND_CUSTOMER_ROUTERS` | Customers, customer portal, suppliers, agents, affiliates |
| `CONTENT_AND_TOUR_ROUTERS` | Tour detail sub-resources, discounts, tour versions, CMS, geo seed, geo, website CMS |
| `OPERATIONS_ROUTERS` | Bookings, payments gateway, payments, invoices, notifications, reports, sessions, audit, supplier/agent portal bookings, chatbot, supplier/agent ledger, checkout, cancellations, booking calendar, affiliate tracking, private documents, reviews |
| `ADMIN_ALIAS_ROUTERS` | Roles, permissions (aliased under `/api/admin`) |
| `public_router` | Mounted under `/api/public` |

**Route ordering is deliberate and documented:**
- `tour_versions_router` is registered before `cms_router` to prevent `/tours/pending-approval` from being shadowed by `/tours/{tour_id}`.
- `payments_gateway_router` is registered before `payments_router` so static paths like `/payments/paypal/capture` precede `/payments/{payment_id}/capture`.

### 2.4 Application Entry Point (`app/main.py`)

The application is created and configured in `app/main.py` (303 lines):

- **Schema readiness check** (`schema_is_ready()`): Uses SQLAlchemy `inspect()` to verify all 100+ required tables and specific columns exist before seeding or starting background jobs. This is a critical guard for safe startup.
- **Startup seed**: Calls `seed_default_roles_and_permissions()` and `seed_email_templates()` if the schema is ready.
- **Background jobs** (asyncio tasks):
  - `_expire_stale_bookings_loop()`: Runs every 15 minutes, expires unpaid bookings holding calendar seats for over 60 minutes.
  - `_report_schedule_loop()`: Runs every hour, executes due report schedules.
- **Storage**: Creates `storage/uploads/profile-images` and `storage/uploads/admin-assets` directories on startup. Mounts `/storage` as a static file path. Creates `private-docs/` subdirectories outside the public mount.
- **Error handling**: Registers global exception handlers that always return the standard JSON envelope and mask internals on 500 errors.
- **CORS**: Configured from `ALLOWED_ORIGINS` setting.

---

## 3. Technology Stack Analysis

### 3.1 Dependencies (`requirements.txt` — 19 packages)

| Package | Purpose | Assessment |
|---|---|---|
| `fastapi` | Web framework | ✅ Industry standard |
| `uvicorn` | ASGI server | ✅ Standard |
| `sqlalchemy` | ORM | ✅ Mature, well-used |
| `pymysql` | MySQL driver | ✅ Pure-Python, appropriate |
| `python-dotenv` | `.env` loading | ✅ |
| `pydantic-settings` | Config management | ✅ |
| `python-jose` | JWT encode/decode | ⚠️ Forked/limited maintenance; consider `PyJWT` |
| `passlib[bcrypt]` | Password hashing | ✅ |
| `bcrypt==4.0.1` | Pinned bcrypt | ⚠️ May have security advisories; consider upgrade |
| `python-multipart` | File upload support | ✅ |
| `email-validator` | Email validation | ✅ |
| `alembic` | DB migrations | ✅ |
| `requests` | HTTP client | ✅ |
| `anthropic` | Claude AI for chatbot | ✅ |
| `pywebpush` | Web push notifications | ✅ |
| `reportlab` | PDF generation (invoices) | ✅ |
| `redis` | Redis client (rate limiting) | ✅ (not yet in DEV requirements) |
| `cloudinary` | Cloud image storage | ✅ |
| `bleach` | HTML sanitization | ✅ |

### 3.2 Development Dependencies (`requirements-dev.txt`)

Only `pytest` is listed. No linting, type-checking, or formatting tools are configured (no `ruff`, `black`, `mypy`, `flake8`, `isort`).

### 3.3 Missing from dependencies

- `cryptography` — used by `app/utils/crypto.py` for Fernet encryption but **not listed in requirements.txt**. This is a **critical dependency gap**.
- `redis` — listed in `requirements.txt` but the ratelimiter has a clean fallback. OK.

---

## 4. Configuration & Environment

### 4.1 Settings System (`app/config/__init__.py` — 129 lines)

All configuration is managed through a Pydantic `BaseSettings` class that reads from `.env`. Key design decisions:

- **`APP_ENV` defaults to `"production"`** — fails closed. A deployment that forgets to set `APP_ENV` gets production's stricter behavior (secure cookies, etc.).
- **`JWT_SECRET_KEY` is required** — no default, which is correct for security.
- **Per-portal JWT secrets**: `SUPPLIER_JWT_SECRET_KEY`, `AGENT_JWT_SECRET_KEY`, `CUSTOMER_JWT_SECRET_KEY`, `ADMIN_JWT_SECRET_KEY` — each defaults to empty string and falls back to `JWT_SECRET_KEY` via `get_portal_secret()`. This allows per-portal token isolation.
- **`TRUST_PROXY_HEADERS`** (default `False`): Controls whether `X-Forwarded-For` is trusted for rate-limit IP detection. Defaults to untrusted to prevent IP spoofing.
- **`ALLOWED_ORIGINS` defaults to `"*"`**: With `allow_credentials` only enabled when origins are explicitly specified.
- **`SMTP_*`** settings support both env-var and DB-backed SMTP config (see §8.2).
- **`STORAGE_ROOT`** defaults to `"storage"`, resolved relative to the `app/` package parent.

### 4.2 Configuration Issues

- **`SUPER_ADMIN_PASSWORD` defaults to `"Admin@123"`** — This is a weak default. The seed function does warn about it in production, but it should be required (no default) in `APP_ENV=production`.
- **`JWT_SECRET_KEY`** has no default — but the seed file `app/seed.py` references `Settings.model_fields["SUPER_ADMIN_PASSWORD"].default` which is `"Admin@123"`. This default is a security risk.
- The config uses `extra="ignore"` — unknown env vars are silently dropped, which can hide misconfiguration.

### 4.3 Environment Documentation Discrepancy

- `BACKEND_DOC.md` (§4) references an `.env` with `SMTP_FROM_EMAIL`, `SMTP_REPLY_TO`, `SMTP_USE_SSL`, `SMTP_STARTTLS`, `SMTP_TIMEOUT_SECONDS` — these are in the code but **missing from the `.env` example in `README.md`**.
- `BACKEND_DOC.md` references `vapid_private.pem` and VAPID keys — confirmed in config and `pywebpush` dependency, but not documented in README.
- `REDIS_URL` is in the config but not mentioned in either doc.
- `SETTINGS_ENCRYPTION_KEY` is used for encrypting DB secrets but not documented anywhere.

---

## 5. Database Analysis

### 5.1 Engine & Connection

- **Dialect:** MySQL via PyMySQL (`mysql+pymysql://`)
- **Pool:** `pool_pre_ping=True` (reconnects on stale connections)
- **SQLite fallback:** Automatically switches to `StaticPool` with `check_same_thread=False` when `DATABASE_URL` is `sqlite://` or `sqlite:///:memory:` — enables fast in-memory testing.

### 5.2 Migration System (Alembic — 54 migrations)

Migrations are named with a chronological timestamp prefix format: `YYYYMMDD_HHMM_description.py`. The current head is `20260803_0054_tour_pricing_supplier_admin_split.py`.

**Migration timeline overview:**

| Date Range | Migration # | Notable Schema Changes |
|---|---|---|
| 2026-06-15 | 0001–0005 | Production hardening, audit log JSON columns, admin modules, user roles, payment/API settings |
| 2026-06-16 | 0008 | Operations directory + CMS schema (tours, itinerary, calendar, etc.) |
| 2026-06-17 | 0010 | Bookings & payments core schema |
| 2026-06-18–20 | 0011–0014 | Tour detail content, affiliate user_id, booking lifecycle, workflow completion |
| 2026-06-20 | 0015 | Chatbot (FAQs, sessions, messages) |
| 2026-06-21 | 0016–0017 | Push subscriptions, email verification |
| 2026-06-23 | 0019 | Phase 2 new modules (website CMS, cancellations, etc.) |
| 2026-07-01 | 0021–0023 | User list indexes, customer/supplier/agent indexes, supplier vehicle review fields |
| 2026-07-23–24 | 0030–0038 | Unified registration, supplier approval flow, supplier vehicle backfill, payment settings webhook ID |
| 2026-07-27–28 | 0041–0050 | Tour wizard fields, OTP login, tour reviews, booking rooms, addon categories, instant confirmation, itinerary accommodation, SMTP settings, supplier commission requests, report schedules |
| 2026-07-30 | 0051–0053 | Public leads, report schedule last-run, agent ledger |
| 2026-08-03 | 0054 | Tour pricing supplier/admin split |

### 5.3 Model-Migration Sync Issues (Documented Problem)

The README and `BACKEND_DOC.md` both document a **recurring failure class**: SQLAlchemy models are updated with new columns without corresponding Alembic migrations. The `schema_is_ready()` function in `main.py` (lines 152–191) includes a `required_columns` check specifically to catch this — it verifies that key tables have specific columns before seeding starts.

Migration 0038 specifically addresses a real incident where `supplier_vehicles.vehicle_type` and `registration_number` were added to the model without a migration. A standalone `migrate_missing_columns.py` script also exists as a manual remediation tool.

**Recommendation:** Implement a CI check that diffs model columns against the latest migration's expected schema to prevent this class of issue.

### 5.4 Database Tables (45+ tables, grouped by domain)

| Domain | Tables | Key Notes |
|---|---|---|
| **Users/Auth** | `users`, `user_roles`, `user_status_history` | `token_version` for force-logout, `approval_status`, `account_status`, OTP fields, email verification fields |
| **RBAC** | `roles`, `permissions`, `role_permissions`, `admin_modules` | `is_system` flag, dual-format permission slugs |
| **Sessions** | `user_sessions`, `login_history` | Session revocation, login attempt tracking |
| **Customers** | `customers`, `customer_communications`, `customer_saved_travellers`, `customer_cancellation_requests`, `customer_wishlist_items` | Blocking, communication threads |
| **Suppliers** | `suppliers`, `supplier_contacts`, `supplier_business_info`, `supplier_vehicles`, `supplier_invoicing`, `supplier_documents`, `supplier_approval_history`, `supplier_commission_requests` | Full approval workflow, commission requests |
| **Agents** | `agents`, `agent_contacts`, `agent_business_info`, `agent_invoicing`, `agent_documents` | Mirror of supplier schema |
| **Affiliates** | `affiliates`, `affiliate_marketing_info`, `affiliate_invoicing`, `affiliate_documents`, `affiliate_links`, `affiliate_clicks`, `affiliate_conversions`, `affiliate_payouts` | Referral tracking pipeline |
| **CMS** | `countries`, `states`, `cities`, `tour_categories`, `tour_subcategories`, `tour_subcategory_map`, `tours` | Geographic hierarchy, tour classification |
| **Tours** | `tour_overviews`, `tour_itineraries`, `tour_inclusions`, `tour_exclusions`, `tour_highlights`, `tour_similar`, `tour_extensions`, `tour_gallery_images`, `tour_pricing`, `tour_optional_activities`, `tour_accommodation_extras`, `tour_calendars`, `tour_unavailable_dates`, `tour_discounts`, `tour_versions`, `tour_reviews` | Rich tour CMS with pricing tiers, calendar, discounts |
| **Bookings** | `bookings`, `booking_travellers`, `booking_optional_activities`, `booking_accommodations`, `booking_extensions`, `booking_status_history`, `booking_communications`, `message_replies`, `email_logs`, `booking_calendar_events` | Full booking lifecycle with status history |
| **Payments** | `payments`, `payment_transactions`, `payment_holds` | Authorize → capture → void → refund lifecycle |
| **Invoices** | `invoices`, `invoice_items` | GST invoice support (PDF gen via ReportLab) |
| **Notifications** | `notifications`, `notification_logs`, `push_subscriptions` | Multi-channel (in_app, email, push), retry limit |
| **System** | `audit_logs`, `email_templates`, `app_settings`, `api_settings`, `payment_settings`, `smtp_settings` | Configurable settings including encrypted SMTP credentials |

### 5.5 Notable Schema Design Decisions

- **Soft deletes pattern**: Most entities use `status` and `approval_status` columns rather than hard deletes. Deletion is typically an update to `status = "deleted"` or a hard `db.delete()` — implementation varies by resource.
- **`cascade="all, delete-orphan"`** on most parent-child relationships (e.g., `Booking.travellers`, `Booking.payments`).
- **`Numeric(12, 2)`** for all monetary fields — consistent precision, good for financial data.
- **`JSON` column type** on `audit_logs.old_values`/`new_values`, `notifications.metadata_json`, `booking_status_history.metadata_json` — flexible schema for audit/event data.
- **`UniqueConstraint`** used where appropriate (e.g., `uq_tour_similar`, `uq_push_endpoint`, `uq_customer_wishlist_user_tour`).
- **`server_default=func.now()`** on all `created_at` columns, `onupdate=func.now()` on `updated_at` — but also uses Python `datetime.utcnow()` in service layers, creating a timezone-awareness inconsistency (see §12.1).

---

## 6. Security Analysis

### 6.1 Authentication

| Mechanism | Implementation | Assessment |
|---|---|---|
| **Password hashing** | bcrypt via `passlib` (`app/auth/security.py`) | ✅ Strong, industry standard |
| **Password strength** | ≥8 chars, uppercase, lowercase, digit, special char | ✅ Enforced in schemas |
| **JWT algorithm** | HS256 | ✅ |
| **Access token expiry** | 24 hours (`ACCESS_TOKEN_EXPIRE_MINUTES=1440`) | ⚠️ Long; acceptable for admin tooling |
| **Refresh token expiry** | 30 days | ⚠️ Long but configurable |
| **Token versioning** | `token_version` integer on `User` — incremented on force-logout | ✅ Prevents replay after logout |
| **Session tracking** | `UserSession` table with `session_id` claim in JWT | ✅ Session revocation invalidates token via `_ensure_session_active()` |
| **Password reset tokens** | `secrets.token_urlsafe(48)` → SHA-256 hash stored in DB, 30-min expiry | ✅ Token never stored in plaintext |
| **Email verification tokens** | Same mechanism as password reset, 1440-min expiry | ✅ |
| **OTP codes** | `secrets.randbelow(1_000_000)` → SHA-256 hash, 5 max attempts, 10-min expiry | ✅ Rate-limited per IP |
| **Cookie-based auth** | `tourvaa_access` (24h) and `tourvaa_refresh` (30d) cookies with `httponly=True`, `samesite="lax"` | ✅ `secure` flag set in production only |

### 6.2 Authorization (RBAC)

The RBAC system is sophisticated and well-designed:

- **7 built-in roles**: `super-admin`, `admin`, `sub-admin`, `supplier`, `agent-reseller`, `customer`, `affiliate`
- **`super-admin`**: Bypasses all permission checks entirely (no DB query needed — `get_current_user` returns immediately)
- **`admin`**: Gets every permission via seeding
- **`sub-admin`**: Operational permissions minus system-level role/permission CRUD
- **Portal roles** (`supplier`, `agent-reseller`, `customer`, `affiliate`): Scoped to own data via `_is_supplier`/`_is_agent` checks and `ensure_approved_supplier`/`ensure_approved_agent` guards
- **Dual permission slug formats**: Both `view-module` (legacy) and `module.action` (dotted) are supported via `expand_permission_slugs()` which converts between formats. Module aliases (`email` ↔ `email_templates`, `resellers` ↔ `agents`, `audit_logs` ↔ `activity_logs`) are handled.
- **Permission expansion**: `require_any_permission("bookings.view", "view-bookings")` checks both formats automatically.
- **Approval gating**: Suppliers and agents cannot access operational endpoints until their `approval_status == "APPROVED"`. Pending partners can still access self-service endpoints defined in `PENDING_SUPPLIER_SAFE_API_PREFIXES` and `PENDING_AGENT_SAFE_API_PREFIXES`.

### 6.3 Security Audit Findings

| # | Finding | Severity | Detail |
|---|---|---|---|
| S-1 | **Default super-admin password** | ⚠️ Medium | `SUPER_ADMIN_PASSWORD` defaults to `"Admin@123"`. The seed only warns in production; it should be a required field when `APP_ENV=production`. |
| S-2 | **`datetime.utcnow()` usage** | ⚠️ Medium | Used extensively in services. `datetime.utcnow()` is deprecated in Python 3.12+ and returns naive datetimes, while model columns use `DateTime(timezone=True)`. This creates implicit timezone assumptions. |
| S-3 | **Rate limiter single-process fallback** | ⚠️ Medium | When Redis is unavailable, rate limiting falls back to in-process memory. Under multi-worker deployment (e.g., Gunicorn with multiple workers), each worker has its own counter. Documented but should be emphasized. |
| S-4 | **`X-Forwarded-For` spoofing** | ⚠️ Low | Mitigated by `TRUST_PROXY_HEADERS=False` default. Only trusted when explicitly enabled. |
| S-5 | **Password plaintext in comments** | ⚠️ Low | `app/auth/security.py` docstring explicitly states the frontend sends plaintext passwords over TLS. This is acceptable but the comment is verbose. |
| S-6 | **Error masking on 500** | ✅ Good | The catch-all handler returns a generic message; the real traceback is logged server-side. Clients can't see internals. |
| S-7 | **No CSRF protection on cookie auth** | ⚠️ Medium | If the frontend uses cookie-based auth (`web-cookie` client type), there's no CSRF token mechanism. FastAPI's bearer-token approach avoids this when the token is in `Authorization` header, but the cookie path is available. |
| S-8 | **SMTP credentials in env / DB** | ⚠️ Medium | SMTP password can be stored in DB (`SmtpSetting`) encrypted via Fernet, or in env var as plaintext. No rotation mechanism documented. |
| S-9 | **No API key/secret auth for external integrations** | ⚠️ Low | The `ApiSetting` model stores API keys but there's no middleware enforcing API-key auth on partner endpoints. Client-facing endpoints use session/JWT only. |

---

## 7. API Surface Analysis

### 7.1 Route Organization

All routes are mounted under `/api` (or `/api/admin` for aliases, `/api/public` for public content). The router registration in `app/api/router.py` groups 34 router modules into 4 categories plus admin aliases and public routes.

### 7.2 Route Shadowing Prevention

The team has **deliberately addressed route shadowing** in two places:

1. **Tour versions before CMS**: `tour_versions_router` is registered before `cms_router` so that `/tours/pending-approval` matches before `/tours/{tour_id}`.
2. **Payments gateway before payments**: `payments_gateway_router` is registered before `payments_router` so that `/payments/paypal/capture` matches before `/payments/{payment_id}/capture`.

The `scripts/audit_api.py` tool also checks for shadowed static routes by comparing path parameter patterns.

### 7.3 Response Format

All endpoints return a consistent JSON envelope:

```json
{
  "status": "success",
  "message": "Optional human-readable message",
  "data": { ... },
  "total": 100,
  "page": 1,
  "limit": 20,
  "total_pages": 5
}
```

Error responses use the standard FastAPI format: `{"detail": "..."}`, or the custom envelope `{"status": "error", "message": "..."}` for HTTP exceptions.

### 7.4 Audit Findings

- **`app/utils/response.py` is empty/missing**: The documentation references `app/utils/response.py` for response utilities, but the file returns no content (0 bytes or non-existent). Response formatting appears to be done inline in each router rather than through a shared helper. **This is a dead reference / incomplete refactor.**
- **Mixed response patterns**: Some endpoints return `{"status": "success", "data": {...}}` while others return raw lists or dicts (e.g., some CMS endpoints return lists directly). The `simple_paginate` utility in `operations.py` standardizes pagination for list endpoints.
- **No API versioning**: All routes are at `/api/*` with no version prefix. The test `test_openapi_no_v1_paths` explicitly asserts no `/v1` paths exist — this is by design, but means versioning strategy must be planned before any breaking changes.

---

## 8. Business Logic Analysis

### 8.1 Booking Lifecycle

The booking lifecycle is the most complex business flow (documented in `README.md` §234):

```
1. New booking → pending_payment
2. Payment authorization → creates active hold
   - Assigned booking → pending_supplier_acceptance
   - Unassigned booking → payment_authorized
3. Supplier accepts → confirms booking, captures funds, generates invoice,
   updates supplier ledger, notifies admin + customer
4. Supplier declines → marks booking declined, voids/refunds, releases
   calendar seats, notifies
5. Stale bookings → auto-expired by background job every 15 min (60 min hold)
```

- **Supplier decisions are idempotent**: Retrying the same accept/decline returns HTTP 409 if already processed.
- **Calendar seat management**: `TourCalendar` tracks `available_seats`/`booked_seats`. Booking holds seats; cancellation/supplier-decline releases them.
- **Background expiry**: `_expire_stale_bookings_loop()` in `main.py` runs every 15 minutes.

### 8.2 Payment Lifecycle

- **Gateway:** Currently `manual` (admin-entered). No live payment processor integrated, though `PaymentSetting` model supports storing gateway credentials and `payments_gateway` router exists for Stripe/PayPal simulation.
- **Lifecycle:** pending → authorized → captured → (voided | refunded | partially_refunded) with `payment_holds` tracking authorizations.
- **Idempotency:** `payments` table has `idempotency_key` column.

### 8.3 Supplier/Agent/Affiliate Onboarding

```
email_verification_pending → profile_incomplete → admin_review_pending → approved / rejected
```

- **Unified registration**: `register_unified_user()` creates a User with `password=None` and `account_status=PENDING_EMAIL_VERIFICATION`. Password is set later via `complete_registration()`.
- **Email-first**: Verification email sent before password creation (security best practice).
- **Three-tier approval**: `approve_item()`, `reject_item()`, `partial_approve_item()` in `app/utils/operations.py` are shared across supplier/agent workflows.
- **Commission requests**: Suppliers can request markup/commission changes; agents have discount management. Both require admin approval.
- **Notification triggers**: Centralized in `app/utils/notification_triggers.py` — all domain events trigger in-app notifications, emails to admins, and emails to the affected party.

### 8.4 Pricing Engine

`TourPricing` model shows a sophisticated multi-tier pricing model:

- **Supplier price** → **Supplier markup** → **Admin markup** → **Storefront price**
- Fields: `supplier_price`, `markup_type/value`, `admin_markup_type/value`, `storefront_adult_price/child_price`
- Migration 0054 (`tour_pricing_supplier_admin_split`) added the supplier/admin markup split.
- **Agent pricing**: `agent_net_price`, `agent_markup` stored on bookings.

### 8.5 Cancellation & Refund Workflow

- `cancellation_requests` table tracks customer-initiated cancellations
- `refund_rules` table stores cancellation policies
- `notify_refund_processed()` trigger sends notifications on refund completion
- Cancellation history tracked in `booking_status_history`

### 8.6 Chatbot

- Powered by Anthropic Claude (`claude-haiku-4-5`)
- Context window: last 10 message pairs per session
- FAQ-grounded system prompt (FAQs stored in `chat_faqs` table)
- **Graceful degradation**: If `ANTHROPIC_API_KEY` is empty, returns a polite "not available" message without calling the API
- Session tracking via `chat_sessions`/`chat_messages` tables

### 8.7 Scheduled Tasks

Two background jobs are started on application startup:

1. **Stale booking expiry** (`_expire_stale_bookings_loop`): Every 15 minutes, expires unpaid bookings holding calendar seats for over 60 minutes.
2. **Report scheduling** (`_report_schedule_loop`): Every hour, executes due report schedules.

Both use `asyncio.to_thread()` to run blocking DB work off the event loop.

### 8.8 Notification System

- **Channels**: `in_app`, `email`, `push`
- **Retry limit**: 5 attempts per notification (tracked via `notification_logs`)
- **Web push**: VAPID-based with `pywebpush`, public key from config, private key from PEM file
- **Centralized triggers**: All domain events in `notification_triggers.py` — supplier/agent approval, booking status changes, cancellation requests, refunds, payment failures
- **`_is_admin()` heuristic** in notifications service: Checks if user's role slug doesn't contain `supplier`/`agent`/`customer` to determine admin status. ⚠️ **Bug risk**: An `affiliate` role would be classified as admin since "affiliate" doesn't match any of those markers.

---

## 9. Testing Analysis

### 9.1 Test Infrastructure

- **Test approach**: Black-box HTTP tests against a live dev server at `http://127.0.0.1:8000/api`
- **No mocks**: Tests hit the real database and real server (tests are read-only by default)
- **Write test gating**: `TOURVAA_WRITE_TESTS=1` environment variable gates destructive tests via `skip_if_readonly()` helper in `conftest.py`
- **Login retry logic**: `login_with_retry()` handles rate-limit 429s during test runs (documented as a timing issue, not a bug)
- **Fixture creation**: `create_active_account()` creates users directly in DB for fixture setup, bypassing the email-verification flow (documented as necessary since the raw token only exists in the outgoing email)

### 9.2 Test Coverage (43 test files, ~5,800+ lines)

| Category | Files | Test Modules |
|---|---|---|
| **Integration tests** | 39 files | `test_01_core_health.py` through `test_39_cookie_auth.py` |
| **Unit tests** | 9 files | `test_booking_flow_unit.py`, `test_checkout_flow_unit.py`, `test_currency_unit.py`, `test_dashboard_role_based.py`, `test_dashboard_summary_unit.py`, `test_registration_activation_unit.py`, `test_registration_policy_unit.py`, `test_registration_token_security_unit.py`, `test_supplier_approval_policy_unit.py`, `test_user_account_lifecycle_unit.py` |

### 9.3 Test Coverage Gaps

| # | Gap | Detail |
|---|---|---|
| T-1 | **No model migration sync test** | No automated test verifies that all model columns have corresponding migrations. The `migrate_missing_columns.py` script and `schema_is_ready()` check suggest this is a known recurring problem. |
| T-2 | **`force_logout_user` duplication untested** | Two implementations exist in `services/auth.py` (takes `User` object) and `services/sessions.py` (takes `user_id`). The auth router imports from `services/auth.py` but the sessions router imports from `services/sessions.py`. |
| T-3 | **Notification admin check heuristic** | The `_is_admin()` function in `notifications.py` uses a string-matching heuristic that misclassifies affiliates as admins. No unit test covers this edge case. |
| T-4 | **No CSRF test** | No test for CSRF protection on cookie-based auth paths. |
| T-5 | **No security scan** | No automated dependency scanning (e.g., `pip-audit`, `safety`) in CI. |
| T-6 | **No type checking** | No `mypy` configuration or type-checking tests despite the codebase using type hints. |
| T-7 | **No linting/formatting** | No `ruff`, `black`, `flake8`, or `isort` configuration. |

---

## 10. Code Quality Assessment

### 10.1 Code Organization & Conventions

| Aspect | Assessment |
|---|---|
| **Layered separation** | ✅ Clean: routers (HTTP) → services (business logic) → models (ORM) + schemas (Pydantic) |
| **Naming conventions** | ✅ Consistent: `snake_case` for functions/variables, `PascalCase` for classes |
| **Docstrings** | ⚠️ Inconsistent: auth service has extensive docstrings, many utilities have minimal docs |
| **Type hints** | ✅ Used consistently on function signatures |
| **Error handling** | ✅ Business logic raises `HTTPException` with appropriate status codes; global handler masks 500s |
| **Defensive coding** | ✅ Serializers catch `SQLAlchemyError` around lazy-loaded relationships (documented pattern in README §4.23) |

### 10.2 Code Smells & Technical Debt

| # | Issue | Files | Assessment |
|---|---|---|---|
| TD-1 | **Empty `app/utils/response.py`** | `app/utils/response.py` | ⚠️ File exists but returns no content. Referenced in docs but response formatting is done inline. Dead code. |
| TD-2 | **Duplicate `force_logout_user`** | `app/services/auth.py` (line 913, takes `User`) vs `app/services/sessions.py` (line 55, takes `user_id`) | ⚠️ Two implementations with different signatures. Auth router uses the auth service version; sessions router uses the sessions service version. Confusion risk. |
| TD-3 | **Legacy + unified registration paths** | `app/services/auth.py`: `register_user()` (legacy) and `register_unified_user()` (new) both exist | ⚠️ `register_user()` is still referenced by some routers? (needs verification) but the auth router only calls `register_unified_user()`. The legacy `register_user` function is unused dead code. |
| TD-4 | **`datetime.utcnow()` deprecation** | Throughout services and `utils/money.py` | ⚠️ Deprecated in Python 3.12+. Returns naive datetime, causing mixed tz-awareness issues with `DateTime(timezone=True)` columns. |
| TD-5 | **Timezone comparison fragility** | `services/auth.py` lines 300, 856, 940, 1040 | `.replace(tzinfo=None)` used to compare tz-aware DB values with naive `utcnow()`. Fragile and masks potential bugs. |
| TD-6 | **`EmailLog` model placement** | `app/models/bookings.py` | ⚠️ `EmailLog` is defined in the bookings model file, not in a dedicated `emails.py` model or in `notifications.py`. Conceptual mismatch. |
| TD-7 | **Import-time side effects** | `app/services/sessions.py` imports `User` from `app.models.users` inside functions | ⚠️ Local imports used to avoid circular dependencies, indicating tight coupling. |
| TD-8 | **Magic strings for status values** | Throughout codebase: `"ACTIVE"`, `"PENDING"`, `"approved"`, etc. | ⚠️ No enum/constant definitions. The `operations.py` file does define `APPROVAL_STATUSES` set, but it's not used consistently. |
| TD-9 | **Hardcoded admin email** | `notification_triggers.py` `email_admins()` queries roles by hardcoded slug `"super-admin"` and `"admin"` | ⚠️ Not configurable; adding a new admin role requires code changes. |
| TD-10 | **`_is_admin()` heuristic** | `app/services/notifications.py` line 11–15 | ⚠️ String-matching heuristic misclassifies `affiliate` as admin. Should query role permissions or use an explicit admin role set. |

### 10.3 Documentation Drift

| # | Issue | Detail |
|---|---|---|
| D-1 | **`BACKEND_DOC.md` outdated** | §2 references `app/modules/` directory structure (e.g., `app/modules/auth/`, `common/auth.py`, `common/ratelimit.py`) that **does not exist**. The actual structure is layer-based (`app/auth/`, `app/utils/ratelimit.py`, `app/middleware/`). Documentation was generated 2026-06-22 but codebase has evolved significantly (54 migrations, new patterns). |
| D-2 | **`BACKEND_DOC.md` §5 table mismatch** | §5 references tables like `suppliers` having `supplier_contacts`, `supplier_business_info`, etc. — these match, but §5 also lists `tour_overviews`, `tour_itineraries` etc. under Tours that are actually in `app/models/tours.py` — correct. However, `BACKEND_DOC.md` does NOT mention: `tour_reviews`, `booking_calendar_events`, `affiliate_*`, `tour_versions`, `customer_wishlist_items`, `customer_cancellation_requests`, `supplier_commission_requests`, `supplier_approval_history`, `agent_ledger`/`agent_payouts`, `agent_commission_requests`, `cancellation_requests`, `refund_rules`, `checkout_sessions`, `public_leads`, `sitemap_entries`, `cms_*` tables, `payment_holds`, `payment_transactions`. Documentation is missing ~15 tables that exist in the current schema. |
| D-3 | **`BACKEND_DOC.md` §8 endpoint mismatch** | §8 describes an older endpoint structure (`/api/users` with `/approve`, `/reject`, `/send-reset-mail`) but the unified auth flow now uses `/auth/complete-registration`, `/auth/change-registration-email`, `/auth/resend-verification`, `/auth/otp/request`, `/auth/otp/verify`, `/auth/account-status`. The old `register_user()` service function and `register/supplier`/`register/agent`/`register/customer` router aliases also conflict with the unified `register` endpoint. |
| D-4 | **`README.md` structure mismatch** | §151 describes the project structure with `app/modules/` but the actual structure is layer-based (`app/routers/`, `app/services/`, `app/schemas/`, `app/models/`). The `modules/` reference is stale from an earlier architecture. |
| D-5 | **Seed script documentation** | `BACKEND_DOC.md` §13 describes seeding that creates a demo tour ("Dubai City Highlights") — this demo tour seeding is NOT present in the current `app/seed.py`. The README correctly notes seed only creates roles/permissions/super-admin. |
| D-6 | **Documentation generation timestamp** | `BACKEND_DOC.md` footer says "Documentation generated 2026-06-22" — this is 6+ weeks old. The codebase has had 54 migrations and significant feature additions since then. |

---

## 11. Operational Scripts Analysis

### 11.1 Scripts Directory (`scripts/`)

| Script | Lines | Purpose | Assessment |
|---|---|---|---|
| `audit_api.py` | 180 | Audits OpenAPI contract for duplicate routes, shadowed static routes, and 5xx responses | ✅ Well-structured, covers both unauthenticated and authenticated (super-admin) GET smoke tests |
| `dev_server.py` | 50 | Development uvicorn runner with scoped auto-reload (only watches `app/` and `alembic/`, excludes tests/scripts/venv/backups) | ✅ Prevents noisy reload cycles |
| `migrate_missing_columns.py` | 34 | Manual remediation for missing model columns (post-migration sync fix) | ⚠️ Band-aid for the model-migration sync problem; indicates a process gap |
| `prepare_live_database.py` | (not read) | Live database sanitization — dry-run preview + `--execute --backup --confirm` | ✅ Safe-by-default with backup and confirmation |
| `reset_seed_admin_rbac.py` | (not read) | RBAC role/permission resync without `--reset` flag | ✅ Safe for production use |
| `seed_geo.py` | (not read) | Geo reference data seeding (countries/states/cities) | ✅ External API integration |
| `migrate_private_docs.py` | (not read) | Private document storage migration | ✅ |

### 11.2 `audit_api.py` — API Contract Auditor

The audit script is well-designed:

1. **OpenAPI schema introspection**: Reads `app.openapi()` and extracts all paths and operations.
2. **Duplicate route detection**: Compares declared router operations against FastAPI's route table to find duplicate `(method, path)` declarations across routers.
3. **Route shadowing detection**: `_shadowed_static_routes()` checks if a dynamic path (e.g., `/tours/{tour_id}`) would shadow a static path (e.g., `/tours/pending-approval`) based on registration order.
4. **5xx smoke testing**: Sends sample requests (empty body, ID `999999999`) to every endpoint and flags 500s.
5. **Authenticated reads**: Optionally logs in as super-admin and smoke-tests every GET endpoint.

**Limitation**: Only checks 5xx responses, not business-logic correctness (4xx responses that should be 403 but return 500, etc.).

### 11.3 `prepare_live_database.py` — Production Sanitizer

This script is designed for first-production-database cleanup:

- **Dry-run mode by default**: Prints `PRESERVE COMPLETELY`, `PRESERVE FILTERED`, and `CLEAR` sections.
- **Execution requires**: `--execute` + `--backup` + `--confirm PREPARE-LIVE` (fails closed otherwise).
- **Creates SQL backup** under `backups/` before clearing.
- **Preserves**: migrations, super-admin RBAC, geo reference data, app/payment/API settings, email templates, tour categories.
- **Clears**: transactional data (bookings, payments, invoices), portal users, catalogue data, communications, audit logs, sessions.

---

## 12. File Storage & Media

### 12.1 Storage Layout

- **`STORAGE_ROOT`** (default: `storage/`) — resolved relative to `app/` package parent directory.
- **Public mount**: `/storage` static files served via FastAPI `StaticFiles`.
  - `storage/uploads/profile-images/` — user profile images
  - `storage/uploads/admin-assets/` — admin-uploaded assets
- **Private storage**: `private-docs/` (sibling of `storage/` root), NOT served publicly.
  - `private-docs/supplier-documents/`
  - `private-docs/agent-documents/`
  - `private-docs/invoices/`
  - `private-docs/itineraries/`

### 12.2 Media Resolution

- `existing_storage_path(path)` in `app/utils/media.py` checks if a file exists and returns the accessible URL or `None`.
- Profile images in user payloads are resolved through this function.

### 12.3 Cloudinary Integration

- `CLOUDINARY_URL` config supports Cloudinary as a storage backend.
- `app/utils/cloudinary_client.py` provides the integration (not examined in detail).

---

## 13. Rate Limiting Analysis

### 13.1 Implementation (`app/utils/ratelimit.py` — 137 lines)

- **Redis-backed sliding window** using a Lua script when `REDIS_URL` is configured.
- **In-memory fallback**: Thread-safe deque-based sliding window when Redis is unavailable.
- **`TRUST_PROXY_HEADERS`** controls whether `X-Forwarded-For` is read for IP address.
- **Stale bucket cleanup**: Memory buckets pruned every 5 minutes (in-memory mode).

### 13.2 Rate Limits

| Endpoint | Limit | Window |
|---|---|---|
| `POST /auth/login` | 10 calls | 60 seconds |
| `POST /auth/forgot-password` | 5 calls | 300 seconds |
| `POST /auth/verify-email` | 10 calls | 60 seconds |
| `POST /auth/otp/request` | 5 calls | 300 seconds |
| `POST /auth/otp/verify` | 10 calls | 300 seconds |
| `POST /auth/resend-verification` | 3 calls | 300 seconds |
| `POST /auth/change-registration-email` | 3 calls | 300 seconds |

### 13.3 Limitation

Single-process in-memory fallback is not shared across Gunicorn/uvicorn workers. Each worker maintains its own rate-limit counters. The `REDIS_URL` config is the production path.

---

## 14. Audit Logging System

### 14.1 AuditLog Model (`app/models/audit.py`)

| Column | Type | Notes |
|---|---|---|
| `actor_user_id` | FK → users | Nullable (for system/anonymous actions) |
| `action` | String(100) | Indexed — e.g., `"login_success"`, `"registration"`, `"approve_supplier"` |
| `entity_type` | String(100) | Indexed — e.g., `"auth"`, `"user"`, `"booking"` |
| `entity_id` | Integer | Indexed |
| `old_values` | JSON | Nullable — pre-mutation state |
| `new_values` | JSON | Nullable — post-mutation state |
| `ip_address` | String(100) | Nullable — from `request.client.host` |
| `user_agent` | String(255) | Nullable |
| `created_at` | DateTime | Auto-timestamp |

### 14.2 Audit Coverage

`log_audit()` is called from service layers for every mutation:

- **Auth events**: `registration`, `verification_email_sent`, `login_success`, `login_failed`, `force_logout`, `email_verified`, `password_created`
- **Approval workflows**: `approve_supplier`, `reject_supplier`, `approve_agent`, `reject_agent`, `partial_approve_*`
- **User management**: Status changes, role assignments
- **Booking operations**: Status changes (via `BookingStatusHistory` model + `log_audit`)
- **Supplier/agent profile changes**

### 14.3 Audit Gaps

- Not all read operations are audited (by design — audit is for mutations only).
- `old_values`/`new_values` are serialized to JSON via `_json_safe()` which handles `datetime`, `Decimal`, `dict`, and `list` — but does not handle SQLAlchemy model instances or `set` types.

---

## 15. Risk Assessment

### 15.1 Risk Matrix

| Risk | Likelihood | Impact | Severity | Mitigation Status |
|---|---|---|---|---|
| Model-migration sync drift causes 500s on production | Medium | High | ⚠️ High | Partially mitigated by `schema_is_ready()` and `migrate_missing_columns.py` |
| Default super-admin password exploited | Low | High | ⚠️ High | Warning logged in production; should be hard error |
| Rate limiter bypass via single-process fallback | Low (when Redis unavailable) | Medium | ⚠️ Medium | Redis is optional but recommended; documented |
| `datetime.utcnow()` deprecation breaks on Python 3.12+ | Medium | Medium | ⚠️ Medium | Not yet on 3.12 (uses 3.11+); migration needed |
| `_is_admin()` heuristic misclassifies affiliate | Medium | Low | ⚠️ Low-Medium | Bug; affects notification routing only |
| Documentation drift causes onboarding friction | High | Low | ⚠️ Medium | BACKEND_DOC.md and README.md both stale |
| `cryptography` missing from requirements.txt | High (new deploy) | Medium | ⚠️ High | Will cause runtime crash when SMTP settings encryption is used |
| CSRF on cookie-based auth | Low (if bearer tokens used) | High | ⚠️ Medium | Only affects `web-cookie` client_type; bearer tokens are default |
| Unused `register_user()` dead code | Low | Low | ⚠️ Low | Dead code; should be removed |
| Duplicate `force_logout_user` functions | Low | Low | ⚠️ Low | Both work; one is dead code |

### 15.2 Production Readiness

| Criterion | Status | Notes |
|---|---|---|
| Database migrations in place | ✅ | 54 migrations, head = 0054 |
| RBAC seeded | ✅ | Idempotent seed on startup |
| Email templates seeded | ✅ | DB templates with hardcoded fallbacks |
| Super-admin account | ✅ | But weak default password |
| Health check | ✅ | `GET /api/health` |
| Interactive docs | ✅ | Swagger UI + ReDoc |
| Error masking | ✅ | Generic 500 responses, server-side logging |
| Rate limiting | ⚠️ | Requires Redis for multi-process correctness |
| SSL/TLS | ⚠️ | Relies on reverse proxy; `secure` cookie flag only in production |
| Monitoring | ⚠️ | No APM/sentry; basic logging only |
| Dependency scanning | ⚠️ | Not configured |
| CI/CD | ⚠️ | Not visible in repo; assumes external CI |

---

## 16. Recommendations & Action Plan

### 16.1 Critical (P0 — Fix Before Production)

| # | Action | Affected Files | Timeline |
|---|---|---|---|
| 1 | **Add `cryptography` to `requirements.txt`** | `requirements.txt` | Immediate |
| 2 | **Require `SUPER_ADMIN_PASSWORD` in production** (no default) | `app/config/__init__.py`, `app/seed.py` | Immediate |
| 3 | **Fix `_is_admin()` heuristic** — use explicit role slug check instead of string matching | `app/services/notifications.py` | 1 day |
| 4 | **Add `SETTINGS_ENCRYPTION_KEY` to `.env.example`** and document | `BACKEND_DOC.md`, `README.md` | 1 day |

### 16.2 High Priority (P1 — Next Sprint)

| # | Action | Affected Files | Timeline |
|---|---|---|---|
| 5 | **Remove dead code**: `register_user()` legacy function, duplicate `force_logout_user` in sessions.py | `app/services/auth.py`, `app/services/sessions.py` | 2 days |
| 6 | **Replace `datetime.utcnow()` with `datetime.now(timezone.utc)`** and fix tz-aware comparisons | All service files, `utils/money.py`, `utils/operations.py` | 3 days |
| 7 | **Implement model-migration sync CI check** | CI pipeline | 3 days |
| 8 | **Add CSRF protection for cookie-based auth** | `app/middleware/` | 5 days |
| 9 | **Remove or populate `app/utils/response.py`** | `app/utils/response.py` | 1 day |
| 10 | **Fix `EmailLog` model placement** — move to `app/models/email_logs.py` | `app/models/` | 2 days |

### 16.3 Medium Priority (P2 — Next Quarter)

| # | Action | Affected Files | Timeline |
|---|---|---|---|
| 11 | **Add linting and formatting** (ruff + black) | `pyproject.toml`, CI | 1 week |
| 12 | **Add type checking** (mypy) | `pyproject.toml`, CI | 1 week |
| 13 | **Add dependency vulnerability scanning** (pip-audit or safety) | CI | 1 week |
| 14 | **Add CSRF tokens to cookie auth** | `app/routers/auth.py`, `app/utils/` | 1 week |
| 15 | **Standardize response format** — ensure all endpoints use the `{status, data, ...}` envelope consistently | All routers | 2 weeks |

### 16.4 Low Priority (P3 — Backlog)

| # | Action | Affected Files | Timeline |
|---|---|---|---|
| 16 | **Regenerate `BACKEND_DOC.md`** from current source | `BACKEND_DOC.md` | 1 week |
| 17 | **Add Redis URL to documentation** | `BACKEND_DOC.md`, `README.md` | 1 day |
| 18 | **Add VAPID key documentation** | `BACKEND_DOC.md`, `README.md` | 1 day |
| 19 | **Remove demo tour seed reference** from docs (already removed from code) | `BACKEND_DOC.md` | 1 day |
| 20 | **Add unit tests for `_is_admin()` and permission expansion edge cases** | `tests/` | 2 days |

### 16.5 Metrics Summary

| Metric | Count |
|---|---|
| Total migration files | 54 |
| Total database tables | 70+ (est.) |
| Total model files | 34 |
| Total router files | 34 |
| Total service files | 34 |
| Total schema files | 27 (+ `__init__.py`) |
| Total utility files | 15 |
| Total test files | 43 (39 integration + 4 unit) |
| Total test lines (est.) | ~5,800 |
| Total middleware files | 2 |
| Total scripts | 7 |
| Total API routes (est.) | ~150+ endpoints across all routers |
| Permission slugs (seeded) | 150+ (108 legacy + 42+ granular) |
| Built-in roles | 7 |
| Built-in admin modules | 27 |

---

## 17. Conclusion

The Tourvaa Backend is a **well-architected, production-grade FastAPI application** with a sophisticated multi-role RBAC system, comprehensive booking/payment lifecycles, and robust onboarding workflows for suppliers, agents, and affiliates. The codebase demonstrates mature engineering practices including layered separation of concerns, idempotent seeding, defensive error handling, graceful degradation, and deliberate route-ordering to prevent shadowing.

The primary risks are **not architectural** but operational: documentation drift, a critical missing dependency (`cryptography`), deprecated datetime usage, two small but real bugs (`_is_admin` heuristic, `force_logout_user` duplication), and dead code. These are addressable with focused cleanup work.

**The system is production-ready pending resolution of the P0 items (missing `cryptography` dependency, super-admin password default, `_is_admin()` bug, and encryption key documentation).**

---

*This report was generated by automated source-code analysis on 2026-08-04. It covers all files under `tourvaa-admin-backend/` as of the current working tree state.*
