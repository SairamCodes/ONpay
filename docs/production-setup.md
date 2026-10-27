# Production and device setup

## Email OTP

Copy `backend/.env.example` to `backend/.env`. Obtain the values below from the email provider that will send ONPay's transactional mail; the example values are intentionally blank and are not credentials.

```dotenv
APP_ENV=production
DEV_OTP_MODE=false
SECRET_KEY=<a random secret with at least 32 characters>
SMTP_HOST=<provider SMTP hostname>
SMTP_PORT=587
SMTP_USERNAME=<provider SMTP username>
SMTP_PASSWORD=<provider SMTP password or app password>
SMTP_FROM=<verified sender name and email>
SMTP_STARTTLS=true
SMTP_USE_SSL=false
```

Use the provider's documented host and port. Port 587 uses STARTTLS. Port 465 uses implicit TLS; set `SMTP_USE_SSL=true` (port 465 is also detected automatically). `SMTP_FROM` must be an address the provider has authorized. Credentials belong only in the untracked `backend/.env` or a deployment secret store, never in the repository or browser bundle.

The API requires `SMTP_HOST`, a valid `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, a valid authorized `SMTP_FROM`, and TLS. Missing or insecure email settings return HTTP 503; provider delivery failures return a safe HTTP 502. The API persists an OTP challenge and its keyed hash before delivery, marks it `sent` only after the provider accepts the request, and records a `failed` state and clears the hash if delivery fails. OTPs are cryptographically random, six digits, expire after five minutes, have a resend cooldown and attempt limit, and are consumed after verification. A successful request response includes `accepted: true`; the frontend does not open the verification screen without that flag and a valid challenge ID. Production ignores `DEV_OTP_MODE` and never returns the OTP. For isolated development only, set both `APP_ENV=development` and `DEV_OTP_MODE=true` to receive a dynamically generated mock code in the response.

To test real email delivery, use a dedicated test inbox and the provider's actual SMTP credentials. The mock SMTP unit test confirms STARTTLS setup and delivery-state handling but does not send a real message.

## Frontend and backend connectivity

For local development, leave `VITE_API_BASE_URL` unset. Vite uses the browser's current hostname on port 8000, so a page opened from another device does not accidentally call that device's own `localhost`. To test from a phone or another computer, run the API bound to your development machine's network interface (for example `uvicorn app.main:app --reload --host 0.0.0.0`) and add the exact frontend origin, such as `http://192.168.1.40:5173`, to backend `FRONTEND_ORIGINS`. Only add trusted devices on your local network. Production builds require `VITE_API_BASE_URL` to be set to the backend's public HTTPS origin in the frontend hosting platform before the build. For example, use the API origin such as `https://api.your-domain.example`, without `/api` at the end. This is public build configuration, so never put SMTP credentials, database URLs, or other secrets in a `VITE_` variable. Rebuild and redeploy the frontend after changing it.

On the backend hosting platform, set `APP_ENV=production`, a random `SECRET_KEY` of at least 32 characters, and `FRONTEND_ORIGINS` to a comma-separated list of exact frontend origins, such as `https://onpay.your-domain.example,https://preview.your-domain.example`. The API permits credentials only for those configured origins. Do not set a wildcard origin. Configure SMTP and database variables on the backend service. Both the frontend and API must be reachable over HTTPS for browsers to allow credentialed requests.

The session cookie defaults to `SESSION_COOKIE_SAMESITE=lax`. Keep this for same-site frontend/API deployments, including different subdomains of one site. If the frontend and API are on different sites, set `SESSION_COOKIE_SAMESITE=none`; ONPay then marks the cookie Secure. Browsers may block third-party cookies, so a same-site API domain or reverse proxy is more reliable.

The registration form sends `POST /api/auth/otp/request` with JSON fields `channel`, `contact`, `intent`, and, for signup, `full_name` and `college`. It opens the verification screen only after the API returns success. Network failures are logged with method, API origin, route, and error type; request bodies and authentication data are not logged.

## Optional mobile OTP

ONPay uses Twilio Verify when mobile OTP is enabled; email OTP does not require Twilio. All three server-only values are required, and no production fallback to a local OTP is permitted:

```dotenv
TWILIO_ACCOUNT_SID=<Twilio Account SID>
TWILIO_AUTH_TOKEN=<Twilio Auth Token>
TWILIO_VERIFY_SERVICE_SID=<Twilio Verify Service SID>
```

`TWILIO_PHONE_NUMBER` is not needed for Verify. It would be used only if the implementation changed to direct SMS delivery. The current implementation never falls back from production Twilio to a local code.

## Automatic location and nearby listings

1. Serve the frontend through HTTPS. Browsers allow geolocation on localhost during development; ordinary HTTP hosts are blocked.
2. In the browser's site settings, allow location. Returning to the authenticated Home screen then retrieves a fresh location without another prompt. If permission is still `prompt`, ONPay waits until the user selects **Enable** or **Use current location**.
3. A successful location is sent to the authenticated ONPay API for reverse geocoding and nearby listing filtering. The location label is shown in the app header. Discovery searches a 25 km radius.
4. New listings store latitude and longitude rounded to three decimal places (about 100 m at the equator); exact device coordinates are never returned in listing JSON. Listings created before coordinate capture have no proximity point and will not appear in a GPS-filtered result until recreated with location enabled.
5. Manual campus selection remains available when permission is denied, unavailable, timed out, or unsupported. It does not block chat, profile, or other app features.

Location Settings displays the browser-provided coordinates, accuracy radius, and position timestamp, plus only the place name actually returned by the configured reverse-geocoder. Refresh makes a new one-shot geolocation request; ONPay does not continuously track location. A manually selected campus or neighborhood is stored on the signed-in user's profile, while precise device coordinates are not stored there.

The default reverse-geocoder endpoint is Nominatim-compatible. Set a real identifying `REVERSE_GEOCODER_USER_AGENT`, for example `ONPay/0.1 (+mailto:operator@your-domain.example)`, and set the provider attribution. The backend caches locality lookups and spaces uncached requests to one per second. Nominatim's public service requires an identifying User-Agent, attribution, caching, and no more than one request per second; it is intended for moderate, end-user-triggered use. For production traffic, use a provider or self-hosted service that you operate and can switch to without a frontend release. See the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/).

## QR and payment flow on a device

1. Open ONPay on a phone over HTTPS (or localhost during development) and allow camera access when the scanner opens.
2. Camera and image scanning use the ZXing browser QR reader. Camera access still depends on browser support for `getUserMedia`, a secure connection, and user permission. The app explains camera denial and offers gallery and manual UPI ID fallbacks.
3. Scan a standard `upi://pay` QR. ONPay displays the payee, UPI ID, currency, and any amount fixed into the QR. A fixed amount that differs from the exchange is rejected; ONPay does not rewrite it. If the QR has no amount, the agreed exchange amount is used.
4. Choose **Continue to UPI app** and select an installed payment app. If no app opens, use an installed UPI app or return to ONPay. A cancelled or returned app flow stays pending; it is not settlement proof.
5. Test the real camera, gallery decode, browser app chooser, cancellation, and return behavior on each target device. Automated tests cover URI parsing and mock pending/reconciliation flows only; they do not test physical cameras or real UPI apps.

ONPay creates a direct student VPA UPI intent. It does not use YouPI-PG merchant checkout for student-to-student settlement, because that checkout is merchant-account collection. A successful status still requires independent reconciliation; the current build has no authoritative person-to-person payment provider configured.

## Subscription plans and limits

The API catalog is fixed to Free ₹0 / 5, Plus ₹199 / 20, and Premium ₹499 / unlimited per India calendar month. It counts verified completed exchanges and reserves slots for active exchanges to avoid overbooking. Failed and cancelled exchanges release the reservation. Expired paid subscriptions fall back to Free. Subscription billing is not integrated; Plus and Premium checkout return unavailable and never activate a plan.

## Migration and verification

Run `alembic upgrade head` from the directory containing the active backend `.env` before starting/deploying the API. Migration `0002_location_otp_plans` adds coordinate and OTP delivery state columns and renames stored `pro` plan values to `premium`. `create_all()` at API startup creates missing tables but does not apply schema upgrades to existing tables.

Run the backend with `python -m unittest discover -s tests -v`. From `frontend/`, run `npm test` and `npm run build`. Real SMTP, GPS permissions, location provider calls, camera devices, UPI apps, subscription billing, and real-money settlement require external configuration and device-level validation.
