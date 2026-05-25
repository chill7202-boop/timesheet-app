import streamlit as st
import psycopg2
import pandas as pd
import uuid
import re
import os
from datetime import date, datetime

st.set_page_config(page_title="Timesheet", page_icon="🕐", layout="wide")


def _db_url():
    try:
        url = st.secrets.get("DATABASE_URL", "")
    except Exception:
        url = ""
    return url or os.environ.get("DATABASE_URL", "")


@st.cache_resource
def _get_pool():
    import psycopg2.pool
    return psycopg2.pool.SimpleConnectionPool(1, 5, _db_url())


def get_conn():
    pool = _get_pool()
    con = pool.getconn()
    con.autocommit = True
    return con


def release_conn(con):
    _get_pool().putconn(con)


def init_db():
    con = get_conn()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id VARCHAR PRIMARY KEY,
            entry_date DATE,
            client VARCHAR,
            project VARCHAR,
            description VARCHAR,
            hours NUMERIC(6,2),
            rate NUMERIC(8,2),
            employee VARCHAR DEFAULT 'Self',
            status VARCHAR DEFAULT 'open',
            cost_rate NUMERIC(8,2) DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key VARCHAR PRIMARY KEY,
            value TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id VARCHAR PRIMARY KEY,
            name VARCHAR,
            address VARCHAR,
            contact_name VARCHAR,
            email VARCHAR,
            billing_type VARCHAR DEFAULT 'hourly',
            day_rate NUMERIC(8,2) DEFAULT 0,
            website VARCHAR,
            abn VARCHAR,
            billable BOOLEAN DEFAULT TRUE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id VARCHAR PRIMARY KEY,
            name VARCHAR,
            email VARCHAR,
            role VARCHAR,
            rate NUMERIC(8,2),
            cost_rate NUMERIC(8,2) DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id        VARCHAR PRIMARY KEY,
            code      VARCHAR,
            name      VARCHAR,
            client_id VARCHAR
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id             VARCHAR PRIMARY KEY,
            invoice_number VARCHAR,
            client         VARCHAR,
            invoice_date   DATE,
            subtotal       NUMERIC(10,2),
            gst            NUMERIC(10,2),
            total          NUMERIC(10,2),
            billing_type   VARCHAR DEFAULT 'hourly',
            invoice_type   VARCHAR DEFAULT 'timesheet',
            paid           BOOLEAN DEFAULT FALSE,
            paid_date      DATE,
            html_content   TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS adhoc_draft_lines (
            id          VARCHAR PRIMARY KEY,
            client      VARCHAR,
            description VARCHAR,
            qty         NUMERIC(8,2),
            unit_price  NUMERIC(10,2),
            sort_order  INTEGER DEFAULT 0
        )
    """)
    for stmt in [
        "ALTER TABLE employees ADD COLUMN IF NOT EXISTS cost_rate NUMERIC(8,2) DEFAULT 0",
        "ALTER TABLE entries ADD COLUMN IF NOT EXISTS cost_rate NUMERIC(8,2) DEFAULT 0",
        "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS description VARCHAR",
    ]:
        try:
            cur.execute(stmt)
        except Exception:
            pass
    cur.close()
    release_conn(con)


@st.cache_data(ttl=300)
def get_employees():
    con = get_conn()
    df = pd.read_sql("SELECT * FROM employees ORDER BY name", con)
    release_conn(con)
    return df.copy()


def save_employee(emp_id, name, email, role, rate, cost_rate=0):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    if emp_id:
        cur.execute(
            "UPDATE employees SET name=%s, email=%s, role=%s, rate=%s, cost_rate=%s WHERE id=%s",
            [name, email, role, rate, cost_rate, emp_id]
        )
    else:
        cur.execute(
            "INSERT INTO employees (id, name, email, role, rate, cost_rate) VALUES (%s,%s,%s,%s,%s,%s)",
            [str(uuid.uuid4()), name, email, role, rate, cost_rate]
        )
    cur.close()
    release_conn(con)


def delete_employee(emp_id):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    cur.execute("DELETE FROM employees WHERE id = %s", [emp_id])
    cur.close()
    release_conn(con)


@st.cache_data(ttl=300)
def get_clients_list():
    con = get_conn()
    df = pd.read_sql("SELECT * FROM clients ORDER BY name", con)
    release_conn(con)
    return df.copy()


def save_client(client_id, name, address, contact_name, email, billing_type='hourly', day_rate=0, website='', billable=True):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    if client_id:
        cur.execute(
            "UPDATE clients SET name=%s, address=%s, contact_name=%s, email=%s, billing_type=%s, day_rate=%s, website=%s, billable=%s WHERE id=%s",
            [name, address, contact_name, email, billing_type, day_rate, website, billable, client_id]
        )
    else:
        cur.execute(
            "INSERT INTO clients (id,name,address,contact_name,email,billing_type,day_rate,website,billable) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [str(uuid.uuid4()), name, address, contact_name, email, billing_type, day_rate, website, billable]
        )
    cur.close()
    release_conn(con)


def delete_client(client_id):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    cur.execute("DELETE FROM clients WHERE id = %s", [client_id])
    cur.close()
    release_conn(con)


@st.cache_data(ttl=300)
def get_setting(key, default=''):
    con = get_conn()
    cur = con.cursor()
    cur.execute("SELECT value FROM settings WHERE key = %s", [key])
    row = cur.fetchone()
    cur.close()
    release_conn(con)
    return row[0] if row else default


def save_setting(key, value):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        [key, value]
    )
    cur.close()
    release_conn(con)


def add_entry(entry_date, client, project, description, hours, rate, employee='Self', cost_rate=0):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO entries (id, entry_date, client, project, description, hours, rate, employee, status, cost_rate) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        [str(uuid.uuid4()), entry_date, client, project, description, hours, rate, employee, 'open', cost_rate]
    )
    cur.close()
    release_conn(con)


@st.cache_data(ttl=60)
def load_entries(client=None, project=None, from_date=None, to_date=None, employee=None, status=None):
    con = get_conn()
    query = "SELECT * FROM entries WHERE 1=1"
    params = []
    if client:
        query += " AND client = %s"
        params.append(client)
    if project:
        query += " AND project = %s"
        params.append(project)
    if from_date:
        query += " AND entry_date >= %s"
        params.append(from_date)
    if to_date:
        query += " AND entry_date <= %s"
        params.append(to_date)
    if employee:
        query += " AND employee = %s"
        params.append(employee)
    if status:
        if isinstance(status, list):
            placeholders = ','.join(['%s' for _ in status])
            query += f" AND status IN ({placeholders})"
            params.extend(status)
        else:
            query += " AND status = %s"
            params.append(status)
    query += " ORDER BY entry_date DESC"
    df = pd.read_sql(query, con, params=params)
    release_conn(con)
    return df


def delete_entry(entry_id):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    cur.execute("DELETE FROM entries WHERE id = %s", [entry_id])
    cur.close()
    release_conn(con)


def set_status(entry_id, status):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    cur.execute("UPDATE entries SET status = %s WHERE id = %s", [status, entry_id])
    cur.close()
    release_conn(con)


def set_status_bulk(ids, status):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    for i in ids:
        cur.execute("UPDATE entries SET status = %s WHERE id = %s", [status, i])
    cur.close()
    release_conn(con)


def get_next_invoice_number():
    prefix = get_setting('inv_prefix', 'INV') or 'INV'
    fmt    = get_setting('inv_format', 'date') or 'date'
    if fmt == 'sequential':
        num = int(get_setting('inv_next_num', '1') or 1)
        return f"{prefix}-{num:03d}"
    base = f"{prefix}-{datetime.now().strftime('%Y%m%d')}"
    con = get_conn()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM invoices WHERE invoice_number LIKE %s", [f"{base}%"])
    count = cur.fetchone()[0]
    cur.close()
    release_conn(con)
    return base if count == 0 else f"{base}-{count + 1}"


def increment_invoice_number():
    fmt = get_setting('inv_format', 'date') or 'date'
    if fmt == 'sequential':
        num = int(get_setting('inv_next_num', '1') or 1)
        save_setting('inv_next_num', str(num + 1))


def save_invoice(invoice_number, client, subtotal, gst, total, billing_type='hourly', invoice_type='timesheet', html_content=''):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO invoices (id,invoice_number,client,invoice_date,subtotal,gst,total,billing_type,invoice_type,paid,html_content) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        [str(uuid.uuid4()), invoice_number, client, date.today(), subtotal, gst, total, billing_type, invoice_type, False, html_content]
    )
    cur.close()
    release_conn(con)


@st.cache_data(ttl=60)
def get_invoices(client=None):
    con = get_conn()
    q = "SELECT * FROM invoices WHERE 1=1"
    p = []
    if client:
        q += " AND client = %s"
        p.append(client)
    q += " ORDER BY invoice_date DESC, invoice_number DESC"
    df = pd.read_sql(q, con, params=p)
    release_conn(con)
    return df


def mark_invoice_paid(invoice_id, paid=True):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    if paid:
        cur.execute("UPDATE invoices SET paid=TRUE, paid_date=%s WHERE id=%s", [date.today(), invoice_id])
    else:
        cur.execute("UPDATE invoices SET paid=FALSE, paid_date=NULL WHERE id=%s", [invoice_id])
    cur.close()
    release_conn(con)


def update_invoice_description(invoice_id, description):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    cur.execute("UPDATE invoices SET description=%s WHERE id=%s", [description, invoice_id])
    cur.close()
    release_conn(con)


def invoice_number_exists(inv_number):
    con = get_conn()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM invoices WHERE invoice_number = %s", [inv_number])
    row = cur.fetchone()
    cur.close()
    release_conn(con)
    return row[0] > 0


# ── Ad hoc draft line helpers ──────────────────────────────────────────────────

def load_adhoc_lines(client):
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        "SELECT id, description, qty, unit_price FROM adhoc_draft_lines WHERE client=%s ORDER BY sort_order",
        [client]
    )
    rows = cur.fetchall()
    cur.close()
    release_conn(con)
    return [{'id': r[0], 'description': r[1], 'qty': float(r[2]), 'unit_price': float(r[3])} for r in rows]

def add_adhoc_line(client, description, qty, unit_price):
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        "SELECT COALESCE(MAX(sort_order),0) FROM adhoc_draft_lines WHERE client=%s", [client]
    )
    max_order = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO adhoc_draft_lines (id, client, description, qty, unit_price, sort_order) VALUES (%s,%s,%s,%s,%s,%s)",
        [str(uuid.uuid4()), client, description, qty, unit_price, int(max_order) + 1]
    )
    cur.close()
    release_conn(con)

def update_adhoc_line(line_id, description, qty, unit_price):
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        "UPDATE adhoc_draft_lines SET description=%s, qty=%s, unit_price=%s WHERE id=%s",
        [description, qty, unit_price, line_id]
    )
    cur.close()
    release_conn(con)

def delete_adhoc_line(line_id):
    con = get_conn()
    cur = con.cursor()
    cur.execute("DELETE FROM adhoc_draft_lines WHERE id=%s", [line_id])
    cur.close()
    release_conn(con)

def clear_adhoc_lines(client):
    con = get_conn()
    cur = con.cursor()
    cur.execute("DELETE FROM adhoc_draft_lines WHERE client=%s", [client])
    cur.close()
    release_conn(con)


@st.cache_data(ttl=300)
def get_clients():
    con = get_conn()
    cur = con.cursor()
    cur.execute("SELECT DISTINCT client FROM entries ORDER BY client")
    rows = cur.fetchall()
    cur.close()
    release_conn(con)
    return [r[0] for r in rows]


@st.cache_data(ttl=300)
def get_projects(client=None):
    con = get_conn()
    cur = con.cursor()
    if client:
        cur.execute("SELECT DISTINCT project FROM entries WHERE client = %s ORDER BY project", [client])
    else:
        cur.execute("SELECT DISTINCT project FROM entries ORDER BY project")
    rows = cur.fetchall()
    cur.close()
    release_conn(con)
    return [r[0] for r in rows]


@st.cache_data(ttl=300)
def get_projects_list(client_id=None):
    con = get_conn()
    if client_id:
        df = pd.read_sql("SELECT * FROM projects WHERE client_id=%s ORDER BY code, name", con, params=[client_id])
    else:
        df = pd.read_sql("SELECT * FROM projects ORDER BY code, name", con)
    release_conn(con)
    return df


def save_project(project_id, code, name, client_id=None):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    if project_id:
        cur.execute("UPDATE projects SET code=%s, name=%s, client_id=%s WHERE id=%s", [code, name, client_id, project_id])
    else:
        cur.execute("INSERT INTO projects VALUES (%s, %s, %s, %s)", [str(uuid.uuid4()), code, name, client_id])
    cur.close()
    release_conn(con)


def delete_project(project_id):
    st.cache_data.clear()
    con = get_conn()
    cur = con.cursor()
    cur.execute("DELETE FROM projects WHERE id=%s", [project_id])
    cur.close()
    release_conn(con)


@st.cache_data(ttl=60)
def get_dashboard_data():
    con = get_conn()
    today = date.today()
    yr, mo = today.year, today.month
    three_months_ago = (today.replace(day=1) - pd.DateOffset(months=3)).date()

    cur = con.cursor()
    cur.execute("""
        SELECT
            COALESCE(SUM(total), 0),
            COALESCE(SUM(CASE WHEN paid THEN total ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN NOT paid THEN total ELSE 0 END), 0),
            (
                SELECT COALESCE(json_agg(h), '[]'::json)
                FROM (
                    SELECT client, ROUND(SUM(hours),2) AS hours
                    FROM entries
                    WHERE EXTRACT(YEAR FROM entry_date)=%s AND EXTRACT(MONTH FROM entry_date)=%s
                    GROUP BY client ORDER BY hours DESC
                ) h
            ),
            (
                SELECT COALESCE(json_agg(u ORDER BY u.invoice_date), '[]'::json)
                FROM (
                    SELECT client, invoice_number, invoice_date::text, total
                    FROM invoices WHERE paid=FALSE
                ) u
            ),
            (
                SELECT COALESCE(json_agg(t), '[]'::json)
                FROM (
                    SELECT client, ROUND(SUM(total),2) AS revenue
                    FROM invoices WHERE invoice_date >= %s
                    GROUP BY client ORDER BY revenue DESC LIMIT 10
                ) t
            )
        FROM invoices
        WHERE EXTRACT(YEAR FROM invoice_date)=%s AND EXTRACT(MONTH FROM invoice_date)=%s
    """, [yr, mo, three_months_ago, yr, mo])

    row = cur.fetchone()
    cur.close()
    release_conn(con)

    revenue = (row[0], row[1], row[2])
    hours      = pd.DataFrame(row[3] or [])
    unpaid     = pd.DataFrame(row[4] or [])
    top_clients = pd.DataFrame(row[5] or [])

    if not unpaid.empty and 'invoice_date' in unpaid.columns:
        unpaid['invoice_date'] = pd.to_datetime(unpaid['invoice_date'])

    return revenue, hours.copy(), unpaid.copy(), top_clients.copy()


def _abr_json(resp_text):
    """Strip JSONP wrapper and parse."""
    import json as _json
    t = resp_text.strip()
    if t.startswith('callback(') and t.endswith(')'):
        t = t[9:-1]
    return _json.loads(t)

def abr_search(query, guid):
    """Search ABR by business name or ABN. Returns list of dicts."""
    import httpx
    query = query.strip()
    is_abn = bool(re.match(r'^\d[\d\s]{9,12}\d$', query))
    try:
        if is_abn:
            abn_clean = re.sub(r'\s', '', query)
            resp = httpx.get('https://abr.business.gov.au/json/AbnDetails.aspx',
                             params={'abn': abn_clean, 'guid': guid}, timeout=10)
            data = _abr_json(resp.text)
            if data.get('AbnStatus') == 'Active':
                name = data.get('EntityName', '')
                bnames = [b for b in data.get('BusinessName', []) if b]
                if bnames: name = bnames[0]
                state, pc = data.get('AddressState', ''), data.get('AddressPostcode', '')
                return [{'abn': data.get('Abn',''), 'name': name,
                         'state': state, 'postcode': pc,
                         'address': f'{state} {pc}'.strip()}]
            return []
        else:
            resp = httpx.get('https://abr.business.gov.au/json/MatchingNames.aspx',
                             params={'name': query, 'guid': guid}, timeout=10)
            data = _abr_json(resp.text)
            results = []
            for entry in data.get('Names', []):
                parts = [p.strip() for p in entry.strip().split('\n') if p.strip()]
                if len(parts) >= 2:
                    name   = parts[0]
                    abn    = re.sub(r'\s', '', parts[1])
                    status = parts[2] if len(parts) > 2 else ''
                    if 'Active' in status:
                        results.append({'abn': abn, 'name': name,
                                        'state': '', 'postcode': '', 'address': ''})
            return results[:15]
    except Exception:
        return []

def abr_get_detail(abn, guid):
    """Fetch ABN details. Returns dict with name, state, postcode."""
    import httpx
    try:
        resp = httpx.get('https://abr.business.gov.au/json/AbnDetails.aspx',
                         params={'abn': abn, 'guid': guid}, timeout=10)
        data = _abr_json(resp.text)
        name = data.get('EntityName', '')
        bnames = [b for b in data.get('BusinessName', []) if b]
        if bnames: name = bnames[0]
        state, pc = data.get('AddressState', ''), data.get('AddressPostcode', '')
        return {'abn': data.get('Abn', ''), 'name': name,
                'state': state, 'postcode': pc,
                'address': f'{state} {pc}'.strip()}
    except Exception:
        return {}

def generate_invoice_html(entries_df, settings, invoice_number, include_gst, payment_terms='', billing_type='hourly', client_day_rate=0, adhoc_lines=None, due_date=None, period_end=None):
    import base64 as _b64
    my_name    = settings.get('name', '')
    my_company = settings.get('company', '')
    my_address = settings.get('address', '')
    my_abn     = settings.get('abn', '')
    my_email   = settings.get('email', '')
    bank_name      = settings.get('bank_name', '')
    account_name   = settings.get('account_name', '')
    bsb            = settings.get('bsb', '')
    account_number = settings.get('account_number', '')

    client_name    = settings.get('inv_client_name', '')
    client_address = settings.get('inv_client_address', '')
    inv_date       = date.today().strftime('%d %B %Y')
    if due_date is None:
        days_in_month = [31,28,29,30,31,30,31,31,30,31,30,31][date.today().month - 1]
        due_date = date(date.today().year, date.today().month, min(date.today().day + 14, days_in_month))
    due_date_str = due_date.strftime('%d %B %Y')
    period_end_str = period_end.strftime('%d %B %Y') if period_end else ''

    # ── Logo (embedded) ──────────────────────────────────────────────────────
    LOGO_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAqkAAACHCAYAAAA1H8CoAAAACXBIWXMAACxLAAAsSwGlPZapAAAUFklEQVR4nO3de5RtRX3g8S+PgAoFaETRUmE0YUgpzjWAUUGXS6MG1IA8DDISlyHxgXkoxvAQBSbhHYOPjFEkGlEBRaNEgwQNuRpBozgjKBUUjc9CjPKQEomM4PyxN+bmcvbp291779Pd5/tZ66wFp3ZX/W7f292/3rvq9wNJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkqTVa7NZByBJK02IaRvgV4BfBnYEtgXuAn4EfBf4MnBtLfmnMwtSkta4VZmk3nb5Tj+bdQxLsc3eN6zKz/eGQkxdn/vTa8nHLHPunYErgAd3XPJ1YJ9a8vVLmHvIuLvmvgb41VryHcuZf5FrLvvPsxQhpj2BxwKPBnYHHgBs377uAm5pXzcCVwOfB64Erq4lr4iv5xDTdsDzgUOAJwBbLfAhtwKXAe8GLhoyYV1pf9+TTIlxKCfVkk/c1ItDTKcAx3YMf7iW/Ju9RPWf6z2K5t/6pO/7NwEPryX/cJFzjvrvIMR0GnD0pLFa8rJ+ns3oe/Jq+HpZMTGuBFvOOgAJIMS0I/AxuhPUG4CnLSVBnaFHAq8GTph1IEMIMe0OvBA4CHjYApfv1L4A9t7g/W+GmN4FvLOW/NX+o1xYiOlewFHAMUBYxIduBxzQvr4ZYjqmlnxB7wGqL2cALwV2mDD27BDTulryF3pc7zV03wg6Y7EJqjSPNp91AFKIKQAfpXm0OsnNwNNryV8bL6reHNsmc2tGiGn3ENP7gauAV7BwgjrNzsDxwHUhpvNCTA/pI8ZNFWLaDfgccDKLS1A3tjNwfojpohDTfXsJTr2qJd8CnDnlktf0tVb77+rgjuHvAW/qay1pLTNJ1UyFmLYGPgTs0XHJj4Fn1pK/OFpQ/foF4O0hpi1mHchyhZi2ah//fYHm7mnf21eeB3w5xHRsiGnwrTEhpj1otpc8qsdpfxO4IsS004JXahbeQJMkTvKc9hF9H46n++frybXkH/e0jrSmmaRqZkJMmwPvAZ7ScckdwHNqyZ8eL6pB7EnzOHnVCjH9EvBZmv1pQ37fuA9wCnBhiOk+Qy3S3rH9B2CIu567AR8bMn4tTS35Npp/X5NsRpNcLkv7tXJox/C3gLcudw1pXrgnVbP0VzR35Ca5C3h+LfnSEeMZ0kkhpg/Vkq+bdSCLFWJ6NHAp8MBNuPxO4Cs0B0Z+APyQ5m7y9sCDgHXAQzdhnoOAXUJMv94+pu3bu4BfnDL+beAC4GLga8C/A1vQ/Bn2An4L2J/uu8mPonmke0RP8a5mlwMfH2De9Uv8uLcCr2TyNpVDQkwn1pKvXXJUzT70ricnJw1xkFJaq0xSNRMhppOBF0255MW15AvHimcE9wbOCTE9eaWcZt8UIabH0Jxg32GBSy+muSv+4VpyXWDOhwKH0fz9P3zKpXsAF4SY9qsl37XJQS8gxLQ/8OSO4Z8BpwJ/Vku+fcL419rXBSGmx9Mksl17cl8YYnpzLfnzywx5tfvUYk7hD62W/JMQ0/8CzpkwvDlNknn4UuYOMe1CUyFikq8A71zKvNK88nG/Rhdi+iPguCmXHF1LnvQDZLV7EvCSWQexqdqKCx9ieoL6CWDPWvIza8nnLZSgAtSSv11LPp2mDunRNNs6ujwDOG2Tg940fzhl7FW15Fd3JKj/RbsN5TE0NVMn2Qx41RLi0/D+hiZpnOR57SP7pTiO7ps/J9SS71zivNJcMknVqEJMhwFnTbnk9FryGWPFMwOnt3cSV7R2v/D76L5LeCfND+SnLPVOYS35jvbv+qk09VO7vLLdcrBsbeL95I7hT9WSX7eY+WrJN9HUVf1JxyX7t40BtIK0yeJrO4a3YPov0RO1X9cv6Bi+GnjvYueU5p1JqkYTYtqX5g5G1z6+s+egiHFgdRyc+F26k7k7gcNryaf28Ri+lvwpmv2dXXdUN6d5BN+Hvej+vveGpUzYVp7oqo96L7orV2i23kdTqWKSw0NM/22R8x1DdwOI41fTNh9ppTBJ1Sja/XvvpzlEM8n7aAptryW3dLy/b4hpSXvextDW+Tx5yiVH1pLP73PNWvLlTD9ZvV+I6XE9LLXrlLH/s4x5p+017LPElXrSJo1dtVG3pLs71T2EmB5M9yG5f6klf3iR4UnCJFUjCDE9EvgITXmhSS6hOcnf2+GYFeIdwJc6xl4fYnrAmMEswiuB+3eMnVdLPnugdd8IfHPK+GE9rLHDlLGyjHnzlLH7LWNeDaiW/BGaWrmTvGARW3P+BNi6Y+zViw5MEmCSqoGFmB5GU4+y6wf1FcBBteT/N15Uo7kD+B2ax+Mbux/wl+OGs7C2uUJX1YVbgZcPtXYt+Sc0iX2X5/RQ5H/aI9cdlzppLfl7wO4dr7ctdV6Nomv/6VY0j/CnCjE9kO6vmX+qJf/jUgOT5p0lqDSY9pDKpUDsuORqmm5Sa7b7Si35cyGms4A/njB8SIjpObXkD44d1xSH0p2snVlL/v7A67+d6Z2sdqBpk7tUP5gy9mjgO0uduJbcdddcK1gt+RMhpo8BT5swfESI6eRa8vVTpvhjmhJzk3gXVVoGk1QNIsS0LU3tzP/ecclXgacPVKh9pXktcAAwqazNm0NM/7SCPg/P7Xj/DuAtQy9eS/42cOKAS3SVHYKmNNXFA66tles4JiepW9M8yn/5pA8KMd2f7r30H1kD3fKkmfJxv3oXYtqKpr7mnh2XFOBp7SPSNa+tuXkEkx817wT8xbgRTRZiuhfdJ/ovqiVPuwu5WlwOdG0teUaIaa1Xl9AEteQrab5nTfKi9pH+JEcBk0qMTTuUJWkTmaSqV219zXfT1L6c5EaaO6jfGC2oFaCW/Em670S+MMT09DHj6fBEug+3/f2YgQyl3Vryt1MuOTXEdE6IKYwVk1aM42naMW/s3kzYrtNWwfj9jrkurCV/ob/QpPlkkqq+/W+a4uaT3A7sV0uedhJ6LTuapif8JGevgKLvvzpl7LLRohjeqUxORu52BPC1ENNxbSKiOVBLvgY4r2P4pe2j/Q29nKbu8camNQqQtAgmqepNiOlPmd72c2umn65e09qWoV2ngHemv4L1S/UrHe9/v90ruibUkq9i4X2vO9LUir0hxPSBENOB7XYIrW0nMHk7yDY0j/YBCDFtT3d73XNryV2tciUtggen1JeDgUcscM3mNHcM95zXHta15EtCTOcCvz1h+GUhpve2he1nYbeO9786ahTjOJmm5evvLnDdVsCB7evWENNFNO0tL12jZdOGsE+I6cQe51tfS17f43w/V0v+txDTXzP5l+3fDzGdWUu+mSZB3WHCNXcAJw0R2wL6/hz/fN4B5pQ2mUmq+rJQgnq3dTSPyRbVI32NeQXwDGDjwxibA+eEmNa1NUPH1nU45BtjBjGGtnHE74WYvk5zV7WrE9qGtgMOb183h5jeC5xTS/78YIGuDXu3rz6t73m+Df0p8ALuWVYqAC8PMZ1Jd73gt9WSpzWkGMoQn2Np5kxSNQsnhZgurCV/a9aBzEIt+aYQ08to2sRubDeaR45dBcaHtG3H+7cud+IQU2/bPGrJyy3ov+Fcp4SY/p7mUNti2q7el+Zu20tCTF+g6ZZ17rw+IVhLasnXh5jeTNN5bWN/SHN3fVJzktuZ3k5Y0iK5J1VD6jqcsg3NAau5VUv+APCBjuFXhZgeM2Y8ra4T7beNGsXIaslX1ZIfD+wH/PMSplhH04TgSyGmg/uMTTNzKlAnvL8D3V2o3lRL/u5gEUlzyCRVQ/kgTUvQLs8KMR00VjAr1MuAmya8vyXw9hDT2E86tuh4fy4Ou9WSP1pLfhKwK80dsX9b5BS7AReGmC6eUldTq0At+UYWV7/4VuCMgcKR5pZJqobwj8DzasnvbP+7yxtDTNuNFNOK0zYzOKpjeB1Np5sx/ajj/VmXxhpVLfm6WvLxteRHAHsBf87i9uXuC3wmxLTrEPFpNK+jqeu8Kf6iTWwl9cg9qerbvwAHbHDw50jgapryUxt7MM0dqz8YKbYVp5b8zhDTocBvTBh+bYjpb2vJ144Uzo+YfGJ5bgvbt52IrqTZgvFY4PnAoTQlqqbZBbg0xPS4WvINw0a54p1eS151nbxqyTXEdDoL3yG9EThrhJCmGeRzHGI6jaa+szQTJqnq0zU0xfp/fkeulvyV9hvdCR0fc2SI6dxa8udGiXBlejHwJe6ZDG4N/HWI6YntafSh3Qw8ZML7D+th7sWW5dkXeGwP6/amlvxZ4LMhplfSlFw7Fth9yofsDPwNk38B0erwlzQn+R885ZrTasnLPlwo6Z5MUtWXr9O0O520x/JU4DDglyeMWTu15G+1PeMnHSZ7Ak3rxTeOEMp1TE66fmm5E9eST1zM9SGmdctdcyhtfdTzQ0wX0DRneB3dWyKeEWLav5Z80WgBqje15NtDTH8GvLnjku8y54dApSG5J1V9eV8t+fpJA+2j/yOnfOw6uusOzou/Aj7ZMXZKiGmXEWLo2lbwoBDTA0ZYf0NdjQVWjFryz2rJb6XZt/qDKZd27TvW6nDOlLHza8m3jxaJNGdMUjWKWvLH6e6LDU3t1D4eK69KteSf0XQ/mvQDbxvg7BHCuGbK2JNHWB+Atv3ow8dab7lqyf8KPBv4accl+4SYFtrDqhVqgc5idh2TBmSSqjEdBdzSMWbt1JKvo3vv7tNCTNNKevXhMrrLTY25r/KpbFoHqBWjlvwZ4B0dw5sDe4wYjiStCSapGk1bcunYKZdYO7WpzXhlx9jrQkwPGmrh9hT61R3Dh4SYujpS9e3ZQ0waYto/xHTAhNcje1ri/CljlqOSpEUySdXY3gp8Zsr4vNdOvZOmCcKkx4g70H2Aoy8f7nh/W+C3B16bENO9gQMHmv49NE0mNn69tKf5uxJ8gO17WkOS5oZJqkbV7r18Md379+6unTq3aslfBE7pGD4gxPTcAZd/G9BVZeE1IaahC/u/hIVrkC7VzR3vP6Kn+X84ZWxVbV+QpJXAJFWjqyVfDbxhyiVHhpj2GiueFeoUmtqpk7xpqEVryd8C/q5jeCcWX+90k7XbCV411PzAlzvef0KIaase5r/vlLFbephfkuaKSapm5QTg2x1jd9dO7eolv+bVku+geew/6a7m0OWgTga6mgccFWJ61kDrvgUYbM8t3Xt9twMO6WH+ac0HvtLD/JI0V0xSNRO15NuY3g51HXNeO7XtwjV6u8Va8ueBt3cMb0ZTyP5Jfa4ZYnoR8D/7nHOCrjvE0JRAu88y5/+9jvfvAj67zLklae6YpGpm2i48CyUOc1s7tfVa4KszWPc44PsdY9sCF4eYntfHQm2b0bf0MdcCPk335/IRNC1oN1vKxCGm5wP7dwx/opb870uZV5LmmUmqZu0PgNs6xqyd2nSzOYLu+qVDrft94Ll0H3DbBjgvxPSepf4iEWJ6WIjpXcCf09yh3VDvvdDbQ3vT9tQeCrw/xLSok/htst515xnGaWkrSWvOlrMOQPOt7Vt/InBmxyXPCjEdVEv+wIhhrSi15E+GmN5Cf6WSNnXd9SGmo5ieZB0GHBxiejdNR7H1bRmtiUJMWwNPAA6m6bA16cDSv9KUKnv9EkOf5jzgRcATO8YPBB4fYjoFeFcteeKJ/Xa/9N7AMcC+U9b7dC35Q0sPd0H7tF8/vakl9zofA8TYWl9LXj/AvFq75vLrZYAYR2OSqpXg9cDhwKM7xt8YYvpYLbn3u2uryNHAs4CHjrloLflNIaYtaZoMdNmK5pDX7wA/CjFdRXOS/haaNq/3Be5PcyhqT+DeU+a6HfgtYJflxj5JLfmuENNhwP9tY5rkQTQVFM4KMV0JZOAHNIfYdgQeCDx+ysff7TbgBX3EPcXe7atPJ/Y83xAx3m39QPNqbZrXr5cTe55vNCapmrla8k9DTC8GruCej33hP2unTjtotabVkmt7uOijM1j7rBDTLTSNBO61wOXbsvRvsj8Gnl1L/mJb1H8QteTvhJh+naYN7P2mXLol8Lj2tVh3AAe1rW4lSUvgnlStCG3v87OnXDL3tVNryZcA585o7XcAezG9q9Jy3AT8Ri35svb/vzfQOgDUkq+iSaSvGWD6m4Bn1pL/YYC5JWlumKRqJTkG6DoFPfe1U1uvYOAErkst+Us0iWrfMXwQSLXkf97gvcH/jLXka2lqm54G/KSnaS8B9qglf7yn+SRpbpmkasWoJd8CHDXlknVYO/Um4GUzXP+OWvLrgYfTbL+4gqVVHriTJjl9ai35wFryf0lKa8n/AdRlhrugWvKPa8nHArsCZ9BddmshlwH71ZL3rSV/o6/4JGmeLakm4KzddvlOo5bj6cs2e9+wKj/f0jQhpocATwUeA/wPmsNd29N0ctoC+A/gRpoOYxn4DHBJLfn6Bebdhwl7YIe8S9keEvs14Ck0f5ZdaQ5SbQNsTbNv9lbgm8C1NLVXP1pL/s5QMUmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSVp//D9bteFEy/1JzAAAAAElFTkSuQmCC'

    # ── Row generation ────────────────────────────────────────────────────────
    rows_html = ''
    if billing_type == 'fixed':
        for idx, line in enumerate(adhoc_lines or []):
            amount = float(line.get('qty', 1)) * float(line.get('unit_price', 0))
            rows_html += f"""
        <tr>
          <td>{idx + 1}</td>
          <td colspan="2">{line.get('description', '')}</td>
          <td class="num">{float(line.get('qty', 1)):.2f}</td>
          <td class="num">${float(line.get('unit_price', 0)):,.2f}</td>
          <td class="num amt">${amount:,.2f}</td>
        </tr>"""
        subtotal = sum(float(l.get('qty', 1)) * float(l.get('unit_price', 0)) for l in (adhoc_lines or []))
    elif billing_type == 'day_rate':
        grouped = entries_df.groupby('entry_date', sort=True)
        for entry_date, grp in grouped:
            projects = ', '.join(grp['project'].dropna().unique())
            descs    = '; '.join(grp['description'].dropna().tolist())
            amount   = float(client_day_rate)
            rows_html += f"""
        <tr>
          <td style="white-space:nowrap">{pd.to_datetime(entry_date).strftime('%d/%m/%Y')}</td>
          <td>{projects}</td>
          <td>{descs}</td>
          <td class="num">1</td>
          <td class="num">${float(client_day_rate):,.2f}</td>
          <td class="num amt">${amount:,.2f}</td>
        </tr>"""
        subtotal = len(grouped) * float(client_day_rate)
    else:
        for _, row in entries_df.iterrows():
            amount = float(row['hours']) * float(row['rate'])
            rows_html += f"""
        <tr>
          <td style="white-space:nowrap">{pd.to_datetime(row['entry_date']).strftime('%d/%m/%Y')}</td>
          <td>{row['project']}</td>
          <td>{row['description']}</td>
          <td class="num">{float(row['hours']):.2f}</td>
          <td class="num">${float(row['rate']):,.2f}</td>
          <td class="num amt">${amount:,.2f}</td>
        </tr>"""
        subtotal = sum(float(r['hours']) * float(r['rate']) for _, r in entries_df.iterrows())

    gst   = subtotal * 0.1 if include_gst else 0
    total = subtotal + gst

    gst_row = f'<tr><td class="lbl">GST (10%)</td><td class="val">${gst:,.2f}</td></tr>' if include_gst else ''

    sender_display = my_company or my_name
    abn_html       = f'<div>ABN &nbsp;{my_abn}</div>' if my_abn else ''
    email_html     = f'<div>{my_email}</div>' if my_email else ''
    addr_html      = f'<div style="white-space:pre-line">{my_address}</div>' if my_address else ''
    client_addr_html = f'<div class="c-addr">{client_address}</div>' if client_address else ''
    period_row     = f'<tr><td class="lbl">Period ending</td><td class="val">{period_end_str}</td></tr>' if period_end_str else ''

    # Payment details block
    pay_rows = ''
    if bank_name:      pay_rows += f'<tr><td>Bank</td><td>{bank_name}</td></tr>'
    if account_name:   pay_rows += f'<tr><td>Account name</td><td>{account_name}</td></tr>'
    if bsb:            pay_rows += f'<tr><td>BSB</td><td>{bsb}</td></tr>'
    if account_number: pay_rows += f'<tr><td>Account</td><td>{account_number}</td></tr>'
    pay_rows += f'<tr><td>Reference</td><td>{invoice_number}</td></tr>'
    payment_section = f'''
  <div class="pay-section">
    <div class="section-label">PAYMENT DETAILS</div>
    <table class="pay-table">{pay_rows}</table>
  </div>''' if (bank_name or bsb or account_number) else ''

    notes_section = f'''
  <div class="notes-section">
    <div class="section-label">NOTES</div>
    <div class="notes-body">{payment_terms.replace(chr(10), '<br>')}</div>
  </div>''' if payment_terms.strip() else ''

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Tax Invoice {invoice_number}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 13px;
    color: #374151;
    background: #F3F4F6;
    padding: 40px 20px;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
    line-height: 1.6;
  }}
  .page {{
    max-width: 800px;
    margin: 0 auto;
    background: #ffffff;
    box-shadow: 0 1px 12px rgba(0,0,0,0.08);
  }}
  .top-bar {{ height: 5px; background: #1F4D78; }}

  /* Header */
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 36px 48px 28px;
    border-bottom: 1px solid #E5E7EB;
  }}
  .logo {{ height: 36px; object-fit: contain; }}
  .inv-title {{
    font-size: 28px;
    font-weight: 600;
    color: #0D1B2A;
    letter-spacing: -0.5px;
    text-align: right;
  }}
  .inv-number {{
    font-size: 14px;
    color: #6B7280;
    text-align: right;
    margin-top: 4px;
  }}

  /* Meta section */
  .meta {{
    display: flex;
    justify-content: space-between;
    padding: 28px 48px;
    background: #F9FAFB;
    border-bottom: 1px solid #E5E7EB;
    gap: 40px;
  }}
  .bill-to {{ flex: 1; }}
  .meta-label {{
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #9CA3AF;
    margin-bottom: 8px;
  }}
  .client-name {{
    font-size: 16px;
    font-weight: 600;
    color: #0D1B2A;
    line-height: 1.3;
  }}
  .c-addr {{
    font-size: 12px;
    color: #6B7280;
    margin-top: 4px;
    line-height: 1.6;
    white-space: pre-line;
  }}
  .inv-meta-right {{ text-align: right; min-width: 220px; }}
  .meta-table {{ margin-left: auto; border-collapse: collapse; }}
  .meta-table td {{ padding: 3px 0 3px 20px; font-size: 13px; }}
  .meta-table td:first-child {{ color: #6B7280; text-align: left; }}
  .meta-table td:last-child {{ color: #0D1B2A; font-weight: 500; text-align: right; }}
  .status-badge {{
    display: inline-block;
    margin-top: 12px;
    padding: 3px 12px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    background: #FEF3C7;
    color: #92400E;
    border: 1px solid #FDE68A;
  }}

  /* Sender strip */
  .sender-strip {{
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    padding: 14px 48px;
    border-bottom: 1px solid #E5E7EB;
    font-size: 12px;
    color: #6B7280;
    gap: 2px;
  }}
  .sender-strip strong {{ color: #0D1B2A; font-weight: 600; font-size: 14px; }}

  /* Table */
  .table-wrap {{ padding: 0 48px; }}
  table.items {{ width: 100%; border-collapse: collapse; margin: 28px 0 0; font-size: 13px; }}
  table.items thead tr {{ background: #1F4D78; }}
  table.items thead th {{
    padding: 11px 14px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #ffffff;
    text-align: left;
  }}
  table.items thead th.num {{ text-align: right; }}
  table.items tbody tr {{ border-bottom: 1px solid #F3F4F6; }}
  table.items tbody tr:nth-child(even) {{ background: #F9FAFB; }}
  table.items tbody td {{ padding: 11px 14px; color: #374151; vertical-align: top; }}
  table.items tbody td.num {{ text-align: right; }}
  table.items tbody td.amt {{ color: #0D1B2A; font-weight: 500; }}

  /* Totals */
  .totals-wrap {{ display: flex; justify-content: flex-end; padding: 16px 48px 32px; }}
  table.totals {{ border-collapse: collapse; min-width: 240px; font-size: 13px; }}
  table.totals td {{ padding: 6px 12px; }}
  .lbl {{ text-align: right; color: #6B7280; }}
  .val {{ text-align: right; color: #0D1B2A; font-weight: 500; }}
  tr.divider td {{ border-top: 1px solid #E5E7EB; padding-top: 10px; }}
  tr.total-row td {{
    background: #0D1B2A;
    color: #ffffff;
    font-weight: 600;
    font-size: 14px;
    padding: 12px 14px;
  }}
  tr.total-row td:first-child {{ text-align: right; border-radius: 4px 0 0 4px; }}
  tr.total-row td:last-child  {{ text-align: right; border-radius: 0 4px 4px 0; }}

  /* Payment + Notes */
  .pay-section, .notes-section {{
    margin: 0 48px 24px;
    padding: 18px 20px;
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
  }}
  .section-label {{
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #1F4D78;
    margin-bottom: 10px;
  }}
  table.pay-table {{ border-collapse: collapse; font-size: 13px; }}
  table.pay-table td {{ padding: 3px 20px 3px 0; color: #374151; }}
  table.pay-table td:first-child {{ color: #6B7280; width: 130px; }}
  .notes-body {{ font-size: 12.5px; color: #6B7280; line-height: 1.7; }}

  /* Footer */
  .footer {{
    border-top: 1px solid #E5E7EB;
    padding: 16px 48px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #F9FAFB;
    font-size: 11px;
    color: #9CA3AF;
  }}
  .footer strong {{ color: #374151; }}

  @page {{ margin: 0; size: A4; }}
  @media print {{
    html, body {{ background: white; padding: 0; margin: 0; }}
    .page {{ box-shadow: none; margin: 0; max-width: 100%; }}
    .print-btn {{ display: none !important; }}
  }}
  .print-btn {{
    position: fixed; bottom: 24px; right: 24px; z-index: 999;
  }}
  .print-btn button {{
    background: #1F4D78; color: #fff; border: none;
    padding: 11px 22px; font-family: 'Inter', sans-serif;
    font-size: 13px; font-weight: 500; cursor: pointer;
    border-radius: 4px; box-shadow: 0 4px 12px rgba(31,77,120,0.3);
  }}
  .print-btn button:hover {{ background: #0D1B2A; }}
</style>
</head>
<body>
<div class="print-btn"><button onclick="var w=window.open('','_blank');w.document.write(document.documentElement.outerHTML);w.document.close();w.focus();w.print();">Print / Save as PDF</button></div>
<div class="page">
  <div class="top-bar"></div>

  <div class="header">
    <img src="data:image/png;base64,{LOGO_B64}" class="logo" alt="Kingsleyhill">
    <div>
      <div class="inv-title">TAX INVOICE</div>
      <div class="inv-number">{invoice_number}</div>
    </div>
  </div>

  <div class="sender-strip">
    <span><strong>{sender_display}</strong></span>
    {f'<span>{my_address}</span>' if my_address else ''}
    {f'<span>ABN {my_abn}</span>' if my_abn else ''}
    {f'<span>{my_email}</span>' if my_email else ''}
  </div>

  <div class="meta">
    <div class="bill-to">
      <div class="meta-label">Bill To</div>
      <div class="client-name">{client_name}</div>
      {client_addr_html}
    </div>
    <div class="inv-meta-right">
      <table class="meta-table">
        <tr><td>Date</td><td>{inv_date}</td></tr>
        <tr><td>Due Date</td><td>{due_date_str}</td></tr>
        {period_row}
      </table>
    </div>
  </div>

  <div class="table-wrap">
    <table class="items">
      <thead>
        <tr>
          <th>{'#' if billing_type == 'fixed' else 'Date'}</th>
          <th>{'Description' if billing_type == 'fixed' else 'Project'}</th>
          <th>{'&nbsp;' if billing_type == 'fixed' else 'Description'}</th>
          <th class="num">{'Qty' if billing_type == 'fixed' else ('Days' if billing_type == 'day_rate' else 'Hours')}</th>
          <th class="num">{'Unit Price' if billing_type == 'fixed' else ('Day Rate' if billing_type == 'day_rate' else 'Rate')}</th>
          <th class="num">Amount</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>

  <div class="totals-wrap">
    <table class="totals">
      <tr><td class="lbl">Subtotal</td><td class="val">${subtotal:,.2f}</td></tr>
      {gst_row}
      <tr class="divider"><td colspan="2"></td></tr>
      <tr class="total-row"><td>Total Due (AUD)</td><td>${total:,.2f}</td></tr>
    </table>
  </div>

  {payment_section}
  {notes_section}

  <div class="footer">
    <span><strong>{sender_display}</strong> &nbsp;·&nbsp; Technology Consulting &amp; Professional Services</span>
    <span>Thank you for your business</span>
  </div>
</div>
</body>
</html>"""
    return html


