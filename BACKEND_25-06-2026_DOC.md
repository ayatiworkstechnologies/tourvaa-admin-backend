# Tourvaa Backend Documentation - 25-06-2026

## Executive Summary

Tourvaa backend is a FastAPI REST API for a multi-role travel booking platform. It supports admin operations, public tour browsing, customer booking, supplier acceptance, agent booking support, affiliate tracking, payments, invoices, reports, notifications, audit logs, website CMS, cancellations, supplier ledgers, and chatbot FAQs.

This document is based on the backend source under `D:\ayati\tourvaa\backend` as inspected on 25-06-2026.

| Area | Status | Notes |
| --- | --- | --- |
| Backend API | Partially Completed | Broad API surface exists, but several workflows need production hardening and frontend contract cleanup. |
| Database Models | Mostly Completed | Around 70 SQLAlchemy models are present across operational modules. |
| Authentication | Mostly Completed | JWT, password hashing, refresh, email verification, password reset, sessions, token version invalidation exist. |
| RBAC | Mostly Completed | Role/permission system exists, but permission slug formats are mixed. |
| Booking Flow | Mostly Completed | Admin, agent, supplier, and customer booking flows exist. |
| Payment Flow | Partially Completed | Manual/payment lifecycle and Stripe/PayPal routes exist; gateway production validation is still required. |
| CMS/Tour Management | Mostly Completed | Base tours and detailed tour sub-resources are implemented. |
| Production Readiness | Not Ready | Needs security, contract, deployment, logging, file upload, and payment hardening. |

## 1. Project Overview

| Item | Details |
| --- | --- |
| Project Name | Tourvaa Backend |
| Purpose | Backend API for tour marketplace, admin panel, partner portals, and public website. |
| Main Users | Super Admin, Admin/Sub Admin, Customer, Supplier, Agent/Reseller, Affiliate. |
| API Framework | FastAPI |
| ORM | SQLAlchemy |
| Migration Tool | Alembic |
| Validation | Pydantic v2 |
| Auth | JWT using `python-jose`, bcrypt using Passlib |
| Database | Configurable through `DATABASE_URL`; SQLite-compatible for tests and likely MySQL/PostgreSQL-compatible for production. |
| Storage | Local storage mounted at `/storage` through FastAPI static files. |

Main business flow:

1. Admin configures roles, permissions, locations, categories, payment/API settings, and CMS content.
2. Supplier, agent, affiliate, and customer users register.
3. Supplier/agent/affiliate accounts go through approval or profile completion workflows.
4. Admin or supplier creates tours and tour detail content.
5. Supplier submits tours for approval.
6. Admin approves/rejects tour versions.
7. Customer or agent creates bookings.
8. Supplier accepts, declines, completes, cancels, postpones, or notifies about booking.
9. Payment, invoice, cancellation, refund, supplier payout, and affiliate commission flows are tracked.
10. Reports, notifications, sessions, and audit logs support operations.

## 2. Backend Technology Stack

| Component | File / Package | Purpose |
| --- | --- | --- |
| FastAPI app | `app/main.py` | Creates app, mounts CORS/static storage, registers routers. |
| Settings | `app/config.py` | Loads environment variables through Pydantic settings. |
| Database | `app/database.py` | SQLAlchemy engine, session factory, declarative base. |
| Security | `app/security.py` | Password hashing, JWT creation, reset token hashing. |
| Auth dependencies | `app/modules/common/auth.py` | Current user, portal guard, permission guard. |
| Pagination | `app/modules/common/pagination.py` | Common page/limit/search dependency. |
| Rate limit | `app/modules/common/ratelimit.py` | In-memory rate limiting for auth endpoints. |
| Email | `app/modules/common/mailer.py` | SMTP email sending. |
| Migrations | `alembic/versions/*.py` | Schema history from production hardening through phase modules. |
| Tests | `tests/test_*.py` | Backend regression tests by module. |

## 3. Backend Folder Structure

| File / Folder Path | Purpose | Status | Notes |
| --- | --- | --- | --- |
| `backend/app/main.py` | FastAPI application entry | Working | Registers all routers and startup seed. |
| `backend/app/config.py` | Environment config | Working | Defaults are development-oriented; production values required. |
| `backend/app/database.py` | DB engine/session | Working | Supports SQLite with `check_same_thread=False`. |
| `backend/app/security.py` | Password/JWT utilities | Working | Supports portal-specific JWT secrets. |
| `backend/app/seed.py` | Default role/permission/admin seed | Working | Runs at startup only when schema is ready. |
| `backend/app/modules/auth` | Login/register/password/email auth | Mostly working | Needs stronger token storage strategy on frontend side. |
| `backend/app/modules/users` | User CRUD and approval | Mostly working | Includes role assignment and reset mail. |
| `backend/app/modules/roles` | Role CRUD and role permissions | Mostly working | Duplicate router mount under `/api` and `/api/admin`. |
| `backend/app/modules/permissions` | Permission CRUD | Mostly working | Uses legacy permission guards. |
| `backend/app/modules/admin_modules` | Sidebar/admin module definitions | Working | Used by dashboard/menu. |
| `backend/app/modules/dashboard` | Role-aware dashboard data | Mostly working | Needs performance review as dataset grows. |
| `backend/app/modules/profile` | Current user profile/password | Working | Password change increments token version. |
| `backend/app/modules/settings` | App/payment/API settings | Mostly working | Sensitive settings need encryption at rest. |
| `backend/app/modules/email_templates` | Email template CRUD | Mostly working | Template fallback exists. |
| `backend/app/modules/uploads` | Profile/admin asset uploads | Partially working | Needs production file validation and scanning. |
| `backend/app/modules/client` | Public/client tour API | Working | Separate from `/api/public` public router. |
| `backend/app/modules/public` | Public website API | Working | Mounted under `/api/public`. |
| `backend/app/modules/customers` | Customer admin + portal | Mostly working | Profile APIs have both `/customers/me` and `/customer/profile` patterns. |
| `backend/app/modules/suppliers` | Supplier onboarding/admin/profile | Mostly working | Frontend currently calls one submit-verification URL incorrectly. |
| `backend/app/modules/agents` | Agent onboarding/admin/profile | Mostly working | Agent message API is likely incomplete. |
| `backend/app/modules/affiliates` | Affiliate admin profile | Mostly working | Tracking is in separate module. |
| `backend/app/modules/affiliate_tracking` | Links, clicks, conversions, payouts | Mostly working | Payout lifecycle needs more states/actions. |
| `backend/app/modules/cms` | Countries/states/cities/categories/tours | Mostly working | Includes geo routers. |
| `backend/app/modules/tours` | Tour detail sub-resources | Mostly working | Broad CRUD coverage. |
| `backend/app/modules/tour_versions` | Tour approval workflow | Mostly working | Snapshot approval flow exists. |
| `backend/app/modules/bookings` | Booking lifecycle | Mostly working | Complex role filtering and supplier flow exist. |
| `backend/app/modules/payments` | Payment lifecycle and gateways | Partially working | Gateway/webhook hardening needed. |
| `backend/app/modules/invoices` | Invoice generation/download/email | Mostly working | PDF file existence errors handled. |
| `backend/app/modules/notifications` | In-app/push notification | Mostly working | Push depends on VAPID config. |
| `backend/app/modules/reports` | Reports and snapshots | Mostly working | Export endpoint appears JSON-oriented. |
| `backend/app/modules/sessions` | User sessions/login history | Mostly working | Useful for force logout and audits. |
| `backend/app/modules/audit` | Activity log listing/export | Mostly working | Frontend uses `/audit-logs`, backend exposes `/activity-logs`. |
| `backend/app/modules/chatbot` | FAQ/chat endpoints | Partially working | Depends on external AI key where configured. |
| `backend/app/modules/website_cms` | Public website CMS | Mostly working | Frontend public pages need full wiring. |
| `backend/app/modules/cancellations` | Cancellation/refund rules | Mostly working | Refund gateway integration needs validation. |
| `backend/app/modules/booking_calendar` | Booking calendar/ICS sync | Partially working | Calendar provider handling needs verification. |
| `backend/app/modules/supplier_ledger` | Supplier ledger and payouts | Partially working | Backend lacks frontend-expected payout approval endpoint. |
| `backend/alembic` | DB migrations | Mostly working | Migration state must be verified in target DB. |
| `backend/tests` | Pytest backend tests | Present | Run before handover/deployment. |

