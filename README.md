# ONPay

ONPay helps students find a nearby person to exchange physical cash for a UPI payment. It is a matching and coordination service; it is not a bank, wallet, escrow service, or payment processor.

## Project map

- `frontend/` — mobile-first React + TypeScript app built with Vite.
- `backend/` — FastAPI service with SQLAlchemy persistence and an Alembic migration.
- `docs/payment-integration.md` — UPI and YouPI-PG compatibility assessment.
- `docs/production-setup.md` — Mailjet email delivery, location, camera, plans, and device testing.

## Local development

Requirements: Node.js 20+ and Python 3.10+.

1. Copy `backend/.env.example` to `backend/.env`. For a local mock code, explicitly set `DEV_OTP_MODE=true` while `APP_ENV=development`.
2. Start the API from `backend/`:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   alembic upgrade head
   uvicorn app.main:app --reload
   ```

   The first run creates the local SQLite database. API docs are at `http://localhost:8000/docs`.
3. In another terminal, start the web app from `frontend/`:

   ```powershell
   npm install
   npm run dev
   ```

   Open `http://localhost:5173`. For testing on a phone on the same network, bind the API with `uvicorn app.main:app --reload --host 0.0.0.0`, leave `VITE_API_BASE_URL` unset, and set `FRONTEND_ORIGINS` to the exact frontend origin shown in that device's browser (for example `http://192.168.1.40:5173`).

Mock OTPs are returned only when both `APP_ENV=development` and `DEV_OTP_MODE=true`. To test email delivery, set `DEV_OTP_MODE=false`, choose `EMAIL_PROVIDER=mailjet`, and configure Mailjet's API keys and an active sender address. Email is sent through Mailjet's HTTPS API; ONPay does not use SMTP. Production OTP delivery never includes the OTP in the API response. Never use the development mock in a deployed environment.

## Configuration

See `backend/.env.example` and `frontend/.env.example`. For PostgreSQL, set `DATABASE_URL` to a PostgreSQL SQLAlchemy URL and run `alembic upgrade head` from `backend/`. SQLite is intended for local development.

For deployed builds, set the frontend hosting variable `VITE_API_BASE_URL` to the backend's public HTTPS origin and set backend `FRONTEND_ORIGINS` to the exact frontend origins, comma separated. During local development, Vite uses the browser's current hostname on port 8000 unless `VITE_API_BASE_URL` is explicitly set. `VITE_*` values are public and must never contain credentials or secrets. See `docs/production-setup.md` for hosting setup.

## Location, QR scanning, and plans

On the authenticated home screen, ONPay checks the browser's geolocation permission state. It retrieves coordinates automatically only when permission is already granted; otherwise the user can explicitly enable it or choose a campus manually. Nearby discovery uses the current coordinates and listings created with a rounded approximate position. Exact coordinates are not included in listing responses. Camera scanning uses the ZXing browser QR reader and requires HTTPS (or localhost) plus camera permission; image and manual UPI ID entry remain available as fallbacks.

Plans are Free (₹0 / 5 completed exchanges per India calendar month), Plus (₹199 / 20), and Premium (₹499 / unlimited). The backend reserves available slots for in-progress exchanges and releases them for failed or cancelled exchanges. Paid billing is not configured, so the app shows it as unavailable and never activates a paid plan from an upgrade click.

## Safety and payment status

ONPay builds a standard `upi://pay` intent and asks the user to confirm before opening a payment app. Returning from that app, a screenshot, or a client-side button does not prove settlement. In this build, UPI attempts remain **Verification pending** until an authoritative provider integration is configured. Cash handover confirmations are recorded separately. No success state, reward, monthly quota usage, or friendship is granted from a payment-app redirect.

The available YouPI-PG project is a self-hosted experimental merchant collection gateway. Its documented payment endpoints create merchant orders and its checkout is tied to a receiving merchant account; it does not provide arbitrary student-to-student transfers. See the compatibility assessment in `docs/payment-integration.md` before any real-money work.

## Tests and builds

```powershell
# Backend
cd backend
python -m unittest discover -s tests -v

# Frontend
cd ../frontend
npm test
npm run build
```

The test suites mock email API, geocoding, and payment behavior; they do not send email, request device GPS, open a camera, or move real money.

For real-money use, obtain a supported payment provider with server-side authoritative settlement callbacks, review applicable Indian payment and privacy requirements with qualified professionals, and complete security and reconciliation reviews.