# ── Init ─────────────────────────────────────────────────────────────────────

init_db()

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# Auto-timeout after 8 hours of inactivity
SESSION_TIMEOUT = 3600
if st.session_state.authenticated:
    last = st.session_state.get('last_activity', datetime.now().timestamp())
    if datetime.now().timestamp() - last > SESSION_TIMEOUT:
        st.session_state.authenticated = False
        st.session_state['last_activity'] = None
st.session_state['last_activity'] = datetime.now().timestamp()

if not st.session_state.authenticated:
    st.title("KingsleyHill System")
    pwd = st.text_input("Password", type="password")
    if st.button("Sign in"):
        try:
            correct = str(st.secrets["APP_PASSWORD"]).strip()
        except Exception:
            correct = ""
        if pwd.strip() == correct:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    st.stop()

st.markdown("""<style>
.stAppDeployButton { display: none !important; }
[data-testid="stAppDeployButton"] { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stHeader"] a { display: none !important; }
#MainMenu { display: none !important; }

/* ── Compact client list ── */
div.client-list [data-testid="stHorizontalBlock"] {
    margin-bottom: -0.75rem !important;
}

/* ── Mobile responsiveness ── */
@media (max-width: 640px) {
    /* Stack columns vertically on phones */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }
    [data-testid="column"] {
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }
    /* Prevent iOS auto-zoom on input focus */
    input, textarea, select {
        font-size: 16px !important;
    }
    /* Make tables scroll horizontally instead of overflowing */
    [data-testid="stDataFrame"] > div,
    [data-testid="stDataEditor"] > div {
        overflow-x: auto !important;
    }
    /* Full-width buttons in forms */
    .stButton > button {
        width: 100% !important;
    }
}
</style>""", unsafe_allow_html=True)