## 4. Authentication and Security Flow

### 4.1 Auth Endpoints

| Method | Endpoint | File | Purpose | Auth |
| --- | --- | --- | --- | --- |
| POST | `/api/auth/register` | `app/modules/auth/router.py` | Generic registration | Public |
| POST | `/api/auth/register/customer` | `app/modules/auth/router.py` | Customer registration | Public |
| POST | `/api/auth/register/supplier` | `app/modules/auth/router.py` | Supplier registration | Public |
| POST | `/api/auth/register/agent` | `app/modules/auth/router.py` | Agent registration | Public |
| POST | `/api/auth/login` | `app/modules/auth/router.py` | Login and token creation | Public, rate limited |
| GET | `/api/auth/me` | `app/modules/auth/router.py` | Current session/user payload | Bearer |
| POST | `/api/auth/forgot-password` | `app/modules/auth/router.py` | Send reset link | Public, rate limited |
| POST | `/api/auth/reset-password` | `app/modules/auth/router.py` | Reset password by token | Public |
| GET | `/api/auth/reset-password/validate` | `app/modules/auth/router.py` | Validate reset token | Public |
| POST | `/api/auth/refresh-token` | `app/modules/auth/router.py` | Refresh expired token if version valid | Bearer |
| POST | `/api/auth/refresh` | `app/modules/auth/router.py` | Alias for refresh-token | Bearer |
| POST | `/api/auth/logout` | `app/modules/auth/router.py` | Logout current user | Bearer |
| POST | `/api/auth/verify-email` | `app/modules/auth/router.py` | Verify email token | Public, rate limited |
| GET | `/api/auth/login-history` | `app/modules/auth/router.py` | Current user's login history | Bearer |
| POST | `/api/auth/force-logout` | `app/modules/auth/router.py` | Force logout self or user | `update-users` |

### 4.2 Auth Implementation

| Item | Implementation |
| --- | --- |
| Password hashing | `hash_password()` and `verify_password()` in `app/security.py` using bcrypt. |
| Password validation | Strong password regex in `app/modules/auth/schemas.py`: uppercase, lowercase, digit, special character, minimum 8 chars. |
| Phone validation | E.164-like regex in `RegisterSchema`. |
| JWT creation | `create_token(data, portal)` in `app/security.py`. |
| Portal secrets | `Settings.get_portal_secret()` in `app/config.py`. |
| Token validation | `_decode_token()` and `get_current_user()` in `app/modules/common/auth.py`. |
| Session invalidation | `users.token_version` is checked on every authenticated request. |
| Email verification | Token stored hashed, expiry supported. |
| Reset password | Token stored hashed, expiry supported. |

### 4.3 Security Issues

| Severity | Issue | File | Recommendation |
| --- | --- | --- | --- |
| High | Default `ALLOWED_ORIGINS="*"` is not production-safe. | `app/config.py` | Use explicit production frontend domains. |
| High | Local static storage is public once stored under `/storage`. | `app/main.py`, upload modules | Use private object storage for sensitive documents. |
| High | Payment gateway webhooks need strict production verification and replay protection. | `app/modules/payments/gateway_router.py` | Enforce signature verification, idempotency, event logs. |
| Medium | In-memory rate limiter is not shared between workers. | `app/modules/common/ratelimit.py` | Replace with Redis rate limiting. |
| Medium | API/payment secrets appear stored as plain DB values. | `app/modules/settings/models.py` | Encrypt sensitive config at rest. |
| Medium | Permission slug formats are mixed. | `app/modules/common/auth.py`, seed/services | Normalize to one canonical format. |
| Medium | Not every route uses `require_portal()`. | `app/modules/common/auth.py` | Enforce portal claim for portal-only APIs. |

## 5. RBAC and User Roles

| Role | Purpose | Flow |
| --- | --- | --- |
| `super-admin` | Full platform ownership | Seeded; broad permissions. |
| `admin` / `sub-admin` | Back-office operations | Created/managed by admin users. |
| `customer` | Browse/book tours, view bookings/payments/support | Can register publicly. |
| `supplier` | Manage tours and supplier bookings | Register, complete profile, submit verification, admin approval. |
| `agent-reseller` | Create bookings for customers, manage agent profile/customers | Register, approval/profile flow. |
| `affiliate` | Referral links, clicks, conversions, payouts | Managed through affiliate modules. |

Permission system:

