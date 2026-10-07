# U-Tender — Requirements and features (Stages 1–4)

Stages 1 and 2 were built before the Stage 3–4 work and are reconstructed here
from the code and test suite. Stages 3 and 4 record what was built against the
numbered prompts (3.1 … 4.10). Stage 5 (offer submission and competition) will
be added as its prompts (5.1, 5.2, …) are delivered.

---

## Stage 1 — Platform foundation

### Accounts & security

- Sign up as owner or service provider; admin accounts are separate.
- Email verification with single-use tokens; resend is skipped if already verified.
- Forgot/reset password: single-use tokens, and the reset response never reveals whether an email is registered.
- Change password signs out other sessions; a reset signs out all of them.
- Short-lived access cookies plus refresh tokens; logout revokes the refresh token.
- Login locks after repeated failures, counted per account.
- Production refuses default secrets; the cookie `Secure` flag follows configuration.
- A request-size cap also covers uploads sent without a declared length.
- Interface language (EN/AR) is saved per user.

### Marketplace access (providers)

- Two gates: verification approved, then payment active.
- Payment is a Stripe subscription (checkout, billing portal, webhook) or an admin override that is audited and needs a reason.
- Status shown to the provider: documents incomplete → submitted → changes requested / rejected → payment required → active / suspended.
- An approved but unpaid provider can browse the feed; opening a requirement, downloading documents and bidding need full access.
- A suspended provider is blocked everywhere, even with an active subscription.

### Tendering engine

- Two tender types:
  - **Owner-visible:** the owner sees offers as they arrive.
  - **Sealed:** amounts, identities, messages and offer history stay hidden until the deadline, from every route including questions.
- One offer per provider per requirement. Revising keeps a full revision history; withdrawing is also recorded.
- Deadlines are enforced by the server, including the exact instant.
- The requirement row is locked for every offer, close and award, so simultaneous actions can't both succeed.
- Award: one winner, the other live offers are rejected, and a permanent award record is kept. The awarded provider can view it.
- The owner can review the winning provider after award.

### Documents & storage

- Uploads: drawings, PDF, images, `.dwg`, Excel, Word, and zip files (entries extracted, unsafe names normalised, disallowed types skipped).
- Re-uploading the same file name creates a new revision; the full history is kept and the zip contains the current versions.
- Storage is local disk or S3, switched by configuration alone, with HMAC-signed expiring links.

### Admin

- Review queue; approve, reject or request changes on providers and owners; set and clear document expiry.
- Suspend, reactivate or delete users. Deletion is blocked where history (offers, reviews) would be lost.
- Edit or suspend projects and offers. Edits respect the sealed rule; an awarded offer can't be edited.
- Admin-editable checklist of verification documents (optional or required, with effective dates).
- Audit log with previous and new values.

### Public site & notifications

- Public homepage CMS in EN/AR, editable by admin, with defaults and reset.
- Live stats (open tenders, total awarded value) and public pricing taken from the Stripe configuration.
- In-app notifications with unread count, mark-read and read-all, plus emails, rendered in each user's language.
- Deadline-reminder job notifies the owner's team.

---

## Stage 2 — Onboarding, identity & verification

- **Public onboarding:** role explainers, the live document checklist per role, real prices, and the chosen role carried through signup.
- **Stakeholder identity:**
  - Every account declares whether it represents an individual or an organisation (legal name, authorised representative, position).
  - An organisation holds many people; members join by emailed invitation and can be removed.
  - Members act through the organisation's verified profile.
- **Shared organisation records:** an organisation's requirements, offers, attachments and questions belong to it. A member who leaves loses access; the organisation keeps the work.
- **Verification policy:**
  - Admin defines the documents per role and stakeholder type; no document type is named in code.
  - Policy changes apply to new verifications, not to past approvals.
  - Correction and resubmission; expiry dates required where the policy says so.
  - Users can't verify themselves; verification documents stay private.
- **Owner verification:** owners must also be approved before posting.
- **Arabic everywhere:** every server message has an Arabic translation, enforced by a test.

---

## Stage 3 — Requirements (owner side)

### 3.1–3.10 Building a requirement

- **3.1 Start:** a draft is created under the owner's stakeholder (individual or organisation); repeated submission of the same start creates one draft.
- **3.2 Basics:** title, type of work (platform category or free text), location, description.
- **3.3 Scope of work:** long-form, keeps line breaks, with a length limit.
- **3.4 Pricing basis:** one total, or per item with quantity, unit and specification.
- **3.5 Site:** governorate and area are public; the exact address is shown only to providers who can open the full requirement.
- **3.6 Documents:** type (drawing, BOQ, specification, photo, site, other), "essential for pricing" vs supplementary, remove or relabel while still a draft.
- **3.7 Dates:** the response deadline (the one the server enforces) is separate from the expected work start, completion and duration.
- **3.8 Response requirements:** price, completion period, technical approach, assumptions, named documents and declarations, each required or optional and enforced on offers.
- **3.9 Eligibility:** organisations only, platform-approved qualifications, must serve the type of work, must serve the governorate. The same rule decides what the provider is told and what the server enforces.
- **3.10 Tender rules:**
  - Offer type: sealed or owner-visible.
  - Questions: allowed or not, with a cut-off before the offer deadline.
  - Commercial conditions: offer validity, payment stages adding up to 100%, retention, warranty.
  - Other conditions and instructions to bidders.

### 3.11–3.14 Draft to published

- **3.11 Drafts:**
  - Save incomplete and resume; a "your drafts" prompt when starting a new one.
  - Discard deliberately; a draft whose deadline passes expires.
  - A save from an out-of-date page is refused instead of overwriting.
  - Drafts are never visible to providers.
