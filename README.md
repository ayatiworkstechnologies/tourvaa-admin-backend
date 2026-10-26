# Project Name: Tourvaa Backend

**Tourvaa** is a travel-booking platform. This repository contains its FastAPI backend.

## Project Core

- Authentication, role-based access, and portal sessions for customers, suppliers, agents, affiliates, and administrators.
- Tour catalogue, availability, pricing, checkout, bookings, cancellations, payments, invoices, and confirmation receipts.
- Supplier acceptance and Tourvaa final-confirmation workflow; payment success is not itself final booking confirmation.
- Notifications, email templates, secure booking/support messages, and audit logs.
- Affiliate referral tracking, conversions, commissions, and currency-specific payout requests.
- CMS, countries, destinations, discounts, reporting, and platform settings.

## How to Run

### Run Command

After completing the one-time setup below, start the backend from the `tourvaa-admin-backend` folder with:

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to confirm the API is running.

### Before you start

Install Python and MySQL, then create an empty MySQL database for local development. Run every command below from the `tourvaa-admin-backend` folder.

### 1. Create the virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure the environment

Create a file named `.env` directly inside `tourvaa-admin-backend` (next to `requirements.txt`). Use your own local MySQL credentials:

```env
APP_ENV=development
APP_DEBUG=true
DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/DATABASE_NAME
JWT_SECRET_KEY=replace-with-a-strong-secret
ADMIN_JWT_SECRET_KEY=replace-with-a-different-strong-secret
NORMAL_JWT_SECRET_KEY=replace-with-a-different-strong-secret
FRONTEND_URL=http://localhost:3000
ALLOWED_ORIGINS=http://localhost:3000
```

`DATABASE_URL` and `JWT_SECRET_KEY` are required for startup. The two role-specific JWT secrets are recommended and must be different in production. Add SMTP and payment-provider values only when those integrations need local testing. Never commit `.env` or real credentials.

### 4. Apply the database migrations

```powershell
alembic upgrade head
alembic current
```

### 5. Seed local roles and reference data

```powershell
python seed.py
```

This is safe to re-run for local setup. Do not use destructive seed options against a database that contains data you need to keep.

### 6. Start the backend

```powershell
uvicorn app.main:app --reload
```

The backend starts with auto-reload at `http://127.0.0.1:8000`.

Verify that it is running:

- `http://127.0.0.1:8000/api/health` — health response
- `http://127.0.0.1:8000/docs` — Swagger API documentation
- `http://127.0.0.1:8000/openapi.json` — OpenAPI JSON

## Run tests

```powershell
pip install -r requirements-dev.txt
pytest tests -v
```

Use a local test database. Do not run write-enabled tests against production data.

## Licence

Copyright © 2026 Tourvaa. Developed by Ayatiworks — Rubankumar Sankar.

All rights reserved. This software is proprietary and may not be copied, modified, distributed, or used without prior written permission from Tourvaa.