| Table | Purpose |
| --- | --- |
| `roles` | Role records with `slug`, `name`, active/system flags. |
| `permissions` | Permission records with `slug`, `module`, `action`. |
| `role_permissions` | Many-to-many role/permission assignment. |
| `user_roles` | Additional many-to-many user role assignment beyond `users.role_id`. |

Important note: `app/modules/common/auth.py` supports both dotted slugs like `bookings.view` and legacy slugs like `view-bookings`, but module aliases are limited. This is useful for compatibility but should be cleaned up before production.

## 6. Database Structure

### 6.1 Core Tables and Fields

| Table | Model File | Fields |
| --- | --- | --- |
| `admin_modules` | `app/modules/admin_modules/models.py` | `id`, `name`, `slug`, `description`, `is_active`, `is_system`, `created_at`, `updated_at` |
| `roles` | `app/modules/roles/models.py` | `id`, `name`, `slug`, `is_active`, `is_system`, `created_at` |
| `permissions` | `app/modules/permissions/models.py` | `id`, `name`, `slug`, `module`, `action`, `is_active`, `is_system`, `created_at` |
| `role_permissions` | `app/modules/permissions/models.py` | `id`, `role_id`, `permission_id` |
| `users` | `app/modules/users/models.py` | `id`, `name`, `email`, `phone`, `password`, `profile_image`, `address`, `country`, `state`, `city`, `pincode`, `role_id`, `is_active`, `approval_status`, `reset_password_token`, `reset_password_expires_at`, `token_version`, `email_verified_at`, `email_verification_token`, `email_verification_expires_at`, `two_factor_enabled`, `force_password_reset`, `created_at`, `updated_at` |
| `user_roles` | `app/modules/users/models.py` | `id`, `user_id`, `role_id`, `created_at` |
| `user_sessions` | `app/modules/sessions/models.py` | `id`, `user_id`, `session_id`, `ip_address`, `user_agent`, `status`, `revoked_at`, `last_seen_at`, `created_at` |
| `login_history` | `app/modules/sessions/models.py` | `id`, `user_id`, `email`, `status`, `failure_reason`, `client_type`, `device_id`, `device_name`, `ip_address`, `user_agent`, `session_id`, `created_at` |
| `audit_logs` | `app/modules/audit/models.py` | `id`, `actor_user_id`, `action`, `entity_type`, `entity_id`, `old_values`, `new_values`, `ip_address`, `user_agent`, `created_at` |

### 6.2 Customer and Partner Tables

| Table | Model File | Fields |
| --- | --- | --- |
| `customers` | `app/modules/customers/models.py` | Customer identity/profile/status/block/verification fields, location fields, booking/payment metadata, timestamps. |
| `customer_communications` | `app/modules/customers/models.py` | `id`, `customer_id`, `booking_id`, message/email fields, status fields, timestamps. |
| `customer_saved_travellers` | `app/modules/customers/models.py` | Traveller name/contact/type/age/gender/passport/allergy/special note fields. |
| `customer_cancellation_requests` | `app/modules/customers/models.py` | Customer cancellation request, status, admin notes, review fields. |
| `suppliers` | `app/modules/suppliers/models.py` | `id`, `user_id`, `supplier_code`, `supplier_name`, `supplier_type`, location IDs, operation years, status, approval fields, markup fields, timestamps. |
| `supplier_contacts` | `app/modules/suppliers/models.py` | Contact person fields and primary flag. |
| `supplier_business_info` | `app/modules/suppliers/models.py` | Business certificates, customer/destination/tax/registration fields. |
| `supplier_vehicles` | `app/modules/suppliers/models.py` | Vehicle make/model/year/capacity/doc/photo approval fields. |
| `supplier_invoicing` | `app/modules/suppliers/models.py` | Bank/account/tax/contact invoicing fields. |
| `supplier_documents` | `app/modules/suppliers/models.py` | Document type/name/path/size/mime/status/review fields. |
| `agents` | `app/modules/agents/models.py` | Agent code/name/type, location, operation years, status, approval fields, discount fields. |
| `agent_contacts` | `app/modules/agents/models.py` | Agent contact details. |
| `agent_business_info` | `app/modules/agents/models.py` | Agent business proof, target market, destinations, IATA/GST. |
| `agent_invoicing` | `app/modules/agents/models.py` | Agent bank/account/tax/contact fields. |
| `agent_documents` | `app/modules/agents/models.py` | Agent document metadata and review state. |
| `affiliates` | `app/modules/affiliates/models.py` | Affiliate code/business/name/email/phone/site/location/status/approval/API link fields. |
| `affiliate_marketing_info` | `app/modules/affiliates/models.py` | Promotion methods, audience, platform data. |
| `affiliate_invoicing` | `app/modules/affiliates/models.py` | Bank/contact/tax fields. |
| `affiliate_documents` | `app/modules/affiliates/models.py` | Affiliate document metadata and review state. |

### 6.3 Tour, Booking, Payment, Operations Tables

