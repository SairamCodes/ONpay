# Production and device setup

## Email OTP

ONPay sends email OTPs through Mailjet's HTTPS Send API v3.1. Before sending, add the sender address in Mailjet under **Account Settings → Senders & Domains** and confirm the verification email. Mailjet's API requires an active sender address; a whole sending domain can be validated instead if you control its DNS. The request uses HTTPS Basic Auth with the public API key as the username and private API key as the password. ONPay does not send email through SMTP.

For local development, copy `backend/.env.example` to `backend/.env`. For Render, set these as backend service environment variables in the Render dashboard; do not put credentials in the repository or frontend environment:

```dotenv
APP_ENV=production
DEV_OTP_MODE=false
SECRET_KEY=<a random secret with at least 32 characters>
EMAIL_PROVIDER=mailjet
MAILJET_API_KEY=<Mailjet public API key>
MAILJET_SECRET_KEY=<Mailjet private API key>
EMAIL_FROM=ONPay <verified-sender@example.com>
```

Use the exact sender address that Mailjet shows as active. Mailjet also offers sender-address verification without DNS, but it warns that Gmail, Yahoo, Outlook, and other free-mail sender domains can be spam-foldered or rejected because you cannot configure their SPF/DKIM records. A custom domain with SPF/DKIM is the recommended sender identity for dependable production OTP delivery. See Mailjet's [sender verification guide](https://documentation.mailjet.com/hc/en-us/articles/360042759253-How-to-add-a-sender-address) and [free-mail sender guidance](https://documentation.mailjet.com/hc/en-us/articles/19308800104091-Why-you-should-avoid-free-webmail-as-a-sender-address).

The backend requires `EMAIL_PROVIDER=mailjet`, both Mailjet API keys, and a valid `EMAIL_FROM`. It sends `POST https://api.mailjet.com/v3.1/send` with a 10-second timeout and marks a challenge sent only after Mailjet returns HTTP success, message status `success`, and a message ID. Missing configuration returns HTTP 503; provider rejection or transport errors return a safe HTTP 502 and leave the challenge failed with its code hash cleared. OTPs remain cryptographically random, six digits, expire after five minutes, have a resend cooldown and attempt limit, and are consumed after verification. Ineligible signup/login requests are still suppressed to avoid revealing whether an account exists. A successful eligible request includes `accepted: true`; the frontend does not open the verification screen without that flag and a valid challenge ID. Production never returns the OTP. For isolated development only, set both `APP_ENV=development` and `DEV_OTP_MODE=true` to receive a dynamically generated mock code in the response.

To test real email delivery, set `DEV_OTP_MODE=false`, use a test inbox, and configure Mailjet's real API credentials and active sender address. Automated tests mock the HTTPS API and never send real email.

## Frontend and backend connectivity

For local development, leave `VITE_API_BASE_URL` unset. Vite uses the browser's current hostname on port 8000, so a page opened from another device does not accidentally call that device's own `localhost`. To test from a phone or another computer, run the API bound to your development machine's network interface (for example `uvicorn app.main:app --reload --host 0.0.0.0`) and add the exact frontend origin, such as `http://192.168.1.40:5173`, to backend `FRONTEND_ORIGINS`. Only add trusted devices on your local network. Production builds require `VITE_API_BASE_URL` to be set to the backend's public HTTPS origin in the frontend hosting platform before the build. For example, use the API origin such as `https://api.your-domain.example`, without `/api` at the end. This is public build configuration, so never put Mailjet API keys, database URLs, or other secrets in a `VITE_` variable. Rebuild and redeploy the frontend after changing it.

On the backend hosting platform, set `APP_ENV=production`, `DEV_OTP_MODE=false`, a random `SECRET_KEY` of at least 32 characters, and `FRONTEND_ORIGINS` to a comma-separated list of exact frontend origins, such as `https://onpay.your-domain.example,https://preview.onpay.example`. Set `EMAIL_PROVIDER=mailjet`, `MAILJET_API_KEY`, `MAILJET_SECRET_KEY`, and `EMAIL_FROM` on the backend service, along with the database variables. Keep provider credentials server-side; never use a `VITE_` variable for them. The API permits credentials only for configured frontend origins. Do not set a wildcard origin. Both the frontend and API must be reachable over HTTPS for browsers to allow credentialed requests.

When `SESSION_COOKIE_SAMESITE` is unset, ONPay uses `lax` in development and `none` with `Secure` outside development. Netlify's `netlify.app` frontend and Render's `onrender.com` API are different sites, so configure `SESSION_COOKIE_SAMESITE=none` on Render. The frontend sends credentialed requests, and OTP sign-in is considered complete only after `/api/auth/me` confirms the session cookie. Some browsers block third-party cookies regardless of `SameSite`; a same-site custom API domain or reverse proxy is more reliable in those browsers.

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

The API catalog is Free ₹0 / up to 5, Plus ₹199 per month / up to 20, and Pro / unlimited qualifying transactions. Pro price and billing period are intentionally unset until decided. If configured later, set `PRO_PLAN_PRICE_INR` and `PRO_PLAN_BILLING_PERIOD` on the backend service; they are display settings, not proof of payment. Usage counts completed exchanges recorded this month in India time. In-progress exchanges temporarily reserve capacity to prevent simultaneous matches exceeding a plan limit; failed and cancelled exchanges do not count and release their reservation. Completed exchanges may be recipient-confirmed or independently bank/provider-verified, and the UI keeps those outcomes distinct. Expired and cancelled paid subscriptions do not grant entitlements; only an active, currently valid server-side subscription does. Subscription billing is not integrated; Plus and Pro checkout return unavailable and never activate a plan.

## Migration and verification

Run `alembic upgrade head` from the directory containing the active backend `.env` before starting/deploying the API. Migration `0003_receiver_confirmation_pro` adds nullable receiver-confirmation audit fields and renames stored `premium` plan values to `pro`, preserving existing rows. `create_all()` at API startup creates missing tables but does not apply schema upgrades to existing tables.

Run the backend with `python -m unittest discover -s tests -v`. From `frontend/`, run `npm test` and `npm run build`. Real Mailjet delivery, GPS permissions, location provider calls, camera devices, UPI apps, subscription billing, and real-money settlement require external configuration and device-level validation.
