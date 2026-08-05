# Full-Flow Bug Analysis Report — Tourvaa

**Date:** 2026-08-04  
**Scope:** `tourvaa-admin-backend` (Python/FastAPI) + `tourvaa-admin-frontend` (Next.js/TypeScript)  
**Analyst:** Automated full-codebase sweep

---

## Executive Summary

A comprehensive end-to-end audit covered authentication, session management, permission checking, dashboard data flow, reporting, and the frontend routing/guard layers. **10 code bugs** and **2 documentation drift issues** were identified across both codebases.

| Severity | Count |
|----------|-------|
| 🔴 MEDIUM | 5 |
| 🟡 LOW | 7 |

---

## 1. Full Data Flow Overview

### 1.1 Authentication Flow (Cookie-based)

```
User submits login (portal: /login, admin: /admin/login)
  → Frontend POST /api/auth/login { identifier/email, password, client_type: "web-cookie" }
  → Backend: auth.py router → login_user() → _finalize_login()
    → create_token() (JWT with tz-aware claims)
    → create_session() (UserSession row in DB)
    → _set_auth_cookies() (httpOnly cookies: access + refresh)
  → Frontend: refreshSession() → GET /api/dashboard/me
    → AuthProvider stores dashboard data (user, permissions, menus, dashboard_type)
  → All subsequent API calls use Axios with withCredentials: true (cookies auto-sent)
  → On 401: interceptor calls POST /api/auth/refresh-token
    → If refresh cookie valid → new access token issued
    → If invalid → clearSession() + redirect to login
```

**Key configuration files:**
- `src/lib/api/client.ts` — Axios instances (`api` with `withCredentials`, `authAxios`)
- `src/lib/api/session.ts` — `clearSession()` (localStorage only), `getToken()`, `setToken()`
- `app/auth/permissions.py` — `ACCESS_COOKIE_NAME = "tourvaa_access"`, JWT verification
- `app/models/users.py` — All datetime columns use `DateTime(timezone=True)`

### 1.2 Permission Check Flow

**Backend:**
```
require_permission("view-users") / require_any_permission("a", "b")
  → expand_permission_slugs() — converts between dotted (users.view) and legacy (view-users) formats
  → queries DB: Permission.slug IN (expanded slugs) JOIN RolePermission WHERE role_id IN (user's roles)
  → User must have at least one matching permission
```

**Frontend:**
```
hasPermission("view-users")
  → permissionAliases("view-users") — generates alias set (mirrors expand_permission_slugs)
  → checks if ANY of user's stored permission aliases intersect with requested aliases
  → Gates UI visibility only (backend still enforces)
```

### 1.3 Admin Dashboard Data Flow

1. `app/admin/layout.tsx` → `AdminRouteGuard` (checks logged in + admin dashboard type)
2. `app/admin/dashboard/page.tsx` → `ProtectedRoute` → `useDashboard()` (reads from context)
3. `AdminDashboardContent` calls `Promise.allSettled`:
   - `GET /api/dashboard/summary` → stats (bookings, customers, suppliers, agents, revenue, pending)
   - `GET /api/suppliers?limit=1000` → pending supplier approvals
   - `GET /api/agents?limit=1000` → pending agent approvals
   - `GET /api/dashboard/charts` → booking/payment status charts
   - `GET /api/dashboard/recent-activities` → recent admin actions
   - `GET /api/reports/snapshot` → reports snapshot (booking performance, revenue, supplier approval, etc.)
   - `GET /api/countries?limit=200` → country filter dropdown
4. Approval actions:
   - `PATCH /api/suppliers/{id}/approve`
   - `PATCH /api/suppliers/{id}/reject`
   - `PATCH /api/agents/{id}/approve`
   - `PATCH /api/agents/{id}/reject`

### 1.4 Session Management Data Flow

```
Login:    POST /auth/login → _finalize_login() → create_session() → UserSession(active)
Logout:   POST /auth/logout → force_logout_user (auth.py) → token_version++ (sessions NOT revoked)
ForceLogout (sessions UI): POST /sessions/users/{id}/force-logout → force_logout_user (sessions.py) → token_version++ + sessions revoked
Session View: GET /sessions/ → list_sessions() → returns all UserSession rows
Session Revoke: POST /sessions/{id}/revoke → revoke_session() → status="revoked"
Token Refresh: POST /auth/refresh-token → checks token_version + session.status
```

