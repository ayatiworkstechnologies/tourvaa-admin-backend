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

### Step 1: Open the backend folder

```powershell
cd tourvaa-admin-backend
```

Run the remaining commands from this folder.

### Step 2: Check Python

```powershell
python --version
```

### Step 3: Create the virtual environment

```powershell
python -m venv venv
```

### Step 4: Activate the virtual environment

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

Windows Command Prompt:

```bat
venv\Scripts\activate.bat
```

Linux / Ubuntu:

```bash
source venv/bin/activate
```

If PowerShell blocks activation, run this once for the current terminal, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Step 5: Upgrade pip and install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 6: Configure `.env`

Create `.env` in this backend folder, next to `requirements.txt`. Create a local MySQL database first, then set its connection details:

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

`DATABASE_URL` and `JWT_SECRET_KEY` are required. Never commit `.env` or real credentials.

### Step 7: Apply migrations and seed local data

```powershell
alembic upgrade head
python seed.py
```

`seed.py` creates the required roles, permissions, reference data, and configured local bootstrap accounts. It is safe to re-run for normal local setup. Do not use destructive seed options against a database that contains data you need to keep.

### Step 8: Run the FastAPI server

Tourvaa uses `app/main.py`, so run:

```powershell
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 9: Open the API

- API: `http://localhost:8000`
- Health: `http://localhost:8000/api/health`
- Swagger documentation: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Windows PowerShell quick start

Run each command in order:

```powershell
cd tourvaa-admin-backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
# Create .env and a local MySQL database before continuing.
alembic upgrade head
python seed.py
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Ubuntu / Linux quick start

```bash
cd /var/www/tourvaa/tourvaa-admin-backend
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
# Create .env and a local MySQL database before continuing.
alembic upgrade head
python seed.py
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Run tests

```powershell
pip install -r requirements-dev.txt
pytest tests -v
```

Use a local test database. Do not run write-enabled tests against production data.

## Licence

Copyright © 2026 Tourvaa. Developed by Ayatiworks — Rubankumar Sankar.

All rights reserved. This software is proprietary and may not be copied, modified, distributed, or used without prior written permission from Tourvaa.