if 'page' not in st.session_state:
    st.session_state['page'] = 'home'

def go(page):
    st.session_state['page'] = page

def back_button():
    if st.button("← Back", key="back"):
        st.session_state['page'] = 'home'
        st.rerun()

page = st.session_state['page']

# ── Home ─────────────────────────────────────────────────────────────────────

if page == 'home':
    st.markdown("""<style>
    .stButton > button,
    [data-testid="stBaseButton-secondary"],
    [data-testid="stBaseButton-primary"],
    [data-testid="stButton"] > button {
        height: 160px !important;
        width: 160px !important;
        min-width: 160px !important;
        min-height: 160px !important;
        font-size: 5rem !important;
        padding: 0 !important;
        border-radius: 20px !important;
        line-height: 1 !important;
    }
    .stButton > button p,
    .stButton > button span,
    [data-testid="stBaseButton-secondary"] p,
    [data-testid="stBaseButton-primary"] p,
    [data-testid="stBaseButton-secondary"] span,
    [data-testid="stBaseButton-primary"] span {
        font-size: 5rem !important;
        line-height: 1 !important;
    }
    .stButton, [data-testid="stButton"] {
        display: flex !important;
        justify-content: center !important;
    }
    </style>""", unsafe_allow_html=True)

    company = get_setting('company') or get_setting('name') or 'Timesheet'
    st.title(company)
    st.write("")

    tiles = [
        ("🕐", "Log Time",   'log',        True),
        ("📊", "Dashboard",  'dashboard',  False),
        ("📋", "Timesheet",  'timesheet',  False),
        ("🧾", "Invoice",    'invoice',    False),
        ("👥", "Clients",    'clients',    False),
        ("📁", "Projects",   'projects',   False),
        ("👤", "Employees",  'employees',  False),
        ("💰", "Profitability", 'profitability', False),
        ("📄", "Statements", 'statements', False),
        ("⚙️", "Settings",  'settings',   False),
        ("🔒", "Log Out",    'logout',     False),
    ]

    cols = st.columns(len(tiles))
    for col, (icon, label, dest, primary) in zip(cols, tiles):
        with col:
            if st.button(icon, key=f"nav_{dest}", help=label,
                         type="primary" if primary else "secondary"):
                if dest == 'logout':
                    st.session_state.authenticated = False
                    st.session_state['page'] = 'home'
                    st.rerun()
                else:
                    go(dest); st.rerun()