---

## 2. Backend Bugs

### BUG-01: `_is_admin()` Misclassifies Affiliates as Admin
**Severity:** MEDIUM (Data Privacy)  
**File:** `app/services/notifications.py`, lines 11–15  
**Status:** ❌ Confirmed

```python
def _is_admin(actor: "User | None") -> bool:
    if not actor or not actor.role:
        return True
    slug = actor.role.slug or ""
    return not any(marker in slug for marker in ("supplier", "agent", "customer"))
```

**Problem:** The `"affiliate"` role slug contains none of the markers `"supplier"`, `"agent"`, `"customer"`. `any()` returns `False`, so `not False` = `True`. Affiliates are classified as admins.

**Affected functions:**
- `list_notifications()` — line 42: `if not _is_admin(actor): user_id = actor.id` → affiliates see ALL users' notifications
- `get_notification()` — line 55: `if not _is_admin(actor):` → 404 check bypassed for affiliates on any notification
- `mark_notification_read()` — line 66: `if not _is_admin(actor) and n.user_id != actor.id:` → affiliates can mark any notification as read
- `mark_all_read()` — line 72: `if not _is_admin(actor):` → affiliates can mark ALL notifications as read globally

**Fix:**
```python
def _is_admin(actor: "User | None") -> bool:
    if not actor or not actor.role:
        return True
    slug = actor.role.slug or ""
    return not any(marker in slug for marker in ("supplier", "agent", "customer", "affiliate"))
```

---

### BUG-02: Duplicate `force_logout_user` with Inconsistent Behavior
**Severity:** MEDIUM (Security)  
**Files:** `app/services/auth.py` (line 913) vs `app/services/sessions.py` (line 55)  
**Status:** ❌ Confirmed

**`services/auth.py` version (used by `POST /auth/logout` and `POST /auth/force-logout`):**
```python
def force_logout_user(db: Session, target_user: User, actor: User | None = None, request=None):
    old_version = target_user.token_version
    target_user.token_version += 1
    log_audit(db, actor=actor, action="force_logout", ...)
    db.commit()
    db.refresh(target_user)
    return {"user_id": target_user.id, "token_version": target_user.token_version}
```
- **Only** increments `token_version`.
- Does **NOT** revoke `UserSession` rows.

**`services/sessions.py` version (used by `POST /sessions/users/{user_id}/force-logout`):**
```python
def force_logout_user(db: Session, user_id: int):
    user = db.query(User).filter(User.id == user_id).first()
    user.token_version = (user.token_version or 0) + 1
    db.query(UserSession).filter(
        UserSession.user_id == user_id, UserSession.status == "active"
    ).update({"status": "revoked", "revoked_at": utcnow()})
    db.commit()
    return {"user_id": user_id, "revoked": True}
```
- Increments `token_version` **AND** revokes all active sessions.

**Impact:**
| Endpoint | Service Function | Sessions Revoked? | Token Version Bumped? |
|---|---|---|---|
| `POST /auth/logout` | `services.auth.force_logout_user` | ❌ No | ✅ Yes |
| `POST /auth/force-logout` | `services.auth.force_logout_user` | ❌ No | ✅ Yes |
| `POST /sessions/users/{id}/force-logout` | `services.sessions.force_logout_user` | ✅ Yes | ✅ Yes |

After logout via `/auth/logout`, `UserSession` rows remain `"active"` in the DB. The `/sessions/` endpoint will display stale active sessions for users who have already logged out. Additionally, the `refresh_token` endpoint (line 254) checks `session.status != "active"` to reject revoked sessions — but since logout doesn't revoke sessions, this check is ineffective for logout-initiated sessions.

**Fix:** Consolidate both functions. The auth.py version should also revoke `UserSession` rows:
```python
def force_logout_user(db: Session, target_user: User, actor: User | None = None, request=None):
    old_version = target_user.token_version
    target_user.token_version += 1
    db.query(UserSession).filter(
        UserSession.user_id == target_user.id, UserSession.status == "active"
    ).update({"status": "revoked", "revoked_at": utcnow()})
    log_audit(db, actor=actor, action="force_logout", ...)
    db.commit()
    db.refresh(target_user)
    return {"user_id": target_user.id, "token_version": target_user.token_version}
```

