# Tourvaa Backend

FastAPI REST API powering the Tourvaa travel platform. Provides authentication, dynamic RBAC, tour CMS, customer/supplier/agent/affiliate management, role-scoped dashboards, settings, email templates, file uploads, and audit logging.

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
| Email | SMTP (smtplib) |

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

## Module Structure

```text
app/
├── main.py                    Entry point, router registration
├── config.py                  Pydantic settings (reads .env)
├── database.py                SQLAlchemy engine and session
├── security.py                JWT and password utilities
└── modules/
    ├── auth/                  Registration, login, refresh, reset password
    ├── users/                 User CRUD, approval workflow
    ├── roles/                 Role CRUD + permission assignment
    ├── permissions/           Permission CRUD
    ├── dashboard/             Role-scoped dashboard data
    ├── customers/             Customer CRUD, communications, block/unblock
    ├── suppliers/             Supplier CRUD, approval, markup
    ├── agents/                Agent CRUD, approval, discount
    ├── affiliates/            Affiliate CRUD, approval, API link
    ├── cms/                   Tours, categories, subcategories, countries, cities
    ├── settings/              App, system, payment, API integration settings
    ├── email_templates/       Email template CRUD
    ├── profile/               User profile, password change
    ├── uploads/               Profile images, admin assets
    └── common/                Shared auth helpers, permission checks
```

---

## API Endpoints

### Auth — `/api/auth`

| Method | Path | Description |
| --- | --- | --- |
| POST | `/register` | User registration |
| POST | `/login` | Login (rate limited: 10/min) |
| GET | `/me` | Current user session |
| POST | `/forgot-password` | Request password reset (rate limited: 5/5min) |
| POST | `/reset-password` | Reset password with token |
| GET | `/reset-password/validate` | Validate reset token |
| POST | `/refresh-token` | Refresh JWT access token |
| POST | `/verify-email` | Verify email address |
| GET | `/login-history` | User login history |
| POST | `/force-logout` | Force logout other sessions |

### Users — `/api/users`

| Method | Path | Description |
| --- | --- | --- |
| GET/POST | `/` | List / create users |
| GET/PUT | `/{id}` | Get / update user |
| DELETE | `/{id}` | Delete user |
| POST | `/{id}/approve` | Approve pending user |
| POST | `/{id}/reject` | Reject pending user |
| POST | `/{id}/send-reset-mail` | Send password reset email |
| POST | `/{id}/roles` | Assign roles to user |

### Roles — `/api/roles`

| Method | Path | Description |
| --- | --- | --- |
| GET | `/public/options` | Public role options (for registration) |
| GET/POST | `/` | List / create roles |
| GET/PUT | `/{id}` | Get / update role |
| DELETE | `/{id}` | Delete role |
| GET/POST | `/{id}/permissions` | Get / assign permissions |

### Permissions — `/api/permissions`

| Method | Path | Description |
| --- | --- | --- |
| GET/POST | `/` | List / create permissions |
| GET/PUT | `/{id}` | Get / update permission |
| DELETE | `/{id}` | Delete permission |

### Dashboard — `/api/dashboard`

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

Dashboard responses differ by role:

| Role | Summary Content |
| --- | --- |
| super-admin / admin | Platform-wide totals (users, tours, bookings, revenue) |
| sub-admin | Module-specific totals based on assigned permissions |
| supplier | Own tour count, booking count, revenue, pending payouts |
| agent | Own booking count, clients, commission |
| customer | Own booking count, spend, upcoming trips |
| affiliate | Referral count, commission, payouts |

### CMS — `/api`

| Method | Path | Description |
| --- | --- | --- |
| GET/POST | `/countries` | List / create countries |
| GET/PUT/PATCH | `/countries/{id}` | Get / update / toggle status |
| GET/POST | `/cities` | List / create cities |
| GET/PUT/PATCH | `/cities/{id}` | Get / update / toggle status |
| GET/POST | `/tour-categories` | List / create tour categories |
| GET/PUT/PATCH | `/tour-categories/{id}` | Get / update / toggle status |
| GET/POST | `/tour-subcategories` | List / create subcategories |
| GET/PUT/PATCH | `/tour-subcategories/{id}` | Get / update / toggle status |
| GET/POST | `/tours` | List / create tours |
| GET/PUT/PATCH | `/tours/{id}` | Get / update / toggle status |

### Customers — `/api/customers`