# ── Log Time ─────────────────────────────────────────────────────────────────

if page == 'log':
    back_button()
    st.subheader("Log Time")

    saved_clients = get_clients_list()

    if saved_clients.empty:
        st.info("Add your clients in the **Clients** page first, then come back to log time.")
    else:
        client_names = saved_clients['name'].tolist()

        # Client search outside the form so it can react as you type
        search = st.text_input("Search client", placeholder="Type to find a client...")
        if search:
            matches = [c for c in client_names if search.lower() in c.lower()]
        else:
            matches = client_names

        if not matches:
            st.warning("No clients match your search.")
            selected_client = None
        else:
            selected_client = st.radio("Select client", matches, horizontal=True,
                                       label_visibility="collapsed")

        st.divider()

        if selected_client:
            st.markdown(f"**Client:** {selected_client}")

            # Employee and rate outside form so they react immediately
            emp_df      = get_employees()
            emp_options = emp_df['name'].tolist() if not emp_df.empty else []
            ec1, ec2    = st.columns(2)

            rate_default = float(get_setting('default_rate', '0') or 0)
            if not emp_options:
                st.warning("Add employees in the **Employees** page before logging time.")
                employee = ''
            else:
                employee = ec1.selectbox("Employee", emp_options, key="log_employee")
                emp_row = emp_df[emp_df['name'] == employee]
                emp_cost_rate = 0.0
                if not emp_row.empty:
                    if float(emp_row.iloc[0]['rate'] or 0) > 0:
                        rate_default = float(emp_row.iloc[0]['rate'])
                    emp_cost_rate = float(emp_row.iloc[0].get('cost_rate') or 0)

            # Force rate to update when employee changes by writing to session_state first
            if st.session_state.get('_log_employee_prev') != employee:
                st.session_state['log_rate_input'] = rate_default
                st.session_state['_log_employee_prev'] = employee

            rate = ec2.number_input("Hourly rate ($)", min_value=0.0, step=5.0,
                                    value=rate_default, key="log_rate_input")

            with st.form("log_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    entry_date = st.date_input("Date", value=date.today(), format="DD/MM/YYYY")
                    _cl_row    = saved_clients[saved_clients['name'] == selected_client]
                    _cl_id     = _cl_row.iloc[0]['id'] if not _cl_row.empty else None
                    proj_df    = get_projects_list(client_id=_cl_id) if _cl_id else get_projects_list()
                    if proj_df.empty:
                        st.warning("No projects for this client — add them in the **Projects** page.")
                        project = None
                    else:
                        proj_options = [f"{r['code']} — {r['name']}" if r['code'] else r['name']
                                        for _, r in proj_df.iterrows()]
                        proj_sel = st.selectbox("Project", proj_options)
                        idx      = proj_options.index(proj_sel)
                        project  = proj_df.iloc[idx]['name']
                with col2:
                    hours = st.number_input("Hours", min_value=0.25, max_value=24.0, step=0.25, value=1.0)

                description = st.text_area("Description", placeholder="What did you work on?")
                submitted   = st.form_submit_button("Save Entry", type="primary", use_container_width=True)

            if submitted:
                # Read rate from session state (outside-form widget)
                rate_used = st.session_state.get("log_rate_input", rate_default)
                if not project:
                    st.error("Set up projects in the Projects page before logging time.")
                elif not description:
                    st.error("Description is required.")
                elif hours <= 0:
                    st.error("Hours must be greater than 0.")
                else:
                    add_entry(entry_date, selected_client, project.strip(), description.strip(), hours, rate_used, employee, emp_cost_rate)
                    st.success(f"Saved {hours:.2f}h on {project} for {selected_client} — {employee}")

# ── Timesheet ─────────────────────────────────────────────────────────────────

if page == 'timesheet':
    back_button()
    st.subheader("Timesheet")

    clients  = get_clients()
    emp_df   = get_employees()
    emp_list = ['All'] + emp_df['name'].tolist() if not emp_df.empty else ['All']

    # ── Filters ──
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        filter_client = st.selectbox("Client", ['All'] + clients, key='ts_client')
    with col2:
        proj_list = get_projects(filter_client if filter_client != 'All' else None)
        filter_project = st.selectbox("Project", ['All'] + proj_list, key='ts_project')
    with col3:
        filter_employee = st.selectbox("Employee", emp_list, key='ts_employee')
    with col4:
        from_date = st.date_input("From", value=None, key='ts_from', format="DD/MM/YYYY")
    with col5:
        to_date = st.date_input("To", value=None, key='ts_to', format="DD/MM/YYYY")

    show_invoiced = st.checkbox("Show invoiced entries", value=False, key='ts_show_invoiced')

    df = load_entries(
        client    = filter_client   if filter_client   != 'All' else None,
        project   = filter_project  if filter_project  != 'All' else None,
        employee  = filter_employee if filter_employee != 'All' else None,
        from_date = from_date,
        to_date   = to_date,
    )

    if df.empty:
        st.info("No entries found.")
    else:
        df['amount'] = df['hours'].astype(float) * df['rate'].astype(float)
        if 'status' not in df.columns:
            df['status'] = 'open'
        df['status'] = df['status'].fillna('open')

        open_df      = df[df['status'] == 'open'].copy()
        submitted_df = df[df['status'] == 'submitted'].copy()
        approved_df  = df[df['status'] == 'approved'].copy()
        invoiced_df  = df[df['status'] == 'invoiced'].copy()

        billable_hours = df[df['status'].isin(['open', 'submitted', 'approved'])]['hours'].astype(float).sum()

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Open",          len(open_df))
        m2.metric("Submitted",     len(submitted_df))
        m3.metric("Approved",      len(approved_df))
        m4.metric("Invoiced",      len(invoiced_df))
        m5.metric("Billable Hrs",  f"{billable_hours:.2f}")

        st.divider()

        # ── Open — editable ──
        if not open_df.empty:
            st.markdown("**Open** — edit entries, tick to submit")
            open_df = open_df.reset_index(drop=True)
            edit_cols = ['entry_date','employee','client','project','description','hours','rate']
            open_display = open_df[edit_cols].rename(columns={
                'entry_date':'Date','employee':'Employee','client':'Client',
                'project':'Project','description':'Description','hours':'Hours','rate':'Rate ($)'
            })
            open_display.insert(0, 'Submit', False)
            edited = st.data_editor(
                open_display,
                use_container_width=True, hide_index=True, num_rows="fixed",
                column_config={
                    'Submit':      st.column_config.CheckboxColumn('Submit', default=False),
                    'Date':        st.column_config.DateColumn('Date', format='DD/MM/YYYY'),
                    'Hours':       st.column_config.NumberColumn('Hours', min_value=0.25, step=0.25, format="%.2f"),
                    'Rate ($)':    st.column_config.NumberColumn('Rate ($)', min_value=0, step=5.0, format="%.2f"),
                    'Employee':    st.column_config.TextColumn('Employee'),
                    'Client':      st.column_config.TextColumn('Client'),
                    'Project':     st.column_config.TextColumn('Project'),
                    'Description': st.column_config.TextColumn('Description'),
                },
                key="open_editor"
            )
            selected_open = open_df.iloc[edited[edited['Submit'] == True].index]['id'].tolist()

            bc1, bc2, bc3 = st.columns(3)
            if bc1.button("Save Changes", key="save_open"):
                con = get_conn()
                cur = con.cursor()
                ids = open_df['id'].tolist()
                for i, row in edited.iterrows():
                    if i < len(ids):
                        cur.execute("""
                            UPDATE entries SET entry_date=%s, employee=%s, client=%s, project=%s,
                            description=%s, hours=%s, rate=%s WHERE id=%s
                        """, [row['Date'], row['Employee'], row['Client'], row['Project'],
                              row['Description'], row['Hours'], row['Rate ($)'], ids[i]])
                cur.close()
                release_conn(con)
                st.cache_data.clear()
                st.success("Saved.")
                st.rerun()
            if bc2.button("Submit Selected", type="primary", key="submit_selected",
                          disabled=len(selected_open) == 0):
                set_status_bulk(selected_open, 'submitted')
                st.success(f"Submitted {len(selected_open)} {'entry' if len(selected_open)==1 else 'entries'}.")
                st.rerun()
            if bc3.button("Submit All", key="submit_open"):
                set_status_bulk(open_df['id'].tolist(), 'submitted')
                st.success("All marked as submitted.")
                st.rerun()

        # ── Submitted — awaiting approval ──
        if not submitted_df.empty:
            st.divider()
            st.markdown("**Submitted** — tick entries to approve or reject")
            submitted_df = submitted_df.reset_index(drop=True)
            sub_display = submitted_df[['entry_date','employee','client','project','description','hours','rate','amount']].copy()
            sub_display.columns = ['Date','Employee','Client','Project','Description','Hours','Rate ($)','Amount ($)']
            sub_display['Date'] = pd.to_datetime(sub_display['Date']).dt.strftime('%d/%m/%Y')
            sub_display.insert(0, 'Approve', False)
            edited_sub = st.data_editor(
                sub_display,
                use_container_width=True, hide_index=True,
                disabled=['Date','Employee','Client','Project','Description','Hours','Rate ($)','Amount ($)'],
                column_config={
                    'Approve':    st.column_config.CheckboxColumn('Approve', default=False),
                    'Amount ($)': st.column_config.NumberColumn(format='$%.2f'),
                    'Rate ($)':   st.column_config.NumberColumn(format='$%.2f'),
                },
                key="submitted_editor"
            )
            selected_sub = submitted_df.iloc[edited_sub[edited_sub['Approve'] == True].index]['id'].tolist()

            sc1, sc2, sc3 = st.columns(3)
            if sc1.button("Approve Selected", type="primary", key="approve_selected",
                          disabled=len(selected_sub) == 0):
                set_status_bulk(selected_sub, 'approved')
                st.success(f"Approved {len(selected_sub)} {'entry' if len(selected_sub)==1 else 'entries'}.")
                st.rerun()
            if sc2.button("Approve All", key="approve_all"):
                set_status_bulk(submitted_df['id'].tolist(), 'approved')
                st.success("All approved.")
                st.rerun()
            if sc3.button("Reject Selected", key="reject_selected",
                          disabled=len(selected_sub) == 0):
                set_status_bulk(selected_sub, 'open')
                st.success(f"Returned {len(selected_sub)} {'entry' if len(selected_sub)==1 else 'entries'} to open.")
                st.rerun()

        # ── Approved — ready to invoice ──
        if not approved_df.empty:
            st.divider()
            st.markdown("**Approved** — ready to invoice")
            app_display = approved_df[['entry_date','employee','client','project','description','hours','rate','amount']].copy()
            app_display.columns = ['Date','Employee','Client','Project','Description','Hours','Rate ($)','Amount ($)']
            app_display['Date'] = pd.to_datetime(app_display['Date']).dt.strftime('%d/%m/%Y')
            st.dataframe(app_display, use_container_width=True, hide_index=True)

            with st.expander("Unapprove entries"):
                ua_options = approved_df['id'].tolist()
                ua_selected = st.multiselect(
                    "Select entries to unapprove",
                    ua_options,
                    format_func=lambda i: approved_df[approved_df['id'] == i].apply(
                        lambda r: f"{pd.to_datetime(r['entry_date']).strftime('%d/%m/%Y')} | {r['client']} | {r['project']} | {r['hours']}h", axis=1
                    ).values[0],
                    key="unapprove_select"
                )
                uc1, uc2 = st.columns(2)
                if uc1.button("Unapprove Selected", key="unapprove_sel_btn", disabled=not ua_selected):
                    set_status_bulk(ua_selected, 'submitted')
                    st.success(f"Moved {len(ua_selected)} {'entry' if len(ua_selected)==1 else 'entries'} back to submitted.")
                    st.rerun()
                if uc2.button("Unapprove All", key="unapprove_all_btn"):
                    set_status_bulk(approved_df['id'].tolist(), 'submitted')
                    st.success("All approved entries moved back to submitted.")
                    st.rerun()

        # ── Invoiced ──
        if not invoiced_df.empty:
            if show_invoiced:
                st.divider()
                st.markdown("**Invoiced**")
                inv_display = invoiced_df[['entry_date','employee','client','project','description','hours','amount']].copy()
                inv_display.columns = ['Date','Employee','Client','Project','Description','Hours','Amount ($)']
                inv_display['Date'] = pd.to_datetime(inv_display['Date']).dt.strftime('%d/%m/%Y')
                st.dataframe(inv_display, use_container_width=True, hide_index=True)
            else:
                st.caption(f"__{len(invoiced_df)} invoiced {'entry' if len(invoiced_df)==1 else 'entries'} hidden — tick 'Show invoiced entries' to view__")

        st.divider()
        export_df = df[['entry_date','employee','client','project','description','hours','rate','amount','status']].copy()
        export_df.columns = ['Date','Employee','Client','Project','Description','Hours','Rate ($)','Amount ($)','Status']
        export_df['Date'] = pd.to_datetime(export_df['Date']).dt.strftime('%d/%m/%Y')
        csv = export_df.to_csv(index=False)
        st.download_button("Export to CSV", csv, "timesheet.csv", "text/csv")

        with st.expander("Delete an entry"):
            deletable = df[df['status'].isin(['open','submitted'])]
            if deletable.empty:
                st.info("Only open or submitted entries can be deleted.")
            else:
                delete_id = st.selectbox(
                    "Select entry",
                    deletable['id'].tolist(),
                    format_func=lambda i: deletable[deletable['id'] == i].apply(
                        lambda r: f"{r['entry_date']} | {r['client']} | {r['project']} | {r['hours']}h", axis=1
                    ).values[0]
                )
                if st.button("Delete", type="primary"):
                    delete_entry(delete_id)
                    st.success("Deleted.")
                    st.rerun()

# ── Invoice ───────────────────────────────────────────────────────────────────

if page == 'invoice':
    back_button()
    st.subheader("Generate Invoice")

    client_records = get_clients_list()

    if client_records.empty:
        st.info("Add your clients in the **Clients** page first so their details can be looked up.")
    else:
        # ── Ready to invoice summary ──
        all_approved = load_entries(status='approved')
        if not all_approved.empty:
            # Exclude internal (non-billable) clients from ready-to-invoice summary
            if 'billable' in client_records.columns:
                internal_names = client_records[client_records['billable'] == False]['name'].tolist()
                all_approved = all_approved[~all_approved['client'].isin(internal_names)]
            all_approved['amount'] = all_approved['hours'].astype(float) * all_approved['rate'].astype(float)
            pending_clients = (
                all_approved.groupby('client')
                .agg(entries=('id', 'count'), hours=('hours', 'sum'), amount=('amount', 'sum'))
                .reset_index()
            )
            st.caption(f"{len(pending_clients)} client{'s' if len(pending_clients) != 1 else ''} with approved entries ready to invoice")
            pcols = st.columns(min(max(len(pending_clients), 1), 4))
            for col, (_, row) in zip(pcols, pending_clients.iterrows()):
                with col:
                    if st.button(
                        f"**{row['client']}**\n{int(row['entries'])} entries · ${row['amount']:,.2f}",
                        use_container_width=True, key=f"pend_{row['client']}"
                    ):
                        st.session_state['inv_search'] = row['client']
                        st.rerun()
            st.divider()

        # Only show billable clients in invoice page
        billable_records = client_records[client_records.get('billable', True) != False] if 'billable' in client_records.columns else client_records
        client_names = billable_records['name'].tolist()

        # Pre-select client if arriving from Timesheet page
        _preset = st.session_state.pop('inv_preset_client', None)
        if _preset:
            st.session_state['inv_search'] = _preset

        # Client search
        inv_search = st.text_input("Search client", placeholder="Type to find a client...", key='inv_search')
        if inv_search:
            matches = [c for c in client_names if inv_search.lower() in c.lower()]
        else:
            matches = client_names

        if not matches:
            st.warning("No clients match your search.")
            inv_client = None
        else:
            inv_client = st.radio("Select client", matches, horizontal=True,
                                  label_visibility="collapsed", key='inv_client_radio')

        st.divider()

        if inv_client:
            matched = client_records[client_records['name'] == inv_client]
            prefill_address     = matched.iloc[0]['address'] if not matched.empty else ''
            _bt                 = matched.iloc[0]['billing_type'] if not matched.empty else 'hourly'
            client_billing_type = _bt if _bt in ('hourly', 'day_rate') else 'hourly'
            client_day_rate     = float(matched.iloc[0]['day_rate'] or 0) if not matched.empty else 0.0

            billing_label = 'Hourly' if client_billing_type != 'day_rate' else f'Day Rate (${client_day_rate:.2f}/day)'
            st.markdown(f"**Client:** {inv_client} &nbsp;·&nbsp; Default billing: **{billing_label}**")

            inv_mode = st.radio(
                "Invoice type",
                ['timesheet', 'fixed'],
                format_func=lambda x: 'Timesheet entries (approved only)' if x == 'timesheet' else 'Fixed price / ad hoc',
                horizontal=True,
                key='inv_mode',
            )

            st.divider()

            col1, col2 = st.columns(2)
            with col2:
                client_address = prefill_address
                if client_address:
                    st.markdown(f"**Client address**")
                    st.caption(client_address)
                else:
                    st.caption("No address on file — add it on the Clients page.")
                include_gst    = st.checkbox("Include GST (10%)", value=True)
                from datetime import timedelta
                _default_due   = date.today() + timedelta(days=14)
                inv_due_date   = st.date_input("Due date", value=_default_due, key='inv_due_date', format="DD/MM/YYYY")
            with col1:
                _days_to_fri   = (4 - date.today().weekday()) % 7 or 7
                _default_period = date.today() + timedelta(days=_days_to_fri)
                inv_period_end = st.date_input("Period ending", value=_default_period, key='inv_period_end', format="DD/MM/YYYY")

            if inv_mode == 'timesheet':
                # Warn about unapproved entries
                _unapproved = load_entries(client=inv_client, status=['open', 'submitted'])
                if not _unapproved.empty:
                    _hrs = _unapproved['hours'].astype(float).sum()
                    st.warning(f"⚠️ {len(_unapproved)} unapproved {'entry' if len(_unapproved)==1 else 'entries'} ({_hrs:.2f}h) not yet approved for {inv_client} — approve them in the Timesheet page before invoicing.")

                with col1:
                    inv_project = st.selectbox(
                        "Filter by project",
                        ['All'] + get_projects(inv_client),
                        key='inv_project'
                    )
                    inv_number = get_next_invoice_number()
                    st.markdown(f"**Invoice number:** {inv_number}")

                use_date_range = st.checkbox("Filter by date range", value=False)
                if use_date_range:
                    dc1, dc2 = st.columns(2)
                    inv_from = dc1.date_input("From date", key='inv_from', format="DD/MM/YYYY")
                    inv_to   = dc2.date_input("To date", value=date.today(), key='inv_to', format="DD/MM/YYYY")
                else:
                    inv_from = inv_to = None

                # ── Show approved entries ──
                available_df = load_entries(
                    client    = inv_client,
                    project   = inv_project if inv_project != 'All' else None,
                    from_date = inv_from,
                    to_date   = inv_to,
                    status    = 'approved',
                )

                if available_df.empty:
                    st.warning("No approved entries match the current filters. Approve entries on the Timesheet page first.")
                else:
                    available_df['amount'] = available_df['hours'].astype(float) * available_df['rate'].astype(float)

                    if client_billing_type == 'day_rate':
                        num_days    = len(available_df['entry_date'].unique())
                        avail_total = num_days * client_day_rate
                        st.success(f"{len(available_df)} approved entries across **{num_days} day{'s' if num_days != 1 else ''}** · **${avail_total:,.2f}** to invoice (day rate)")
                        show_cols = ['entry_date', 'employee', 'project', 'description', 'hours']
                        col_names = ['Date', 'Employee', 'Project', 'Description', 'Hours']
                    else:
                        avail_hours = available_df['hours'].astype(float).sum()
                        avail_total = available_df['amount'].sum()
                        st.success(f"{len(available_df)} approved entries · **{avail_hours:.2f} hrs** · **${avail_total:,.2f}** to invoice")
                        show_cols = ['entry_date', 'employee', 'project', 'description', 'hours', 'rate', 'amount']
                        col_names = ['Date', 'Employee', 'Project', 'Description', 'Hours', 'Rate ($)', 'Amount ($)']

                    disp = available_df[show_cols].copy()
                    disp.columns = col_names
                    st.dataframe(disp, use_container_width=True, hide_index=True)

                if not available_df.empty:
                    already_used_ts = invoice_number_exists(inv_number)
                    if already_used_ts:
                        st.warning(f"Invoice {inv_number} has already been recorded. Tick below to override.")
                        ts_override = st.checkbox("Override — regenerate this invoice", key="ts_override")
                    else:
                        ts_override = True

                    if ts_override and st.button("Generate Invoice", type="primary", key="gen_ts"):
                        inv_df = available_df
                        reserved_num = get_next_invoice_number()
                        increment_invoice_number()
                        settings_dict = {
                            'name': get_setting('name'), 'company': get_setting('company'),
                            'address': get_setting('address'), 'abn': get_setting('abn'),
                            'email': get_setting('email'),
                            'inv_client_name': inv_client, 'inv_client_address': client_address,
                        }
                        html = generate_invoice_html(
                            inv_df, settings_dict, reserved_num, include_gst,
                            payment_terms=get_setting('payment_terms', ''),
                            billing_type=client_billing_type, client_day_rate=client_day_rate,
                            due_date=inv_due_date, period_end=inv_period_end,
                        )
                        if client_billing_type == 'day_rate':
                            subtotal = len(inv_df['entry_date'].unique()) * client_day_rate
                        else:
                            subtotal = sum(float(r['hours']) * float(r['rate']) for _, r in inv_df.iterrows())
                        gst   = subtotal * 0.1 if include_gst else 0
                        total = subtotal + gst
                        st.session_state['generated_invoice'] = {
                            'html': html, 'ids': inv_df['id'].tolist(),
                            'client': inv_client, 'subtotal': subtotal, 'gst': gst, 'total': total,
                            'entries': len(inv_df), 'inv_number': reserved_num,
                            'is_timesheet': True, 'billing_type': client_billing_type,
                        }

            else:  # fixed price
                with col1:
                    inv_number = st.text_input("Invoice number", value=get_next_invoice_number(), key='inv_num_fp')

                fp_lines = load_adhoc_lines(inv_client)

                # ── Saved lines list ──
                if fp_lines:
                    lines_df = pd.DataFrame([
                        {
                            'Description':  l['description'],
                            'Qty':          float(l['qty']),
                            'Unit Price ($)': float(l['unit_price']),
                            'Amount ($)':   float(l['qty']) * float(l['unit_price']),
                        }
                        for l in fp_lines
                    ])
                    st.dataframe(lines_df, use_container_width=True, hide_index=True,
                                 column_config={
                                     'Qty':            st.column_config.NumberColumn(format='%.2f'),
                                     'Unit Price ($)': st.column_config.NumberColumn(format='$%.2f'),
                                     'Amount ($)':     st.column_config.NumberColumn(format='$%.2f'),
                                 })

                    fp_subtotal = sum(float(l['qty']) * float(l['unit_price']) for l in fp_lines)
                    fp_gst      = fp_subtotal * 0.1 if include_gst else 0
                    st.caption(f"Subtotal: ${fp_subtotal:,.2f}  ·  GST: ${fp_gst:,.2f}  ·  **Total: ${fp_subtotal + fp_gst:,.2f}**")

                    with st.expander("✏️ Edit a line"):
                        ed_idx = st.selectbox(
                            "Select line to edit",
                            range(len(fp_lines)),
                            format_func=lambda i: f"{i+1}. {fp_lines[i]['description']}",
                            key='edit_line_sel',
                        )
                        ed_line = fp_lines[ed_idx]
                        ed_desc  = st.text_input("Description", value=ed_line['description'], key=f'ed_desc_{ed_line["id"]}')
                        ec1, ec2 = st.columns(2)
                        ed_qty   = ec1.number_input("Quantity", min_value=0.0, step=1.0, value=float(ed_line['qty']), key=f'ed_qty_{ed_line["id"]}')
                        ed_price = ec2.number_input("Unit price ($)", min_value=0.0, step=100.0, value=float(ed_line['unit_price']), key=f'ed_price_{ed_line["id"]}')
                        if st.button("Save changes", key="save_edit_line", type="primary"):
                            if not ed_desc.strip():
                                st.error("Description is required.")
                            else:
                                update_adhoc_line(ed_line['id'], ed_desc.strip(), ed_qty, ed_price)
                                st.session_state.pop('generated_invoice', None)
                                st.rerun()

                    with st.expander("🗑️ Remove a line"):
                        rm_idx = st.selectbox(
                            "Select line to remove",
                            range(len(fp_lines)),
                            format_func=lambda i: f"{i+1}. {fp_lines[i]['description']}",
                        )
                        if st.button("Remove line", key="rm_line"):
                            delete_adhoc_line(fp_lines[rm_idx]['id'])
                            st.session_state.pop('generated_invoice', None)
                            st.rerun()

                    st.divider()

                # ── Add line form ──
                with st.form("add_line_form", clear_on_submit=True):
                    st.markdown("**Add a line item**")
                    new_desc = st.text_input("Description", placeholder="e.g. Website design, Project management…")
                    ac1, ac2 = st.columns(2)
                    new_qty   = ac1.number_input("Quantity", min_value=0.0, step=1.0, value=1.0)
                    new_price = ac2.number_input("Unit price ($)", min_value=0.0, step=100.0, value=0.0)
                    add_btn   = st.form_submit_button("+ Add Line", use_container_width=True)

                if add_btn:
                    if not new_desc.strip():
                        st.error("Description is required.")
                    else:
                        try:
                            add_adhoc_line(inv_client, new_desc.strip(), new_qty, new_price)
                            st.session_state.pop('generated_invoice', None)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to save line: {e}")

                if fp_lines:
                    already_used_fp = invoice_number_exists(inv_number)
                    if already_used_fp:
                        st.warning(f"Invoice {inv_number} has already been recorded. Tick below to override.")
                        fp_override = st.checkbox("Override — regenerate this invoice", key="fp_override")
                    else:
                        fp_override = True
                    gcol, clrcol = st.columns(2)
                    if fp_override and gcol.button("Generate Invoice", type="primary", key="gen_fp", use_container_width=True):
                        fp_reserved_num = inv_number.strip() or get_next_invoice_number()
                        settings_dict = {
                            'name': get_setting('name'), 'company': get_setting('company'),
                            'address': get_setting('address'), 'abn': get_setting('abn'),
                            'email': get_setting('email'),
                            'inv_client_name': inv_client, 'inv_client_address': client_address,
                        }
                        html = generate_invoice_html(
                            None, settings_dict, fp_reserved_num, include_gst,
                            payment_terms=get_setting('payment_terms', ''),
                            billing_type='fixed', adhoc_lines=fp_lines,
                            due_date=inv_due_date, period_end=inv_period_end,
                        )
                        subtotal = sum(float(l['qty']) * float(l['unit_price']) for l in fp_lines)
                        gst      = subtotal * 0.1 if include_gst else 0
                        total    = subtotal + gst
                        st.session_state['generated_invoice'] = {
                            'html': html, 'ids': [],
                            'client': inv_client, 'subtotal': subtotal, 'gst': gst, 'total': total,
                            'entries': len(fp_lines), 'inv_number': fp_reserved_num,
                            'is_timesheet': False, 'billing_type': 'fixed',
                        }
                    if clrcol.button("Clear all lines", key="clear_fp", use_container_width=True):
                        clear_adhoc_lines(inv_client)
                        st.session_state.pop('generated_invoice', None)
                        st.rerun()

            # ── Download / mark invoiced ──
            inv_data = st.session_state.get('generated_invoice')
            if inv_data and inv_data.get('client') == inv_client:
                st.success(f"Invoice {inv_data['inv_number']} — {inv_data['entries']} line{'s' if inv_data['entries'] != 1 else ''} — Total: ${inv_data['total']:,.2f}")
                st.caption("Open the downloaded file in your browser — a Print / Save as PDF button appears in the corner.")

                dl_col, mark_col = st.columns(2)
                with dl_col:
                    st.download_button(
                        "⬇ Download Invoice",
                        inv_data['html'],
                        f"{inv_data['inv_number']}.html",
                        "text/html",
                        type="primary",
                        use_container_width=True,
                    )
                with mark_col:
                    if inv_data.get('is_timesheet') and inv_data['ids']:
                        if st.button("✓ Mark entries as Invoiced", use_container_width=True, key="mark_invoiced"):
                            set_status_bulk(inv_data['ids'], 'invoiced')
                            save_invoice(inv_data['inv_number'], inv_data['client'],
                                         inv_data.get('subtotal', inv_data['total']),
                                         inv_data.get('gst', 0), inv_data['total'],
                                         inv_data.get('billing_type', 'hourly'), 'timesheet',
                                         html_content=inv_data.get('html', ''))
                            st.session_state.pop('generated_invoice', None)
                            go('statements')
                            st.rerun()
                    else:
                        _approved_entries = load_entries(client=inv_data['client'], status='approved')
                        if not _approved_entries.empty:
                            _ap_hrs = _approved_entries['hours'].astype(float).sum()
                            mark_approved = st.checkbox(
                                f"Also mark {len(_approved_entries)} approved timesheet {'entry' if len(_approved_entries)==1 else 'entries'} ({_ap_hrs:.2f}h) as invoiced",
                                value=False, key="fp_mark_approved"
                            )
                        else:
                            mark_approved = False
                        if st.button("✓ Record Invoice Sent", use_container_width=True, key="mark_fp_done"):
                            save_invoice(inv_data['inv_number'], inv_data['client'],
                                         inv_data.get('subtotal', inv_data['total']),
                                         inv_data.get('gst', 0), inv_data['total'],
                                         'fixed', 'fixed',
                                         html_content=inv_data.get('html', ''))
                            increment_invoice_number()
                            if mark_approved and not _approved_entries.empty:
                                set_status_bulk(_approved_entries['id'].tolist(), 'invoiced')
                            st.session_state.pop('generated_invoice', None)
                            clear_adhoc_lines(inv_data['client'])
                            go('statements')
                            st.rerun()

                with st.expander("Preview"):
                    st.components.v1.html(inv_data['html'], height=700, scrolling=True)

# ── Projects ──────────────────────────────────────────────────────────────────

if page == 'projects':
    back_button()
    st.subheader("Projects")

    proj_df      = get_projects_list()
    client_df    = get_clients_list()
    client_opts  = {row['id']: row['name'] for _, row in client_df.iterrows()}
    col_list, col_form = st.columns([1, 1])

    with col_form:
        st.markdown("**Add / Edit project**")
        editing = st.session_state.get('editing_project')

        if editing and not proj_df.empty:
            row = proj_df[proj_df['id'] == editing]
            if not row.empty:
                row = row.iloc[0]
                f_code, f_name = row['code'] or '', row['name'] or ''
                f_client_id    = row.get('client_id') or ''
            else:
                editing = None
                f_code = f_name = f_client_id = ''
        else:
            f_code = f_name = f_client_id = ''

        with st.form("proj_form", clear_on_submit=True):
            # Client selector
            cl_ids   = [''] + list(client_opts.keys())
            cl_names = ['— No client —'] + list(client_opts.values())
            cl_idx   = cl_ids.index(f_client_id) if f_client_id in cl_ids else 0
            p_client = st.selectbox("Client", cl_names, index=cl_idx)
            p_client_id = cl_ids[cl_names.index(p_client)]

            p_code = st.text_input("Project code", value=f_code, placeholder="e.g. P001")
            p_name = st.text_input("Project name", value=f_name, placeholder="e.g. Website Redesign")
            save_btn = st.form_submit_button("Save Project", type="primary", use_container_width=True)

        if save_btn:
            if not p_name:
                st.error("Project name is required.")
            else:
                save_project(editing, p_code.strip(), p_name.strip(), p_client_id or None)
                st.session_state.pop('editing_project', None)
                st.success(f"{'Updated' if editing else 'Saved'}: {p_name}")
                st.rerun()

        if editing and st.button("Cancel edit", key="cancel_proj"):
            st.session_state.pop('editing_project', None)
            st.rerun()

    with col_list:
        st.markdown("**Saved projects**")
        if proj_df.empty:
            st.info("No projects added yet.")
        else:
            # Group by client
            for cid, cname in [('', '— No client —')] + [(k, v) for k, v in client_opts.items()]:
                grp = proj_df[proj_df['client_id'] == cid] if cid else proj_df[proj_df['client_id'].isna() | (proj_df['client_id'] == '')]
                if grp.empty:
                    continue
                st.caption(cname)
                for _, row in grp.iterrows():
                    c1, c2, c3 = st.columns([3, 1, 1])
                    label = f"**{row['code']}** — {row['name']}" if row['code'] else f"**{row['name']}**"
                    c1.markdown(label)
                    if c2.button("Edit",   key=f"pedit_{row['id']}"):
                        st.session_state['editing_project'] = row['id']
                        st.rerun()
                    if c3.button("Delete", key=f"pdel_{row['id']}"):
                        delete_project(row['id'])
                        st.rerun()

# ── Clients ───────────────────────────────────────────────────────────────────

if page == 'clients':
    back_button()
    st.subheader("Clients")

    client_records = get_clients_list()

    col_list, col_form = st.columns([1, 1])

    with col_form:
        st.markdown("**Add / Edit client**")
        editing = st.session_state.get('editing_client')

        if editing:
            _match = client_records[client_records['id'] == editing]
            if _match.empty:
                editing = None
                st.session_state.pop('editing_client', None)
            else:
                row = _match.iloc[0]
                form_name         = row['name']
                form_address      = row['address'] or ''
                form_contact_name = row['contact_name'] or ''
                form_email        = row['email'] or ''
                _bt               = row.get('billing_type', 'hourly')
                form_billing_type = _bt if _bt in ('hourly', 'day_rate') else 'hourly'
                form_day_rate     = float(row.get('day_rate', 0) or 0)
                form_billable     = bool(row.get('billable', True))
        if not editing:
            form_name = form_address = form_contact_name = form_email = form_website = ''
            form_billing_type = 'hourly'
            form_day_rate     = 0.0
            form_billable     = True
        else:
            form_website = row.get('website', '') or ''

        # Force-load form fields from the appropriate source (runs once per trigger)
        if st.session_state.pop('cf_apply_fresh', False):
            _a = st.session_state.get('client_apply', {})
            st.session_state['cf_name']    = _a.get('name', '')
            st.session_state['cf_address'] = _a.get('address', '')
            st.session_state['cf_contact'] = ''
            st.session_state['cf_email']   = _a.get('email', '')
            st.session_state['cf_website'] = _a.get('website', '')
            st.session_state['cf_abn']     = _a.get('abn', '')
        elif st.session_state.pop('cf_edit_fresh', False):
            st.session_state['cf_name']    = form_name
            st.session_state['cf_address'] = form_address
            st.session_state['cf_contact'] = form_contact_name
            st.session_state['cf_email']   = form_email
            st.session_state['cf_website'] = form_website
        elif st.session_state.pop('cf_reset_fresh', False):
            st.session_state['cf_name']    = ''
            st.session_state['cf_address'] = ''
            st.session_state['cf_contact'] = ''
            st.session_state['cf_email']   = ''
            st.session_state['cf_website'] = ''

        # ── ABR Lookup ──
        _abr_guid = get_setting('abr_guid', '')
        if not _abr_guid:
            st.info("Add your free ABR GUID in **Settings** to enable business name lookup.")
        else:
            srch_col, btn_col = st.columns([3, 1], vertical_alignment="bottom")
            abr_query = srch_col.text_input("Search business name or ABN", key="abr_query",
                                            placeholder="e.g. Company or ABN")
            if btn_col.button("Search ABR", key="abr_search_btn", use_container_width=True):
                if abr_query.strip():
                    with st.spinner("Searching…"):
                        try:
                            results = abr_search(abr_query.strip(), _abr_guid)
                            st.session_state['abr_results'] = results
                            if not results:
                                st.warning("No active businesses found.")
                        except Exception as _e:
                            st.error(f"ABR error: {_e}")
                    st.rerun()
                else:
                    st.warning("Enter a business name or ABN.")

            abr_results = st.session_state.get('abr_results')
            if abr_results is not None:
                if abr_results:
                    st.markdown("**Select a business:**")
                    for i, r in enumerate(abr_results):
                        rc1, rc2, rc3 = st.columns([3, 1, 1])
                        rc1.write(f"**{r['name']}**")
                        rc2.caption(f"ABN {r['abn']}")
                        rc3.caption(f"{r['state']} {r['postcode']}")
                        if st.button("Select", key=f"abr_sel_{i}", use_container_width=True):
                            with st.spinner("Fetching details…"):
                                detail = abr_get_detail(r['abn'], _abr_guid)
                            apply = {
                                'name': detail.get('name') or r['name'],
                                'address': detail.get('address') or '',
                                'email': '',
                                'website': '',
                                'abn': r['abn'],
                            }
                            st.session_state['client_apply'] = apply
                            st.session_state['cf_apply_fresh'] = True
                            st.session_state.pop('abr_results', None)
                            st.rerun()
                else:
                    st.caption("No results.")
            st.divider()

        c_name    = st.text_input("Company name", key="cf_name", placeholder="e.g. Acme Corp")
        c_address = st.text_area("Address",       key="cf_address", height=80)
        c_contact = st.text_input("Contact name", key="cf_contact")
        c_email   = st.text_input("Email",        key="cf_email")
        c_website = st.text_input("Website",      key="cf_website")
        c_billable = st.checkbox("Billable client", value=form_billable,
                                 help="Uncheck for internal clients — time is tracked but excluded from invoices")
        with st.expander("Billing (advanced)"):
            c_billing = st.radio(
                "Billing type", ['hourly', 'day_rate'],
                format_func=lambda x: 'Hourly' if x == 'hourly' else 'Day Rate',
                index=0 if form_billing_type != 'day_rate' else 1,
                horizontal=True,
            )
            c_day_rate = st.number_input(
                "Day rate ($)", min_value=0.0, step=50.0, value=form_day_rate,
                help="Used when billing type is Day Rate",
            )
        save_btn = st.button("Save Client", type="primary", use_container_width=True)
        if save_btn:
            if not st.session_state.get('cf_name', '').strip():
                st.error("Company name is required.")
            else:
                save_client(editing,
                            st.session_state.get('cf_name', '').strip(),
                            st.session_state.get('cf_address', '').strip(),
                            st.session_state.get('cf_contact', '').strip(),
                            st.session_state.get('cf_email', '').strip(),
                            c_billing, c_day_rate,
                            st.session_state.get('cf_website', '').strip(),
                            c_billable)
                st.session_state.pop('editing_client', None)
                st.session_state.pop('client_lookup', None)
                st.session_state.pop('client_apply', None)
                st.session_state['cf_reset_fresh'] = True
                st.success(f"{'Updated' if editing else 'Saved'}: {st.session_state.get('cf_name','')}")
                st.rerun()

        if editing and st.button("Cancel edit", key="cf_cancel"):
            st.session_state.pop('editing_client', None)
            st.session_state.pop('client_apply', None)
            st.session_state['cf_reset_fresh'] = True
            st.rerun()

    with col_list:
        st.markdown("**Saved clients**")
        if client_records.empty:
            st.info("No clients saved yet.")
        else:
            st.markdown('<div class="client-list">', unsafe_allow_html=True)
            for _, row in client_records.iterrows():
                c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="center")
                is_billable = bool(row.get('billable', True))
                label = f"**{row['name']}**" + ("" if is_billable else " `Internal`")
                if row['contact_name']:
                    label += f"  \n<small>{row['contact_name']}</small>"
                c1.markdown(label, unsafe_allow_html=True)
                if c2.button("Edit", key=f"edit_{row['id']}"):
                    st.session_state['editing_client'] = row['id']
                    st.session_state.pop('client_apply', None)
                    st.session_state['cf_edit_fresh'] = True
                    st.rerun()
                if c3.button("Delete", key=f"del_{row['id']}"):
                    delete_client(row['id'])
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