---

### BUG-03: `datetime.utcnow()` (Naive) on `DateTime(timezone=True)` Columns
**Severity:** MEDIUM (Correctness)  
**Files:** `app/services/auth.py` (33+ usages), `app/services/customers.py`, `app/services/agents.py`, `app/services/suppliers.py`, `app/services/users.py`  
**Status:** ❌ Confirmed

**Problem:** All service files import `from datetime import datetime, timedelta` and use `datetime.utcnow()`, which returns a **naive** datetime. The `User` model (`app/models/users.py`) defines all datetime columns as `DateTime(timezone=True)`.

A correct timezone-aware `utcnow()` function exists in `app/utils/money.py`:
```python
def utcnow() -> datetime:
    return datetime.now(timezone.utc)
```

But it's only imported by `sessions.py`, `notifications.py`, and `reports.py`. The auth, customers, agents, suppliers, and users services all use the naive version.

**Critical instances in `services/auth.py`:**

| Line | Code | Issue |
|------|------|-------|
| 224 | `now = datetime.utcnow()` | Naive datetime used for registration token |
| 285 | `if user.email_verification_expires_at.replace(tzinfo=None) < datetime.utcnow():` | Strips tzinfo from DB value, compares with naive — fragile |
| 300 | `now = datetime.utcnow()` | Used for password reset token |
| 402 | `user.last_login_at = datetime.utcnow()` | Naive datetime assigned to tz-aware column |
| 485 | `now = datetime.utcnow()` | Used for registration |
| 702 | `user.last_login_at = datetime.utcnow()` | Naive datetime assigned to tz-aware column |
| 728 | `now = datetime.utcnow()` | Used for OTP |
| 775 | `if user.otp_expires_at < datetime.utcnow():` | Comparing **tz-aware** DB value with **naive** datetime → `TypeError` in PostgreSQL |
| 802 | `user.email_verified_at = datetime.utcnow()` | Naive datetime assigned to tz-aware column |
| 995 | `if expires_at.replace(tzinfo=None) < datetime.utcnow():` | Fragile workaround |
| 1040 | `if user.reset_password_expires_at.replace(tzinfo=None) < datetime.utcnow():` | Fragile workaround |

**Impact:**
- In PostgreSQL with asyncpg/psycopg2: `TypeError: can't compare offset-naive and offset-aware datetimes` when comparing `user.otp_expires_at` (tz-aware from DB) with `datetime.utcnow()` (naive) at line 775.
- In SQLite (dev): comparisons silently work but may produce incorrect results if the DB stores values in a different timezone.
- Naive datetimes assigned to `DateTime(timezone=True)` columns may be stored without tzinfo, leading to inconsistent timezone handling.

**Fix:** Replace all `datetime.utcnow()` with `utcnow()` imported from `app.utils.money` in all service files. Remove the `.replace(tzinfo=None)` workarounds.

---

### BUG-04: Dead `register_user()` Function
**Severity:** LOW (Code Quality)  
**File:** `app/services/auth.py` (line ~438)  
**Status:** ❌ Confirmed — 0 imports across the codebase

A legacy `register_user(db, data)` function exists alongside the current `register_unified_user()` function. It is **never imported by any router** (confirmed via search: 0 results for `register_user` in imports). It is leftover from a previous refactoring where registration was consolidated into `register_unified_user()`.

**Fix:** Remove the dead function.

---

### BUG-05: Empty `app/utils/response.py`
**Severity:** LOW (Code Quality)  
**File:** `app/utils/response.py`  
**Status:** ❌ Confirmed — 0 bytes, 0 imports

The file is completely empty. It is never imported anywhere in the codebase. It appears to be a placeholder that was never implemented or was cleaned out during a refactor.

**Fix:** Remove the file, or implement it if it was intended to provide shared response helpers.

---

### BUG-06: `cryptography` Package Missing from `requirements.txt`
**Severity:** LOW (Dependency)  
**Files:** `requirements.txt` (missing `cryptography`), `app/utils/crypto.py` (line 25)  
**Status:** ❌ Confirmed

```python
from cryptography.fernet import Fernet  # in _get_fernet(), wrapped in try/except
```