| Method | Path | Description |
| --- | --- | --- |
| GET/POST | `/` | List / create customers |
| GET/PUT | `/{id}` | Get / update customer |
| PATCH | `/{id}/status` | Update status |
| POST | `/{id}/block` | Block customer |
| POST | `/{id}/unblock` | Unblock customer |
| POST | `/{id}/reset-password` | Reset password |
| GET | `/{id}/bookings` | Booking history |
| GET | `/{id}/payments` | Payment history |
| GET/POST | `/{id}/communications` | Get / send communications |

### Suppliers — `/api/suppliers`

| Method | Path | Description |
| --- | --- | --- |
| GET/POST | `/` | List / create suppliers |
| GET/PUT | `/{id}` | Get / update supplier |
| PATCH | `/{id}/approve` | Approve supplier |
| PATCH | `/{id}/reject` | Reject supplier |
| PATCH | `/{id}/partial-approve` | Partial approval |
| PATCH | `/{id}/markup` | Update markup settings |

### Agents — `/api/agents`

| Method | Path | Description |
| --- | --- | --- |
| GET/POST | `/` | List / create agents |
| GET/PUT | `/{id}` | Get / update agent |
| PATCH | `/{id}/approve` | Approve agent |
| PATCH | `/{id}/reject` | Reject agent |
| PATCH | `/{id}/partial-approve` | Partial approval |
| PATCH | `/{id}/discount` | Update discount settings |

### Affiliates — `/api/affiliates`

| Method | Path | Description |
| --- | --- | --- |
| GET/POST | `/` | List / create affiliates |
| GET/PUT | `/{id}` | Get / update affiliate |
| PATCH | `/{id}/approve` | Approve affiliate |
| PATCH | `/{id}/reject` | Reject affiliate |
| PATCH | `/{id}/api-link` | Update API link |

### Settings — `/api/settings`

| Method | Path | Description |
| --- | --- | --- |
| GET/PUT | `/` | General settings |
| GET/PUT | `/system` | System settings |
| GET/PUT | `/payment` | Payment provider settings |
| GET | `/payment/summary` | Payment summary |
| PUT | `/payment/{provider_name}` | Update single provider |
| GET/PUT | `/api` | API integration settings |
| GET | `/api/summary` | API summary |
| PUT | `/api/{api_name}` | Update single API config |

### Other Modules

| Module | Base Path | Description |
| --- | --- | --- |
| Email Templates | `/api/email-templates` | CRUD |
| Profile | `/api/profile` | View / update profile, change password |
| Uploads | `/api/uploads` | Profile images, admin assets |
| Client API | `/api/client` | Public/external client API |

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

Permission format: `{module}.{action}` (e.g. `dashboard.view`, `bookings.view`) or legacy `view-{module}` — both supported via `expand_permission_slugs()`.

---

## Tests

```bash
# Run all tests
venv\Scripts\python -m pytest tests/ -v

# Run a specific test file
venv\Scripts\python -m pytest tests/test_dashboard_role_based.py -v
```

Test files:

| File | Coverage |
| --- | --- |
| `test_01_core_health.py` | Health check endpoint |
| `test_02_auth.py` | Auth flows (register, login, refresh, reset) |
| `test_03_rbac.py` | Role and permission checks |
| `test_04_dashboard.py` | Dashboard endpoints |
| `test_05_settings.py` | Settings CRUD |
| `test_06_customers.py` | Customer management |
| `test_07_suppliers.py` | Supplier management |
| `test_08_agents.py` | Agent management |
| `test_09_affiliates.py` | Affiliate management |
| `test_10_countries.py` | Country CMS |
| `test_11_cities.py` | City CMS |
| `test_12_tour_categories.py` | Tour category CMS |
| `test_13_tour_subcategories.py` | Tour subcategory CMS |
| `test_14_basic_tours.py` | Basic tour CRUD |
| `test_15_advanced_tour_cms.py` | Advanced tour CMS |
| `test_16_tour_pricing.py` | Tour pricing |
| `test_17_tour_calendar.py` | Tour calendar |
| `test_18_tour_discounts.py` | Tour discounts |
| `test_19_uploads.py` | File uploads |
| `test_dashboard_role_based.py` | Role-scoped dashboard data (32 tests) |

---

## Production Checklist

- [ ] Set `JWT_SECRET_KEY` to a strong random secret (32+ chars)
- [ ] Set `SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP=false`
- [ ] Change default super admin password
- [ ] Point `DATABASE_URL` to production MySQL
- [ ] Configure real SMTP credentials
- [ ] Set `ALLOWED_ORIGINS` to production frontend domains
- [ ] Set `APP_ENV=production` and `APP_DEBUG=false`