| Table | Model File | Fields |
| --- | --- | --- |
| `countries` | `app/modules/cms/models.py` | `id`, `country_name`, `country_code`, `phone_code`, `currency_code`, `status`, timestamps |
| `states` | `app/modules/cms/models.py` | `id`, `country_id`, `state_name`, `state_code`, `status`, timestamps |
| `cities` | `app/modules/cms/models.py` | `id`, `country_id`, `state_id`, `city_name`, `status`, timestamps |
| `tour_categories` | `app/modules/cms/models.py` | `id`, `category_name`, `slug`, `description`, `image`, `status`, timestamps |
| `tour_subcategories` | `app/modules/cms/models.py` | `id`, `category_id`, `subcategory_name`, `slug`, `description`, `image`, `status`, timestamps |
| `tour_subcategory_map` | `app/modules/cms/models.py` | `id`, `tour_id`, `subcategory_id`, `created_at` |
| `tours` | `app/modules/cms/models.py` | `id`, `tour_code`, `supplier_id`, title/slug/subtitle, price/currency, location/category IDs, location text, duration, descriptions, SEO/media/status/audit fields |
| `tour_overviews` | `app/modules/tours/models.py` | `id`, `tour_id`, duration/location/group/type/rating/icon data, timestamps |
| `tour_itineraries` | `app/modules/tours/models.py` | Day number/title/location/descriptions/activities/image/order/status/timestamps |
| `tour_inclusions`, `tour_exclusions` | `app/modules/tours/models.py` | Icon/title/description/order/status/timestamps |
| `tour_highlights` | `app/modules/tours/models.py` | Image/title/description/order/status/timestamps |
| `tour_similar_tours` | `app/modules/tours/models.py` | `tour_id`, `similar_tour_id`, display/status |
| `tour_extensions` | `app/modules/tours/models.py` | Extension tour/title/note/price/order/status |
| `tour_gallery_images` | `app/modules/tours/models.py` | Image path/title/alt/caption/type/order/status |
| `tour_pricing` | `app/modules/tours/models.py` | Passenger range, adult/child/supplier/final price, markup, currency, status |
| `tour_optional_activities` | `app/modules/tours/models.py` | Activity name/description/price/image/status |
| `tour_accommodation_extras` | `app/modules/tours/models.py` | Accommodation name/description/extra price/type/default/status |
| `tour_calendar` | `app/modules/tours/models.py` | Tour date/start/end, available/booked seats, status |
| `tour_unavailable_dates` | `app/modules/tours/models.py` | Date/reason |
| `tour_discounts` | `app/modules/tours/models.py` | Category/country, code/type/value/scope/date/usage/minimum/status |
| `tour_versions` | `app/modules/tour_versions/models.py` | `id`, `tour_id`, `version_number`, `snapshot`, `status`, submit/review fields |
| `bookings` | `app/modules/bookings/models.py` | Booking code, customer/tour/calendar/supplier/agent/affiliate IDs, traveller counts, amount breakdown, statuses, notes, cancellation fields, timestamps |
| `booking_travellers` | `app/modules/bookings/models.py` | Traveller type/name/DOB/age/gender/nationality/passport/contact/special fields |
| `booking_optional_activities` | `app/modules/bookings/models.py` | Selected activity snapshot, quantity, price |
| `booking_accommodations` | `app/modules/bookings/models.py` | Accommodation snapshot, quantity, price type, price |
| `booking_extensions` | `app/modules/bookings/models.py` | Extension snapshot, quantity, price |
| `booking_status_history` | `app/modules/bookings/models.py` | Old/new status, actor, source, reason, metadata |
| `booking_communications`, `message_replies`, `email_logs` | `app/modules/bookings/models.py` | Booking communication, replies, email delivery logs |
| `payments`, `payment_transactions`, `payment_holds` | `app/modules/payments/models.py` | Payment code, booking/customer, method/gateway, amount lifecycle, statuses, transactions, holds |
| `invoices`, `invoice_items` | `app/modules/invoices/models.py` | Invoice number, booking/payment/customer links, totals, PDF path, email status, line items |
| `supplier_ledgers`, `supplier_payouts`, `supplier_payout_items` | `app/modules/supplier_ledger/models.py` | Supplier payable ledger, payout, payout items |
| `affiliate_links`, `affiliate_clicks`, `affiliate_conversions`, `affiliate_payouts` | `app/modules/affiliate_tracking/models.py` | Affiliate tracking and payout records |
| `notifications`, `notification_logs`, `push_subscriptions` | `app/modules/notifications/models.py` | Notification delivery/read/log/push subscription records |
| `chat_faqs`, `chat_sessions`, `chat_messages` | `app/modules/chatbot/models.py` | Chatbot FAQ and conversation state |
| `checkout_sessions` | `app/modules/checkout/models.py` | Checkout state by session key, user/customer/tour/booking links |
| `cancellation_requests`, `refund_rules` | `app/modules/cancellations/models.py` | Cancellation/refund review and rules |
| `booking_calendar_events` | `app/modules/booking_calendar/models.py` | External/ICS calendar event state |
| `cms_*` tables | `app/modules/website_cms/models.py` | Homepage banners, popular destinations/tours, deals, blogs, reviews, help centre, policies, popups, external links, sitemap |

### 6.4 Migration and Seed Status

| Area | Status |
| --- | --- |
| Alembic migrations | Present through `20260624_0020_add_states_table.py`. |
| Startup seed | Present in `app/main.py`; runs when required tables/columns exist. |
| Role/permission seed | Present in `app/seed.py`. |
| Email template seed | Present through `seed_email_templates()` from `app/modules/email_templates/service.py`. |
| Geo seed script | Present at `scripts/seed_geo.py`. |

## 7. API Modules and Endpoints

All API endpoints are mounted under `/api` unless otherwise noted.

### 7.1 Core/Admin APIs

| Method | Endpoint | Module | Purpose | Auth |
| --- | --- | --- | --- | --- |
| GET | `/api/health` | Core | Health check | Public |
| GET | `/api/modules` | Admin Modules | List admin modules | Permission |
| GET | `/api/dashboard/me` | Dashboard | Current user dashboard/menus/permissions | Bearer |
| GET | `/api/dashboard/summary` | Dashboard | Role-scoped summary | Bearer |
| GET | `/api/dashboard/charts` | Dashboard | Chart data | Bearer |
| GET | `/api/dashboard/recent-activities` | Dashboard | Recent activity | Bearer |
| GET | `/api/dashboard/alerts` | Dashboard | Alerts | Bearer |
| GET | `/api/dashboard/bookings` | Dashboard | Booking analytics | Bearer |
| GET | `/api/dashboard/revenue` | Dashboard | Revenue analytics | Bearer |
| GET | `/api/dashboard/payments` | Dashboard | Payment summary | Bearer |
| GET | `/api/dashboard/reports` | Dashboard | Report summary | Bearer |
| GET | `/api/profile/me` | Profile | Current user profile | Bearer |
| PUT | `/api/profile/me` | Profile | Update profile | Bearer |
| PUT | `/api/profile/password` | Profile | Change password | Bearer |

### 7.2 RBAC APIs

| Method | Endpoint | Module | Purpose | Auth |
| --- | --- | --- | --- | --- |
| GET | `/api/users/` | Users | List users | Permission |
| POST | `/api/users/` | Users | Create user | Permission |
| GET | `/api/users/{user_id}` | Users | User detail | Permission |
| PUT | `/api/users/{user_id}` | Users | Update user | Permission |
| DELETE | `/api/users/{user_id}` | Users | Delete user | Permission |
| POST | `/api/users/{user_id}/approve` | Users | Approve pending user | Permission |
| POST | `/api/users/{user_id}/reject` | Users | Reject pending user | Permission |
| POST | `/api/users/{user_id}/send-reset-mail` | Users | Send reset email | Permission |
| POST | `/api/users/{user_id}/roles` | Users | Assign user roles | Permission |
| GET | `/api/roles/public/options` | Roles | Public role options | Public |
| GET | `/api/roles/` | Roles | List roles | Permission |
| POST | `/api/roles/` | Roles | Create role | Permission |
| GET | `/api/roles/{role_id}` | Roles | Role detail | Permission |
| PUT | `/api/roles/{role_id}` | Roles | Update role | Permission |
| DELETE | `/api/roles/{role_id}` | Roles | Delete role | Permission |
| GET | `/api/roles/{role_id}/permissions` | Roles | Role permissions | Permission |
| POST | `/api/roles/{role_id}/permissions` | Roles | Assign role permissions | Permission |
| GET | `/api/permissions/` | Permissions | List permissions | Permission |
| POST | `/api/permissions/` | Permissions | Create permission | Permission |
| GET | `/api/permissions/{permission_id}` | Permissions | Permission detail | Permission |
| PUT | `/api/permissions/{permission_id}` | Permissions | Update permission | Permission |
| DELETE | `/api/permissions/{permission_id}` | Permissions | Delete permission | Permission |