The `cryptography` package is not listed in `requirements.txt` (which has 19 packages). The import is inside `_get_fernet()` which has a try/except fallback:
```python
f = _get_fernet()
if not f:
    return value  # encryption unavailable - store plain (safe fallback)
```

So the app doesn't crash, but **all secrets (API keys, payment secrets, encryption keys) are stored in plaintext** at runtime.

**Fix:** Add `cryptography` to `requirements.txt`.

---

### BUG-07: Default Super-Admin Password `"Admin@123"`
**Severity:** LOW (Security)  
**Files:** `app/seed.py` (line 212), `app/config.py` (`SUPER_ADMIN_PASSWORD` field default)  
**Status:** ❌ Confirmed

The seed script detects the default password:
```python
default_password = Settings.model_fields["SUPER_ADMIN_PASSWORD"].default
if settings.APP_ENV.lower() == "production" and settings.SUPER_ADMIN_PASSWORD == default_password:
    logger.warning("SUPER_ADMIN_PASSWORD is still the default value...")
```

But it only **logs a warning** — it still creates the super-admin user with `"Admin@123"`. The `SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP` flag is only checked when the user already exists (line 249), not during initial creation.

**Impact:** Known default credentials for the most privileged account in production.

**Fix:** In production, refuse to seed the super-admin if the password is still the default — raise an error instead of warning.

---

## 3. Frontend Bugs

### BUG-08: `permissionAliases()` Missing `continue`/Early Return
**Severity:** MEDIUM (UX / Permissions)  
**File:** `tourvaa-admin-frontend/src/providers/AuthProvider.tsx`, lines 136–151  
**Status:** ❌ Confirmed

```javascript
function permissionAliases(permission: string) {
  const aliases = new Set([permission]);
  // ... addModuleAliases helper ...

  if (permission.includes(".")) {
    const [moduleName, action] = permission.split(".");
    const legacyAction = dottedToLegacyAction[action];

    if (moduleName && action) addModuleAliases(action, moduleName, "dotted");
    if (moduleName && legacyAction) addModuleAliases(legacyAction, moduleName, "legacy");
  }
  // ← NO continue/return here!

  if (permission.includes("-")) {  // ← This runs even for dotted permissions!
    const [action, ...moduleParts] = permission.split("-");
    const moduleName = moduleParts.join("-");
    const dottedAction = legacyToDottedAction[action];

    if (moduleName) addModuleAliases(action, moduleName, "legacy");
    if (moduleName && dottedAction) addModuleAliases(dottedAction, moduleName, "dotted");
  }

  return aliases;
}
```

**Comparison with backend (`app/auth/permissions.py` lines 81–100):**
```python
def expand_permission_slugs(permission_slugs: tuple[str, ...]):
    expanded = set(permission_slugs)
    for slug in permission_slugs:
        if "." in slug:
            module, action = slug.split(".", 1)
            legacy_action = DOTTED_TO_ACTION.get(action)
            legacy_module = MODULE_ALIASES.get(module, module)
            if legacy_action:
                expanded.add(f"{legacy_action}-{legacy_module}")
            continue  # ← KEY: only one branch executes
        if "-" in slug:
            action, module = slug.split("-", 1)
            dotted_action = ACTION_TO_DOTTED.get(action)
            dotted_module = MODULE_ALIASES.get(module, module)
            if dotted_action:
                expanded.add(f"{dotted_module}.{dotted_action}")
    return list(expanded)
```

The backend uses `continue` after the `"."` branch, so only one format is processed per slug. The frontend processes **both** branches for any permission containing both `.` and `-`.

**Example: `"activity-logs.view"`**
- `"."` branch: `moduleName="activity-logs"`, `action="view"` → correctly adds aliases
- `"-"` branch: `action="activity"`, `moduleName="logs.view"` → produces nonsensical aliases like `activity-logs.view`, `activity_logs.view`

**Example: `"email.view"`**
- `"."` branch: `moduleName="email"`, `action="view"` → correctly adds `view-email`, `view-email_templates`
- `"-"` branch: `action="email"`, `moduleName="view"` → adds `email-view` (incorrect, "email" is not a valid action)

**Impact:** The frontend's `hasPermission()` can produce false positives (showing UI elements the backend denies → 403 on API call) or false negatives (hiding UI elements the backend would allow), because the alias sets don't match between frontend and backend.