# ── Employees ─────────────────────────────────────────────────────────────────

if page == 'employees':
    back_button()
    st.subheader("Employees")

    emp_tab1, emp_tab2 = st.tabs(["Manage Employees", "Import Timesheet"])

    with emp_tab1:
        emp_df = get_employees()
        col_list, col_form = st.columns([1, 1])

        with col_form:
            st.markdown("**Add / Edit employee**")
            editing = st.session_state.get('editing_employee')

            if editing and not emp_df.empty:
                row = emp_df[emp_df['id'] == editing]
                if not row.empty:
                    row = row.iloc[0]
                    f_name, f_email = row['name'], row['email'] or ''
                    f_role, f_rate  = row['role'] or '', float(row['rate'] or 0)
                    f_cost_rate     = float(row.get('cost_rate') or 0)
                else:
                    editing = None
                    f_name = f_email = f_role = ''
                    f_rate = f_cost_rate = 0.0
            else:
                f_name = f_email = f_role = ''
                f_rate = f_cost_rate = 0.0

            with st.form("emp_form", clear_on_submit=True):
                e_name  = st.text_input("Full name",  value=f_name)
                e_email = st.text_input("Email",      value=f_email)
                e_role  = st.text_input("Role / title", value=f_role)
                rc1, rc2 = st.columns(2)
                e_rate      = rc1.number_input("Billing rate ($/hr)", min_value=0.0, step=5.0, value=f_rate)
                e_cost_rate = rc2.number_input("Cost rate ($/hr)",    min_value=0.0, step=5.0, value=f_cost_rate)
                save_btn = st.form_submit_button("Save Employee", type="primary", use_container_width=True)

            if save_btn:
                if not e_name:
                    st.error("Name is required.")
                else:
                    save_employee(editing, e_name.strip(), e_email.strip(), e_role.strip(), e_rate, e_cost_rate)
                    st.session_state.pop('editing_employee', None)
                    st.success(f"{'Updated' if editing else 'Saved'}: {e_name}")
                    st.rerun()

            if editing and st.button("Cancel edit", key="cancel_emp"):
                st.session_state.pop('editing_employee', None)
                st.rerun()

        with col_list:
            st.markdown("**Saved employees**")
            if emp_df.empty:
                st.info("No employees added yet.")
            else:
                for _, row in emp_df.iterrows():
                    c1, c2, c3 = st.columns([3, 1, 1])
                    c1.write(f"**{row['name']}**")
                    if row['role']:
                        c1.caption(f"{row['role']} — ${float(row['rate'] or 0):.0f}/hr")
                    if c2.button("Edit", key=f"eedit_{row['id']}"):
                        st.session_state['editing_employee'] = row['id']
                        st.rerun()
                    if c3.button("Delete", key=f"edel_{row['id']}"):
                        delete_employee(row['id'])
                        st.rerun()

    with emp_tab2:
        st.markdown("**Import a timesheet CSV**")
        st.caption("CSV must have columns: date, project, description, hours (and optionally rate)")

        template_csv = "date,project,description,hours,rate\n2026-05-08,Project Name,Description of work,1.5,150.00\n"
        st.download_button("Download CSV Template", template_csv, "timesheet_template.csv", "text/csv")

        emp_df = get_employees()
        if emp_df.empty:
            st.info("Add employees first before importing.")
        else:
            client_records = get_clients_list()
            col1, col2 = st.columns(2)
            with col1:
                imp_employee = st.selectbox("Employee", emp_df['name'].tolist(), key='imp_emp')
            with col2:
                if not client_records.empty:
                    imp_client = st.selectbox("Client", client_records['name'].tolist(), key='imp_client')
                else:
                    imp_client = st.text_input("Client name", key='imp_client_txt')

            uploaded = st.file_uploader("Upload CSV", type="csv")

            if uploaded:
                try:
                    imp_df = pd.read_csv(uploaded)
                    imp_df.columns = [c.strip().lower() for c in imp_df.columns]

                    required = {'date', 'project', 'description', 'hours'}
                    if not required.issubset(set(imp_df.columns)):
                        st.error(f"CSV must contain columns: {', '.join(required)}")
                    else:
                        emp_row     = emp_df[emp_df['name'] == imp_employee].iloc[0]
                        default_rate = float(emp_row['rate'] or 0)

                        imp_df['date']        = pd.to_datetime(imp_df['date']).dt.date
                        imp_df['hours']       = pd.to_numeric(imp_df['hours'], errors='coerce').fillna(0)
                        imp_df['rate']        = pd.to_numeric(imp_df.get('rate', default_rate), errors='coerce').fillna(default_rate)
                        imp_df['description'] = imp_df['description'].astype(str)
                        imp_df['project']     = imp_df['project'].astype(str)

                        st.write(f"**Preview — {len(imp_df)} rows**")
                        st.dataframe(imp_df[['date','project','description','hours','rate']], use_container_width=True, hide_index=True)

                        if st.button("Import", type="primary"):
                            for _, row in imp_df.iterrows():
                                add_entry(row['date'], imp_client, row['project'],
                                          row['description'], float(row['hours']),
                                          float(row['rate']), imp_employee)
                            st.success(f"Imported {len(imp_df)} entries for {imp_employee}")
                except Exception as e:
                    st.error(f"Could not read CSV: {e}")