### 7.3 CMS and Tour APIs

| Method | Endpoint | Module | Purpose | Auth |
| --- | --- | --- | --- | --- |
| GET/POST | `/api/countries` | CMS | List/create countries | Permission/Public for some usage |
| GET/PUT | `/api/countries/{country_id}` | CMS | Country detail/update | Permission |
| PATCH | `/api/countries/{country_id}/status` | CMS | Change country status | Permission |
| GET/POST | `/api/states` | CMS | List/create states | Permission/Public for some usage |
| GET/PUT | `/api/states/{state_id}` | CMS | State detail/update | Permission |
| PATCH | `/api/states/{state_id}/status` | CMS | Change state status | Permission |
| GET/POST | `/api/cities` | CMS | List/create cities | Permission/Public for some usage |
| GET/PUT | `/api/cities/{city_id}` | CMS | City detail/update | Permission |
| PATCH | `/api/cities/{city_id}/status` | CMS | Change city status | Permission |
| GET/POST | `/api/tour-categories` | CMS | List/create categories | Permission |
| GET/PUT | `/api/tour-categories/{category_id}` | CMS | Category detail/update | Permission |
| PATCH | `/api/tour-categories/{category_id}/status` | CMS | Change category status | Permission |
| GET/POST | `/api/tour-subcategories` | CMS | List/create subcategories | Permission |
| GET/PUT | `/api/tour-subcategories/{subcategory_id}` | CMS | Subcategory detail/update | Permission |
| PATCH | `/api/tour-subcategories/{subcategory_id}/status` | CMS | Change subcategory status | Permission |
| GET/POST | `/api/tours` | CMS | List/create base tours | Permission |
| GET | `/api/tours/categories` | Tours | Category options for tour forms | Bearer/Permission |
| GET/PUT | `/api/tours/{tour_id}` | CMS | Tour detail/update | Permission |
| PATCH | `/api/tours/{tour_id}/status` | CMS | Change tour status | Permission |

Tour detail sub-resource endpoints:

| Resource | Endpoints |
| --- | --- |
| Overview | `GET/POST/PUT /api/tours/{tour_id}/overview` |
| Itineraries | `GET/POST /api/tours/{tour_id}/itineraries`, `GET/PUT/DELETE /api/tours/{tour_id}/itineraries/{itinerary_id}`, `PATCH /api/tours/{tour_id}/itineraries/reorder` |
| Inclusions | `GET/POST /api/tours/{tour_id}/inclusions`, `PUT/DELETE /api/tours/{tour_id}/inclusions/{inclusion_id}` |
| Exclusions | `GET/POST /api/tours/{tour_id}/exclusions`, `PUT/DELETE /api/tours/{tour_id}/exclusions/{exclusion_id}` |
| Highlights | `GET/POST /api/tours/{tour_id}/highlights`, `PUT/DELETE /api/tours/{tour_id}/highlights/{highlight_id}` |
| Similar Tours | `GET/POST /api/tours/{tour_id}/similar-tours`, `DELETE /api/tours/{tour_id}/similar-tours/{similar_id}` |
| Extensions | `GET/POST /api/tours/{tour_id}/extensions`, `PUT/DELETE /api/tours/{tour_id}/extensions/{extension_id}` |
| Gallery | `GET/POST /api/tours/{tour_id}/gallery`, `PUT/DELETE /api/tours/{tour_id}/gallery/{image_id}` |
| Pricing | `GET/POST /api/tours/{tour_id}/pricing`, `PUT/DELETE /api/tours/{tour_id}/pricing/{pricing_id}` |
| Optional Activities | `GET/POST /api/tours/{tour_id}/optional-activities`, `PUT/DELETE /api/tours/{tour_id}/optional-activities/{activity_id}` |
| Accommodation Extras | `GET/POST /api/tours/{tour_id}/accommodation-extras`, `PUT/DELETE /api/tours/{tour_id}/accommodation-extras/{extra_id}` |
| Calendar | `GET/POST /api/tours/{tour_id}/calendar`, `PUT/DELETE /api/tours/{tour_id}/calendar/{calendar_id}` |
| Unavailable Dates | `GET/POST /api/tours/{tour_id}/unavailable-dates`, `DELETE /api/tours/{tour_id}/unavailable-dates/{date_id}` |
| Discounts | `GET/POST /api/tours/{tour_id}/discounts`, `PUT/DELETE /api/tours/{tour_id}/discounts/{discount_id}` |
| Price Calculation | `POST /api/tours/{tour_id}/calculate-price` |
| Version Approval | `POST /api/tours/{tour_id}/submit-for-approval`, `GET /api/tours/pending-approval`, `GET /api/tours/{tour_id}/versions`, `PATCH /api/tours/{tour_id}/versions/{version_id}/approve`, `PATCH /api/tours/{tour_id}/versions/{version_id}/reject` |

### 7.4 Booking APIs

