"""
Hoodfadez — Flask backend
-------------------------
Routes:
  GET  /                  -> homepage (templates/index.html)
  GET  /book              -> booking form (templates/book.html)
  GET  /bookings          -> barber dashboard (templates/bookings.html)
  GET  /api/bookings      -> list bookings (JSON)
  POST /api/bookings      -> create booking (validates conflicts + past times)
  GET  /api/vapid-key     -> public VAPID key for push subscribe
  POST /api/subscribe     -> save a barber's push subscription
  GET  /static/sw.js      -> served automatically from /static

Setup:
  pip install flask pywebpush sqlalchemy

Generate VAPID keys once:
  from py_vapid import Vapid
  v = Vapid(); v.generate_keys()
  v.save_key('vapid_priv.pem'); v.save_public_key('vapid_pub.pem')
  # then base64url-encode the raw public key as VAPID_PUBLIC_KEY below.

Run:
  python app.py
"""
import json, os, sqlite3, uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory

# pip install pywebpush
from pywebpush import webpush, WebPushException

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(APP_ROOT, 'hoodfadez.db')

# ---- VAPID keys (REPLACE with your generated keys) ----
VAPID_PUBLIC_KEY  = os.environ.get('VAPID_PUBLIC_KEY',  'BJBI9KiWgxMwGwGYHqPSm3qjcH-3kJJbJliSo-v36AgGQrr5Qm8NCN8HpaZme5FWya2QnoHrVXYxYs9XqWRGd1o')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', 'I5ExUN1YE7ATwkai2J6kKWOGOERtlh0l83HdRkHEbP8')
VAPID_CLAIMS = {"sub": "mailto:barber@hoodfadez.example"}

OPEN_HOUR, CLOSE_HOUR = 13, 22  # 13:00–22:00

app = Flask(__name__, template_folder='templates', static_folder='static')

# ---------- DB ----------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS bookings(
            id TEXT PRIMARY KEY, name TEXT, phone TEXT, service TEXT,
            duration INTEGER, date TEXT, time TEXT, created_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS subs(
            endpoint TEXT PRIMARY KEY, sub_json TEXT)""")
init_db()

# ---------- Pages ----------
@app.route('/')
def home(): return render_template('index.html')

@app.route('/book')
def book(): return render_template('book.html')

@app.route('/bookings')
def bookings_page(): return render_template('bookings.html')

# ---------- API ----------
@app.route('/api/bookings', methods=['GET'])
def list_bookings():
    with db() as c:
        rows = c.execute("SELECT * FROM bookings ORDER BY date, time").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/bookings', methods=['POST'])
def create_booking():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()[:60]
    phone = (data.get('phone') or '').strip()[:20]
    service = data.get('service')
    duration = int(data.get('duration') or 30)
    date = data.get('date'); time = data.get('time')

    if not (name and phone and date and time and service in ('haircut','hair_beard')):
        return jsonify({"error":"Missing or invalid fields"}), 400
    if duration not in (30, 45):
        return jsonify({"error":"Invalid duration"}), 400

    try:
        slot_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return jsonify({"error":"Bad date/time"}), 400
    if slot_dt < datetime.now():
        return jsonify({"error":"That time has already passed"}), 400

    sh, sm = map(int, time.split(':'))
    start = sh*60 + sm; end = start + duration
    if sh < OPEN_HOUR or end > CLOSE_HOUR*60:
        return jsonify({"error":"Outside opening hours"}), 400

    with db() as c:
        existing = c.execute("SELECT time, duration FROM bookings WHERE date=?",(date,)).fetchall()
        for r in existing:
            h, m = map(int, r['time'].split(':'))
            s = h*60 + m; e = s + (r['duration'] or 30)
            if start < e and end > s:
                return jsonify({"error":"Slot just got taken — pick another"}), 409
        bid = uuid.uuid4().hex
        c.execute("INSERT INTO bookings VALUES(?,?,?,?,?,?,?,?)",
                  (bid, name, phone, service, duration, date, time, datetime.utcnow().isoformat()))

    notify_barber(f"New booking: {name}", f"{date} at {time} — {'Hair + Beard' if service=='hair_beard' else 'Haircut'}")
    return jsonify({"ok": True, "id": bid})

# ---------- Push ----------
@app.route('/api/vapid-key')
def vapid_key():
    return jsonify({"publicKey": VAPID_PUBLIC_KEY})

@app.route('/api/subscribe', methods=['POST'])
def subscribe():
    sub = request.get_json(silent=True) or {}
    endpoint = sub.get('endpoint')
    if not endpoint: return jsonify({"error":"bad subscription"}), 400
    with db() as c:
        c.execute("INSERT OR REPLACE INTO subs(endpoint, sub_json) VALUES(?,?)",
                  (endpoint, json.dumps(sub)))
    return jsonify({"ok": True})

def notify_barber(title, body):
    with db() as c:
        rows = c.execute("SELECT endpoint, sub_json FROM subs").fetchall()
    payload = json.dumps({"title": title, "body": body, "url": "/bookings"})
    dead = []
    for r in rows:
        try:
            webpush(json.loads(r['sub_json']), payload,
                    vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims=dict(VAPID_CLAIMS))
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):
                dead.append(r['endpoint'])
    if dead:
        with db() as c:
            c.executemany("DELETE FROM subs WHERE endpoint=?", [(e,) for e in dead])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