# ── Settings ──────────────────────────────────────────────────────────────────

if page == 'settings':
    back_button()
    st.subheader("Settings")

    if 'settings_unlocked' not in st.session_state:
        st.session_state.settings_unlocked = False

    if not st.session_state.settings_unlocked:
        st.info("Settings are password protected.")
        spwd = st.text_input("Password", type="password", key="settings_pwd")
        if st.button("Unlock", type="primary"):
            try:
                correct = str(st.secrets["SETTINGS_PASSWORD"]).strip()
            except Exception:
                correct = ""
            if spwd.strip() == correct:
                st.session_state.settings_unlocked = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.stop()

    st.caption("These appear on every invoice you generate.")

    with st.form("settings_form"):
        name         = st.text_input("Your name",     value=get_setting('name'))
        company      = st.text_input("Company name",  value=get_setting('company'))
        address      = st.text_area("Address",        value=get_setting('address'), height=80)
        abn          = st.text_input("ABN",           value=get_setting('abn'))
        email        = st.text_input("Email",         value=get_setting('email'))
        default_rate = st.number_input(
            "Default hourly rate ($)",
            min_value=0.0, step=5.0,
            value=float(get_setting('default_rate', '0') or 0)
        )
        payment_terms = st.text_area(
            "Payment terms / notes",
            value=get_setting('payment_terms', 'Payment due within 14 days of invoice date.\nPlease reference the invoice number with your payment.'),
            height=100
        )

        st.divider()
        st.markdown("**Payment / Bank Details**")
        st.caption("Shown on every invoice in the payment details section.")
        bc1, bc2 = st.columns(2)
        bank_name      = bc1.text_input("Bank name",       value=get_setting('bank_name', ''))
        account_name   = bc2.text_input("Account name",    value=get_setting('account_name', ''))
        bc3, bc4 = st.columns(2)
        bsb            = bc3.text_input("BSB",             value=get_setting('bsb', ''))
        account_number = bc4.text_input("Account number",  value=get_setting('account_number', ''))

        st.divider()
        st.markdown("**ABR Business Lookup**")
        abr_guid = st.text_input(
            "ABR GUID",
            value=get_setting('abr_guid', ''),
            help="Free GUID from abr.business.gov.au/Tools/WebServices — enables business name search on the Clients page",
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        )

        st.divider()
        st.markdown("**Invoice numbering**")
        _fmt = get_setting('inv_format', 'date') or 'date'
        inv_format = st.radio(
            "Format",
            ['date', 'sequential'],
            format_func=lambda x: 'Date-based  (e.g. INV-20260508)' if x == 'date' else 'Sequential  (e.g. INV-001)',
            index=0 if _fmt != 'sequential' else 1,
            horizontal=True,
        )
        fc1, fc2 = st.columns(2)
        with fc1:
            inv_prefix = fc1.text_input(
                "Prefix", value=get_setting('inv_prefix', 'INV') or 'INV',
                help="Letters before the number, e.g. INV or KH"
            )
        with fc2:
            inv_next_num = fc2.number_input(
                "Next sequential number", min_value=1, step=1,
                value=int(get_setting('inv_next_num', '1') or 1),
                help="Only used when format is Sequential"
            )

        saved = st.form_submit_button("Save Settings", type="primary")

    if saved:
        for key, val in [
            ('name', name), ('company', company), ('address', address),
            ('abn', abn), ('email', email), ('default_rate', str(default_rate)),
            ('payment_terms', payment_terms),
            ('inv_format', inv_format), ('inv_prefix', inv_prefix),
            ('inv_next_num', str(int(inv_next_num))),
            ('abr_guid', abr_guid),
            ('bank_name', bank_name), ('account_name', account_name),
            ('bsb', bsb), ('account_number', account_number),
        ]:
            save_setting(key, val)
        st.success("Settings saved.")

    st.divider()
    st.caption(f"Next invoice number will be: **{get_next_invoice_number()}**")


    st.divider()
    st.markdown("**Danger Zone**")
    with st.expander("Clear data"):
        st.warning("This permanently deletes data. It cannot be undone.")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            if st.button("Delete all time entries", use_container_width=True):
                st.session_state['confirm_clear'] = 'entries'
                st.rerun()
        with col_b:
            if st.button("Delete all invoices", use_container_width=True):
                st.session_state['confirm_clear'] = 'invoices'
                st.rerun()
        with col_c:
            if st.button("Delete everything", type="primary", use_container_width=True):
                st.session_state['confirm_clear'] = 'all'
                st.rerun()

        confirm = st.session_state.get('confirm_clear')
        if confirm:
            labels = {'entries': 'all time entries', 'invoices': 'all invoices', 'all': 'all time entries AND invoices'}
            st.error(f"Are you sure you want to delete {labels[confirm]}?")
            yes, no = st.columns(2)
            if yes.button("Yes, delete", type="primary", use_container_width=True):
                con = get_conn()
                cur = con.cursor()
                if confirm in ('entries', 'all'):
                    cur.execute("DELETE FROM entries")
                if confirm in ('invoices', 'all'):
                    cur.execute("DELETE FROM invoices")
                cur.close()
                release_conn(con)
                st.cache_data.clear()
                st.session_state.pop('confirm_clear', None)
                st.success("Done.")
                st.rerun()
            if no.button("Cancel", use_container_width=True):
                st.session_state.pop('confirm_clear', None)
                st.rerun()