| Method | Endpoint | Purpose | Auth |
| --- | --- | --- | --- |
| GET | `/api/bookings` | List bookings with filters | Permission |
| POST | `/api/bookings` | Create booking | Permission |
| GET | `/api/bookings/export` | Export bookings | Permission |
| GET | `/api/bookings/upcoming` | Upcoming bookings | Permission |
| POST | `/api/bookings/calculate-price` | Calculate booking price | Permission/Public depending router guard |
| GET | `/api/bookings/{booking_id}` | Booking detail | Permission |
| PUT | `/api/bookings/{booking_id}` | Update booking | Permission |
| PATCH | `/api/bookings/{booking_id}/status` | Change booking status | Permission |
| GET | `/api/bookings/{booking_id}/payment-link` | Payment link | Permission |
| GET | `/api/bookings/{booking_id}/status-history` | Status history | Permission |
| POST | `/api/bookings/{booking_id}/assign-supplier` | Assign supplier | Permission |
| PATCH | `/api/bookings/{booking_id}/cancel` | Cancel booking | Permission |
| POST | `/api/bookings/{booking_id}/communications` | Add booking communication | Permission |
| POST | `/api/bookings/communications/{communication_id}/replies` | Reply to communication | Permission |
| GET | `/api/supplier/bookings` | Supplier bookings | Bearer/Permission |
| GET | `/api/supplier/bookings/{booking_id}` | Supplier booking detail | Bearer/Permission |
| POST | `/api/supplier/bookings/{booking_id}/accept` | Supplier accepts booking | Bearer/Permission |
| POST | `/api/supplier/bookings/{booking_id}/decline` | Supplier declines booking | Bearer/Permission |
| PATCH | `/api/supplier/bookings/{booking_id}/complete` | Supplier completes booking | Bearer/Permission |
| PATCH | `/api/supplier/bookings/{booking_id}/cancel` | Supplier cancels booking | Bearer/Permission |
| PATCH | `/api/supplier/bookings/{booking_id}/postpone` | Supplier postpones booking | Bearer/Permission |
| POST | `/api/supplier/bookings/{booking_id}/notify` | Supplier sends notification | Bearer/Permission |

### 7.5 Customer APIs

| Method | Endpoint | Purpose | Auth |
| --- | --- | --- | --- |
| GET/POST | `/api/customers/` | List/create customers | Permission |
| GET | `/api/customers/me` | Customer profile by current user | Bearer |
| PUT/PATCH | `/api/customers/me` | Update own customer profile | Bearer |
| GET/PUT | `/api/customers/{customer_id}` | Customer detail/update | Permission |
| PATCH | `/api/customers/{customer_id}/status` | Update customer status | Permission |
| PATCH/POST | `/api/customers/{customer_id}/block` | Block customer | Permission |
| PATCH/POST | `/api/customers/{customer_id}/unblock` | Unblock customer | Permission |
| POST | `/api/customers/{customer_id}/reset-password` | Reset customer password | Permission |
| GET | `/api/customers/{customer_id}/bookings` | Customer bookings | Permission |
| GET | `/api/customers/{customer_id}/payments` | Customer payments | Permission |
| GET/POST | `/api/customers/{customer_id}/communications` | Customer communications | Permission |
| POST | `/api/customers/me/bookings` | Current customer booking | Bearer |
| GET/PUT | `/api/customer/profile` | Customer portal profile | Bearer |
| POST | `/api/customer/change-password` | Customer password change | Bearer |
| GET/POST | `/api/customer/bookings` | Customer portal bookings | Bearer |
| GET | `/api/customer/bookings/{booking_id}` | Customer booking detail | Bearer |
| POST | `/api/customer/bookings/{booking_id}/cancel` | Customer cancellation request | Bearer |
| GET | `/api/customer/payments` | Customer payments | Bearer |
| GET | `/api/customer/invoices` | Customer invoices | Bearer |
| GET | `/api/customer/invoices/{invoice_id}/download` | Customer invoice download data | Bearer |
| GET/POST | `/api/customer/messages` | Customer support messages | Bearer |
| GET/POST | `/api/customer/travellers` | Saved travellers | Bearer |
| PUT/DELETE | `/api/customer/travellers/{traveller_id}` | Update/delete saved traveller | Bearer |
| GET | `/api/customer/cancellations` | Customer cancellation requests | Bearer |
| POST | `/api/customer/bookings/calculate-price` | Customer price calculation | Bearer |

### 7.6 Supplier, Agent, Affiliate APIs

| Module | Key Endpoints |
| --- | --- |
| Suppliers | `POST /api/suppliers/register`, `POST /api/suppliers/verify-email`, `POST /api/suppliers/submit-verification`, `GET /api/suppliers/pending`, `GET/POST /api/suppliers`, `GET/PATCH/PUT /api/suppliers/me`, `POST /api/suppliers/me/commission-request`, `GET/PUT/PATCH /api/suppliers/{supplier_id}`, `GET/POST /api/suppliers/{supplier_id}/documents`, approval/reject/partial approve/reupload/markup endpoints |
| Agents | `POST /api/agents/register`, `POST /api/agents/verify-email`, `POST /api/agents/submit-verification`, `GET /api/agents/pending`, `GET/POST /api/agents`, `GET/PATCH/PUT /api/agents/me`, `GET/PUT/PATCH /api/agents/{agent_id}`, approval/reject/partial approve/correction/discount endpoints |
| Affiliates | `GET/POST /api/affiliates`, `GET/PUT /api/affiliates/{affiliate_id}`, approve/reject/API link endpoints |
| Affiliate Tracking | `POST/GET /api/affiliates/{affiliate_id}/links`, `GET /api/affiliates/track/{ref_code}`, `GET /api/affiliates/{affiliate_id}/clicks`, `/conversions`, `/commissions`, `GET/POST /api/affiliate-payouts` |

### 7.7 Payment, Invoice, Report, Operations APIs

