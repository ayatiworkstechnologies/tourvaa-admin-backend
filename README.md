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

### 1. Create and activate a Python environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure the environment

Create `.env` in this repository. At minimum, configure:

```env
DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/DATABASE_NAME
JWT_SECRET_KEY=replace-with-a-strong-secret
ADMIN_JWT_SECRET_KEY=replace-with-a-different-strong-secret
NORMAL_JWT_SECRET_KEY=replace-with-a-different-strong-secret
FRONTEND_URL=http://localhost:3000
ALLOWED_ORIGINS=http://localhost:3000
```

Add SMTP and payment-provider values only when those integrations need to be tested. Never commit real credentials.

### 4. Create the database and apply migrations

```powershell
python -m alembic upgrade head
python -m alembic current
```

For local reference data and roles, run:

```powershell
python seed.py
```

### 5. Start the API

```powershell
python -m scripts.dev_server
```

The API runs at `http://127.0.0.1:8000`.

- Swagger: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Health check: `http://127.0.0.1:8000/api/health`

## Run tests

```powershell
pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m pytest tests -v
```

Use a local test database. Do not run write-enabled tests against production data.

## Licence

Copyright © 2026 Tourvaa. Developed by Ayatiworks — Rubankumar Sankar.

All rights reserved. This software is proprietary and may not be copied, modified, distributed, or used without prior written permission from Tourvaa.
