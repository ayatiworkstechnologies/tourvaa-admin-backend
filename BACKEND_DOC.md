# Tourvaa Backend - End-to-End Documentation

---

## Table of Contents

1. [Overview](#1-overview)
2. [Project Structure](#2-project-structure)
3. [Tech Stack & Dependencies](#3-tech-stack--dependencies)
4. [Configuration & Environment](#4-configuration--environment)
5. [Database](#5-database)
6. [Security & Authentication](#6-security--authentication)
7. [RBAC - Roles & Permissions](#7-rbac--roles--permissions)
8. [API Modules - Full Endpoint Reference](#8-api-modules--full-endpoint-reference)
   - [Auth](#81-auth--apiauth)
   - [Users](#82-users--apiusers)
   - [Roles](#83-roles--apiroles--apiadminroles)
   - [Permissions](#84-permissions--apipermissions--apiadminpermissions)
   - [Dashboard](#85-dashboard--apidashboard)
   - [Customers](#86-customers--apicustomers)
   - [Suppliers](#87-suppliers--apisuppliers)
   - [Agents](#88-agents--apiagents)
   - [Affiliates](#89-affiliates--apiaffiliates)
   - [CMS - Countries, Cities, Categories](#810-cms--countries-cities-categories)
   - [Tours (CMS)](#811-tours-cms--apitours)
   - [Tour Detail Sub-Resources](#812-tour-detail-sub-resources--apitours)
   - [Bookings](#813-bookings--apibookings)
   - [Payments](#814-payments--apipayments)
   - [Invoices](#815-invoices--apiinvoices)
   - [Notifications](#816-notifications--apinotifications)
   - [Reports](#817-reports--apireports)
   - [Chatbot](#818-chatbot--apichatbot)
   - [Settings](#819-settings--apisettings)
   - [Email Templates](#820-email-templates--apiemail-templates)
   - [Profile](#821-profile--apiprofile)
   - [Uploads](#822-uploads--apiuploads)
   - [Audit Logs](#823-audit-logs--apiaudit-logs)
   - [Sessions](#824-sessions--apisessions)
   - [Client API](#825-client-api--apiclient)
9. [Data Models](#9-data-models)
10. [Email System](#10-email-system)
11. [File Storage](#11-file-storage)
12. [Rate Limiting](#12-rate-limiting)
13. [Seeding & Bootstrap](#13-seeding--bootstrap)
14. [Running the Server](#14-running-the-server)
15. [Common Response Format](#15-common-response-format)
16. [Permission Slug Reference](#16-permission-slug-reference)

---

## 1. Overview

Tourvaa Backend is a **FastAPI** REST API that powers the Tourvaa tour-and-travel booking platform. It handles:

- Multi-role user authentication (JWT)
- Role-based access control (RBAC) with fine-grained permissions
- Full tour catalogue management (CMS)
- Booking lifecycle (create → confirm → assign supplier → complete)
- Payment recording and lifecycle (authorize → capture → void → refund)
- Supplier, agent, and affiliate onboarding with approval workflows
- AI chatbot powered by Anthropic Claude
- Web push notifications (VAPID)
- Audit logging for every mutation
- Reporting and analytics

**Base URL:** `http://127.0.0.1:8000` (dev) / configured via `API_BASE_URL`

**API prefix:** All routes are under `/api/`

---

## 2. Project Structure

```
backend/
├── main.py                          # does not exist - app entry is run via uvicorn app.main:app
├── app/
│   ├── config.py                    # Pydantic settings loaded from .env
│   ├── database.py                  # SQLAlchemy engine, SessionLocal, Base, get_db()
│   ├── security.py                  # JWT creation, bcrypt hashing, token utilities
│   ├── seed.py                      # DB seeder - roles, permissions, super admin
│   └── modules/
│       ├── auth/                    # Login, register, password reset, email verify
│       ├── users/                   # User CRUD and role assignment
│       ├── roles/                   # Role management
│       ├── permissions/             # Permission management
│       ├── admin_modules/           # Admin sidebar module definitions
│       ├── dashboard/               # Dashboard summary, charts, activity
│       ├── customers/               # Customer profiles, comms, portal
│       ├── suppliers/               # Supplier onboarding and approval
│       ├── agents/                  # Agent/reseller onboarding and approval
│       ├── affiliates/              # Affiliate management
│       ├── cms/                     # Countries, cities, categories, subcategories, tours
│       ├── tours/                   # Tour sub-resources (itinerary, pricing, gallery, etc.)
│       ├── bookings/                # Booking lifecycle
│       ├── payments/                # Payment lifecycle
│       ├── invoices/                # Invoice records
│       ├── notifications/           # In-app + push notifications
│       ├── reports/                 # Analytics and reporting
│       ├── chatbot/                 # AI chatbot (Anthropic) + FAQ admin
│       ├── settings/                # App / payment / API settings
│       ├── email_templates/         # Email template CRUD
│       ├── profile/                 # User self-service profile
│       ├── uploads/                 # File upload handling
│       ├── audit/                   # Audit log model and service
│       ├── sessions/                # Login history and session tracking
│       ├── client/                  # Public-facing client API
│       └── common/
│           ├── auth.py              # get_current_user, require_any_permission
│           ├── ratelimit.py         # In-memory sliding-window rate limiter
│           ├── mailer.py            # SMTP email sender
│           ├── email_templates.py   # Fallback HTML email templates
│           ├── helpers.py           # Utility functions (slugify, mask_email, etc.)
│           ├── media.py             # File path resolution
│           ├── money.py             # Currency formatting, utcnow()
│           └── pagination.py        # pagination_params dependency
├── alembic/                         # Database migration scripts
├── alembic.ini                      # Alembic config
├── requirements.txt
├── .env                             # Environment variables (not committed to prod)
└── vapid_private.pem                # VAPID private key for web push
```

---

## 3. Tech Stack & Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `sqlalchemy` | ORM |
| `pymysql` | MySQL driver |
| `alembic` | Database migrations |
| `pydantic-settings` | `.env` config |
| `python-jose` | JWT encode/decode |
| `passlib[bcrypt]` + `bcrypt==4.0.1` | Password hashing |
| `python-multipart` | File upload support |
| `email-validator` | Email validation in schemas |
| `python-dotenv` | `.env` loading |
| `anthropic` | Anthropic Claude API (chatbot) |
| `pywebpush` | Web Push / VAPID |
| `requests` | HTTP client (internal use) |

**Python:** 3.11+ required (uses `str | None` union syntax)

---

## 4. Configuration & Environment

All config is read from `backend/.env` via `app/config.py` (Pydantic `BaseSettings`).

### Full `.env` Reference

```env
# App
APP_NAME=Tourvaa Backend
APP_ENV=development          # set to "production" in prod
APP_DEBUG=true               # set to false in prod

# Database
DATABASE_URL=mysql+pymysql://root:password@localhost:3306/tourvaa_db

# JWT
JWT_SECRET_KEY=<64-char hex>  # generate: python -c "import secrets; print(secrets.token_hex(32))"
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440  # 24 hours

# Email verification
REQUIRE_EMAIL_VERIFICATION=false  # set true to enforce email verify before login
EMAIL_VERIFICATION_EXPIRE_MINUTES=1440

# URLs
FRONTEND_URL=https://tourvaa.vercel.app
API_BASE_URL=http://127.0.0.1:8000
ALLOWED_ORIGINS=https://tourvaa.vercel.app,http://localhost:3000
MOBILE_DEEP_LINK_URL=tourvaa://reset-password

# Storage
STORAGE_ROOT=storage   # relative path resolved from backend root; use absolute path in prod

# Super Admin bootstrap (used by seed.py on first run)
SUPER_ADMIN_NAME=Super Admin
SUPER_ADMIN_EMAIL=admin@tourvaa.com
SUPER_ADMIN_PASSWORD=<strong password>
SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP=false

# SMTP
SMTP_HOST=mail.example.com
SMTP_PORT=465
SMTP_USERNAME=smtp@example.com
SMTP_USER=smtp@example.com
SMTP_PASSWORD=<password>
SMTP_FROM_NAME=Tourvaa

# AI Chatbot (Anthropic)
ANTHROPIC_API_KEY=sk-ant-...    # required for chatbot to work

# Web Push (VAPID)
VAPID_PUBLIC_KEY=<base64url public key>
VAPID_PRIVATE_KEY_FILE=vapid_private.pem   # path to PEM file
VAPID_MAILTO=mailto:admin@example.com
```

### Settings Object (`app/config.py`)

Imported everywhere as:
```python
from app.config import settings
```

Key property: `settings.cors_origins` - parses `ALLOWED_ORIGINS` CSV into a list.

---

## 5. Database

### Engine

- **Dialect:** MySQL via PyMySQL
- **ORM:** SQLAlchemy declarative base
- **Pool:** `pool_pre_ping=True` (reconnects on stale connections)
- **SQLite fallback:** Engine switches to `StaticPool` if `DATABASE_URL` is `sqlite://` or `sqlite:///:memory:` (for tests)

### Session

```python
from app.database import get_db
# Used as FastAPI dependency: db: Session = Depends(get_db)
```

### Migrations

```bash
# Apply all pending migrations
python -m alembic upgrade head

# Create a new migration
python -m alembic revision --autogenerate -m "description"

# Check current revision
python -m alembic current
```

### Tables (45+)

| Group | Tables |
|---|---|
| Users | `users`, `user_roles`, `login_history`, `user_sessions` |
| RBAC | `roles`, `permissions`, `role_permissions`, `admin_modules` |
| Customers | `customers`, `customer_communications`, `customer_saved_travellers`, `customer_cancellation_requests` |
| Suppliers | `suppliers`, `supplier_contacts`, `supplier_business_info`, `supplier_vehicles`, `supplier_invoicing`, `supplier_documents` |
| Agents | `agents`, `agent_contacts`, `agent_business_info`, `agent_invoicing`, `agent_documents` |
| Affiliates | `affiliates`, `affiliate_marketing_info`, `affiliate_invoicing`, `affiliate_documents` |
| Tours | `countries`, `cities`, `tour_categories`, `tour_subcategories`, `tour_subcategory_maps`, `tours`, `tour_overviews`, `tour_itineraries`, `tour_inclusions`, `tour_exclusions`, `tour_highlights`, `tour_similar`, `tour_extensions`, `tour_gallery_images`, `tour_pricing`, `tour_optional_activities`, `tour_accommodation_extras`, `tour_calendars`, `tour_unavailable_dates`, `tour_discounts` |
| Bookings | `bookings`, `booking_travellers`, `booking_optional_activities`, `booking_accommodations`, `booking_extensions`, `booking_status_history`, `booking_communications`, `message_replies`, `email_logs` |
| Payments | `payments`, `payment_transactions`, `payment_holds` |
| Invoices | `invoices`, `invoice_items` |
| Notifications | `notifications`, `notification_logs`, `push_subscriptions` |
| Chatbot | `chat_faqs`, `chat_sessions`, `chat_messages` |
| System | `audit_logs`, `email_templates`, `api_settings`, `app_settings`, `payment_settings` |

---

## 6. Security & Authentication

### Password Hashing (`app/security.py`)

- Algorithm: **bcrypt** via `passlib`
- Functions: `hash_password(plain)` → hashed string, `verify_password(plain, hashed)` → bool
- Strength rule: ≥8 chars, must include uppercase, lowercase, digit, special character

### JWT Tokens

- Algorithm: **HS256**
- Expiry: `ACCESS_TOKEN_EXPIRE_MINUTES` (default 24 hours)
- Payload fields: `user_id`, `email`, `role` (slug), `client_type`, `device_id`, `token_version`, `exp`
- Generated via `create_token(data: dict)` in `security.py`

### Token Version (Force Logout)

Each `User` row has a `token_version` integer. On login, it is embedded in the JWT. On every authenticated request, `get_current_user` checks that the token's `token_version` matches the DB value. Incrementing `token_version` (via force logout) invalidates all existing tokens for that user.

### Request Authentication (`app/modules/common/auth.py`)

```python
# Reads Bearer token from Authorization header
get_current_user()          # returns User or raises 401/403

# Requires the user to hold at least one of the listed permissions
require_any_permission("bookings.view", "view-bookings")

# Shorthand alias for single-permission check
require_permission("update-users")
```

### Password Reset Tokens

- Generated via `create_password_reset_token()` → `(plain_token, sha256_hash)`
- Only the SHA-256 hash is stored in `users.reset_password_token`
- Expiry: 30 minutes
- Invalidated after use (token column cleared)

### Email Verification Tokens

- Same mechanism as password reset
- Expiry: `EMAIL_VERIFICATION_EXPIRE_MINUTES` (default 1440 min)
- On verify: sets `email_verified_at`, updates supplier/agent status to `profile_incomplete`

---

## 7. RBAC - Roles & Permissions

### Built-in Roles (seeded)

| Slug | Display Name | Auto-approved |
|---|---|---|
| `super-admin` | Super Admin | Yes |
| `admin` | Admin | Yes (manual seed) |
| `sub-admin` | Sub Admin | Pending → manual approval |
| `supplier` | Supplier | Email verify → profile submit → admin approve |
| `agent-reseller` | Agent / Reseller | Email verify → profile submit → admin approve |
| `customer` | Customer | Auto-approved on register |
| `affiliate` | Affiliate | Pending → admin approve |

### Permission Slug Format

Two formats are accepted interchangeably:

| Format | Example | Used for |
|---|---|---|
| `module.action` | `bookings.view` | Modern granular permissions |
| `action-module` | `view-bookings` | Legacy permissions (auto-expanded) |

The auth middleware expands both formats before checking, so endpoints can safely list either.

### Permission Expansion Logic

`expand_permission_slugs()` converts between formats:
- `bookings.view` → also checks `view-bookings`
- `view-bookings` → also checks `bookings.view`

Module aliases: `email` ↔ `email_templates`

### How to Guard an Endpoint

```python
from app.modules.common.auth import require_any_permission

@router.get("/resource")
def my_endpoint(
    current_user = Depends(require_any_permission("resource.view", "view-resource"))
):
    ...
```

The dependency returns the authenticated `User` object. Raises `403` if none of the listed permissions match.

---

## 8. API Modules - Full Endpoint Reference

All routes are prefixed with `/api`. Every response follows the [standard format](#15-common-response-format).

---

### 8.1 Auth - `/api/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | Public | Register with optional `role_id`. Defaults to customer. Sends email verification. |
| POST | `/auth/register/customer` | Public | Register as customer specifically |
| POST | `/auth/register/supplier` | Public | Register as supplier (starts approval flow) |
| POST | `/auth/register/agent` | Public | Register as agent-reseller (starts approval flow) |
| POST | `/auth/login` | Public (rate limited 10/60s) | Login. Returns `access_token`, `user` payload, `session_id` |
| GET | `/auth/me` | Bearer | Returns current user session - roles, permissions, profile |
| POST | `/auth/forgot-password` | Public (rate limited 5/300s) | Sends password reset email |
| GET | `/auth/reset-password/validate` | Public | Validates a reset token before showing the reset form |
| POST | `/auth/reset-password` | Public | Sets new password using reset token; invalidates all sessions |
| POST | `/auth/refresh-token` | Bearer (expired OK) | Issues new JWT from an expired but valid-version token |
| POST | `/auth/refresh` | Bearer (expired OK) | Alias for `/refresh-token` |
| POST | `/auth/logout` | Bearer | Force-logout current user (increments token_version) |
| POST | `/auth/verify-email` | Public (rate limited 10/60s) | Verifies email with token from link |
| GET | `/auth/login-history` | Bearer | Returns last N audit log entries for login events |
| POST | `/auth/force-logout` | `update-users` | Force-logout another user by `user_id` |

**Login Response:**
```json
{
  "status": "success",
  "data": {
    "access_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 86400,
    "client_type": "web",
    "session_id": "abc123",
    "user": {
      "id": 1,
      "name": "...",
      "email": "...",
      "role": { "id": 1, "name": "Super Admin", "slug": "super-admin" },
      "roles": [...],
      "permissions": [{ "id": 1, "slug": "bookings.view", ... }],
      "customer_id": null
    }
  }
}
```

---

### 8.2 Users - `/api/users`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/users` | `view-users` | Paginated user list with search |
| POST | `/users` | `create-users` | Create user |
| GET | `/users/{id}` | `view-users` | User detail |
| PUT | `/users/{id}` | `update-users` | Update user |
| DELETE | `/users/{id}` | `delete-users` | Delete user |
| POST | `/users/{id}/approve` | `update-users` | Approve pending user |
| POST | `/users/{id}/reject` | `update-users` | Reject pending user |
| POST | `/users/{id}/send-reset-mail` | `update-users` | Send password reset email to user |
| POST | `/users/{id}/roles` | `update-users` | Assign roles to user |

---

### 8.3 Roles - `/api/roles` & `/api/admin/roles`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/roles` | `view-roles` | List roles |
| POST | `/roles` | `create-roles` | Create role |
| GET | `/roles/{id}` | `view-roles` | Role detail |
| PUT | `/roles/{id}` | `update-roles` | Update role |
| DELETE | `/roles/{id}` | `delete-roles` | Delete role |
| GET | `/roles/{id}/permissions` | `view-roles` | List permissions for role |
| POST | `/roles/{id}/permissions` | `update-roles` | Assign permissions to role |
| GET | `/roles/public/options` | Public | Available roles for registration dropdown |

---

### 8.4 Permissions - `/api/permissions` & `/api/admin/permissions`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/permissions` | `view-permissions` | List permissions |
| POST | `/permissions` | `create-permissions` | Create permission |
| GET | `/permissions/{id}` | `view-permissions` | Permission detail |
| PUT | `/permissions/{id}` | `update-permissions` | Update permission |
| DELETE | `/permissions/{id}` | `delete-permissions` | Delete permission |

---

### 8.5 Dashboard - `/api/dashboard`

All endpoints require Bearer token. Response is scoped to the caller's role.

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/dashboard/me` | Bearer | Role-specific profile + sidebar modules |
| GET | `/dashboard/summary` | `dashboard.summary` | Stats cards (total bookings, revenue, etc.) |
| GET | `/dashboard/charts` | `dashboard.charts` | Chart data (monthly bookings/revenue) |
| GET | `/dashboard/recent-activities` | `dashboard.activities` | Recent audit log entries |
| GET | `/dashboard/alerts` | `dashboard.alerts` | System alerts |
| GET | `/dashboard/bookings` | `bookings.view` | Booking analytics for dashboard |
| GET | `/dashboard/revenue` | `payments.view` | Revenue analytics |
| GET | `/dashboard/payments` | `payments.view` | Payment summary |
| GET | `/dashboard/reports` | `reports.view` | Reports summary |

---

### 8.6 Customers - `/api/customers`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/customers` | `customers.view` | Paginated customer list |
| POST | `/customers` | `customers.create` | Create customer record |
| GET | `/customers/{id}` | `customers.view` | Customer detail |
| PUT | `/customers/{id}` | `customers.edit` | Update customer |
| PATCH | `/customers/{id}/status` | `customers.edit` | Update customer status |
| POST | `/customers/{id}/block` | `customers.block` | Block customer |
| POST | `/customers/{id}/unblock` | `customers.unblock` | Unblock customer |
| POST | `/customers/{id}/reset-password` | `customers.reset_password` | Send reset email to customer |
| GET | `/customers/{id}/bookings` | `customers.view_bookings` | Customer booking history |
| GET | `/customers/{id}/payments` | `customers.view_payments` | Customer payment history |
| GET | `/customers/{id}/communications` | `customers.view_communications` | Communications list |
| POST | `/customers/{id}/communications` | `customers.communicate` | Add communication entry |

---

### 8.7 Suppliers - `/api/suppliers`

#### Self-service (Public / Auth)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/suppliers/register` | Public | Supplier registration → creates User + Supplier record |
| POST | `/suppliers/verify-email` | Public | Verify supplier email with token |
| POST | `/suppliers/submit-verification` | Bearer | Submit complete profile for admin review |

#### Admin management

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/suppliers/pending` | `suppliers.view` | List suppliers awaiting review |
| GET | `/suppliers` | `suppliers.view` | List all suppliers with filters |
| POST | `/suppliers` | `suppliers.create` | Create supplier manually |
| GET | `/suppliers/{id}` | `suppliers.view` | Supplier detail |
| PUT | `/suppliers/{id}` | `suppliers.edit` | Update supplier |
| POST/PATCH | `/suppliers/{id}/approve` | `suppliers.approve` | Approve supplier |
| POST/PATCH | `/suppliers/{id}/reject` | `suppliers.reject` | Reject supplier with reason |
| POST/PATCH | `/suppliers/{id}/partial-approve` | `suppliers.partial_approve` | Partial approval with required items list |
| POST | `/suppliers/{id}/request-reupload` | `suppliers.reject` | Request supplier re-upload documents |
| PATCH | `/suppliers/{id}/markup` | `suppliers.manage_markup` | Set supplier markup percentage |

**Supplier Approval Status Flow:**
```
email_verification_pending → profile_incomplete → admin_review_pending → approved / rejected
```

---

### 8.8 Agents - `/api/agents`

Same pattern as Suppliers. Replaces "markup" with:

| Method | Path | Permission | Description |
|---|---|---|---|
| PATCH | `/agents/{id}/discount` | `agents.manage_discount` | Set agent discount percentage |

---

### 8.9 Affiliates - `/api/affiliates`

Same pattern as Suppliers/Agents. Adds:

| Method | Path | Permission | Description |
|---|---|---|---|
| PATCH | `/affiliates/{id}/api-link` | `affiliates.manage_api_link` | Update affiliate API link |

---

### 8.10 CMS - Countries, Cities, Categories

#### Countries

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/countries` | `countries.view` | Paginated list |
| POST | `/countries` | `countries.create` | Create country |
| GET | `/countries/{id}` | `countries.view` | Country detail |
| PUT | `/countries/{id}` | `countries.edit` | Update country |
| PATCH | `/countries/{id}/status` | `countries.disable` | Activate / deactivate |

#### Cities

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/cities?country_id=` | `cities.view` | Paginated list, filterable by country |
| POST | `/cities` | `cities.create` | Create city |
| GET | `/cities/{id}` | `cities.view` | City detail |
| PUT | `/cities/{id}` | `cities.edit` | Update city |
| PATCH | `/cities/{id}/status` | `cities.disable` | Activate / deactivate |

#### Tour Categories

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/tour-categories` | `categories.view` | Paginated list |
| POST | `/tour-categories` | `categories.create` | Create category |
| GET | `/tour-categories/{id}` | `categories.view` | Category detail |
| PUT | `/tour-categories/{id}` | `categories.edit` | Update |
| PATCH | `/tour-categories/{id}/status` | `categories.disable` | Toggle status |

#### Tour Subcategories

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/tour-subcategories?category_id=` | `subcategories.view` | Paginated, filterable |
| POST | `/tour-subcategories` | `subcategories.create` | Create |
| GET | `/tour-subcategories/{id}` | `subcategories.view` | Detail |
| PUT | `/tour-subcategories/{id}` | `subcategories.edit` | Update |
| PATCH | `/tour-subcategories/{id}/status` | `subcategories.disable` | Toggle status |

---

### 8.11 Tours (CMS) - `/api/tours`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/tours?country_id=&city_id=&category_id=&status=` | `tours.view` | Paginated tour list with filters |
| POST | `/tours` | `tours.create` | Create tour (basic info) |
| GET | `/tours/{id}` | `tours.view` | Tour detail |
| PUT | `/tours/{id}` | `tours.edit` | Update tour |
| PATCH | `/tours/{id}/status` | `tours.publish` | Publish / disable tour |

---

### 8.12 Tour Detail Sub-Resources - `/api/tours/{tour_id}/...`

All require `tours.view` for reads and `tours.edit` for writes.

| Sub-resource | Endpoints |
|---|---|
| Overview | `GET/POST/PUT /{tour_id}/overview` |
| Itineraries | `GET/POST /{tour_id}/itineraries` · `GET/PUT/DELETE /{tour_id}/itineraries/{id}` · `PATCH /{tour_id}/itineraries/reorder` |
| Inclusions | `GET/POST /{tour_id}/inclusions` · `PUT/DELETE /{tour_id}/inclusions/{id}` |
| Exclusions | `GET/POST /{tour_id}/exclusions` · `PUT/DELETE /{tour_id}/exclusions/{id}` |
| Highlights | `GET/POST /{tour_id}/highlights` · `PUT/DELETE /{tour_id}/highlights/{id}` |
| Similar Tours | `GET/POST /{tour_id}/similar-tours` · `DELETE /{tour_id}/similar-tours/{id}` |
| Extensions | `GET/POST /{tour_id}/extensions` · `PUT/DELETE /{tour_id}/extensions/{id}` |
| Gallery | `GET/POST /{tour_id}/gallery` · `PUT/DELETE /{tour_id}/gallery/{id}` |
| Pricing | `GET/POST /{tour_id}/pricing` · `PUT/DELETE /{tour_id}/pricing/{id}` |
| Optional Activities | `GET/POST /{tour_id}/optional-activities` · `PUT/DELETE /{tour_id}/optional-activities/{id}` |
| Accommodation Extras | `GET/POST /{tour_id}/accommodation-extras` · `PUT/DELETE /{tour_id}/accommodation-extras/{id}` |
| Calendar | `GET/POST /{tour_id}/calendar` · `PUT/DELETE /{tour_id}/calendar/{id}` |
| Unavailable Dates | `GET/POST /{tour_id}/unavailable-dates` · `DELETE /{tour_id}/unavailable-dates/{id}` |
| Discounts | `GET/POST /{tour_id}/discounts` · `PUT/DELETE /{tour_id}/discounts/{id}` |
| Price Calculation | `POST /{tour_id}/calculate-price` |

---

### 8.13 Bookings - `/api/bookings` & `/api/supplier/bookings`

#### Admin / Agent routes (`/api/bookings`)

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/bookings?customer_id=&booking_status=&payment_status=&supplier_id=&...` | `bookings.view` | Paginated, role-scoped list with many filters |
| POST | `/bookings` | `bookings.create` | Create booking |
| GET | `/bookings/export` | `bookings.view` | Export booking list |
| GET | `/bookings/upcoming` | `bookings.view` | Upcoming bookings |
| POST | `/bookings/calculate-price` | Public | Calculate price without creating booking |
| GET | `/bookings/{id}` | `bookings.view` | Booking detail |
| PUT | `/bookings/{id}` | `bookings.edit` | Update booking |
| PATCH | `/bookings/{id}/status` | `bookings.update_status` | Change booking status |
| GET | `/bookings/{id}/payment-link` | `bookings.view_payments` | Get payment link for booking |
| GET | `/bookings/{id}/status-history` | `bookings.view_history` | Status change log |
| POST | `/bookings/{id}/assign-supplier` | `bookings.assign_supplier` | Assign a supplier to booking |
| PATCH | `/bookings/{id}/cancel` | `bookings.cancel` | Cancel booking |
| POST | `/bookings/{id}/communications` | `bookings.edit` | Add communication thread entry |
| POST | `/bookings/communications/{comm_id}/replies` | `bookings.edit` | Reply to communication thread |

#### Supplier routes (`/api/supplier/bookings`)

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/supplier/bookings` | `bookings.view` | Supplier's own bookings |
| GET | `/supplier/bookings/{id}` | `bookings.view` | Booking detail |
| POST | `/supplier/bookings/{id}/accept` | `bookings.update_status` | Accept booking assignment |
| POST | `/supplier/bookings/{id}/decline` | `bookings.update_status` | Decline booking assignment |

**Booking Status Values:** `pending`, `confirmed`, `in_progress`, `completed`, `cancelled`

**Payment Status Values:** `unpaid`, `partial`, `paid`, `refunded`

---

### 8.14 Payments - `/api/payments`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/payments?customer_id=&booking_id=&payment_status=&...` | `payments.view` | Paginated payment list |
| POST | `/payments` | `payments.create` | Record a payment manually |
| POST | `/payments/authorize` | `payments.create` | Authorize a payment (hold) |
| GET | `/payments/customer/{customer_id}` | `payments.view` | Customer's payment list |
| GET | `/payments/{id}` | `payments.view` | Payment detail |
| PUT | `/payments/{id}` | `payments.edit` | Update payment record |
| PATCH | `/payments/{id}/status` | `payments.edit` | Update payment status |
| POST | `/payments/{id}/capture` | `payments.capture` | Capture authorized payment |
| POST | `/payments/{id}/void` | `payments.void` | Void authorized payment |
| POST | `/payments/{id}/refund` | `payments.refund` | Process refund |

**Payment Status Values:** `pending`, `authorized`, `captured`, `partially_captured`, `voided`, `refunded`, `partially_refunded`, `failed`

**Gateway:** Currently `manual` (admin-entered). No live payment processor is integrated.

---

### 8.15 Invoices - `/api/invoices`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/invoices` | `invoices.view` | Paginated invoice list |
| POST | `/invoices` | `invoices.generate` | Create invoice record |
| GET | `/invoices/{id}` | `invoices.view` | Invoice detail |
| PUT | `/invoices/{id}` | `invoices.generate` | Update invoice |

> **Note:** PDF generation and email delivery are not yet implemented. `Invoice.pdf_path` is a plain string field.

---

### 8.16 Notifications - `/api/notifications`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/notifications?user_id=&is_read=` | `notifications.view` | Paginated notification list |
| POST | `/notifications` | `notifications.manage` | Create notification |
| PATCH | `/notifications/{id}/read` | `notifications.view` | Mark notification as read |
| POST | `/notifications/{id}/retry` | `notifications.retry` | Retry failed notification (max 5 retries) |
| POST | `/notifications/push/subscribe` | Bearer | Save push subscription |
| DELETE | `/notifications/push/subscribe` | Public | Remove push subscription |
| POST | `/notifications/push/broadcast` | `notifications.manage` | Broadcast push to all or specific users |

**Channels:** `in_app`, `email`, `push`

**Retry limit:** 5 attempts per notification (counted via `notification_logs` entries).

---

### 8.17 Reports - `/api/reports`

All require `reports.view` minimum.

| Method | Path | Description |
|---|---|---|
| GET | `/reports/summary` | Total bookings, confirmed, cancelled, captured revenue, pending payments, invoice total |
| GET | `/reports/bookings` | Bookings grouped by status with counts and amounts |
| GET | `/reports/payments` | Payments grouped by status |
| GET | `/reports/pending-payments` | Bookings with `amount_pending > 0` (top 200) |
| GET | `/reports/overdue-payments` | Bookings overdue (tour started, still unpaid) |
| GET | `/reports/country-wise` | Bookings and revenue by country |
| GET | `/reports/cancellations` | Cancelled bookings with reason and amount |
| GET | `/reports/suppliers` | Supplier booking count and revenue |
| GET | `/reports/agents` | Agent booking count and revenue |
| GET | `/reports/customers` | Customer booking count, total, and pending |
| GET | `/reports/exports` | Alias for summary (JSON only currently) |

---

### 8.18 Chatbot - `/api/chatbot`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/chatbot/chat` | Public | Send a user message; returns AI reply and `session_key` |
| GET | `/chatbot/faqs` | Public | Active FAQs for the public chatbot |
| GET | `/chatbot/admin/faqs` | Bearer | All FAQs including inactive |
| POST | `/chatbot/admin/faqs` | Bearer | Create FAQ entry |
| PUT | `/chatbot/admin/faqs/{id}` | Bearer | Update FAQ entry |
| DELETE | `/chatbot/admin/faqs/{id}` | Bearer | Delete FAQ entry |

**Chat request body:**
```json
{ "message": "What tours are available in Dubai?", "session_key": null }
```

**Chat response:**
```json
{ "status": "success", "data": { "reply": "...", "session_key": "abc123" } }
```

**Model:** `claude-haiku-4-5` with FAQ-grounded system prompt.  
**Context window:** Last 10 message pairs per session.  
**Fallback:** If `ANTHROPIC_API_KEY` is empty, returns a polite "not available" message without calling the API.

---

### 8.19 Settings - `/api/settings`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/settings/app` | `settings.view` | App settings |
| PUT | `/settings/app` | `update-settings` | Update app settings |
| GET | `/settings/payment` | `settings.view` | Payment gateway settings |
| PUT | `/settings/payment` | `update-settings` | Update payment settings |
| GET | `/settings/api` | `settings.view` | API / integration settings |
| PUT | `/settings/api` | `update-settings` | Update API settings |

---

### 8.20 Email Templates - `/api/email-templates`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/email-templates` | `view-email` | List templates |
| POST | `/email-templates` | `create-email` | Create template |
| GET | `/email-templates/{id}` | `view-email` | Template detail |
| PUT | `/email-templates/{id}` | `update-email` | Update template |
| DELETE | `/email-templates/{id}` | `delete-email` | Delete template |

**Template keys used by the system:**

| Key | Used when |
|---|---|
| `email_verification` | After registration |
| `password_reset` | Forgot password |
| `password_changed` | After successful reset |
| `registration_pending` | Non-customer registration (awaiting approval) |

If a key is not found in the DB, the system falls back to hardcoded HTML templates in `common/email_templates.py`.

---

### 8.21 Profile - `/api/profile`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/profile` | `profile.view` | Current user's profile |
| PUT | `/profile` | `update-profile` | Update profile |
| POST | `/profile/change-password` | Bearer | Change own password |

---

### 8.22 Uploads - `/api/uploads`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/uploads` | Bearer | Upload a file; returns stored path |

Files are stored under `STORAGE_ROOT` (default: `backend/storage/`).

---

### 8.23 Audit Logs - `/api/audit-logs`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/audit-logs?entity_type=&action=&actor_id=` | `activity_logs.view` | Paginated audit log |

Every service call that mutates data calls `log_audit(db, actor, action, entity_type, entity_id, old_values, new_values)`.

---

### 8.24 Sessions - `/api/sessions`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/sessions` | `sessions.view` | List active sessions |
| DELETE | `/sessions/{id}` | `sessions.revoke` | Revoke a session |

---

### 8.25 Client API - `/api/client`

Public-facing endpoints for the customer-side frontend (tours browsing, booking flow, self-service). Exact endpoints mirror relevant admin reads but without admin permissions.

---

## 9. Data Models

### User

```
id, name, email, phone, password (hashed), profile_image, address, country, state, city, pincode
role_id (FK → roles), is_active, approval_status, token_version
email_verified_at, email_verification_token (hash), email_verification_expires_at
reset_password_token (hash), reset_password_expires_at
created_at, updated_at
```

**Relationships:** `role` (many-to-one), `user_roles` (many-to-many via `UserRole`)

**`approval_status` values:** `pending`, `approved`, `rejected`

### Booking

```
id, booking_code, tour_id, customer_id, supplier_id, agent_id
booking_status, payment_status, supplier_acceptance_status
tour_start_date, tour_end_date, number_of_adults, number_of_children
base_amount, discount_amount, tax_amount, final_amount, amount_paid, amount_pending
promo_code, currency, country_id, notes, cancellation_reason, cancelled_at
created_at, updated_at
```

### Payment

```
id, payment_code, booking_id, customer_id
payment_method, gateway (default: "manual"), gateway_payment_id, gateway_order_id
payment_status, amount, authorized_amount, captured_amount, refunded_amount
transaction_date, due_date, notes
created_at, updated_at
```

### Notification

```
id, user_id, notification_type, title, message, channel
status (pending/sent/failed), is_read, entity_type, entity_id
metadata_json, sent_at, read_at, created_at
```

---

## 10. Email System

**Sending via:** `app/modules/common/mailer.py`

```python
send_email(to, subject, html)      # raises on failure
try_send_email(to, subject, html)  # logs error, does not raise
```

**Config:** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` from `.env`.  
**From name:** `SMTP_FROM_NAME` (default: "Tourvaa").

**Template resolution:**

1. `render_database_email(db, key, context, fallback_subject, fallback_html)` - looks up key in `email_templates` table
2. If not found in DB → uses the fallback HTML passed in (hardcoded templates in `common/email_templates.py`)

**System emails sent:**

| Event | Template key | Recipient |
|---|---|---|
| Registration | `email_verification` | New user |
| Non-customer registration | `registration_pending` | New user |
| Forgot password | `password_reset` | User |
| Password changed | `password_changed` | User |
| Booking created | booking-related | Customer + admin |
| Supplier approved/rejected | - | Supplier |

---

## 11. File Storage

- **Root:** `STORAGE_ROOT` (default: `backend/storage/`, resolved as absolute path relative to `app/`)
- **Upload endpoint:** `POST /api/uploads`
- **Path resolution:** `existing_storage_path(path)` in `common/media.py` checks the file exists and returns the accessible URL or `None`
- **Usage:** Profile images, supplier/agent/affiliate documents, tour gallery images

---

## 12. Rate Limiting

Implemented in `app/modules/common/ratelimit.py`.

**Type:** In-memory sliding-window per `(IP, endpoint_key)`.

**Limits:**

| Endpoint | Max calls | Window |
|---|---|---|
| `POST /auth/login` | 10 | 60 seconds |
| `POST /auth/forgot-password` | 5 | 300 seconds |
| `POST /auth/verify-email` | 10 | 60 seconds |

**IP detection:** Reads `X-Forwarded-For` header first, falls back to `request.client.host`.

**Memory cleanup:** Stale buckets (no activity for 10 min) are pruned every 5 minutes.

**Production limitation:** Single-process only. Under Gunicorn multi-worker, each worker has its own counter. For true multi-process rate limiting, replace with Redis-backed throttling.

---

## 13. Seeding & Bootstrap

**File:** `app/seed.py`  
**Called from:** startup event in the main app on every boot.

**What it does:**
1. Upserts `AdminModule` records (sidebar definitions)
2. Upserts all `Role` records (`super-admin` through `affiliate`)
3. Upserts all `Permission` records (150+)
4. Assigns default permissions to each role
5. Creates or updates the super admin `User` from `SUPER_ADMIN_EMAIL` + `SUPER_ADMIN_PASSWORD`
6. Seeds a demo tour (Dubai City Highlights) if no tours exist

**Safe to re-run:** All operations are upserts - existing records are updated, not duplicated.

**Demo tour:** Only seeded when `tours` table is empty. Useful for local dev smoke tests.

---

## 14. Running the Server

### Development

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### First-time setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create the database
mysql -u root -p -e "CREATE DATABASE tourvaa_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 3. Copy and fill .env
cp .env.example .env
# edit .env - set DATABASE_URL, JWT_SECRET_KEY, SMTP_*, ANTHROPIC_API_KEY

# 4. Run migrations
python -m alembic upgrade head

# 5. Start server (seed runs automatically on startup)
python -m uvicorn app.main:app --reload --port 8000
```

### Interactive API Docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## 15. Common Response Format

All endpoints return a consistent JSON envelope:

**Success:**
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

**Error (FastAPI HTTPException):**
```json
{
  "detail": "Human-readable error message"
}
```

**Pagination query params** (via `pagination_params` dependency):

| Param | Default | Description |
|---|---|---|
| `page` | `1` | Page number |
| `limit` | `20` | Results per page |
| `search` | `""` | Search string |

---

## 16. Permission Slug Reference

### Core CRUD (legacy format)

```
view-dashboard   create-dashboard   update-dashboard   delete-dashboard
view-users       create-users       update-users       delete-users
view-roles       create-roles       update-roles       delete-roles
view-permissions create-permissions update-permissions delete-permissions
view-tours       create-tours       update-tours       delete-tours
view-bookings    create-bookings    update-bookings    delete-bookings
view-payments    create-payments    update-payments    delete-payments
view-reports     create-reports     update-reports     delete-reports
view-invoices    create-invoices    update-invoices    delete-invoices
view-notifications                  update-notifications
view-email       create-email       update-email       delete-email
view-settings                       update-settings
view-profile                        update-profile
view-customers   create-customers   update-customers   delete-customers
view-suppliers   create-suppliers   update-suppliers
view-agents      create-agents      update-agents
view-affiliates
```

### Granular dotted format

```
dashboard.view   dashboard.summary   dashboard.charts   dashboard.activities   dashboard.alerts
customers.view   customers.create    customers.edit     customers.block        customers.unblock
customers.reset_password   customers.view_bookings   customers.view_payments
customers.view_communications   customers.communicate   customers.export
suppliers.view   suppliers.create   suppliers.edit     suppliers.approve      suppliers.reject
suppliers.partial_approve   suppliers.manage_markup   suppliers.view_documents
suppliers.reset_password   suppliers.communicate   suppliers.export
agents.view      agents.create      agents.edit        agents.approve         agents.reject
agents.partial_approve   agents.manage_discount   agents.view_documents
affiliates.view  affiliates.approve affiliates.reject  affiliates.manage_api_link
affiliates.view_documents   affiliates.export
countries.view   countries.create   countries.edit     countries.disable
cities.view      cities.create      cities.edit        cities.disable
categories.view  categories.create  categories.edit    categories.disable
subcategories.view subcategories.create subcategories.edit subcategories.disable
tours.view       tours.create       tours.edit         tours.publish          tours.disable
bookings.view    bookings.create    bookings.edit      bookings.update_status bookings.assign_supplier
bookings.cancel  bookings.view_travellers bookings.view_payments bookings.view_history bookings.export
payments.view    payments.create    payments.edit      payments.capture       payments.void
payments.refund  payments.view_transactions payments.export payments.manage_settings payments.summary
invoices.view    invoices.generate  invoices.email     invoices.download      invoices.export
notifications.view notifications.manage notifications.retry
reports.view     reports.admin      reports.supplier   reports.agent          reports.export
activity_logs.view   activity_logs.export
sessions.view    sessions.revoke    sessions.force_logout
settings.view    profile.view
```

---

*Documentation generated 2026-06-22 from source code. Reflects the current state of `d:\ayati\tourvaa\backend`.*