**Fix:** Add `return;` (or restructure to `if/else`) after the `"."` branch:
```javascript
if (permission.includes(".")) {
    const [moduleName, action] = permission.split(".");
    const legacyAction = dottedToLegacyAction[action];
    if (moduleName && action) addModuleAliases(action, moduleName, "dotted");
    if (moduleName && legacyAction) addModuleAliases(legacyAction, moduleName, "legacy");
    return aliases;  // ← ADD THIS
}
```

---

### BUG-09: Mismatched `moduleAliases` Between Frontend and Backend
**Severity:** MEDIUM (Permissions)  
**File:** `tourvaa-admin-frontend/src/providers/AuthProvider.tsx` (lines 110–115)  
**Backend reference:** `app/auth/permissions.py` (lines 68–78)  
**Status:** ❌ Confirmed

**Frontend `moduleAliases`:**
```javascript
const moduleAliases: Record<string, string[]> = {
    activity_logs: ["activity-logs"],
    "activity-logs": ["activity_logs"],
    email_templates: ["email"],
    email: ["email_templates"],
};
```

**Backend `MODULE_ALIASES`:**
```python
MODULE_ALIASES = {
    "email": "email_templates",
    "email_templates": "email",
    "resellers": "agents",
    "agents": "resellers",
    "audit_logs": "activity_logs",
    "activity_logs": "audit_logs",
}
```

**Three discrepancies:**

1. **`audit_logs ↔ activity_logs` mismatch:**
   - Backend maps `"audit_logs" → "activity_logs"` (both underscore). When expanding `"audit_logs.view"`, the backend adds `"view-activity_logs"`.
   - Frontend has NO entry for `"audit_logs"`. When expanding `"audit_logs.view"`, `moduleAliases["audit_logs"]` is `undefined`, so no cross-module alias is generated.
   - Frontend maps `"activity_logs → activity-logs"` (underscore↔hyphen), which is a **different** mapping than the backend uses.

2. **Missing `resellers ↔ agents` alias:**
   - Backend maps `"resellers" ↔ "agents"`.
   - Frontend has no entry for either. Permissions involving resellers/agents aliases won't cross-expand correctly.

3. **Format mismatch:**
   - Backend uses single-string alias values: `"audit_logs": "activity_logs"`
   - Frontend uses string array values: `activity_logs: ["activity-logs"]`

**Impact:** When a user's permission in the DB is stored as `"activity_logs.view"` (the seed.py stores it with underscores), and the frontend checks `hasPermission("audit_logs.view")` (or vice versa), the frontend's `permissionAliases()` won't produce the cross-module alias that the backend would. `hasPermission()` returns `false`, incorrectly hiding UI elements.

Conversely, the frontend generates hyphenated aliases (`view-activity-logs`) that the backend never produces, potentially causing false positives.

**Fix:** Align the frontend `moduleAliases` with the backend `MODULE_ALIASES`:
```javascript
const moduleAliases: Record<string, string[]> = {
    email: ["email_templates"],
    email_templates: ["email"],
    resellers: ["agents"],
    agents: ["resellers"],
    audit_logs: ["activity_logs"],
    activity_logs: ["audit_logs"],
};
```

---

### BUG-10: `skipTrailingSlashRedirect` with Inconsistent API Rewrites
**Severity:** LOW (Routing)  
**File:** `tourvaa-admin-frontend/next.config.ts`, line 34  
**Status:** ❌ Confirmed

```typescript
skipTrailingSlashRedirect: true,
```

This disables Next.js's automatic trailing-slash normalization. Explicit rewrites are defined only for 5 paths:

| Source | Destination |
|--------|-------------|
| `/api/users` | `/api/users/` |
| `/api/users/` | `/api/users/` |
| `/api/roles` | `/api/roles/` |
| `/api/roles/` | `/api/roles/` |
| `/api/permissions` | `/api/permissions/` |
| `/api/permissions/` | `/api/permissions/` |
| `/api/settings` | `/api/settings/` |
| `/api/settings/` | `/api/settings/` |
| `/api/email-templates` | `/api/email-templates/` |
| `/api/email-templates/` | `/api/email-templates/` |