- **3.12 Quality check:** errors block publishing, warnings advise, scaled to how complex the requirement is.
- **3.13 Preview:**
  - Built from exactly the record a provider will receive, including the offer form.
  - An audience count shows how many verified providers the eligibility rules reach and which rule excludes how many.
- **3.14 Publish:**
  - One guarded step: once only, with a server-recorded publication time and an audit entry.
  - Matching providers get an in-app notification and email in their language.
  - In-app confirmation dialogs replace browser pop-ups.

### 3.15–3.18 After publication

- **3.15 Control:**
  - Pause and resume with a reason shown to providers; nothing is accepted while paused.
  - Extend the deadline; once bids exist it can never move earlier.
  - Close early, recording when offers stopped. A sealed tender can't be closed before its deadline.
  - Each amendment is numbered and announced, and classified as material or not.
  - A material change needs at least 3 days to the deadline, or an extension in the same change.
  - Providers confirm or revise their offer after a material change.
- **3.16 Endings:**
  - Cancel (not needed / postponed / other), close outside U-Tender, or no suitable offer. All are final, keep the offers and create no award.
  - The owner's private note is never shown to providers.
  - "Start a new draft from this" copies the content, documents included, and links back to the original.
  - Providers who were told about the requirement are notified, in-app and by email, if it ends early.
  - Sealed offers stay sealed until the deadline even after an early ending.
- **3.17 Version integrity:**
  - Every change keeps before/after values; each material change starts a new version.
  - Any past version can be rebuilt with the documents current at that time.
  - Each offer, and each earlier submission of it, records the version it priced.
  - Material changes also reach providers who asked about or were told about the requirement.
- **3.18 Lifecycle integrity:**
  - Ended requirements can't be reopened by anyone.
  - Admin edits follow the owner's rules and are recorded as amendments.
  - Admin suspension blocks every provider action; both sides see that it's suspended.
  - The admin suspend and edit actions take the requirement lock and are audited.

---

## Stage 4 — Provider discovery & access

### Finding opportunities

- **4.1 Feed:**
  - Shows only open, not-suspended, before-deadline requirements the provider is eligible for, or already bid on.
  - Paged in the database; an empty state says how many were left out because their conditions don't match.
- **4.2 Search, filter, sort:**
  - Every word must match, across title, area or governorate (EN/AR names), type of work, and the scope only for paid providers.
  - Arabic letter variants, diacritics and digits are normalised; word endings are trimmed.
  - EN↔AR synonyms for types of work; typo tolerance; light Arabic roots.
  - Words of 1–3 letters must start a word; `%` and `_` are taken literally.
  - Filters: type of work, governorate, my types of work, my service areas, at least 3/7/14 days left, accepting offers now.
  - Sorts: closing soonest, closing latest, newest, best match (exact matches rank first).
  - All state lives in the URL; "clear" resets; eligibility is applied in SQL and checked against the Python rules by a parity test.
- **4.3 Card:**
  - Title, area, type of work, opening of the scope (paid providers only), pricing basis, items and documents count.
  - Sealed badge, publication date, work timing.
  - Full deadline in Kuwait time, labelled when the device is elsewhere; time left counted from the server's clock.
  - "Who can respond · you meet these".

### Understanding & access

- **4.4 Full view:**
  - One record shared with the owner preview.
  - Rules stay visible while paused or ended; the outcome label is precise.
  - "Added after publishing" markers and file sizes on documents.
  - Providers who can't open the full requirement see what it is at listing level, with the reasons or an "activate access" prompt.
- **4.5 Eligibility verdict:**
  - One server answer, in this order: lifecycle → account standing (verification, suspension) → requirement conditions → marketplace access.
  - Reasons are split into "you can put these right" and "this opportunity's conditions".
  - A requirement hidden by U-Tender reveals nothing beyond being temporarily unavailable.
- **4.6 Documents:**
  - Links last an hour and are re-issued on every authorised read.
  - The real file name is signed into the link, so it can't be swapped.
  - PDFs and images open in the browser, everything else downloads; no type sniffing or caching.
  - Pages refresh their links automatically.
- **4.7 Clarifications:**
  - Ask from the opportunity; repeated submission of the same question creates one.
  - Answers are owner-only, recorded once under a lock, with who answered.
  - Shared Q&A never shows other providers who asked; the owner can share a privately asked question.
  - Providers involved are notified when an answer is shared.
  - Attachments on questions and answers, up to 5 each.
  - An amendment can be linked to the question that prompted it; the cut-off and lifecycle are enforced.

### Deciding

- **4.8 Save / watch:**
  - Idempotent save and unsave from the card or the page, shared within an organisation.
  - Only discoverable opportunities can be saved.
  - The Saved page shows each item's current state (open, paused, ended, unavailable) and never presents something as available when it isn't.
- **4.9 Participate:**
  - An explicit "Participate — prepare an offer" step, checked on the server under the requirement's lock.
  - Recorded once; submitting an offer counts as participating.
  - Flagged if the requirement changes after the decision.
  - Dashboard shows "Preparing an offer". Declining requires no action.
- **4.10 Integrity:**
  - End-to-end test of the whole journey through suspension, extension, amendment, cancellation and expiry.
  - Every bypass attempt refused: other IDs, other organisations, guessed IDs, manipulated parameters, re-labelled links.
  - A suspended provider account is told it is suspended.

---

## Stage 5 — Offer submission & competition

_To be filled in as prompts 5.1, 5.2, … are implemented._
