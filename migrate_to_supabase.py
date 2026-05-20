"""
One-off migration: DuckDB (MotherDuck) → Supabase (PostgreSQL)

Usage:
    MOTHERDUCK_TOKEN=<token> DATABASE_URL=<supabase_url> python migrate_to_supabase.py

Set DATABASE_URL to your full Supabase connection string, e.g.:
    postgresql://postgres:yourpassword@db.xmrvasnmcweixksybzmu.supabase.co:5432/postgres
"""

import os
import sys
import duckdb
import psycopg2
import pandas as pd

MOTHERDUCK_TOKEN = os.environ.get("MOTHERDUCK_TOKEN", "")
DATABASE_URL     = os.environ.get("DATABASE_URL", "")

if not MOTHERDUCK_TOKEN:
    sys.exit("ERROR: set MOTHERDUCK_TOKEN environment variable")
if not DATABASE_URL:
    sys.exit("ERROR: set DATABASE_URL environment variable")

duck_path = f"md:timesheet?motherduck_token={MOTHERDUCK_TOKEN}"

TABLES = [
    "settings",
    "employees",
    "clients",
    "projects",
    "entries",
    "invoices",
    "adhoc_draft_lines",
]

print("Connecting to MotherDuck...")
duck = duckdb.connect(duck_path)

print("Connecting to Supabase...")
pg = psycopg2.connect(DATABASE_URL)
pg.autocommit = True
cur = pg.cursor()

for table in TABLES:
    print(f"  Migrating {table}...", end=" ", flush=True)
    try:
        df = duck.execute(f"SELECT * FROM {table}").df()
    except Exception as e:
        print(f"SKIP ({e})")
        continue

    if df.empty:
        print("empty, skipped")
        continue

    # Only use columns that exist in the target Postgres table
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name=%s AND table_schema='public'",
        [table]
    )
    pg_cols = {r[0] for r in cur.fetchall()}
    cols = [c for c in df.columns if c in pg_cols]

    if not cols:
        print("no matching columns, skipped")
        continue

    df = df[cols]
    col_list = ", ".join(cols)
    val_list = ", ".join(["%s"] * len(cols))
    if table == "settings":
        conflict = "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
    elif "id" in cols:
        conflict = "ON CONFLICT (id) DO NOTHING"
    else:
        conflict = ""

    for _, row in df.iterrows():
        values = [None if pd.isna(v) else v for v in row]
        cur.execute(
            f"INSERT INTO {table} ({col_list}) VALUES ({val_list}) {conflict}",
            values
        )

    print(f"{len(df)} rows")

cur.close()
duck.close()
pg.close()

print("\nMigration complete.")