# ── Statements ────────────────────────────────────────────────────────────────

if page == 'statements':
    back_button()
    st.subheader("Statements")

    inv_df = get_invoices()

    if inv_df.empty:
        st.info("No invoices recorded yet. Invoices appear here once you click 'Mark as Invoiced' on the Invoice page.")
    else:
        inv_df['subtotal']  = inv_df['subtotal'].astype(float)
        inv_df['gst']       = inv_df['gst'].astype(float)
        inv_df['total']     = inv_df['total'].astype(float)
        inv_df['paid']      = inv_df['paid'].astype(bool)

        total_billed      = inv_df['total'].sum()
        total_paid        = inv_df[inv_df['paid']]['total'].sum()
        total_outstanding = total_billed - total_paid

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Invoices Raised",  len(inv_df))
        m2.metric("Total Billed",     f"${total_billed:,.2f}")
        m3.metric("Received",         f"${total_paid:,.2f}")
        m4.metric("Outstanding",      f"${total_outstanding:,.2f}")

        st.divider()

        # Filters
        fa, fb, fc, fd = st.columns([2, 1.5, 1.5, 2])
        all_clients = ['All'] + sorted(inv_df['client'].dropna().unique().tolist())
        filter_client = fa.selectbox("Client", all_clients, key='stmt_client')

        inv_df['invoice_date'] = pd.to_datetime(inv_df['invoice_date'])
        months = sorted(inv_df['invoice_date'].dt.to_period('M').astype(str).unique(), reverse=True)
        filter_month = fb.selectbox("Month", ['All'] + months, key='stmt_month')

        filter_from = fc.date_input("From date", value=None, key='stmt_from', format="DD/MM/YYYY")
        filter_to   = fd.date_input("To date",   value=None, key='stmt_to', format="DD/MM/YYYY")

        inv_search = st.text_input("Search invoice number", placeholder="e.g. INV-002", key='stmt_search')

        view_df = inv_df.copy()
        if filter_client != 'All':
            view_df = view_df[view_df['client'] == filter_client]
        if filter_month != 'All':
            view_df = view_df[view_df['invoice_date'].dt.to_period('M').astype(str) == filter_month]
        if filter_from:
            view_df = view_df[view_df['invoice_date'] >= pd.Timestamp(filter_from)]
        if filter_to:
            view_df = view_df[view_df['invoice_date'] <= pd.Timestamp(filter_to)]
        if inv_search.strip():
            view_df = view_df[view_df['invoice_number'].str.contains(inv_search.strip(), case=False, na=False)]

        st.write("")

        # ── Outstanding ────────────────────────────────────────────────────────
        outstanding = view_df[~view_df['paid']].sort_values('invoice_date', ascending=False)
        if outstanding.empty:
            st.success("All invoices are paid.")
        else:
            outstanding_total = outstanding['total'].sum()
            st.markdown(
                f"**Outstanding** &nbsp;"
                f"<span style='font-size:0.85rem;color:#888'>"
                f"{len(outstanding)} invoice{'s' if len(outstanding)!=1 else ''} · "
                f"${outstanding_total:,.2f}</span>",
                unsafe_allow_html=True,
            )

            # Column headers
            h1, h2, h3, h4, h5, h6, h7 = st.columns([1.6, 2.0, 1.3, 1.1, 1.5, 1.4, 1.6])
            h1.caption("Invoice #")
            h2.caption("Client")
            h3.caption("Date")
            h4.caption("Age")
            h5.caption("Amount")
            h6.caption("")
            h7.caption("")

            for _, row in outstanding.iterrows():
                inv_date = pd.to_datetime(row['invoice_date'])
                days = (date.today() - inv_date.date()).days
                if days > 60:
                    age_str = f"🔴 {days}d"
                elif days > 30:
                    age_str = f"🟡 {days}d"
                else:
                    age_str = f"{days}d"

                c1, c2, c3, c4, c5, c6, c7 = st.columns([1.6, 2.0, 1.3, 1.1, 1.5, 1.4, 1.6])
                c1.write(f"**{row['invoice_number']}**")
                c2.write(row['client'])
                c3.write(inv_date.strftime('%d/%m/%Y'))
                c4.write(age_str)
                c5.write(f"**${float(row['total']):,.2f}**")
                _html = str(row.get('html_content') or '')
                if _html:
                    c6.download_button("⬇ Reprint", _html.encode('utf-8'), f"{row['invoice_number']}.html", "text/html",
                                       key=f"reprint_{row['id']}", use_container_width=True)
                if c7.button("✓ Mark Paid", key=f"paid_{row['id']}", type="primary", use_container_width=True):
                    mark_invoice_paid(row['id'], paid=True)
                    st.rerun()
                _desc = str(row.get('description') or '')
                edit_key = f"edit_desc_{row['id']}"
                if _desc:
                    st.caption(f"📝 {_desc}")
                if st.button("✏ Edit description", key=f"btn_{edit_key}", use_container_width=False):
                    st.session_state[edit_key] = True
                if st.session_state.get(edit_key):
                    new_desc = st.text_input("Description", value=_desc, key=f"inp_{edit_key}")
                    if st.button("Save", key=f"save_{edit_key}"):
                        update_invoice_description(row['id'], new_desc.strip())
                        st.session_state.pop(edit_key, None)
                        st.rerun()

            st.write("")

        # ── Paid ───────────────────────────────────────────────────────────────
        paid = view_df[view_df['paid']].sort_values('paid_date', ascending=False)
        if not paid.empty:
            paid_total = paid['total'].sum()
            with st.expander(
                f"✅ Paid — {len(paid)} invoice{'s' if len(paid)!=1 else ''} · ${paid_total:,.2f}"
            ):
                h1, h2, h3, h4, h5, h6, h7 = st.columns([1.6, 2.0, 1.3, 1.3, 1.4, 1.4, 1.4])
                h1.caption("Invoice #")
                h2.caption("Client")
                h3.caption("Invoiced")
                h4.caption("Paid on")
                h5.caption("Amount")
                h6.caption("")
                h7.caption("")

                for _, row in paid.iterrows():
                    c1, c2, c3, c4, c5, c6, c7 = st.columns([1.6, 2.0, 1.3, 1.3, 1.4, 1.4, 1.4])
                    c1.write(f"**{row['invoice_number']}**")
                    c2.write(row['client'])
                    c3.write(pd.to_datetime(row['invoice_date']).strftime('%d/%m/%Y'))
                    paid_on = pd.to_datetime(row['paid_date']).strftime('%d/%m/%Y') if pd.notna(row['paid_date']) else '—'
                    c4.write(paid_on)
                    c5.write(f"${float(row['total']):,.2f}")
                    _html = str(row.get('html_content') or '')
                    if _html:
                        c6.download_button("⬇ Reprint", _html.encode('utf-8'), f"{row['invoice_number']}.html", "text/html",
                                           key=f"reprint_{row['id']}", use_container_width=True)
                    if c7.button("Undo", key=f"unpaid_{row['id']}", use_container_width=True):
                        mark_invoice_paid(row['id'], paid=False)
                        st.rerun()
                    _desc = str(row.get('description') or '')
                    edit_key = f"edit_desc_{row['id']}"
                    if _desc:
                        st.caption(f"📝 {_desc}")
                    if st.button("✏ Edit description", key=f"btn_{edit_key}", use_container_width=False):
                        st.session_state[edit_key] = True
                    if st.session_state.get(edit_key):
                        new_desc = st.text_input("Description", value=_desc, key=f"inp_{edit_key}")
                        if st.button("Save", key=f"save_{edit_key}"):
                            update_invoice_description(row['id'], new_desc.strip())
                            st.session_state.pop(edit_key, None)
                            st.rerun()

        # ── Export ─────────────────────────────────────────────────────────────
        st.divider()
        export = view_df[['invoice_number','client','invoice_date','invoice_type','subtotal','gst','total','paid','paid_date']].copy()
        export.columns = ['Invoice #','Client','Date','Type','Subtotal','GST','Total','Paid','Paid Date']
        st.download_button("⬇ Export to CSV", export.to_csv(index=False), "statements.csv", "text/csv")