| Module | Key Endpoints |
| --- | --- |
| Payments | `GET/POST /api/payments`, `POST /api/payments/authorize`, `GET /api/payments/customer/{customer_id}`, `GET/PUT /api/payments/{payment_id}`, `PATCH /api/payments/{payment_id}/status`, `POST /capture`, `/void`, `/refund` |
| Payment Gateways | `POST /api/payments/stripe/create-session`, `POST /api/payments/stripe/webhook`, `POST /api/payments/paypal/create-order`, `POST /api/payments/paypal/capture`, `POST /api/payments/paypal/webhook` |
| Invoices | `GET /api/invoices`, `POST /api/invoices/generate`, `GET /api/invoices/{invoice_id}`, `POST /api/invoices/{invoice_id}/generate-pdf`, `GET /api/invoices/{invoice_id}/download`, `POST /api/invoices/{invoice_id}/email` |
| Notifications | `GET/POST /api/notifications`, `PATCH /api/notifications/{notification_id}/read`, `POST /api/notifications/{notification_id}/retry`, push subscribe/unsubscribe/broadcast endpoints |
| Reports | `/api/reports/summary`, `/bookings`, `/payments`, `/pending-payments`, `/overdue-payments`, `/country-wise`, `/cancellations`, `/suppliers`, `/agents`, `/customers`, `/exports`, `/snapshot` |
| Sessions | `GET /api/sessions`, `GET /api/sessions/login-history`, `POST /api/sessions/expire-inactive`, `POST /api/sessions/{session_id}/revoke`, `POST /api/sessions/users/{user_id}/force-logout` |
| Activity Logs | `GET /api/activity-logs`, `GET /api/activity-logs/export` |
| Chatbot | `POST /api/chatbot/chat`, `GET /api/chatbot/faqs`, admin FAQ CRUD under `/api/chatbot/admin/faqs` |
| Cancellations | `POST /api/bookings/{booking_id}/cancel-request`, `GET /api/cancellations`, approval/reject/refund endpoints, refund-rule CRUD |
| Supplier Ledger | `GET /api/supplier-ledgers`, `GET /api/suppliers/{supplier_id}/ledger`, `GET /api/supplier-statements/{supplier_id}`, `GET/POST /api/supplier-payouts`, `PATCH /api/supplier-payouts/{payout_id}/mark-paid` |
| Booking Calendar | `POST /api/bookings/{booking_id}/calendar-sync`, `GET /api/bookings/{booking_id}/calendar-event`, `GET /api/bookings/{booking_id}/calendar-event/download` |
| Checkout | `POST /api/checkout/start`, `GET/PATCH /api/checkout/session/{session_key}`, `POST /api/checkout/session/{session_key}/confirm` |

### 7.8 Public and Website CMS APIs

| Module | Endpoints |
| --- | --- |
| Public | `GET /api/public/tours`, `GET /api/public/tours/featured`, `GET /api/public/tours/{tour_id}`, `GET /api/public/categories`, `GET /api/public/subcategories`, `GET /api/public/countries`, `GET /api/public/cities` |
| Client | `GET /api/client/config`, `/client/tours`, `/client/tours/{tour_id}`, and public tour detail sub-resources |
| Website CMS | `/api/cms/homepage-banners`, `/popular-destinations`, `/popular-tours`, `/tours-on-deals`, `/blogs`, `/customer-reviews`, `/help-centre`, `/policies`, `/promotional-popups`, `/external-links`, `/sitemap`, `/sitemap.xml` |

## 8. Working Backend Features

| Feature | Evidence |
| --- | --- |
| FastAPI app and router registration | `app/main.py` |
| Environment-driven config | `app/config.py` |
| SQLAlchemy DB sessions | `app/database.py` |
| JWT login and refresh | `app/modules/auth/router.py`, `app/modules/auth/service.py` |
| Password hashing and reset tokens | `app/security.py`, `app/modules/auth/service.py` |
| RBAC permission guards | `app/modules/common/auth.py` |
| Admin users/roles/permissions | `app/modules/users`, `roles`, `permissions` |
| Customer management and portal | `app/modules/customers/router.py`, `customer_router.py` |
| Supplier and agent profile/approval modules | `app/modules/suppliers`, `app/modules/agents` |
| Affiliate base and tracking modules | `app/modules/affiliates`, `affiliate_tracking` |
| Tour CMS and detailed tour builder | `app/modules/cms`, `app/modules/tours` |
| Tour version approval | `app/modules/tour_versions` |
| Booking lifecycle and supplier actions | `app/modules/bookings` |
| Payment lifecycle | `app/modules/payments` |
| Invoice generation/download/email endpoints | `app/modules/invoices` |
| Notifications and push subscriptions | `app/modules/notifications` |
| Reports/snapshot endpoints | `app/modules/reports` |
| Sessions/login history | `app/modules/sessions` |
| Audit log listing/export | `app/modules/audit` |
| Cancellation/refund rules | `app/modules/cancellations` |
| Website CMS | `app/modules/website_cms` |

## 9. Partially Working or Risky Backend Features

| Feature | File Path | Reason |
| --- | --- | --- |
| Payment gateways | `app/modules/payments/gateway_router.py` | Stripe/PayPal routes exist, but production webhook security and reconciliation must be verified. |
| Supplier payouts | `app/modules/supplier_ledger/router.py` | Backend supports create/list/mark-paid but not frontend-expected approval endpoint. |
| Activity/audit naming | `app/modules/audit/router.py` | Backend route is `/activity-logs`; frontend has one page calling `/audit-logs`. |
| Supplier verification URL | `app/modules/suppliers/router.py` | Backend route is `/suppliers/submit-verification`; frontend calls `/suppliers/{id}/submit-verification`. |
| Agent/supplier messages | `app/modules/bookings/router.py`, portal pages | Customer messages exist; direct `/agent/messages` and `/supplier/messages` backend APIs are not evident. |
| File uploads | `app/modules/uploads/router.py` | Basic upload exists; production security controls are incomplete. |
| Website CMS integration | `app/modules/website_cms/router.py` | Backend is broad; frontend public pages appear only partially wired. |
| Rate limiting | `app/modules/common/ratelimit.py` | In-memory only; unsuitable for multi-worker production. |

## 10. Missing Backend Features / Improvements

| Priority | Missing / Needed Work | Recommendation |
| --- | --- | --- |
| Critical | Contract alignment with frontend | Fix mismatched endpoints or add compatibility aliases. |
| Critical | Production payment webhook validation | Persist gateway event IDs, verify signatures, reject replay. |
| High | Secure document storage | Move sensitive docs to private storage with signed URLs. |
| High | Centralized exception handling | Add global handlers for HTTP, validation, and unexpected errors. |
| High | Canonical permission naming | Migrate fully to dotted permission slugs. |
| High | Portal enforcement | Use `require_portal()` for customer/supplier/agent/affiliate-only APIs. |
| Medium | Background jobs | Move email, PDF, push notification, webhook follow-up to worker queue. |
| Medium | Observability | Add structured logs, request IDs, metrics, error tracking. |
| Medium | API documentation | Generate and version OpenAPI docs for frontend contract. |
| Medium | Data protection | Encrypt API/payment secrets stored in DB. |

## 11. Backend / Frontend Contract Issues Found

