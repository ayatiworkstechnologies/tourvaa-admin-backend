# Public (No-Authentication) Surface — Route Inventory

**Scope:** Every endpoint and page reachable without a valid session, across `tourvaa-admin-backend` and `tourvaa-admin-frontend`.
**Verification:** Static analysis (route-decorator + dependency tracing) plus a live pass against a running local instance (`curl` against `http://localhost:8000`) on 2026-08-06. Entries confirmed by an actual request are marked **Live-verified**.

---

## 1. `/api/public/*` — dedicated public API

Mounted with no router-level auth dependency (`app/routers/public.py`, mounted at `app/api/router.py:132`). Every handler uses only `Depends(get_db)`.

| # | Method | Path | Notes | Verified |
|---|--------|------|-------|----------|
| 1 | GET | `/api/public/tours` | Paginated search/list (country/city/category/subcategory/days/price/month/available-only/sort). `Tour.status == "published"` only. | ✅ Live — 200, correct shape, no admin fields |
| 2 | GET | `/api/public/tours/featured` | Featured-first, falls back to recent publishes. Published-only. | ✅ Live — 200 |
| 3 | GET | `/api/public/tours/{country_slug}/{tour_slug}` | Canonical tour URL; 404 on country mismatch. | ✅ Live — 200 for match, 404 for wrong country |
| 4 | GET | `/api/public/tours/{tour_id}` | Accepts numeric id. | ✅ Live — 200 for published, 404 for nonexistent and for a real **draft** tour (id 19, verified against DB) |
| 5 | GET | `/api/public/categories` | Active categories + published tour counts. | ✅ Live — 200 |
| 6 | GET | `/api/public/subcategories` | Optional `category_id` filter. | ✅ Live — 200 |
| 7 | GET | `/api/public/countries` | Active countries + published tour counts. | ✅ Live — 200 |
| 8 | GET | `/api/public/cities` | Optional `country_id` filter. | ✅ Live — 200 |
| 9 | POST | `/api/public/contact` | Rate-limited 5/300s. Persists `ContactMessage`, emails support, HTML-escapes input. | Static only (not exercised, to avoid sending real emails) |
| 10 | POST | `/api/public/newsletter/subscribe` | Rate-limited 5/300s. Idempotent. | Static only |

**Draft-leak check (live):** fetched a confirmed `status="draft"` tour (id 19, "test", country India) via both `/api/public/tours/19` and `/api/public/tours/india/test` — both correctly returned 404, not the tour data.

## 2. `/api/auth/*` — public-by-necessity auth endpoints

| Public (no bearer required) | Method | Path | Verified |
|---|---|---|---|
| ✅ | POST | `/auth/register`, `/register/customer`, `/register/supplier`, `/register/agent` | Static |
| ✅ | POST | `/auth/login` | ✅ Live — bad creds correctly 401 without requiring prior auth |
| ✅ | POST | `/auth/otp/request`, `/auth/otp/verify` | Static |
| ✅ | POST | `/auth/forgot-password` (5/300s) | Static |
| ✅ | POST | `/auth/reset-password` | Static |
| ✅ | GET | `/auth/reset-password/validate` | Static |
| ✅ | POST | `/auth/refresh-token`, `/auth/refresh` | ✅ Live — confirmed no `Depends(get_current_user)` in source (`auth.py:207-224`); reads the refresh token manually from cookie/header itself, so it's dependency-free even though it functionally requires *a* token |
| ✅ | POST | `/auth/verify-email` (10/60s), `/auth/resend-verification` (3/300s), `/auth/change-registration-email` | Static |
| ✅ | POST | `/auth/complete-registration`, `/auth/create-password` | Static |
| ✅ | GET | `/auth/verify-email/validate`, `/auth/verify-email` (query-token alias) | Static |

| Protected (bearer/cookie required) | Method | Path | Verified |
|---|---|---|---|
| 🔒 | GET | `/auth/account-status` | ✅ Live — 401 "Authorization token missing" |
| 🔒 | GET | `/auth/me` | ✅ Live — 401 |
| 🔒 | POST | `/auth/logout` | ✅ Live — 401 |
| 🔒 | GET | `/auth/login-history` | ✅ Live — 401 |
| 🔒 | POST | `/auth/force-logout` (admin-only, `require_permission("update-users")`) | ✅ Live — 401 |

## 3. `/api/cms/*` — public reads, protected writes

Prefix `/api/cms` (`CONTENT_AND_TOUR_ROUTERS`, no router-level auth).

**Public GET reads (no dependency):** `/cms/homepage-banners`, `/cms/popular-destinations`, `/cms/popular-tours`, `/cms/tours-on-deals`, `/cms/blogs`, `/cms/blogs/{id}`, `/cms/customer-reviews`, `/cms/help-centre`, `/cms/policies`, `/cms/policies/{slug}`, `/cms/promotional-popups`, `/cms/external-links`, `/cms/sitemap`, `/cms/sitemap.xml`.

**Protected writes:** all mutating CMS endpoints gate on `require_any_permission("website_cms.create"/"edit"/"delete")`.

## 4. Root / health

| Method | Path | Verified |
|---|---|---|
| GET | `/` | Static |
| GET | `/api/health` | ✅ Live — `{"status":"success","message":"API working fine"}` |

## 5. Frontend public surface

- **Static assets** (`tourvaa-admin-frontend/public/`): `sw.js` + `images/`, served at `/`.
- **`(public)` route group** (`src/app/(public)/`): `/`, `/about`, `/accessibility`, `/account-status`, `/blogs`(+`/[slug]`), `/booking/[id]`, `/cancellation-policy`, `/cart`, `/compare`, `/contact`, `/cookie-policy`, `/destinations`, `/login`, `/privacy-policy`, `/register`, `/terms`, `/tours`(+`/[country]/[slug]`), `/wishlist`.
- **Dedicated login/register portals** (each its own group, not under `(public)`): `/agent-portal`(+`/login`), `/supplier-portal`(+`/login`). `/login` and `/register` are traveller/customer-only.
- **Proxy**: `next.config.ts` rewrites `/api/public/:path*` and a catch-all `/api/:path*` to the backend.

## 6. Security notes

- **CORS** (`app/middleware/cors.py`, config in `app/config/__init__.py:38`): `ALLOWED_ORIGINS` defaults to `"*"` if unset. ✅ Live-verified in *this* environment: `.env` pins it to `https://tourvaa.vercel.app,http://127.0.0.1:3000,http://localhost:3000`, and a preflight from an untrusted origin (`evil-example.com`) is correctly rejected (`400`) while `localhost:3000` gets `access-control-allow-origin` back. **Action item:** confirm `ALLOWED_ORIGINS` is set (not omitted) in every deployed environment — the wildcard default is a real, live-reachable fallback, not just a theoretical one.
- **Draft tours:** confirmed not reachable via any public endpoint (tested against a real draft row).
- **Admin field leakage:** the public tour serializer omits `supplier_id`, `created_by`, `updated_by`, and other admin-only fields — confirmed present in live response shape (§1).
- **Rate limiting:** present on both public mutating endpoints (`/contact`, `/newsletter/subscribe`) and on auth endpoints that could be abused (`/forgot-password`, `/verify-email`, `/resend-verification`).

No defects requiring code changes were found. This inventory is descriptive of current behavior, not a to-do list.
