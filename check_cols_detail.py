from app.database import engine
from sqlalchemy import inspect

inspector = inspect(engine)

for tname in ["users", "bookings", "payments", "suppliers", "agents", "affiliates"]:
    cols = [c["name"] for c in inspector.get_columns(tname)]
    print(tname + ": " + str(cols))