| Frontend Call | Backend Endpoint | Match Status | Issue | Fix Needed |
| --- | --- | --- | --- | --- |
| `GET /api/audit-logs` | `GET /api/activity-logs` | Mismatch | Backend route name differs. | Change frontend to `/activity-logs` or add backend alias. |
| `POST /api/supplier-payouts/{id}/approve` | Not found | Mismatch | Backend has `PATCH /supplier-payouts/{id}/mark-paid`. | Add approve endpoint or remove/modify frontend action. |
| `POST /api/suppliers/{supplierId}/submit-verification` | `POST /api/suppliers/submit-verification` | Mismatch | Backend route has no supplier ID. | Fix frontend URL or add backend route alias. |
| `GET/POST /api/agent/messages` | Not evident | Missing | Agent message page likely calls missing API. | Implement agent messaging endpoints. |
| `GET/POST /api/supplier/messages` | Not evident | Missing | Supplier message page likely calls missing API. | Implement supplier messaging endpoints. |
| `/api/customers/me` and `/api/customer/profile` | Both exist | Duplicated | Two customer profile conventions. | Choose canonical route and keep alias only temporarily. |
| Permission checks | Mixed dotted/legacy | Risk | Aliasing exists but not universal for all module names. | Normalize seed, backend guards, and frontend config. |

## 12. Bugs / Issues Table

| Issue | Area | File Path | Severity | Reason | Suggested Fix |
| --- | --- | --- | --- | --- | --- |
| Frontend audit route mismatch | API Contract | `app/modules/audit/router.py` | Critical | Backend exposes `/activity-logs`, not `/audit-logs`. | Add alias or update frontend. |
| Supplier payout approve mismatch | API Contract | `app/modules/supplier_ledger/router.py` | Critical | Frontend expects approve action missing in backend. | Implement `approve` route and status transition. |
| Supplier verification mismatch | API Contract | `app/modules/suppliers/router.py` | High | Backend route does not include supplier ID. | Align frontend/backend route. |
| Missing direct supplier/agent messages | Portal APIs | `app/modules/bookings/router.py`, customer messaging module | High | Customer messaging exists; supplier/agent direct message endpoints not evident. | Add portal message routers. |
| Payment webhook production risk | Payments | `app/modules/payments/gateway_router.py` | High | Gateway route presence is not enough for production safety. | Add event persistence, signature enforcement, replay protection. |
| Public storage for uploaded documents | Uploads | `app/main.py`, upload modules | High | Mounted storage can expose files. | Separate public assets and private documents. |
| Mixed permission slug formats | RBAC | `app/modules/common/auth.py` | Medium | Compatibility complexity can cause permission misses. | Migrate to dotted slugs. |
| In-memory rate limiting | Security | `app/modules/common/ratelimit.py` | Medium | Not reliable across workers/servers. | Redis-backed limiter. |
| Lack of global exception formatting | API Quality | `app/main.py` | Medium | Error shape may vary. | Add exception handlers. |
| Plain DB storage for API secrets | Settings | `app/modules/settings/models.py` | Medium | Secrets should not be stored unencrypted. | Encrypt or externalize secrets. |

## 13. Production Readiness

| Area | Ready? | Issue | Required Action |
| --- | --- | --- | --- |
| Environment | No | Development defaults exist. | Use production `.env`, strong secrets, explicit CORS. |
| Database migrations | Partially | Migrations exist. | Run migration cycle on staging DB. |
| Seeders | Partially | Startup seed exists. | Verify idempotency and production-safe admin password policy. |
| API docs | Partially | FastAPI docs exist automatically. | Export and version OpenAPI. |
| Error logging | No | No central logging/monitoring setup evident. | Add structured logs and error tracking. |
| Payment gateways | No | Needs full gateway verification. | Complete gateway certification/testing. |
| File uploads | No | Needs security hardening. | Add MIME sniffing, size limits, private storage. |
| Auth security | Partially | Backend JWT is solid baseline. | Enforce portal claims and frontend secure cookies. |
| Tests | Partially | Tests exist. | Run all tests and add contract/e2e tests. |
| Deployment config | Not evident | No PM2/Nginx/systemd/Docker deployment config found in backend root. | Add deployment runbook/config. |

## 14. Recommended Development Roadmap

### Priority 1 - Critical

| Task | Files / Area |
| --- | --- |
| Fix `/audit-logs` vs `/activity-logs` mismatch. | `app/modules/audit/router.py`, frontend audit page |
| Implement or remove supplier payout approval action. | `app/modules/supplier_ledger/router.py` |
| Fix supplier submit-verification route mismatch. | `app/modules/suppliers/router.py`, supplier documents UI |
| Verify all frontend API calls against backend route registry. | Backend routers + frontend services |
| Run backend test suite after contract fixes. | `backend/tests` |

### Priority 2 - High

| Task | Files / Area |
| --- | --- |
| Add supplier and agent message APIs if portal pages must remain. | New or existing messaging modules |
| Harden payment gateway webhook handling. | `app/modules/payments/gateway_router.py` |
| Move sensitive document uploads to private storage. | `app/modules/uploads`, supplier/agent/affiliate document handlers |
| Add global exception handlers and standard error response. | `app/main.py` |
| Enforce portal claims for portal-specific routes. | `app/modules/common/auth.py`, portal routers |

### Priority 3 - Medium

| Task | Files / Area |
| --- | --- |
| Normalize permission slugs. | `app/seed.py`, `app/modules/common/auth.py`, permission guards |
| Replace in-memory rate limiting with Redis. | `app/modules/common/ratelimit.py` |
| Add OpenAPI-based TypeScript client generation. | Backend OpenAPI + frontend API layer |
| Add structured audit coverage for every mutation. | Service modules |
| Add background worker for email/PDF/push notifications. | Email, invoices, notifications |

### Priority 4 - Low

| Task | Files / Area |
| --- | --- |
| Remove duplicate route aliases after frontend migration. | Routers |
| Improve README/setup docs. | `README.md`, deployment docs |
| Add more sample seed data for demo environments. | `app/seed.py`, `scripts` |
| Add API usage examples for each role. | Documentation |

## 15. Final Summary

| Item | Assessment |
| --- | --- |
| Backend completion | Approximately 80-85% |
| Backend API breadth | High |
| Backend reliability | Medium |
| Backend production readiness | Not ready |
| Ready for frontend-backend integration | Partially; contract mismatches must be fixed first. |
| Ready for client demo | Yes for controlled demo after fixing critical API mismatches. |
| Ready for production | No |

Main risks:

1. Endpoint mismatches will break visible frontend pages.
2. Payment and upload flows need production-grade security.
3. Permission slug drift can create hidden access bugs.
4. Portal-specific access should be enforced more strictly.
5. Public website CMS backend exists, but frontend integration must be confirmed.

Recommended next step:

Fix the critical API mismatches first, then run backend tests and a frontend integration smoke test for login, dashboard, tours, bookings, supplier bookings, payouts, and audit logs.

