# Tourvaa Backend

Tourvaa Backend is a FastAPI REST API for the Tourvaa travel platform. It supports the admin web app and future mobile app with authentication, users, roles, permissions, dashboard data, profile, settings, email templates, uploads, and seeded default roles/admin user.

## Tech Stack

- Python
- FastAPI
- MySQL
- SQLAlchemy
- PyMySQL
- JWT authentication

## How To Run

1. Create and activate virtual environment:

```bash
python -m venv venv
venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create `.env` in the `backend` folder:

```env
APP_NAME=Tourvaa Backend
APP_ENV=development
APP_DEBUG=true

DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/DATABASE_NAME

JWT_SECRET_KEY=replace_with_a_strong_secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

API_BASE_URL=http://127.0.0.1:8000
FRONTEND_URL=https://tourvaa.vercel.app
ALLOWED_ORIGINS=https://tourvaa.vercel.app,http://127.0.0.1:3000,http://localhost:3000
MOBILE_DEEP_LINK_URL=tourvaa://reset-password

SUPER_ADMIN_NAME=Super Admin
SUPER_ADMIN_EMAIL=admin@tourvaa.com
SUPER_ADMIN_PASSWORD=Admin@123
SUPER_ADMIN_RESET_PASSWORD_ON_STARTUP=false
```

4. Create the MySQL database used in `DATABASE_URL`.

5. Start the API:

```bash
uvicorn app.main:app --reload
```

6. Open API docs:

```txt
http://127.0.0.1:8000/docs
```

## Default Login

The backend seeds a Super Admin user on startup:

```txt
Email: admin@tourvaa.com
Password: Admin@123
```

## Test / Check

```bash
venv\Scripts\python -c "import app.main; print('backend import ok')"
```
