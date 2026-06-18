from app.database import engine
from sqlalchemy import inspect

inspector = inspect(engine)

checks = {
    "users": ["id","name","email","password_hash","user_type","status","email_verified_at","last_login_at","last_login_ip","failed_login_attempts","created_at","updated_at"],
    "customers": ["id","user_id","customer_code","first_name","last_name","email","phone","status","is_blocked","blocked_reason","total_bookings"],
    "tours": ["id","title","slug","seo_title","seo_description","seo_keywords","status","free_cancellation"],
    "tour_overviews": ["id","tour_id","physical_rating","duration_text","start_location"],
    "bookings": ["id","customer_id","tour_id","booking_reference","status","created_at"],
    "payments": ["id","booking_id","amount","status","created_at"],
    "suppliers": ["id","company_name","status","approval_status"],
    "agents": ["id","company_name","status"],
    "affiliates": ["id","company_name","status"],
    "tour_pricing": ["id","tour_id","passenger_from","passenger_to","adult_price","final_price","currency"],
    "tour_calendar": ["id","tour_id","tour_date","available_seats","booked_seats","status"],
    "tour_discounts": ["id","tour_id","discount_code","discount_type","discount_value","status"],
}

for tname, expected in checks.items():
    actual = [c["name"] for c in inspector.get_columns(tname)]
    missing = [c for c in expected if c not in actual]
    status = "OK" if not missing else "MISSING_COLS"
    print(tname + " [" + status + "] " + str(len(actual)) + " cols | missing=" + str(missing))
