import streamlit as st
import duckdb
import pandas as pd
import uuid
import re
import os
from datetime import date, datetime

st.set_page_config(page_title="Timesheet", page_icon="🕐", layout="wide")

try:
    _md_token = st.secrets.get("MOTHERDUCK_TOKEN", "").replace('\n', '').replace('\r', '').replace(' ', '').strip()
except Exception:
    _md_token = os.environ.get('MOTHERDUCK_TOKEN', '').strip()

if _md_token:
    DB_PATH = f"md:timesheet?motherduck_token={_md_token}"
else:
    DB_PATH = "timesheet.duckdb"


def init_db():
    con = duckdb.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id VARCHAR PRIMARY KEY,
            entry_date DATE,
            client VARCHAR,
            project VARCHAR,
            description VARCHAR,
            hours DECIMAL(6,2),
            rate DECIMAL(8,2)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key VARCHAR PRIMARY KEY,
            value VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id VARCHAR PRIMARY KEY,
            name VARCHAR,
            address VARCHAR,
            contact_name VARCHAR,
            email VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id VARCHAR PRIMARY KEY,
            name VARCHAR,
            email VARCHAR,
            role VARCHAR,
            rate DECIMAL(8,2)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id   VARCHAR PRIMARY KEY,
            code VARCHAR,
            name VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id            VARCHAR PRIMARY KEY,
            invoice_number VARCHAR,
            client        VARCHAR,
            invoice_date  DATE,
            subtotal      DECIMAL(10,2),
            gst           DECIMAL(10,2),
            total         DECIMAL(10,2),
            billing_type  VARCHAR DEFAULT 'hourly',
            invoice_type  VARCHAR DEFAULT 'timesheet',
            paid          BOOLEAN DEFAULT FALSE,
            paid_date     DATE
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS adhoc_draft_lines (
            id          VARCHAR PRIMARY KEY,
            client      VARCHAR,
            description VARCHAR,
            qty         DECIMAL(8,2),
            unit_price  DECIMAL(10,2),
            sort_order  INTEGER DEFAULT 0
        )
    """)
    # Migrations
    for col in [
        "ALTER TABLE entries ADD COLUMN employee VARCHAR DEFAULT 'Self'",
        "ALTER TABLE entries ADD COLUMN status VARCHAR DEFAULT 'open'",
        "ALTER TABLE clients ADD COLUMN billing_type VARCHAR DEFAULT 'hourly'",
        "ALTER TABLE clients ADD COLUMN day_rate DECIMAL(8,2) DEFAULT 0",
        "ALTER TABLE clients ADD COLUMN website VARCHAR",
        "ALTER TABLE clients ADD COLUMN abn VARCHAR",
        "ALTER TABLE projects ADD COLUMN client_id VARCHAR",
        "ALTER TABLE clients ADD COLUMN billable BOOLEAN DEFAULT TRUE",
    ]:
        try:
            con.execute(col)
        except Exception:
            pass
    # Migrate old submitted boolean → status
    try:
        con.execute("UPDATE entries SET status='submitted' WHERE submitted=true AND status='open'")
    except Exception:
        pass
    # Rename old client name
    try:
        con.execute("UPDATE entries SET client='Airnavigator Group' WHERE client='airnavigator.com'")
    except Exception:
        pass
    con.close()


@st.cache_data(ttl=60)
def get_employees():
    con = duckdb.connect(DB_PATH)
    df = con.execute("SELECT * FROM employees ORDER BY name").df()
    con.close()
    return df.copy()


def save_employee(emp_id, name, email, role, rate):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    if emp_id:
        con.execute(
            "UPDATE employees SET name=?, email=?, role=?, rate=? WHERE id=?",
            [name, email, role, rate, emp_id]
        )
    else:
        con.execute(
            "INSERT INTO employees VALUES (?, ?, ?, ?, ?)",
            [str(uuid.uuid4()), name, email, role, rate]
        )
    con.close()


def delete_employee(emp_id):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    con.execute("DELETE FROM employees WHERE id = ?", [emp_id])
    con.close()


@st.cache_data(ttl=60)
def get_clients_list():
    con = duckdb.connect(DB_PATH)
    df = con.execute("SELECT * FROM clients ORDER BY name").df()
    con.close()
    return df.copy()


def save_client(client_id, name, address, contact_name, email, billing_type='hourly', day_rate=0, website='', billable=True):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    if client_id:
        con.execute(
            "UPDATE clients SET name=?, address=?, contact_name=?, email=?, billing_type=?, day_rate=?, website=?, billable=? WHERE id=?",
            [name, address, contact_name, email, billing_type, day_rate, website, billable, client_id]
        )
    else:
        con.execute(
            "INSERT INTO clients (id,name,address,contact_name,email,billing_type,day_rate,website,billable) VALUES (?,?,?,?,?,?,?,?,?)",
            [str(uuid.uuid4()), name, address, contact_name, email, billing_type, day_rate, website, billable]
        )
    con.close()


def delete_client(client_id):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    con.execute("DELETE FROM clients WHERE id = ?", [client_id])
    con.close()


@st.cache_data(ttl=60)
def get_setting(key, default=''):
    con = duckdb.connect(DB_PATH)
    row = con.execute("SELECT value FROM settings WHERE key = ?", [key]).fetchone()
    con.close()
    return row[0] if row else default


def save_setting(key, value):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    con.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", [key, value])
    con.close()


def add_entry(entry_date, client, project, description, hours, rate, employee='Self'):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    con.execute(
        "INSERT INTO entries (id, entry_date, client, project, description, hours, rate, employee, status) VALUES (?,?,?,?,?,?,?,?,?)",
        [str(uuid.uuid4()), entry_date, client, project, description, hours, rate, employee, 'open']
    )
    con.close()


@st.cache_data(ttl=60)
def load_entries(client=None, project=None, from_date=None, to_date=None, employee=None, status=None):
    con = duckdb.connect(DB_PATH)
    query = "SELECT * FROM entries WHERE 1=1"
    params = []
    if client:
        query += " AND client = ?"
        params.append(client)
    if project:
        query += " AND project = ?"
        params.append(project)
    if from_date:
        query += " AND entry_date >= ?"
        params.append(from_date)
    if to_date:
        query += " AND entry_date <= ?"
        params.append(to_date)
    if employee:
        query += " AND employee = ?"
        params.append(employee)
    if status:
        if isinstance(status, list):
            placeholders = ','.join(['?' for _ in status])
            query += f" AND status IN ({placeholders})"
            params.extend(status)
        else:
            query += " AND status = ?"
            params.append(status)
    query += " ORDER BY entry_date DESC"
    df = con.execute(query, params).df()
    con.close()
    return df


def delete_entry(entry_id):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    con.execute("DELETE FROM entries WHERE id = ?", [entry_id])
    con.close()


def set_status(entry_id, status):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    con.execute("UPDATE entries SET status = ? WHERE id = ?", [status, entry_id])
    con.close()


def set_status_bulk(ids, status):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    for i in ids:
        con.execute("UPDATE entries SET status = ? WHERE id = ?", [status, i])
    con.close()


def get_next_invoice_number():
    prefix = get_setting('inv_prefix', 'INV') or 'INV'
    fmt    = get_setting('inv_format', 'date') or 'date'
    if fmt == 'sequential':
        num = int(get_setting('inv_next_num', '1') or 1)
        return f"{prefix}-{num:03d}"
    base = f"{prefix}-{datetime.now().strftime('%Y%m%d')}"
    con = duckdb.connect(DB_PATH)
    count = con.execute("SELECT COUNT(*) FROM invoices WHERE invoice_number LIKE ?", [f"{base}%"]).fetchone()[0]
    con.close()
    return base if count == 0 else f"{base}-{count + 1}"


def increment_invoice_number():
    fmt = get_setting('inv_format', 'date') or 'date'
    if fmt == 'sequential':
        num = int(get_setting('inv_next_num', '1') or 1)
        save_setting('inv_next_num', str(num + 1))


def save_invoice(invoice_number, client, subtotal, gst, total, billing_type='hourly', invoice_type='timesheet'):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    con.execute(
        "INSERT INTO invoices (id,invoice_number,client,invoice_date,subtotal,gst,total,billing_type,invoice_type,paid) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [str(uuid.uuid4()), invoice_number, client, date.today(), subtotal, gst, total, billing_type, invoice_type, False]
    )
    con.close()


@st.cache_data(ttl=60)
def get_invoices(client=None):
    con = duckdb.connect(DB_PATH)
    q = "SELECT * FROM invoices WHERE 1=1"
    p = []
    if client:
        q += " AND client = ?"
        p.append(client)
    q += " ORDER BY invoice_date DESC, invoice_number DESC"
    df = con.execute(q, p).df()
    con.close()
    return df


def mark_invoice_paid(invoice_id, paid=True):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    if paid:
        con.execute("UPDATE invoices SET paid=TRUE,  paid_date=? WHERE id=?", [date.today(), invoice_id])
    else:
        con.execute("UPDATE invoices SET paid=FALSE, paid_date=NULL WHERE id=?", [invoice_id])
    con.close()


def invoice_number_exists(inv_number):
    con = duckdb.connect(DB_PATH)
    row = con.execute("SELECT COUNT(*) FROM invoices WHERE invoice_number = ?", [inv_number]).fetchone()
    con.close()
    return row[0] > 0


# ── Ad hoc draft line helpers ──────────────────────────────────────────────────

def load_adhoc_lines(client):
    con = duckdb.connect(DB_PATH)
    rows = con.execute(
        "SELECT id, description, qty, unit_price FROM adhoc_draft_lines WHERE client=? ORDER BY sort_order",
        [client]
    ).fetchall()
    con.close()
    return [{'id': r[0], 'description': r[1], 'qty': float(r[2]), 'unit_price': float(r[3])} for r in rows]

def add_adhoc_line(client, description, qty, unit_price):
    con = duckdb.connect(DB_PATH)
    max_order = con.execute(
        "SELECT COALESCE(MAX(sort_order),0) FROM adhoc_draft_lines WHERE client=?", [client]
    ).fetchone()[0]
    con.execute(
        "INSERT INTO adhoc_draft_lines (id, client, description, qty, unit_price, sort_order) VALUES (?,?,?,?,?,?)",
        [str(uuid.uuid4()), client, description, qty, unit_price, int(max_order) + 1]
    )
    con.close()

def update_adhoc_line(line_id, description, qty, unit_price):
    con = duckdb.connect(DB_PATH)
    con.execute(
        "UPDATE adhoc_draft_lines SET description=?, qty=?, unit_price=? WHERE id=?",
        [description, qty, unit_price, line_id]
    )
    con.close()

def delete_adhoc_line(line_id):
    con = duckdb.connect(DB_PATH)
    con.execute("DELETE FROM adhoc_draft_lines WHERE id=?", [line_id])
    con.close()

def clear_adhoc_lines(client):
    con = duckdb.connect(DB_PATH)
    con.execute("DELETE FROM adhoc_draft_lines WHERE client=?", [client])
    con.close()


@st.cache_data(ttl=60)
def get_clients():
    con = duckdb.connect(DB_PATH)
    rows = con.execute("SELECT DISTINCT client FROM entries ORDER BY client").fetchall()
    con.close()
    return [r[0] for r in rows]


@st.cache_data(ttl=60)
def get_projects(client=None):
    con = duckdb.connect(DB_PATH)
    if client:
        rows = con.execute(
            "SELECT DISTINCT project FROM entries WHERE client = ? ORDER BY project", [client]
        ).fetchall()
    else:
        rows = con.execute("SELECT DISTINCT project FROM entries ORDER BY project").fetchall()
    con.close()
    return [r[0] for r in rows]


@st.cache_data(ttl=60)
def get_projects_list(client_id=None):
    con = duckdb.connect(DB_PATH)
    if client_id:
        df = con.execute("SELECT * FROM projects WHERE client_id=? ORDER BY code, name", [client_id]).df()
    else:
        df = con.execute("SELECT * FROM projects ORDER BY code, name").df()
    con.close()
    return df


def save_project(project_id, code, name, client_id=None):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    if project_id:
        con.execute("UPDATE projects SET code=?, name=?, client_id=? WHERE id=?", [code, name, client_id, project_id])
    else:
        con.execute("INSERT INTO projects VALUES (?, ?, ?, ?)", [str(uuid.uuid4()), code, name, client_id])
    con.close()


def delete_project(project_id):
    st.cache_data.clear()
    con = duckdb.connect(DB_PATH)
    con.execute("DELETE FROM projects WHERE id=?", [project_id])
    con.close()


@st.cache_data(ttl=60)
def get_dashboard_data():
    con = duckdb.connect(DB_PATH)
    today = date.today()
    yr, mo = today.year, today.month
    three_months_ago = (today.replace(day=1) - pd.DateOffset(months=3)).date()

    revenue = con.execute("""
        SELECT
            COALESCE(SUM(total), 0)                              AS total_invoiced,
            COALESCE(SUM(CASE WHEN paid THEN total ELSE 0 END), 0) AS paid,
            COALESCE(SUM(CASE WHEN NOT paid THEN total ELSE 0 END),0) AS outstanding
        FROM invoices
        WHERE year(invoice_date)=? AND month(invoice_date)=?
    """, [yr, mo]).fetchone()

    hours = con.execute("""
        SELECT client, ROUND(SUM(hours),2) AS hours
        FROM entries
        WHERE year(entry_date)=? AND month(entry_date)=?
        GROUP BY client ORDER BY hours DESC
    """, [yr, mo]).df()

    unpaid = con.execute("""
        SELECT client, invoice_number, invoice_date, total
        FROM invoices WHERE paid=FALSE
        ORDER BY invoice_date
    """).df()

    top_clients = con.execute("""
        SELECT client, ROUND(SUM(total),2) AS revenue
        FROM invoices
        WHERE invoice_date >= ?
        GROUP BY client ORDER BY revenue DESC LIMIT 10
    """, [three_months_ago]).df()

    con.close()
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
    my_name    = settings.get('name', '')
    my_company = settings.get('company', '')
    my_address = settings.get('address', '')
    my_abn     = settings.get('abn', '')
    my_email   = settings.get('email', '')

    client_name    = settings.get('inv_client_name', '')
    client_address = settings.get('inv_client_address', '')
    inv_date       = date.today().strftime('%d %B %Y')
    if due_date is None:
        days_in_month = [31,28,29,30,31,30,31,31,30,31,30,31][date.today().month - 1]
        due_date = date(date.today().year, date.today().month, min(date.today().day + 14, days_in_month))
    due_date = due_date.strftime('%d %B %Y')
    period_end_str = period_end.strftime('%d %B %Y') if period_end else ''
    period_end_html = f"<div style='font-size:15px;font-weight:300;color:var(--slate);margin-top:4px;'>Period ending &nbsp;<span style='color:var(--forest);font-weight:400;'>{period_end_str}</span></div>" if period_end_str else ''

    rows_html = ''
    if billing_type == 'fixed':
        for idx, line in enumerate(adhoc_lines or []):
            amount = float(line.get('qty', 1)) * float(line.get('unit_price', 0))
            rows_html += f"""
        <tr>
          <td style="white-space:nowrap">{idx + 1}</td>
          <td>{line.get('description', '')}</td>
          <td></td>
          <td style="text-align:right">{float(line.get('qty', 1)):.2f}</td>
          <td style="text-align:right">${float(line.get('unit_price', 0)):.2f}</td>
          <td style="text-align:right;font-weight:400;color:#2D4A3E">${amount:.2f}</td>
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
          <td style="text-align:right">1</td>
          <td style="text-align:right">${float(client_day_rate):.2f}</td>
          <td style="text-align:right;font-weight:400;color:#2D4A3E">${amount:.2f}</td>
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
          <td style="text-align:right">{float(row['hours']):.2f}</td>
          <td style="text-align:right">${float(row['rate']):.2f}</td>
          <td style="text-align:right;font-weight:400;color:#2D4A3E">${amount:.2f}</td>
        </tr>"""
        subtotal = sum(float(r['hours']) * float(r['rate']) for _, r in entries_df.iterrows())
    gst = subtotal * 0.1 if include_gst else 0
    total = subtotal + gst

    gst_row = f"""
      <tr>
        <td class="t-label">GST (10%)</td>
        <td class="t-value">${gst:.2f}</td>
      </tr>""" if include_gst else ''

    abn_line         = f'ABN &nbsp;{my_abn}' if my_abn else ''
    sender_display   = my_company or my_name
    sender_sub       = my_name if my_company and my_name != my_company else ''
    client_addr_html = f'<div style="margin-top:6px;color:#6B8F71;font-size:13px;line-height:1.7;white-space:pre-line">{client_address}</div>' if client_address else ''

    contact_parts = [p for p in [my_address, abn_line, my_email] if p]
    contact_html  = '<br>'.join(contact_parts)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Invoice {invoice_number}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,300;1,400&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}

  :root {{
    --forest:    #2D4A3E;
    --navy:      #1C2B3A;
    --sage:      #6B8F71;
    --cream:     #F5F0E8;
    --stone:     #C8BFA8;
    --parchment: #EDE8DC;
    --slate:     #4A5568;
    --chalk:     #FAFAF7;
  }}

  body {{
    font-family: 'DM Sans', sans-serif;
    font-weight: 300;
    color: var(--slate);
    background: var(--cream);
    padding: 48px 24px;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
    line-height: 1.7;
  }}

  .page {{
    max-width: 800px;
    margin: 0 auto;
    background: var(--chalk);
    border: 0.5px solid var(--stone);
  }}

  /* ── Top bar ── */
  .top-bar {{
    height: 4px;
    background: var(--forest);
  }}

  /* ── Header ── */
  .header {{
    display: flex;
    flex-direction: column;
    padding: 44px 52px 36px;
    border-bottom: 0.5px solid var(--stone);
  }}

  .bill-to-col {{
    display: flex;
    flex-direction: column;
  }}

  .sender-col {{
    text-align: right;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
  }}

  .header-meta {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-top: 24px;
  }}

  .wordmark {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 26px;
    font-weight: 400;
    letter-spacing: 0.04em;
    color: var(--forest);
    display: block;
    margin-bottom: 12px;
  }}

  .sender-detail {{
    font-size: 12px;
    font-weight: 300;
    color: var(--slate);
    line-height: 1.8;
    opacity: 0.8;
    text-align: right;
  }}

  .invoice-badge {{ text-align: right; margin-top: 20px; }}

  .invoice-word {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--sage);
    display: block;
    margin-bottom: 8px;
  }}

  .invoice-number {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 42px;
    font-weight: 300;
    color: var(--navy);
    letter-spacing: -0.5px;
    line-height: 1;
    display: block;
    margin-bottom: 14px;
  }}

  .invoice-meta-grid {{
    font-size: 12px;
    font-weight: 300;
    color: var(--slate);
    line-height: 1.9;
  }}
  .invoice-meta-grid span {{ color: var(--forest); font-weight: 400; }}

  /* ── Bill-to ── */
  .bill-strip {{
    padding: 28px 52px;
    border-bottom: 0.5px solid var(--stone);
    background: var(--cream);
  }}

  .bill-eyebrow {{
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--sage);
    display: block;
    margin-bottom: 8px;
  }}

  .bill-name {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 22px;
    font-weight: 400;
    color: var(--navy);
    line-height: 1.2;
  }}

  /* ── Table ── */
  .table-wrap {{ padding: 0 52px; }}

  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 32px 0 0;
    font-size: 13px;
    font-weight: 300;
  }}

  thead tr {{ background: var(--forest); }}

  thead th {{
    padding: 12px 14px;
    font-family: 'DM Sans', sans-serif;
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--cream);
    text-align: left;
  }}
  thead th:nth-child(4),
  thead th:nth-child(5),
  thead th:nth-child(6) {{ text-align: right; }}

  tbody tr {{ border-bottom: 0.5px solid var(--parchment); }}
  tbody tr:nth-child(even) {{ background: var(--cream); }}

  tbody td {{
    padding: 12px 14px;
    color: var(--slate);
    vertical-align: top;
  }}

  /* ── Totals ── */
  .totals-wrap {{
    display: flex;
    justify-content: flex-end;
    padding: 8px 52px 36px;
  }}

  .totals-table {{
    width: 260px;
    border-collapse: collapse;
    font-size: 13px;
    font-weight: 300;
  }}
  .totals-table td {{ padding: 7px 12px; }}
  .totals-table .t-label {{ text-align: right; color: var(--slate); opacity: 0.8; }}
  .totals-table .t-value {{ text-align: right; color: var(--navy); }}
  .totals-table .t-divider td {{ border-top: 0.5px solid var(--stone); padding-top: 12px; }}
  .totals-table .t-total td {{
    background: var(--forest);
    color: var(--cream);
    font-weight: 500;
    font-size: 14px;
    padding: 13px 12px;
  }}
  .totals-table .t-total td:first-child {{ text-align: right; }}
  .totals-table .t-total td:last-child  {{ text-align: right; }}

  /* ── Payment note ── */
  .payment-note {{
    margin: 0 52px 44px;
    padding: 18px 22px;
    border-left: 2px solid var(--sage);
    background: var(--parchment);
    font-size: 12.5px;
    font-weight: 300;
    color: var(--slate);
    line-height: 1.75;
  }}
  .payment-note strong {{ color: var(--forest); font-weight: 500; }}

  /* ── Footer ── */
  .footer {{
    border-top: 0.5px solid var(--stone);
    padding: 20px 52px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--cream);
  }}
  .footer-mark {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 14px;
    font-weight: 400;
    letter-spacing: 0.04em;
    color: var(--forest);
    opacity: 0.7;
  }}
  .footer-note {{
    font-size: 11px;
    font-weight: 300;
    color: var(--stone);
    letter-spacing: 0.04em;
  }}

  @page {{
    margin: 0;
    size: A4;
  }}

  @media print {{
    html, body {{ background: white; padding: 0; margin: 0; }}
    .page {{ border: none; box-shadow: none; margin: 0; max-width: 100%; }}
    .print-btn {{ display: none !important; }}
  }}

  .print-btn {{
    position: fixed;
    bottom: 28px;
    right: 28px;
    z-index: 999;
  }}
  .print-btn button {{
    background: var(--forest);
    color: var(--cream);
    border: none;
    padding: 12px 22px;
    font-family: 'DM Sans', sans-serif;
    font-size: 13px;
    font-weight: 400;
    letter-spacing: 0.04em;
    cursor: pointer;
    box-shadow: 0 4px 16px rgba(45,74,62,0.25);
  }}
  .print-btn button:hover {{ background: var(--navy); }}
</style>
</head>
<body>
<div class="print-btn"><button onclick="var w=window.open('','_blank');w.document.write(document.documentElement.outerHTML);w.document.close();w.focus();w.print();">Print / Save as PDF</button></div>
<div class="page">
  <div class="top-bar"></div>

  <div class="header">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;width:100%;">
      <div class="bill-to-col">
        <span class="bill-eyebrow">Bill To</span>
        <div class="bill-name">{client_name}</div>
        {client_addr_html}
      </div>
      <div class="sender-col">
        <span class="wordmark">{sender_display}</span>
        <div class="sender-detail">{contact_html}</div>
      </div>
    </div>
    <div class="header-meta">
      <div>
        <div style="font-size:15px;font-weight:400;color:var(--forest);">Tax Invoice &nbsp;<strong style="font-size:17px;letter-spacing:0.02em;">{invoice_number}</strong></div>
        {period_end_html}
      </div>
      <div style="font-size:15px;font-weight:300;color:var(--slate);">Date &nbsp;<span style="color:var(--forest);font-weight:400;">{inv_date}</span></div>
    </div>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>{"#" if billing_type == 'fixed' else "Date"}</th>
          <th>{"Description" if billing_type == 'fixed' else "Project"}</th>
          <th>{"" if billing_type == 'fixed' else "Description"}</th>
          <th>{"Qty" if billing_type == 'fixed' else ("Days" if billing_type == 'day_rate' else "Hours")}</th>
          <th>{"Unit Price" if billing_type == 'fixed' else ("Day Rate" if billing_type == 'day_rate' else "Rate")}</th>
          <th>Amount</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>

  <div class="totals-wrap">
    <table class="totals-table">
      <tr>
        <td class="t-label">Subtotal</td>
        <td class="t-value">${subtotal:.2f}</td>
      </tr>
      {gst_row}
      <tr class="t-divider"><td colspan="2"></td></tr>
      <tr class="t-total">
        <td>Total (AUD)</td>
        <td>${total:.2f}</td>
      </tr>
    </table>
  </div>

  <div class="payment-note">
    {payment_terms.replace(chr(10), '<br>')}
  </div>

  <div class="footer">
    <span class="footer-mark">{sender_display}</span>
    <span class="footer-note">Thank you</span>
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
                if not emp_row.empty and float(emp_row.iloc[0]['rate'] or 0) > 0:
                    rate_default = float(emp_row.iloc[0]['rate'])

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
                    add_entry(entry_date, selected_client, project.strip(), description.strip(), hours, rate_used, employee)
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
                con = duckdb.connect(DB_PATH)
                ids = open_df['id'].tolist()
                for i, row in edited.iterrows():
                    if i < len(ids):
                        con.execute("""
                            UPDATE entries SET entry_date=?, employee=?, client=?, project=?,
                            description=?, hours=?, rate=? WHERE id=?
                        """, [row['Date'], row['Employee'], row['Client'], row['Project'],
                              row['Description'], row['Hours'], row['Rate ($)'], ids[i]])
                con.close()
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
            pcols = st.columns(min(len(pending_clients), 4))
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
                _default_due   = date.today().replace(day=min(date.today().day + 14, 28))
                inv_due_date   = st.date_input("Due date", value=_default_due, key='inv_due_date', format="DD/MM/YYYY")
            with col1:
                from datetime import timedelta
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
                                         inv_data.get('billing_type', 'hourly'), 'timesheet')
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
                                         'fixed', 'fixed')
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
                else:
                    editing = None
                    f_name = f_email = f_role = ''
                    f_rate = 0.0
            else:
                f_name = f_email = f_role = ''
                f_rate = 0.0

            with st.form("emp_form", clear_on_submit=True):
                e_name  = st.text_input("Full name",  value=f_name)
                e_email = st.text_input("Email",      value=f_email)
                e_role  = st.text_input("Role / title", value=f_role)
                e_rate  = st.number_input("Hourly rate ($)", min_value=0.0, step=5.0, value=f_rate)
                save_btn = st.form_submit_button("Save Employee", type="primary", use_container_width=True)

            if save_btn:
                if not e_name:
                    st.error("Name is required.")
                else:
                    save_employee(editing, e_name.strip(), e_email.strip(), e_role.strip(), e_rate)
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
            "Payment terms",
            value=get_setting('payment_terms', 'Payment due within 14 days of invoice date.\nPlease reference the invoice number with your payment.'),
            height=100
        )

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
                con = duckdb.connect(DB_PATH)
                if confirm in ('entries', 'all'):
                    con.execute("DELETE FROM entries")
                if confirm in ('invoices', 'all'):
                    con.execute("DELETE FROM invoices")
                con.close()
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
            h1, h2, h3, h4, h5, h6 = st.columns([1.8, 2.2, 1.4, 1.2, 1.6, 1.8])
            h1.caption("Invoice #")
            h2.caption("Client")
            h3.caption("Date")
            h4.caption("Age")
            h5.caption("Amount")
            h6.caption("")

            for _, row in outstanding.iterrows():
                inv_date = pd.to_datetime(row['invoice_date'])
                days = (date.today() - inv_date.date()).days
                if days > 60:
                    age_str = f"🔴 {days}d"
                elif days > 30:
                    age_str = f"🟡 {days}d"
                else:
                    age_str = f"{days}d"

                c1, c2, c3, c4, c5, c6 = st.columns([1.8, 2.2, 1.4, 1.2, 1.6, 1.8])
                c1.write(f"**{row['invoice_number']}**")
                c2.write(row['client'])
                c3.write(inv_date.strftime('%d/%m/%Y'))
                c4.write(age_str)
                c5.write(f"**${float(row['total']):,.2f}**")
                if c6.button("✓ Mark Paid", key=f"paid_{row['id']}", type="primary", use_container_width=True):
                    mark_invoice_paid(row['id'], paid=True)
                    st.rerun()

            st.write("")

        # ── Paid ───────────────────────────────────────────────────────────────
        paid = view_df[view_df['paid']].sort_values('paid_date', ascending=False)
        if not paid.empty:
            paid_total = paid['total'].sum()
            with st.expander(
                f"✅ Paid — {len(paid)} invoice{'s' if len(paid)!=1 else ''} · ${paid_total:,.2f}"
            ):
                h1, h2, h3, h4, h5, h6 = st.columns([1.8, 2.2, 1.4, 1.4, 1.6, 1.6])
                h1.caption("Invoice #")
                h2.caption("Client")
                h3.caption("Invoiced")
                h4.caption("Paid on")
                h5.caption("Amount")
                h6.caption("")

                for _, row in paid.iterrows():
                    c1, c2, c3, c4, c5, c6 = st.columns([1.8, 2.2, 1.4, 1.4, 1.6, 1.6])
                    c1.write(f"**{row['invoice_number']}**")
                    c2.write(row['client'])
                    c3.write(pd.to_datetime(row['invoice_date']).strftime('%d/%m/%Y'))
                    paid_on = pd.to_datetime(row['paid_date']).strftime('%d/%m/%Y') if pd.notna(row['paid_date']) else '—'
                    c4.write(paid_on)
                    c5.write(f"${float(row['total']):,.2f}")
                    if c6.button("Undo", key=f"unpaid_{row['id']}", use_container_width=True):
                        mark_invoice_paid(row['id'], paid=False)
                        st.rerun()

        # ── Export ─────────────────────────────────────────────────────────────
        st.divider()
        export = view_df[['invoice_number','client','invoice_date','invoice_type','subtotal','gst','total','paid','paid_date']].copy()
        export.columns = ['Invoice #','Client','Date','Type','Subtotal','GST','Total','Paid','Paid Date']
        st.download_button("⬇ Export to CSV", export.to_csv(index=False), "statements.csv", "text/csv")

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
