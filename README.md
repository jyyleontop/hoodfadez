# Hoodfadez — Barbershop Booking

Flask + vanilla HTML/CSS/JS. Three pages, smart booking, web-push to the barber.

## Structure
```
hoodfadez/
├── app.py
├── templates/
│   ├── index.html      # Homepage with animated barber-pole stripes
│   ├── book.html       # Booking page (disables past + taken slots)
│   └── bookings.html   # Barber dashboard + push toggle
└── static/
    ├── sw.js           # Service worker for push notifications
    ├── manifest.json   # PWA manifest (so iPhone "Add to Home Screen" works)
    ├── icon-192.png    # ADD YOUR OWN
    └── icon-512.png    # ADD YOUR OWN
```

## Setup

```bash
pip install flask pywebpush py-vapid
```

### Generate VAPID keys (one time)
```python
from py_vapid import Vapid
v = Vapid()
v.generate_keys()
v.save_key('vapid_priv.pem')
v.save_public_key('vapid_pub.pem')
print('PUBLIC :', v.public_key_urlsafe_base64())
print('PRIVATE:', v.private_key_urlsafe_base64())
```

Then either paste those values into `app.py` or set them as env vars:
```bash
export VAPID_PUBLIC_KEY="..."
export VAPID_PRIVATE_KEY="..."
```

### Run
```bash
python app.py
```
Open http://localhost:5000

## How push notifications work on iPhone
1. Barber opens `/bookings` in **Safari** on his iPhone (iOS 16.4+).
2. Share sheet → **Add to Home Screen**.
3. Open the app from the home-screen icon (this matters — push only works for installed PWAs on iOS).
4. Tap **Enable Notifications**, allow the prompt.
5. Every new booking from `/book` triggers a push via `webpush()` in `app.py`.

## Smart booking logic
- Hours: 13:00–22:00, slots every 15 min.
- Haircut = 30 min, Hair + Beard = 45 min.
- Past times are disabled client-side AND rejected server-side.
- Overlapping slots are filtered out client-side AND server-side returns `409` if a race happens.

## API
- `GET  /api/bookings` → all bookings JSON
- `POST /api/bookings` → `{name, phone, service, duration, date, time}`
- `GET  /api/vapid-key` → `{publicKey}`
- `POST /api/subscribe` → push subscription object
