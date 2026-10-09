# U-Tender Kuwait pilot: launch checklist

This page is for the operator who runs a Kuwait pilot with real owners and service providers. U-Tender itself is ready to use (see Stage 9.13 in `requirements.md`). What remains is configuration that only the operator can do. Every step below uses the admin screens, `backend/.env` or `deploy.sh`. None needs a code change.

A fresh install starts empty, so steps 1–4 are needed before you invite anyone.

## Before inviting the first customer

1. **Serve it over HTTPS.**
   - Customers sign in with passwords and upload Civil IDs and company licences. `deploy.sh` on its own serves plain `http://<ip>:<port>` and warns about it.
   - Put a TLS reverse proxy in front and give `deploy.sh` the public addresses once. It remembers them, binds the app to this machine only, and doesn't open the raw ports. A minimal Caddy example (Caddy obtains the certificates itself):

     ```
     utender.example.com      { reverse_proxy 127.0.0.1:8080 }
     api.utender.example.com  { reverse_proxy 127.0.0.1:8081 }
     ```

     Then run:

     ```sh
     PUBLIC_APP_URL=https://utender.example.com PUBLIC_API_URL=https://api.utender.example.com ./deploy.sh
     ```

   - Secure cookies switch on automatically when `APP_URL` is https. The proxy must be on the same machine (uvicorn trusts forwarded client addresses only from 127.0.0.1, which keeps login throttling per customer).

2. **Types of work** (Admin → Categories).
   - A fresh install has none. Requirements then fall back to free text, and providers have nothing to tick under "Types of work you offer".
   - Add the pilot's trades, for example Construction, Waterproofing, Electrical (MEP), Plumbing, HVAC, Painting & finishing, Facility maintenance.

3. **Verification documents** (Admin → Requirements). A fresh install asks:
   - **owners** for a Civil ID and a **Land Ownership Proof**, both required for every owner;
   - **providers** for nothing at all.

   Before launch:
   - Add what you require from providers, for example *Commercial License*, required, applying to organizations.
   - Decide on Land Ownership Proof. A tenant, facility manager or company buying services has no deed. Make it optional, or apply it only where it fits, or those owners can't get verified.
   - Each document has one name, shown as-is in both languages, so write bilingual names: *Civil ID / البطاقة المدنية*, *Commercial License / الرخصة التجارية*.

4. **How customers reach you** (Admin → Content → `support_contact`).
   - Set an email or phone (or WhatsApp) number in both languages.
   - It is shown wherever the app tells a customer to contact the team: a rejected verification, a suspended account, billing that isn't set up or a failed payment. Until it is set those screens show no contact.

## Provider subscriptions

Pick one route before providers arrive.

- **Online billing (Stripe).**
  - Create the monthly and/or annual prices **in KWD**. Providers see exactly that price before checkout, and tender amounts are always KWD.
  - Set `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID_MONTHLY` / `_ANNUAL`, and **`STRIPE_WEBHOOK_SECRET`**. Without the webhook secret, payments are taken but providers are never activated.
  - Point the Stripe webhook at `https://<api>/billing/webhook`.
  - The admin overview shows whether the webhook is configured and when Stripe last reported anything.
- **Manual access for the pilot.**
  - Leave Stripe unset. Providers then see "Online subscription isn't available yet — the U-Tender team can activate your access", plus your support contact.
  - After approving a provider, grant access in Admin → Service providers → *payment override*. A reason is required and the grant is audited. It can be revoked later.

A provider whose card fails is told so and sent to update the card on their existing subscription. U-Tender refuses to start a second one.

## Email and scheduled jobs

- **Email.**
  - Set `RESEND_API_KEY` and a verified sending domain.
  - Without them nobody receives email: notifications stay in-app only, and password-reset emails aren't sent.
  - The overview shows "Not configured", "Failing" or "No failures recorded".
- **Deadline reminders.**
  - Call `GET /cron/deadline-reminders` hourly with `Authorization: Bearer $CRON_SECRET`, for example from root's crontab.
  - `deploy.sh` doesn't schedule it. The overview shows reminders as overdue when it isn't running.
- **Backups.** `deploy.sh` installs the daily backup.
  - Set `BACKUP_ENCRYPTION_KEY_FILE` and `BACKUP_RSYNC_TARGET`, and keep the key off the server.
  - Rehearse one restore (see `disaster-recovery.md`).
  - The overview's Backups line must show a recent success.

## First-day check

Do one complete round yourself, on a phone, with test accounts:

1. Owner signs up, verifies, publishes a requirement with a drawing.
2. A provider verifies, is given access, finds the requirement, asks a question and sends an offer.
3. The owner answers, closes offers and awards.
4. Both parties record start and completion, and review each other.

Then check that **Admin → Overview** shows every section available, with nothing unexpected under "Needs attention".

## What the pilot does not include

Tell customers about these limitations up front:

- **No matching and no in-app chat.**
  - U-Tender does not recommend providers.
  - Questions go through the requirement's Q&A, and contracts and payments are settled between the parties outside U-Tender (the agreement panel says so).
- **No government identity integration.**
  - Verification is a document review by your team.
  - There is no phone-number field. Contact goes through the platform and email.
- **Accepted file types.**
  - Requirement and offer files: PDF, DWG, XLSX, DOCX, JPG/PNG or ZIP.
  - Older `.xls` / `.dxf` files go inside a ZIP. Uploads are limited to 50 MB each (`MAX_UPLOAD_MB`).
- **Times are Kuwait time.** Deadlines are entered and shown in Kuwait time (UTC+3), whatever the device's own timezone.
