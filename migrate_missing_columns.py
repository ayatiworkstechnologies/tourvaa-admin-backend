"""
Migration script: add columns that exist in models but are missing from the DB.
Safe to run multiple times — skips columns that already exist.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app.database import engine
from sqlalchemy import text, inspect

inspector = inspect(engine)


def col_exists(table, col):
    return col in {c["name"] for c in inspector.get_columns(table)}


def add(table, col_name, col_def):
    if col_exists(table, col_name):
        print(f"  skip  {table}.{col_name} (already exists)")
    else:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN {col_name} {col_def}"))
        print(f"  added {table}.{col_name}")


print("supplier_vehicles:")
add("supplier_vehicles", "vehicle_type",       "VARCHAR(75)  NOT NULL DEFAULT '' AFTER `model`")
add("supplier_vehicles", "registration_number", "VARCHAR(100) NOT NULL DEFAULT '' AFTER `vehicle_type`")

# Add more columns here as needed using the same pattern:
# add("table_name", "column_name", "COLUMN_TYPE CONSTRAINTS AFTER `prev_col`")

print("Done.")