# ── Profitability ─────────────────────────────────────────────────────────────

if page == 'profitability':
    back_button()
    st.subheader("Project Profitability")

    con = get_conn()
    entries_df = pd.read_sql("""
        SELECT client, project, employee,
               SUM(hours) AS hours,
               SUM(hours * rate) AS revenue,
               SUM(hours * cost_rate) AS cost
        FROM entries
        WHERE status != 'open' OR status IS NULL
        GROUP BY client, project, employee
        ORDER BY client, project
    """, con)

    invoices_df = pd.read_sql("""
        SELECT client, SUM(total) AS invoiced
        FROM invoices
        GROUP BY client
    """, con)
    release_conn(con)

    if entries_df.empty:
        st.info("No time entries found. Log time and mark entries as submitted to see profitability.")
    else:
        entries_df['hours']   = entries_df['hours'].astype(float)
        entries_df['revenue'] = entries_df['revenue'].astype(float)
        entries_df['cost']    = entries_df['cost'].astype(float)
        entries_df['margin']  = entries_df['revenue'] - entries_df['cost']

        # ── By Client ──────────────────────────────────────────────────────────
        st.markdown("#### By Client")
        client_summary = entries_df.groupby('client').agg(
            Hours=('hours', 'sum'),
            Revenue=('revenue', 'sum'),
            Cost=('cost', 'sum'),
            Margin=('margin', 'sum'),
        ).reset_index()
        client_summary['Margin %'] = (client_summary['Margin'] / client_summary['Revenue'].replace(0, 1) * 100).round(1)

        h1, h2, h3, h4, h5, h6 = st.columns([2.5, 1.2, 1.5, 1.5, 1.5, 1.2])
        h1.caption("Client"); h2.caption("Hours"); h3.caption("Revenue"); h4.caption("Cost"); h5.caption("Margin"); h6.caption("Margin %")

        for _, row in client_summary.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([2.5, 1.2, 1.5, 1.5, 1.5, 1.2])
            c1.write(f"**{row['client']}**")
            c2.write(f"{row['Hours']:.1f}h")
            c3.write(f"${row['Revenue']:,.2f}")
            c4.write(f"${row['Cost']:,.2f}")
            margin_color = "green" if row['Margin'] >= 0 else "red"
            c5.markdown(f"<span style='color:{margin_color}'>**${row['Margin']:,.2f}**</span>", unsafe_allow_html=True)
            c6.write(f"{row['Margin %']}%")

        st.divider()

        # ── By Project ─────────────────────────────────────────────────────────
        st.markdown("#### By Project")
        project_summary = entries_df.groupby(['client', 'project']).agg(
            Hours=('hours', 'sum'),
            Revenue=('revenue', 'sum'),
            Cost=('cost', 'sum'),
            Margin=('margin', 'sum'),
        ).reset_index()
        project_summary['Margin %'] = (project_summary['Margin'] / project_summary['Revenue'].replace(0, 1) * 100).round(1)

        filter_client = st.selectbox("Filter by client", ['All'] + sorted(project_summary['client'].unique().tolist()), key='prof_client')
        if filter_client != 'All':
            project_summary = project_summary[project_summary['client'] == filter_client]

        h1, h2, h3, h4, h5, h6, h7 = st.columns([2, 2, 1.2, 1.5, 1.5, 1.5, 1.2])
        h1.caption("Client"); h2.caption("Project"); h3.caption("Hours"); h4.caption("Revenue"); h5.caption("Cost"); h6.caption("Margin"); h7.caption("Margin %")

        for _, row in project_summary.iterrows():
            c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 2, 1.2, 1.5, 1.5, 1.5, 1.2])
            c1.write(row['client'])
            c2.write(f"**{row['project']}**")
            c3.write(f"{row['Hours']:.1f}h")
            c4.write(f"${row['Revenue']:,.2f}")
            c5.write(f"${row['Cost']:,.2f}")
            margin_color = "green" if row['Margin'] >= 0 else "red"
            c6.markdown(f"<span style='color:{margin_color}'>**${row['Margin']:,.2f}**</span>", unsafe_allow_html=True)
            c7.write(f"{row['Margin %']}%")

        st.divider()
        st.download_button(
            "⬇ Export to CSV",
            project_summary.to_csv(index=False),
            "profitability.csv", "text/csv"
        )

# ── Dashboard ─────────────────────────────────────────────────────────────────

if page == 'dashboard':
    back_button()
    st.subheader("Dashboard")

    revenue, hours_df, unpaid_df, top_clients_df = get_dashboard_data()
    total_invoiced, paid, outstanding = float(revenue[0]), float(revenue[1]), float(revenue[2])
    month_label = date.today().strftime('%B %Y')

    # Split hours into billable vs internal
    all_clients_df = get_clients_list()
    internal_names = []
    if 'billable' in all_clients_df.columns:
        internal_names = all_clients_df[all_clients_df['billable'] == False]['name'].tolist()
    billable_hours_df = hours_df[~hours_df['client'].isin(internal_names)] if not hours_df.empty else hours_df
    internal_hours_df = hours_df[hours_df['client'].isin(internal_names)] if not hours_df.empty else pd.DataFrame()

    # ── This month ──
    st.markdown(f"#### {month_label}")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Invoiced",       f"${total_invoiced:,.0f}")
    m2.metric("Paid",           f"${paid:,.0f}")
    m3.metric("Outstanding",    f"${outstanding:,.0f}")
    m4.metric("Billable Hours", f"{billable_hours_df['hours'].sum():.1f}h" if not billable_hours_df.empty else "0h")
    m5.metric("Internal Hours", f"{internal_hours_df['hours'].sum():.1f}h" if not internal_hours_df.empty else "0h")

    # ── Hours by client this month ──
    import altair as alt
    if not billable_hours_df.empty:
        st.divider()
        st.markdown("#### Billable Hours by Client — This Month")
        chart = alt.Chart(billable_hours_df).mark_bar().encode(
            x=alt.X('client:N', sort='-y', title=None),
            y=alt.Y('hours:Q', title='Hours'),
            color=alt.Color('client:N', legend=None),
            tooltip=['client', 'hours']
        ).properties(height=300)
        st.altair_chart(chart, use_container_width=True)

    if not internal_hours_df.empty:
        st.markdown("#### Internal Hours by Client — This Month")
        chart = alt.Chart(internal_hours_df).mark_bar(color='#9E9E9E').encode(
            x=alt.X('client:N', sort='-y', title=None),
            y=alt.Y('hours:Q', title='Hours'),
            tooltip=['client', 'hours']
        ).properties(height=300)
        st.altair_chart(chart, use_container_width=True)

    # ── Unpaid invoices ──
    st.divider()
    st.markdown("#### Unpaid Invoices")
    if unpaid_df.empty:
        st.success("No outstanding invoices.")
    else:
        total_owed = unpaid_df['total'].sum()
        st.caption(f"{len(unpaid_df)} invoice{'s' if len(unpaid_df)>1 else ''} — **${float(total_owed):,.2f}** total outstanding")
        display = unpaid_df.copy()
        display['invoice_date'] = pd.to_datetime(display['invoice_date']).dt.strftime('%d/%m/%Y')
        display['total'] = display['total'].apply(lambda x: f"${float(x):,.2f}")
        display.columns = ['Client', 'Invoice #', 'Date', 'Amount']
        st.dataframe(display, use_container_width=True, hide_index=True)

    # ── Top clients last 3 months ──
    if not top_clients_df.empty:
        st.divider()
        st.markdown("#### Top Clients — Last 3 Months")
        chart = alt.Chart(top_clients_df).mark_bar().encode(
            x=alt.X('client:N', sort='-y', title=None),
            y=alt.Y('revenue:Q', title='Revenue ($)'),
            color=alt.Color('client:N', legend=None),
            tooltip=['client', 'revenue']
        ).properties(height=300)
        st.altair_chart(chart, use_container_width=True)