All other API paths go through the catch-all rewrite (preserves whatever slash the caller sends):
```typescript
{
    source: "/api/:path*",
    destination: `${apiProxyTarget}/api/:path*`,
},
```

**Inconsistency:** The frontend's `useUsers.ts` calls `api.get("/users/")` (with trailing slash), and the explicit rewrite handles this. But `sessionService.ts` calls `api.get("/sessions/")` (with trailing slash) — this goes through the catch-all, which preserves the slash. The sessions router defines both `@router.get("")` and `@router.get("/")` (lines 11–14), so both work.

However, if any router only defines `@router.get("/")` (with trailing slash) and the frontend calls without one (or vice versa), FastAPI's default `redirect_slashes=True` would return a 307 redirect. With `skipTrailingSlashRedirect: true`, Next.js won't handle this normalization for the catch-all paths.

**Impact:** Potential 307 redirects or 404s for API endpoints where the frontend's request path slash doesn't match the backend's route definition, depending on each router's specific route definitions.

**Fix:** Either remove `skipTrailingSlashRedirect: true`, or add explicit rewrites for all API paths that require trailing slashes.

---

## 4. Documentation Drift

### DOC-01: BACKEND_DOC.md Describes Non-Existent `app/modules/` Structure
**File:** `tourvaa-admin-backend/BACKEND_DOC.md`

The documentation describes an `app/modules/` directory with submodules (e.g., `app/modules/users.py`). The actual codebase uses:
```
app/
├── routers/    (APIRouter instances)
├── services/   (business logic functions)
├── models/     (SQLAlchemy models)
├── schemas/    (Pydantic schemas)
├── auth/       (permissions, security)
├── utils/      (money, crypto, media, etc.)
```

Additionally, the doc claims 42 default permissions, but `seed.py` actually creates 108+ permissions:
- 27 modules × 4 HTTP actions (get/post/put/delete) = 108 base permissions
- Plus: 9 customer granular permissions, 4 email template granular permissions, 8 dashboard permissions, ~100+ operational/granular permissions

### DOC-02: FRONTEND_DOC.md References Old/Renamed Files
**File:** `tourvaa-admin-frontend/FRONTEND_DOC.md`

The documentation references files that have been moved or restructured:

| Doc Reference | Actual File |
|---------------|-------------|
| `lib/api.ts` | `lib/api/client.ts` |
| `lib/services/` | `lib/api/services/` |
| `config/page-permissions.ts` | `providers/AuthProvider.tsx` (permissions inline) |
| `hooks/useApi.ts` | Not found (API calls use raw `api` from `client.ts`) |
| `app/login/page.tsx` | `app/(public)/login/page.tsx` |
| `app/register/page.tsx` | `app/(public)/register/` |
| `hooks/useUsers.ts` mentions `api.post("/users/")` | Correct, but `RegisterSchema` in backend doesn't match `createUser` payload |

---

## 5. Quick Fix Checklist

### High Priority (Security/Data Privacy)
- [ ] **BUG-01:** Add `"affiliate"` to `_is_admin()` markers in `notifications.py`
- [ ] **BUG-02:** Make `services/auth.py:force_logout_user()` also revoke `UserSession` rows
- [ ] **BUG-03:** Replace all `datetime.utcnow()` with `utcnow()` from `app.utils.money` across all service files

### Medium Priority (Permissions/UX)
- [ ] **BUG-08:** Add `return;` after the `"."` branch in `permissionAliases()`
- [ ] **BUG-09:** Align frontend `moduleAliases` with backend `MODULE_ALIASES` (add `resellers↔agents`, `audit_logs↔activity_logs`, fix `activity_logs↔activity-logs`)

### Low Priority
- [ ] **BUG-04:** Remove dead `register_user()` function from `services/auth.py`
- [ ] **BUG-05:** Remove empty `app/utils/response.py` or implement it
- [ ] **BUG-06:** Add `cryptography` to `requirements.txt`
- [ ] **BUG-07:** Fail fast in production if `SUPER_ADMIN_PASSWORD` is still the default
- [ ] **BUG-10:** Remove `skipTrailingSlashRedirect: true` or add explicit rewrites for all API paths
- [ ] **DOC-01:** Update `BACKEND_DOC.md` to reflect actual `app/` structure
- [ ] **DOC-02:** Update `FRONTEND_DOC.md` to reflect actual file locations