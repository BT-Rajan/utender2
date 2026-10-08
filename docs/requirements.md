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

- **5.1 Start an offer:**
  - "Participate — prepare an offer" creates or reuses exactly one offer workspace per provider stakeholder and requirement, shared within an organisation, enforced by the database (per provider and per organisation) and under the requirement's lock.
  - Checked on the server at that moment: signed in as a provider acting for their stakeholder; requirement exists, is published, open, not paused or suspended, and before its deadline by the server's clock; eligible; verified with marketplace access.
  - Bound to the requirement, its current version (material revision), the stakeholder, and the user who started it.
  - After a material amendment the provider confirms they've reviewed the current requirement before continuing; the offer is always prepared against the current version.
  - Refusals say why: no longer accepting offers (and when the deadline passed, that), paused, temporarily unavailable, not eligible, verification or access needed.
  - The offer page states "You are preparing an offer for [requirement]".

- **5.2 Offer identity & draft:**
  - Participate creates the provider's one offer as a **draft**, using the existing offers record and status model with a `draft` state added. The same row is completed on submission, so an offer keeps one ID from start to finish.
  - The draft belongs to the requirement, the version it was started on, the provider stakeholder (the organisation for members), the user who started it and the user who last changed it. It is found by who is asking, never by an ID sent from the browser.
  - Persistent: refresh, leaving, logging out and in, or returning later all find the same draft; leaving never submits it.
  - Private: owners, competitors, admin lists and moderation, offer counts, "my bids" and lifecycle decisions (closed vs expired) never see a draft. It can't be withdrawn, confirmed, edited by an admin or awarded.
  - One per stakeholder and requirement, enforced by the database for both provider and organisation, and decided under the requirement's lock. Organisation members share it.
  - Lifecycle: extending keeps the same draft; after an amendment the draft moves to the current version only once the provider has seen it, and draft holders are notified as people preparing an offer; suspension preserves it; closed, expired or cancelled leave it a draft, never an offer.

- **5.3 Commercial / price:**
  - The provider saves the price on their offer draft with "Save draft", without submitting. They can leave, return, and edit it until they submit.
  - It follows the requirement's pricing basis (Stage 3.4):
    - **One total:** a single amount above 0, with no item table.
    - **Per item:** a rate for each of the requirement's own items. The server multiplies rate by quantity (or uses the rate alone for items with no quantity), rounding to 3 decimals. The offer total is the server's sum, set only once every item is priced, and a total sent by the browser is ignored.
  - Rejected: anything not a number, negative values, more than 3 decimals, totals beyond the limit, items not in this requirement, and the same item twice.
  - The currency is the requirement's (KWD, set on the server); the provider can't change it, and nothing is converted.
  - Saves are refused when the page is out of date (another tab or team member saved since it was opened), and while the requirement is paused, suspended, closed, past its deadline or changed since the provider last reviewed it. Saves are also refused once the offer is submitted. A draft started before a material change also can't be submitted directly until the provider has reviewed the current requirement.
  - Pricing basis, items and quantities can't change after publication (Stage 3.4), so a saved price always refers to the current items.

- **5.4 Technical response:**
  - The technical response is the requirement's own "Technical approach / method" (Stage 3.8): how the provider will do the work and how it meets the scope, item specifications, deliverables and instructions to bidders. It's free text up to 10,000 characters with line breaks kept, not a fixed template.
  - It is saved on the same offer draft as the price ("Save draft" saves both). The provider can leave, return and edit; nothing is submitted, and a price save leaves the technical response untouched (and the reverse).
  - The owner's required/optional setting (Stage 3.8) is enforced when the offer is submitted, not while drafting.
  - Saving has the same checks as 5.3: the provider's own side's draft only, found on the server; refused from an out-of-date page; refused while the requirement is paused, suspended, closed, past its deadline or materially amended and not yet reviewed. No requirement field can be changed through it.
  - The form points the provider to the item specifications and instructions to bidders when the requirement has them.

- **5.5 Delivery / completion commitment:**
  - The provider commits in the requirement's own terms (Stage 3.7): a proposed start date, and either a completion date or a duration in days. The free-text "completion period" (Stage 3.8) stays for anything else.
  - It is saved on the same offer draft ("Save draft" saves price, technical response and timing together), and the provider can leave, return and edit. Nothing is submitted, and the price and technical response are untouched.
  - Validated by the same rules as the owner's timing:
    - real dates;
    - a completion date or a duration, not both;
    - a duration of 1–3,650 days;
    - completion not before start;
    - no start or finish before offers close, measured from the server's response deadline.
  - Where it differs from the owner's expected timing (starts later, finishes later, takes longer), it is kept exactly as entered and flagged to the provider. Once submitted, the owner sees it too, but not while a sealed tender is still open.
  - A required completion period is met by the free text or by a committed completion date or duration.
  - Earlier commitments stay in the offer's revision history.
  - Saving has the same checks as 5.3/5.4 (own side's draft only, up-to-date page, open requirement, amended timing reviewed first). The owner's timing can't be changed through the offer API.

- **5.6 Supporting documents:**
  - The provider attaches only the documents the requirement asks for (Stage 3.8 document list, set by the owner). There's no universal list.
  - Uses the existing private file store: allowed file types only (no zip), empty files refused, and the platform's request-size cap. Files are stored under a server-made key, never under the uploaded name.
  - Each document belongs to the provider's offer (the draft, or the offer it became), the requirement, the provider or organisation, the user who supplied it, and the requirement version it was supplied against.
  - Attaching starts the draft if the provider has none yet. Nothing is submitted, and the price, technical response and timing stay as they are.
  - Upload, view, replace (same document name) and remove while the requirement is open. Removing has the same checks as uploading: an active account, eligibility, and the provider's own side only.
  - Links last an hour, are issued fresh on every authorised read, and carry the real file name signed in. Pages refresh them automatically. Other providers can't list or open them, and neither can the owner until the offer is submitted (and unsealed).
  - Owner requirement documents and provider offer documents stay separate.
  - After an owner document change (material amendment): the provider sees the current document, the earlier version stays on record, the provider's earlier documents keep their version, and new ones wait until the change has been reviewed.
  - Suspended, closed, expired or cancelled requirements: documents are kept and still viewable, but can't be changed.

- **5.7 Assumptions, exclusions & clarifications:**
  - The provider states what their offer depends on, what it excludes, qualifications, departures from the specification needing owner acceptance, and other commercial or technical clarifications. This uses the offer's existing "Assumptions, exclusions & clarifications" field (Stage 3.8): free text up to 10,000 characters, line breaks kept, optional unless the requirement says otherwise.
  - It is saved on the same offer draft ("Save draft" saves every part together). The provider can leave, return and edit, and nothing is submitted. Price, technical response, timing and documents stay intact.
  - Kept exactly as written; never interpreted or accepted by the platform. The owner receives it with the submitted offer (not while sealed), and earlier wording stays in the offer's revision history.
  - Separate from requirement questions (Stage 4.7 Q&A): nothing entered here becomes a question or a message, and the form says where to ask about the requirement.
  - Saving has the same checks as 5.3–5.6 (own side's draft only, up-to-date page, open requirement, amendment reviewed first). No requirement field can be changed through it.

- **5.8 Offer validation / quality gate:**
  - `GET /projects/{id}/offers/draft/check` answers "Ready to submit" or "Cannot submit yet", listing every issue by part of the offer: requirement, account, eligibility, price, technical, timing, documents, declarations. Messages are in the provider's language.
  - It checks only what this requirement asks for (Stage 3.8), by the same rules submission enforces:
    - the price on the requirement's basis (a valid total, or a rate for every item);
    - the technical approach, a completion period and documents, each only when the requirement makes it required;
    - every declaration accepted;
    - the saved start/completion commitment still valid now.
  - Optional parts never block.
  - It is re-judged every time, as things stand now:
    - the requirement is open, not paused or suspended, and before its deadline (by the server's clock);
    - the offer is on the current requirement version (after a material amendment, it must be reviewed first);
    - the provider is verified, not suspended, has active access, and still meets the requirement's eligibility rules.
  - Read-only and private to the provider's side. Drafts can always be saved incomplete. Declarations can now be saved on the draft too.
  - It grants nothing: submission repeats its own checks under the requirement's lock, now including the saved timing. A stale "ready" or a direct API call can't get round it.
  - Not an evaluation: no scoring, ranking or judgement of quality.

- **5.9 Offer preview:**
  - "Preview offer" shows the provider's saved draft exactly as submitting would send it:
    - the requirement it answers (title, area, deadline, version and latest amendment, pricing basis, scope on demand);
    - who it's from;
    - the price (each item as quantity × rate with its line total, and the total, in the requirement's currency);
    - the technical approach;
    - the start/completion commitment with any conflicts against the owner's timing;
    - the assumptions;
    - each requested document with the file attached, or "not provided";
    - each declaration, accepted or not.
  - Built on the server from the one stored offer on every request (`GET /projects/{id}/offers/draft/preview`); there's no separate preview copy. Edit → Save → Preview → Back to edit → change → Save → Preview always shows the latest saved values. The form stays open behind the preview, so nothing typed is lost.
  - Carries the Stage 5.8 verdict: "Passed the current checks — ready to submit", or "Cannot submit yet" with each issue and a "Go to section" link back to that part of the form. It never implies ready when the offer isn't.
  - After a material amendment, it shows the current requirement and flags that the offer predates it (not ready until reviewed).
  - Only the provider's own side's offer, on a requirement they may open; anything else is not found. Documents are listed through the usual short-lived signed links, never storage paths.
  - Previewing submits, seals and locks nothing.

- **5.10 Save / resume:**
  - "Save draft" saves the whole form in one step (`PUT /projects/{id}/offers/draft`): price, technical approach, assumptions, declarations and timing. Every part is checked by its 5.3–5.8 rule before anything is written, so a save lands whole (one new draft version) or not at all. A failure, refresh or retry never leaves a half-saved draft or a false "changed somewhere else" conflict. Documents are attached separately (5.6).
  - Resume: the same draft after a refresh, leaving, or logging out and in; opening the requirement again never creates another. The offer page shows "Draft — not submitted · started … · last saved …". Feed and Saved cards say "Offer in progress", and the dashboard's "Preparing an offer" shows when each was last saved.
  - Typed-but-unsaved changes are marked "Unsaved changes", and the browser asks before the page is left or refreshed. No autosave.
  - Organisation members share the one draft. A save from an out-of-date tab, a colleague's older copy or a repeated request is refused (If-Match), never merged or overwritten.
  - On resume everything is re-judged as it is now:
    - the current deadline is shown (saving never moves it);
    - after a material amendment, saving, "ready" and submitting wait for the current requirement to be reviewed;
    - suspended, past-deadline or cancelled requirements keep the draft as saved but allow no saving or submitting.
  - Saving never submits, seals, or shows the draft to the owner or competitors.
  - Offer timestamps are sent as explicit UTC instants.

- **5.11 Submit offer:**
  - Draft → Validate → Preview → Submit: "Submit offer" asks for confirmation, saves the form, then submits the stored draft exactly as previewed (`POST /projects/{id}/offers/draft/submit`, If-Match the saved draft version). A colleague's or another tab's later change is never submitted unseen.
  - Everything is re-checked at that moment, on the server, under the requirement's lock (the lock every close, pause, suspension, amendment and deadline sync takes), so one outcome wins any race:
    - signed in, acting for the stakeholder, the offer belongs to them;
    - requirement open, not paused or suspended, before its deadline (strictly: exactly at the deadline is too late);
    - still eligible, with active access;
    - still a draft, on the current requirement version;
    - then the full Stage 5.8 gate on exactly what will be committed.
  - Atomic: one commit, or a rollback leaving the draft exactly as saved (still a draft, no submission time, the tender type not locked).
  - Once only: a repeated request, another tab or a colleague gets "already submitted". There's one offer row per provider and organisation.
  - The direct submission route (`POST /projects/{id}/offers`, also used for revisions) runs the same final gate.
  - After submission:
    - the offer has `submitted_at` (when first submitted), and the provider sees "Offer submitted" with the time, the revision number, and that it can be updated or withdrawn until offers close;
    - it appears in "my bids", and the owner gets it through the existing offer list (sealed tenders reveal nothing until the deadline, ordered by submission time);
    - competitors can't reach it.
  - Notifications: the owner gets "New offer" on the first submission only. Later revisions send "Offer revised" (an existing notification type that had no template yet). Nothing is sent for a failed submission.

- **5.12 Sealed offer / confidentiality integrity:**
  - Audited every read route of the API. Once a provider has submitted, nothing of that offer reaches another provider, an unrelated owner or an unverified account: no price, item prices, technical approach, timing, assumptions, documents, or even the provider's identity. This holds whatever IDs are put in the path (their own, the offer's, the document's, the provider's, the organisation's, guessed version numbers), in every requirement state: open, suspended, extended, amended, closed at its deadline, cancelled, and ended outside U-Tender.
  - The owner gets offers only through the owner workflow, for their own requirements. A sealed tender reveals content and identity only once its deadline has passed; ending it early never opens it.
  - The provider always has their own offer. Offer documents are reachable only through short-lived signed links issued to someone authorised; a forged or re-pointed link is refused.
  - Platform admins see all offers for oversight, by existing design.
  - The award outcome is shown to the requirement's bidders after award, also by existing design.
  - A permanent regression test sweeps every read route with every known ID as a competitor, an unrelated owner and an unverified account, so a future route can't leak an offer unnoticed. It checks itself against the routes that should show the data.
  - The opportunity card's "offers so far" count (including for sealed tenders) is an existing design choice and was left as is.

- **5.13 Edit / replace / resubmit before deadline:**
  - Existing rule kept: until offers close, a submitted offer can be revised, or withdrawn and resubmitted. It's always the same offer row, so there's one current offer per provider (organisation) and requirement. Each revision is recorded.
  - Revising goes through the existing route (`POST /projects/{id}/offers`) with the same server checks as submission: the lock, the server deadline (exactly at the deadline is too late), open and not paused or suspended, eligibility, the Stage 5.8 gate on exactly what would be committed, and the review step after a material amendment. On failure, the current submission is untouched.
  - The whole offer can be revised, including the start/completion commitment (applied only when sent).
  - Each earlier version is kept in full in the offer's history (seen by the provider, and by the owner once unsealed): price, items, method, timing, assumptions, declarations, the documents that went with it (names; the files are never deleted), the requirement version it answered, and when and by whom it was submitted.
  - Documents replaced while preparing a revision don't reach the owner until the revision is submitted. The owner sees the documents of the current submitted version.
  - A revision from a page showing an earlier revision (another tab, a colleague, a retried request) is refused (If-Match on the revision number), never overwritten. Simultaneous revisions: one wins.
  - "Update offer" asks for confirmation and says the previous version stays in the history. Competitors and sealed rules are unaffected.

- **5.14 Withdraw offer:**
  - Existing rule kept: a submitted offer can be withdrawn only while offers are open. That means before the deadline (exactly at it is too late) and not when paused, suspended, closed early, cancelled, ended or awarded. It's decided on the server under the requirement's lock, so it can't race a close or an award.
  - Only the provider's own side's offer. IDs in the request are ignored; drafts and other providers' offers aren't withdrawable.
  - Nothing is deleted: the offer keeps its content, documents and files. The submitted version goes into the history, and the withdrawal time and who did it are recorded.
  - A withdrawn offer can't be awarded and doesn't count as a live offer at the deadline (a requirement with only withdrawn offers expires).
  - The owner sees it as withdrawn; sealed tenders still reveal nothing.
  - Once only: a repeat, a retry or a second tab is refused.
  - Resubmission works as before (same offer, recorded in the history).
  - The page asks for confirmation, then shows "Offer withdrawn" with the time. The button becomes "Submit again" while offers are open.
  - The owner isn't notified of a withdrawal: the existing `bid_withdrawn` notification type was never wired up and is left as is.

- **5.15 Deadline / concurrency / submission integrity:**
  - Every route that changes an offer or starts one runs under the requirement's row lock (the same lock the owner's close, pause, cancel and amend, the admin's suspend, the award and the deadline sync take). These are: participate, draft saves, document attach/remove, submit, revise, confirm and withdraw. Each is judged at that moment by the server's clock (exactly at the deadline is too late) and the requirement's current lifecycle. No client-supplied time is consulted.
  - One outcome per race:
    - two submissions: one, the other "already submitted";
    - revise vs withdraw: both applied in order, or the stale one refused;
    - submit vs suspend or close: accepted before it, or refused after it;
    - award vs offer suspension: never an award of a suspended offer.
  - Submission is atomic (the final Stage 5.8 gate on exactly what is committed, or a full rollback). Retries and old tabs are refused with If-Match. The offer keeps the requirement version it was made against until it is revised.
  - Fixes:
    - the admin's offer suspend and delete now take the requirement lock;
    - confirming an offer after an amendment re-checks its start/completion commitment, which an extended deadline may have invalidated (then it must be revised);
    - the offer page re-reads the server's state after any refused submit, revise or withdraw.

- **5.16 Provider offer history & status:**
  - "My bids" lists each offer the provider's side has put forward, once each. Drafts appear only under "Preparing an offer"; a withdrawn offer is no longer listed there as well.
  - Each entry shows its status as the provider sees it (offer placed, revised with its revision number, withdrawn, awarded, not selected), the requirement's outcome (open, suspended, closed, cancelled, ended outside U-Tender, no award, awarded), and when it was first submitted and last changed (UTC).
  - Bounded: most recent first, 200 per page (up to 500), with an offset.
  - After offers close, the provider can still open their own offer in full, read-only (the same stored record as the preview), with its earlier versions as submitted.
  - Only their own side's offers; organisation members share them; never another provider's.

- **5.17 Final integrity audit:** all of 5.1–5.16 verified end to end (authorization, confidentiality, lifecycle, deadline/concurrency, version history) on SQLite and MySQL. Stage 5 ready. Follow-ups on the audit's limitations:
  - **Withdrawal notice:** the owner's team is notified when an offer is withdrawn, anonymously while the tender is sealed.
  - **Sealed offer count:** while a tender is sealed and open, competitors aren't told how many offers are in. Cards and requirement details show "sealed"; the owner still sees the count.
  - **Dashboard totals:** active, won and total offers come from `/service-provider/my-bids/summary`, counted by the database over all offers, so they stay right however many pages the list has.
  - **Earlier-version files:** each version in an offer's history links to the files that went with it (short-lived signed links, never storage paths), for whoever may read that history.
  - **One clock:** deadlines are judged by the database's clock (`UTC_TIMESTAMP` on MySQL), read under the requirement's lock, along with the expiry sweep and publishing. Every app server agrees.
  - **Safe rollback:** a downgrade below 0039 is refused before anything changes while any draft holds a provider's work, unless `ALLOW_DRAFT_LOSS=1` is set.
  - **By design:** platform admins see all offers for oversight.

## Stage 6 — Offer evaluation & award

- **6.1 Owner offer inbox:** `GET /owner/projects/{id}/offers`, shown on the owner's requirement page.
  - The offers put forward on that requirement only: drafts and admin-suspended offers are left out. An offer id from another requirement, or a suspended offer, isn't found by its history either.
  - Only the requirement's owner side (its organisation's members, or the individual owner) can open it. Anyone else gets "not found". Admins use their own offer oversight.
  - Each offer shows its provider, its status as the server holds it (received, withdrawn, awarded, not selected), when it was submitted and its revision. A withdrawn offer is listed after the live ones, dimmed, and can't be awarded.
  - Sealed and before the deadline (including one ended early): only that offers are in, as a count of live offers plus how many were withdrawn. No provider, price, response, documents or history.
  - Stays readable after the requirement closes, ends, expires or is awarded. Reading it never changes the requirement.
  - Bounded: 200 per page (up to 500), with an offset, in a fixed order: live first, then by submission time and id (Stage 6.7: never by price).
  - The page shows "couldn't load the offers" on an error, never "no offers", and "no offers were received" once offers have closed.

- **6.2 Offer access & confidentiality:** all offer read paths were traced: the owner workflow, the provider's own-offer routes, admin oversight, the offer-document file route, the award record and notifications.
  - Every offer read is authorised on the server, for the specific requirement. The owner side (organisation members, or the individual owner) reads its own requirement's offers. A provider reads only its own side's offer. Admin routes need the admin role, which can't be self-assigned at sign-up.
  - Ids from another requirement, another owner or another provider find nothing. Removing a member takes away their access on their very next request.
  - Offer documents are reached only through short-lived signed links (Stage 4.6), issued only to someone who may read the offer. A forged or re-pointed link is refused.
  - **Withdrawn offers:** the owner sees who withdrew and when, never the content (price, items, response, timing, assumptions, documents or history). This also means a sealed offer withdrawn before the deadline isn't opened at the deadline. The provider keeps their own in full.
  - **Offer document links are checked on every click** (follow-up). Offer lists no longer contain signed links. Each document points to a download route: `/owner/projects/{id}/offers/{offer}/documents/file` for the owner, and `/projects/{id}/offers/mine/documents/file` or `/projects/{id}/offers/documents/{doc}/file` for the provider.
    - Each click checks access again on the server: membership as it is now, the offer not withdrawn or suspended, the seal lifted.
    - Only then does it redirect to a signed link that lasts one minute, using the same signed-link mechanism.
    - Files are found by label and version within the caller's own offer, never by a path from the request.
    - A link kept by someone who has since lost access no longer opens.
  - **By design:** admins see all offers for oversight. On a sealed tender, the owner choosing to close bidding early opens the offers (the page says so). Cancelling or ending it early does not.

- **6.3 Offer completeness & status:**
  - Offer statuses are the existing ones: draft (never shown to the owner), submitted (shown as "received"), withdrawn, awarded and not selected.
  - One offer per provider side: a revision updates it (version N). Earlier versions are kept in its history.
  - An offer reaches the owner only after passing the Stage 5 submission gate. That gate checks completeness against the requirement's own response rules (frozen once published) and the provider's eligibility.
  - Each offer keeps the requirement version it answered. An amendment flags it as made on the earlier version until its provider confirms or revises it.
  - A withdrawn offer is listed as withdrawn, can't be awarded, and its history is kept.
  - The inbox shows how many offers were received, how many are active, withdrawn and revised, counted from the server's list.
  - The owner's dashboard, the requirement page and providers' cards count the same offers as the inbox: an admin-suspended offer is left out of all of them.
  - The inbox and requirement state refresh every minute and when the owner returns to the page. A refused action (for example, approving an offer that has just been withdrawn) reloads both, so the page never acts on stale data.

- **6.4 Offer detail review:** `GET /owner/projects/{id}/offers/{offer}`, at `/owner/projects/{id}/offers/{offer}` ("View offer" from the inbox).
  - Same access as the inbox: the requirement's owner side only, the offer on that requirement, unsealed, not withdrawn, not suspended. Anything else is not found; providers are refused.
  - Shows the stored record exactly as submitted, with nothing recalculated: provider, status, when it was submitted, its version and when it last changed.
    - Price: the total and the item lines (rate, quantity and line total as the provider priced them; items can't change after publishing).
    - Technical response, start, completion or duration, and the completion period.
    - Timing flags: where the offer's dates are later or longer than the owner expects.
    - Assumptions; each declaration asked for, with whether it was accepted.
    - Each requested document with the file attached, opened through the owner's authorised download route.
  - Beside it, the requirement it answers. It says which version the offer was made against; if the requirement has since been amended, it says so and links to that version as it stood (Stage 3.17).
  - The offer's earlier versions, each with its own requirement version and files.
  - Same display as the provider's own preview (shared component).
  - Read-only: the route only reads; awarding stays on the requirement page. Refreshes every minute and on returning to the page. Withdrawn, sealed or unavailable offers say so instead of showing stale content.

- **6.5 Requirement-to-offer context:** the existing Stage 3.17 mechanism is the one record of versions; no second versioning was added.
  - **What the versions record:** an offer belongs to exactly one requirement (`offers.project_id`; every owner route checks the requirement and offer ids together). It records the material version it answered (`based_on_material_revision`), and so does each earlier version of it.
  - **What makes a new version:** a material amendment does. That is a change to scope, location, dates or documents, including adding or replacing a document after publishing. A title correction or a deadline extension is not material, so offers stay current.
  - **How amendments affect offers:** an amendment never changes a submitted offer. An offer made earlier shows the version it answered, and the owner's offer page says it was made on an earlier version and links to that version. It becomes current only when its provider confirms or revises it. Earlier versions stay in its history with their own version and files.
  - **Mixed versions in the inbox:** when live offers answer different versions, the inbox says so (listing the versions) before the price figures across them.
  - **Document integrity (fixed):** adding or replacing a requirement document after publishing now commits the file together with its amendment, in one transaction under the requirement's lock. Before, the file was committed first and only tied to the new version in a second step. Until that second step (or if it failed), a replacement file would count as part of the earlier version, so earlier offers would appear to have priced it, and the lock was released early.
  - **Over the requirement's life:** each offer's version stays the same through suspend, resume, extension, closing and ending without an award.

- **6.6 Offer comparison:** `GET /owner/projects/{id}/offers/compare?ids=…`, at `/owner/projects/{id}/compare`. The owner ticks offers in the inbox, then chooses "Compare selected".
  - **What can be compared:** only live offers the owner may review on that requirement: the owner side, unsealed, not withdrawn, not suspended. Any other id (another requirement's offer, a withdrawn or suspended one) is left out and only counted as "no longer comparable", never shown. Providers are refused.
  - **Limits:** 2–10 offers, each once, in the order chosen.
  - **What it shows:** each offer exactly as stored, its current version only (earlier versions stay in each offer's history). Side by side:
    - status and the requirement version answered (flagged if earlier), plus a note when the offers answer different versions;
    - submission time and total in the requirement's currency;
    - for per-item pricing, each item's rate and line total;
    - start, completion or duration, completion period and timing flags;
    - technical response and assumptions, word for word;
    - each requested document, opened through the authorised route;
    - each declaration accepted or not.
  - **Differences:** rows where the offers differ are marked ≠, without saying which is better.
  - **No scoring:** nothing is recalculated, normalised, scored, ranked or recommended.
  - **Freshness:** read-only; refreshes every minute and on returning to the page, so a withdrawal or revision appears as it happens.

- **6.7 Commercial evaluation:**
  - **Already working:** the commercial terms each offer actually holds are shown exactly as stored:
    - the total, in the marketplace currency;
    - on itemised requirements, each item's rate, quantity, unit and line total;
    - assumptions and exclusions.
  - **Pricing basis:** one total for a single-price requirement; per-item pricing only where the requirement is itemised.
  - **Server-side pricing:** totals are computed by the server (line = rate × quantity to 3 decimals, total = the sum). Any total or line total sent by the browser is ignored. Malformed prices are refused (negative, more than 3 decimals, not a number), never stored or rounded.
  - **Same figures everywhere:** the inbox, the offer page and the comparison all build from the same stored record.
  - **Over time:** a revision's price is current and earlier prices stay in the history. A withdrawn offer's price isn't shown. An amendment never changes a price; the offer keeps the version it answered.
  - **Competitors:** never get another provider's price on any endpoint (Stage 5.12 / 6.2).
  - **No price ranking (fixed):**
    - The owner's offer list was ordered cheapest first, which ranked offers by price. It now lists them in the order they came in: live first, then by submission time and id. Offers submitted within the same second are ordered by id.
    - The summary's lowest / average / highest figures stay as plain facts; the lowest is no longer highlighted green.
  - **Not captured:** payment terms and offer validity aren't fields of the offer or the requirement, so they aren't shown. Adding them would be new fields, not evaluation. Providers can state such conditions in assumptions and exclusions.

- **6.8 Technical evaluation:**
  - **Already working:** the owner's offer page (6.4) and comparison (6.6) show each provider's technical response exactly as stored. Wording, line breaks and Arabic are kept; saving trims only outer whitespace.
    - Also shown: completion period, start / completion / duration with timing flags, assumptions, declarations and each requested document. Documents open through the owner's authorised route.
    - Required parts are enforced at submission; optional ones are never forced.
    - Revised, withdrawn and amended offers and competitors behave as in 6.2–6.5.
  - **Fixed, context beside the response:**
    - each item's specification (per-item pricing);
    - a single-price requirement's items of work, with quantities, units and specifications (previously not shown at all);
    - whether the technical response and the completion period were required or optional;
    - a link to the requirement exactly as the offer answered it (scope, dates, documents then), always, not only after an amendment.
  - **No judgement:** nothing assesses, scores or passes/fails a technical response; the owner judges suitability.

- **6.9 Delivery & commitment evaluation:**
  - **Already working:** the provider's start, completion date or duration, and completion period are stored and shown exactly as submitted, on the offer page and in the comparison.
    - They are checked when saved: completion or duration, not both; 1–3,650 days; completion not before start; nothing before offers close.
    - Differences from what the owner expects (later start, later finish, longer duration) are flagged, never changed.
    - Nothing is forced where the requirement sets no timing.
    - Amendments, revisions (history keeps the original dates), withdrawals and competitors behave as in 6.2–6.5. Dates are calendar days shown with the existing date formatting.
  - **Fixed:**
    - The requirement's own expected timing is shown beside each commitment, on the offer page and the comparison's timing row.
    - The owner's pages now speak about the offer ("Starts after the start date you expect"), not to the provider ("You propose…").
    - New `before_close` flag. A deadline extension isn't a material change, so it can leave a still-current offer with dates before offers now close (a state the submission rules forbid). This is now flagged to the owner and the provider (who is asked to revise), never rewritten.
  - **Facts only:** no scheduling, feasibility judgement or scoring.

- **6.10 Clarification during evaluation:**
  - **Before:** the Stage 4.7 clarification system was one-way: a provider asks about the requirement while offers are open, and the owner answers, privately or for everyone. It had no way for the owner to ask a provider about a submitted offer.
  - **Now:** the same `clarifications` record carries the owner's questions about a submitted offer. Migration 0045 adds `offer_id`, `offer_revision` and `asked_by`, plus the notification types `offer_clarification_requested` and `offer_clarification_answered`. No separate messaging system was added.
  - **Owner endpoints:** `GET/POST /owner/projects/{id}/offers/{offer}/clarifications`. Same access as reviewing the offer: the owner side, the offer on that requirement (ids checked together), unsealed, live, not suspended.
    - Asking needs an approved, active owner account and takes the requirement's lock, so it can't race the award or other outcome.
    - A retry of a question still waiting for its answer is the same question.
  - **Provider endpoints:** `GET /projects/{id}/offers/mine/clarifications` and `POST …/mine/clarifications/{c}/answer`. Only for the offer's own side (found from who is asking, never an id from the request), and each question is answered once.
  - **Private:** only the owner side and that offer's side see the question and answer. Offer clarifications never appear in the requirement's Q&A, can't be answered or given files through it, and can't be cited by an amendment. Competitors get nothing.
  - **Offer unchanged:** an answer is text beside the offer. Price, response, timing, documents, assumptions, revision and timestamps stay as submitted. Formal changes are Stage 5 revisions, which aren't possible once offers have closed. Nor can the requirement be amended then, so each question's offer and version context stays fixed; it records the offer version it was about.
  - **When:** only while offers are being evaluated (closed or under evaluation). Not while open, since the provider can still revise formally then. Not after the outcome (awarded, no award, cancelled, expired), and not on a suspended requirement or suspended offer. Answers are given after the bid deadline by nature. The history stays readable.
  - **Notifications and history:** each side is notified through the existing notifications, and each question and answer is recorded in the audit log (who, when, which offer).
  - **Pages:** the owner's offer page (6.4) shows the clarifications and a form to ask while allowed. The provider's read-only offer page shows them with an answer form.
  - **Rollback guard:** a downgrade below 0045 is refused while any offer clarification exists, unless `ALLOW_CLARIFICATION_LOSS=1` is set.

- **6.11 Evaluation notes:**
  - **Before:** there was no notes mechanism for evaluation. The only "notes" were `closure_note` (the owner's private reason a requirement ended), admin notes on verification documents and the audit log (actions, not observations). None could hold notes on an offer.
  - **Now:** one small table, `evaluation_notes` (migration 0046). Endpoints: `GET/POST /owner/projects/{id}/notes` (list all, or `?offer_id=`) and `PUT/DELETE /owner/projects/{id}/notes/{note}`.
  - **Who:** the requirement's owner side only (its organization's members, or the individual owner), in any state of the requirement. Providers, competitors, other owners and the public get nothing.
  - **What a note can attach to:** the requirement, or one of its own offers that has been put forward and isn't admin-suspended. Never a draft, another requirement's offer, or an offer on a tender still sealed (a note on the requirement itself is fine then).
  - **Editing:** members read all the side's notes; each author edits or removes their own, with `If-Match` on the note's version against stale pages. A submission carrying the same client token twice is one note.
  - **Writing access:** writing needs an active owner account and takes the requirement's lock.
  - **History:** author and timestamps are kept, and adding, editing and removing are recorded in the audit log. Notes are kept through closing, expiry, cancellation, ending outside U-Tender and award.
  - **Pages:** a notes panel on the owner's offer page (notes on that offer) and on the requirement page (notes on the requirement).
  - **No judgement:** nothing scores, ranks or interprets.
  - **Rollback guard:** a downgrade below 0046 is refused while any note exists, unless `ALLOW_NOTE_LOSS=1` is set.

- **6.12 Shortlist:**
  - **Before:** there was no shortlist or preferred-offer state. Offer statuses are draft, submitted, approved (awarded), rejected and withdrawn; the requirement has an under-evaluation status but no preference marker. The nearest things were the 6.6 comparison's selection (temporary, in the page) and 6.11 notes (free text).
  - **Now:** an owner-private marker in its own table, `offer_shortlist` (migration 0047), so the provider's offer row is never touched. Endpoints: `GET/PUT/DELETE /owner/projects/{id}/offers/{offer}/shortlist`.
  - **Several at once:** any number of offers can be shortlisted; there's no single winner.
  - **Which offers:** only the owner side's own requirement, and only a live, unsealed, not-suspended offer on it (ids checked together). Withdrawn offers, other requirements' offers and other owners are refused; providers are refused.
  - **When:** only while offers are being evaluated (closed or under evaluation). By then offers can't be revised or withdrawn and the requirement can't be amended, so a shortlisting can't race those or point at the wrong version. Each records the offer version and requirement version.
  - **Concurrency:** changes take the requirement's lock, so they're serialized with closing and award. Add and remove are idempotent: retries, two tabs and colleagues converge, and the last request wins.
  - **After the outcome:** once the requirement is awarded, ends without an award, or is cancelled or expired, the shortlist is frozen and kept.
  - **Not an award:** the requirement and offers stay exactly as they were, nothing is sent to anyone, and providers never see it (the field is empty in every provider-facing response).
  - **Audit:** add and remove are recorded in the audit log. Notes (6.11) stay separate.
  - **Pages:** a shortlist button and badge on the owner's offer page, a badge and count in the inbox, and a row in the comparison.
  - **Rollback guard:** a downgrade below 0047 is refused while any offer is shortlisted, unless `ALLOW_SHORTLIST_LOSS=1` is set.

- **6.13 Award decision:**
  - **Already working:** `POST /owner/projects/{id}/offers/{offer}/approve` awards one live offer.
    - Owner side, active account, under the requirement's lock (serialized with closing, cancelling, a second award, another member or tab), only once offers have closed (closed or under evaluation). The offer must be this requirement's, live and not suspended.
    - One transaction: the winner becomes approved, every other live offer rejected (withdrawn ones stay withdrawn) and the requirement awarded. It writes the award record (one per requirement, enforced by the database) with the offer, its revision, the amount and who awarded, plus an audit entry.
    - Winner and others are notified through the existing notifications.
    - **Final:** a repeat or stale request is refused, and nothing is awarded twice. The offers, the shortlist and the notes are untouched, and new or changed offers are refused.
  - **Fixed:**
    - No award on an admin-suspended requirement.
    - An offer made against an earlier requirement version, not confirmed by its provider since, is awarded only when the owner says so explicitly (`acknowledge_earlier_version`). Otherwise the server returns 409 and nothing changes.
    - The owner's Approve button now asks for confirmation. The dialog states the provider, the amount, that the decision is final (not a contract or payment) and, where it applies, the earlier-version warning.

- **6.14 No-award / reject / close decision:**
  - **Already working:** the Stage 3.16 lifecycle already concludes a requirement without an award, with no new state needed:
    - **No suitable offer:** `POST …/no-award` after offers close; status `no_award`, reason `no_suitable_offer`. This covers prices or technical responses that aren't acceptable, explained in the owner's note.
    - **Ended outside U-Tender:** `…/close-externally`; status `no_award`, reason `closed_externally`.
    - **Cancelled:** `…/cancel`, with the reasons not needed, postponed or other; status `canceled`.
    - **Expired:** reached automatically at the deadline with no live offers. Awarded stays distinct.
  - **How each ending is recorded:** the owner side only, an active account, under the requirement's lock (serialized with the award, another member, another tab or the expiry sweep). It stores the owner's optional note and an audit entry (who, what, why), and notifies bidders and watchers through the existing notifications. The owner's page confirms before each ending.
  - **What stays:** nobody is awarded; offers keep their status and content, and the shortlist and notes stay as they were. The owner still reads the offers.
  - **What's refused afterwards:** new or changed offers, an award, a shortlist change, or another ending. A retry or stale page gets a refusal, never a second outcome.
  - **Fixed:** no ending is recorded while an admin has the requirement suspended, the same rule as the award (6.13).

- **6.15 Decision integrity & concurrency:**
  - **Already guaranteed, one outcome per requirement:**
    - Every decision (award, no award, end outside U-Tender, cancel, close, start evaluation) re-checks ownership, an active account and the requirement's current status under its row lock. So simultaneous decisions, other members, other tabs, double clicks, retries and stale pages settle on exactly one outcome, and the rest are refused.
    - The database allows one award record per requirement. The award writes the record, the offer statuses, the requirement status and the audit entry in one transaction.
    - Withdrawing and revising need offers to be open; awarding and the no-award endings need them closed. Both are judged under the same lock, so a withdrawn or superseded offer can never be awarded. New offers are refused once the requirement isn't open.
    - The expiry sweep locks the rows it changes and skips any being decided (`SKIP LOCKED`), and only moves open requirements on. Nothing moves a requirement out of an ended state.
    - An awarded offer can't be deleted, even by an admin.
  - **Fixed:** an admin could still edit an offer on a cancelled or expired requirement (only awarded or no-award ones were protected). Every ended requirement's offers now stay exactly as they were.
  - **Verified on MySQL:**
    - simultaneous award vs no award, award vs cancel, award vs end outside U-Tender, and no award vs cancel: exactly one succeeds, and the requirement, offer statuses, award record and audit log agree;
    - four simultaneous identical awards make one award;
    - retries and stale requests after an award change nothing.

- **6.16 Provider notification & decision visibility:**
  - **Already working:** providers read the outcome from the authoritative record, not from notifications.
    - **Offer statuses:** approved ("Awarded") for the winner; rejected ("Not selected") for other live offers. Withdrawn stays withdrawn.
    - **Requirement outcome:** shown with its reason on "My bids", the requirement page and the offer page.
    - **Notifications:** the existing in-app and email notifications are sent after the decision is committed: award won and award lost; no award, cancelled or ended to live bidders. While unread they are de-duplicated per page, and withdrawn bidders aren't told they lost.
    - **Private:** the owner's closure note, evaluation notes and shortlist never reach providers. Only bidders can open an ended requirement and its award.
  - **Fixed:**
    - **Winner's price:** `GET /projects/{id}/award` gave every losing bidder the winning offer's price, id and provider id. Other bidders now see only "Awarded to a successful bidder. Best wishes for your future endeavours." (follow-up: not even the winner's name; the same wording in the in-app notification and email). The winner sees `mine: true` with their amount ("Your offer was awarded, at …"); the owner side and admins see everything.
    - **Ended requirements:** an offer still "submitted" on a requirement that ended without an award (no suitable offer, ended outside U-Tender, cancelled, expired) showed "Offer placed" on the dashboard and offer page. It now shows the requirement's outcome, in neutral styling.
    - **Notification failures:** notifications after an award or ending are best-effort. A failure is logged and rolled back, and never fails the owner's request or undoes the decision (previously a server error after a committed decision).

- **6.17 Final evaluation & decision integrity audit:** the whole owner journey was traced end to end: receive → review → compare → evaluate → shortlist → award or no award → provider outcome.
  - **Scenarios** (`tests/test_stage6_17_end_to_end.py`):
    - normal competition to an award;
    - no suitable provider;
    - a withdrawn offer can't win;
    - an amendment keeps each response on its version;
    - the deadline passes while reviewing;
    - a provider probing every owner and provider endpoint with competitors' ids;
    - stale tabs and retries across organisation members;
    - a notification failure.
  - **Simultaneous decisions:** the MySQL race tests from 6.15.
  - **Fixed during the audit:**
    - Losing bidders no longer learn the winner's name (see 6.16).
    - The owner's page reloads the requirement and its offers after a refused ending, close or start of evaluation, as it already did after a refused award. Before, a page refused because a colleague had already decided kept showing the old state and actions. (A draft being edited is never reloaded under the owner.)
  - **Verdict:** Stage 6 ready.

## Stage 7 — Post-award

- **7.1 Award handover:**
  - **Already working:** the award is one permanent record (`award_records`, one per requirement).
    - **What it records:** the requirement, the winning offer and its provider, the amount, the offer's revision, who awarded it and when.
    - **What it sets:** in the same transaction the winning offer becomes approved ("Awarded"), the other live offers rejected ("Not selected"), and the requirement awarded.
    - **Unchanged history:** withdrawn offers stay withdrawn, and revisions, shortlist, notes, amendments and documents are untouched. The post-award view is the same record, not a copy.
    - **Notification:** the winner's links to its own offer page.
    - **Nothing reopens it:** new or changed offers, another award, endings, closing, amendments and the expiry sweep are all refused or skip it.
    - **Access:** losing bidders learn only that it was awarded to a successful bidder; outsiders and other owners get nothing.
  - **Fixed:**
    - **Award time:** `GET /projects/{id}/award` now sends its time as UTC (`…Z`); it was a bare local time that pages would misread.
    - **Version:** it also gives the requirement version the awarded offer answered (`material_revision`), to the owner side, admins and the winner only.
    - **Owner page:** an awarded requirement shows an award summary (who, value, when, which version) with a link to the awarded offer.
    - **Winner's page:** it now says when the offer was awarded.
    - **Document upload:** an awarded (or otherwise ended) requirement's page no longer offers to add documents, which the server refuses once a requirement isn't open.

- **7.2 Post-award transaction record:**
  - **Already working:** the award record is the transaction record, so no second entity was added.
    - It says "owner X awarded requirement Y to provider Z on offer W": requirement, winning offer, provider, amount, offer revision, requirement revision, who awarded it, and when (UTC).
    - It is created in the same transaction as the award, under the requirement's lock, and is unique per requirement, so a retry, double-click or second tab can't make a second record.
    - Its server-generated id is the stable reference.
    - The post-award status is the requirement's status (Awarded) and the winning offer's (Awarded).
    - The currency is the requirement's.
  - **Fixed:**
    - **Who awarded it:** the winner can now see who awarded it, as the owner's organisation legal name or the individual owner's name (`owner_name`). Only the owner side, admins and the winner get it.
    - **Award reference:** the owner's award summary and the winner's offer page show the award reference (the record's id).
    - **Losers:** losing bidders no longer get the record's id.
    - **Winner deletion:** an admin can no longer delete a provider that has won an award. The delete would have cascaded away the awarded offer and left the award record broken. Suspend the account instead, as already applies to deleting the awarded offer itself.

- **7.3 Contract / agreement:**
  - **Audit:**
    - **What already worked (WORKING):** the award record (7.2) already names the parties, the requirement, the winning offer, the value (in the marketplace currency), the scope version and the award reference. Organisation-based access, the requirement lock, audit logging and file storage were all reusable.
    - **What was missing (MISSING):** any record of the agreement itself: where it stands, when it takes effect, the parties' own contract or PO number, and the signed papers.
  - **Added: one agreement per award (`agreements`, migration 0048):**
    - **Creation:** created with the award, in the same transaction as the award record. Every earlier award is backfilled, so no award lacks an agreement and no agreement lacks an award.
    - **Never moves:** it can't be created through the API, re-pointed, or attached to another requirement, offer or provider. A losing, withdrawn or unawarded offer can never have one.
    - **What it reads, not copies:** parties, value, offer and scope version come from the award record. The agreement can neither drift from the award nor rewrite it.
    - **What it holds:**
      - status: preparing → active ("in force") → terminated, or preparing → terminated;
      - effective date;
      - the parties' own reference;
      - termination reason;
      - created and updated times and a version.
    - **Terminating it:** the requirement stays awarded and the award record is unchanged. Completion, variations and payments are later stages.
  - **Who may change it:**
    - **Owner side:** any member of the owner's side records the reference and effective date while preparing. It marks the agreement in force, which needs the effective date first, and it can terminate it with a reason. Organisation members share this, not only whoever made the award.
    - **Stale changes:** a change from a stale tab is refused (409, If-Match on the agreement's version). A repeated activation or termination is refused (400).
    - **Locking:** every change takes the requirement lock and is audit-logged (`agreement.*`).
  - **Documents (`agreement_documents`):**
    - **Who attaches:** either party attaches the signed agreement, a work order, purchase order, final quotation, agreed scope or other paper. These go through the existing storage with the existing file-type checks.
    - **No orphans:** a failed save deletes the stored file, so no stored file is left without a record.
    - **Removing:** a side may remove its own papers only while the agreement is being prepared. Once it is in force or terminated, they stay on record.
    - **Opening:** opened through a one-minute signed link, authorised on every click.
  - **Access:**
    - **Endpoints:** `GET/PATCH /projects/{id}/agreement`, `POST …/activate`, `POST …/terminate`, and `POST/DELETE/GET …/documents`.
    - **Who reads it:** the owner side, the winning provider's side (all members of its organisation) and admins, who can read but not change it.
    - **Who gets nothing:** losing or withdrawn bidders, outsiders, other owners, a suspended account and providers of a suspended requirement get 404, whatever ids they send. Document ids are checked against the requirement in the path.
    - **Writes:** need an approved, unsuspended account; a suspended requirement is frozen.
  - **UI:**
    - **Agreement panel:** an agreement panel under the award summary on the owner's requirement page, and on the winner's offer page. It shows the parties, value, award date, effective date, references, status and documents.
    - **Owner controls:** the owner gets the edit, activate and terminate controls. English and Arabic.

- **7.4 Contract documents:**
  - **Already working (from 7.3):** the post-award papers are the agreement's documents (`agreement_documents`).
    - **Kept apart:** they have their own table and storage bucket, separate from requirement and offer documents. No pre-award file is ever reused as one.
    - **Attached to one agreement:** each document belongs to exactly one agreement, so to one award, one requirement, one owner side and one winning side. Ids are checked against the requirement in the path.
    - **Upload checks:** the existing file-type check, the global upload size limit and safe file names. A failed save removes the stored file.
    - **Opening:** authorised on every click, then a one-minute signed link. The open link alone, without a session, gets 401.
    - **Removing:** a side removes only its own papers, and only while the agreement is being prepared. Once in force or terminated they stay on record, and terminated agreements' papers stay readable by the parties only.
    - **Access:** members who leave an organisation lose access; the organisation keeps it.
    - **The award is untouched:** a document never changes or reopens the award.
  - **Fixed:**
    - **Separate stored files:** each stored file is now keyed by its document's own id. Two uploads of the same name in the same millisecond (owner and provider, or a repeated submit) can no longer share one stored file, where removing one would have removed both.
    - **Certificate type:** added "Certificate" as a document type.
    - **Who uploaded it:** each document now shows the uploading member's name to that member's own side (and admins). The other party still sees only which side it came from.

- **7.5 Execution start:**
  - **Audit:**
    - **Already working:** the planned start existed already: the winning offer's committed start date (Stage 5), or the requirement's expected start. Award, agreement, organisation access, lock, audit and notification were all reusable.
    - **Missing:** any record that the work had started, and any execution status.
    - **Not applicable:** a provider acknowledgement step. None exists, and the agreement (7.3) is where the parties' agreement is recorded.
  - **Added, on the award's agreement (migration 0049):** no new entity.
    - **Start record:** `work_started_at` (server time), `work_started_party`, `work_started_by` and an optional note.
    - **Derived status:** not started, in progress, or terminated, read from the agreement and never stored, so it can't disagree with it.
    - **Planned start:** read from the winning offer, else the requirement, never copied.
  - **Recording the start (`POST /projects/{id}/agreement/start-work`):**
    - **Who:** either party may record it, as any member of the owner's side or of the winning provider's side.
    - **When:** once, at the server's time, under the requirement's lock, with If-Match against stale pages.
    - **Refused:** a repeat or the other party's later attempt (400), a terminated agreement, and anything without an award (404: open, cancelled, never awarded). Admins can only read it.
    - **Termination:** the agreement can still be terminated after the start. The start stays on record and the status becomes terminated.
    - **The award is untouched:** the requirement stays awarded and the award record and winning offer are unchanged.
  - **Notification:** `work_started` goes to the other party's side, linking to its own page. It is sent best-effort after the commit; a failure never undoes the start. Losing bidders get nothing.
  - **Audit:** `agreement.start_work`, recording not_started → in_progress, the actor, the time and the note.
  - **UI:** an Execution section in the agreement panel, for both parties:
    - the status;
    - the planned start, and where it comes from;
    - the actual start;
    - who recorded it (the member's name for their own side);
    - the note;
    - the "Record that work has started" action.

- **7.6 Execution progress:**
  - **Audit:**
    - **Already working:** 7.5's start record and its derived status (not started, in progress, terminated) on the award's agreement. Lock, If-Match versioning, audit and best-effort notifications were reusable.
    - **Missing:** "on hold", progress notes, and a history the parties can read.
    - **Not applicable:** percentage progress, since requirements aren't measured that way, and completion, which is a later stage.
    - **Why a small table:** the admin audit log keeps recording every event. It is moderation-only and doesn't record which party acted, so it can't be the parties' history.
  - **Added (migration 0050):**
    - **`execution_updates`:** an add-only history, never edited: started (backfilled from 7.5), progress notes, put on hold, resumed. Each entry records the side, the member, a note and server time. Entries are numbered 1, 2, 3… per agreement under the requirement's lock, with a unique (agreement, number) pair, so order never depends on timestamps.
    - **`agreements.on_hold_at`:** the current hold.
    - **Status:** still derived, now not started, in progress, on hold or terminated. Both parties read the same state and the same history.
  - **Recording (`POST /projects/{id}/agreement/progress`):**
    - **Actions:** `update` (a note is required), `hold` and `resume` (note optional). Either party may record them, as any member of its side.
    - **Allowed when:** only after the start and while the agreement isn't terminated. A hold when already on hold, or a resume when not on hold, is refused with 400. Stale pages get 409.
    - **Refused outright:** anything without an award (404) and admin changes (403).
    - **Termination while on hold:** allowed. The status becomes terminated, the history stays, and nothing resumes it.
    - **Unaffected:** the award, the winning offer, the requirement, the agreement and its documents.
  - **Notification:** `execution_updated` goes to the other side when the work is put on hold or resumed. Progress notes don't notify. It is sent best-effort; repeated unread notices merge into one.
  - **Audit:** `agreement.execution_progress`, `…_on_hold` and `…_resumed`, each with the previous and new status, the actor and the note.
  - **UI:** the Execution section shows:
    - the status;
    - on hold since;
    - the history, oldest first (the member's name for one's own side);
    - add a progress note;
    - put on hold or resume.

  - **Follow-up: clearer refusals.**
    - **What the server says:** every agreement and execution refusal caused by someone else acting first (another tab, a colleague, the other party) now says what happened. Examples: "The work was already put on hold (by the other party, a colleague or another tab). This page now shows the latest."
    - **What the page does:** it reloads the agreement and shows the refusal as an amber notice, not a red error, and closes any form opened on the old state.
    - **Repeats:** buttons are disabled while a request is in flight, so double-clicks don't repeat.
- **7.7 Milestones / deliverables:**
  - **Audit:**
    - **Partly there:** requirement items (description, quantity, unit, specification) existed as the scope's measurable parts.
    - **Missing:** any deliverable record, and any delivered vs accepted distinction.
    - **Not applicable:** payment stages, which belong to payments.
  - **Added (migration 0051): `milestones` on the award's agreement.**
    - **Fields:** position, title, description, due date, an optional link to a requirement item, and status: pending → delivered → accepted, or returned → delivered again. Accepted is final.
    - **Recorded:** delivery and decision times (server clock), who delivered and who decided, notes, and a version.
    - **A simple one-off job has none,** and the section is hidden.
  - **Who does what:**
    - **Setting out:** the owner side sets deliverables out only while the agreement is being prepared, so the winner sees them before agreeing. Once in force they stay as agreed, and later changes are variations.
    - **Checks:** a due date can't be before the award, and an item must belong to this requirement. At most 50 per agreement.
    - **Removing:** only a pending deliverable with no evidence can be removed.
    - **Delivering:** the winner's side delivers, only after the work has started, not while on hold, and not after termination.
    - **Deciding:** the owner side accepts, or returns for correction with a note. Delivered is never accepted automatically.
  - **Reuse:**
    - **Evidence:** agreement documents (7.4) with a `milestone_id`, which must be one of this agreement's deliverables. None can be added to an accepted one.
    - **History:** each delivery and decision is a 7.6 execution-history entry naming its deliverable.
    - **Audit:** `milestone.create`, `update`, `remove`, `deliver`, `accept` and `return`.
    - **Notification:** `milestone_updated`, to the owner side on delivery and to the winner on a decision. It is best-effort, and unread notices merge.
  - **Concurrency:** every action runs under the requirement's lock with the deliverable's version, so a stale tab gets 409 and a repeat an explained 409. Simultaneous accept, return and re-deliver always apply one at a time as a valid chain.
  - **Access:** losing bidders, other organisations, other owners and other transactions' deliverable ids get 404. Admins can only read.
  - **The rest is untouched:** the requirement, its items, the winning offer and the award never change.

- **7.8 Change / variation during execution:**
  - **Audit:**
    - **Not applicable:** requirement amendments and offer revisions are pre-award mechanisms. Reusing them would rewrite pre-award history.
    - **Already working:** the award record is immutable, and the agreement's details and deliverables are fixed once in force.
    - **Missing:** any way to record an agreed post-award change.
  - **Added (migration 0052): `variations` on the award's agreement.**
    - **What a proposal holds:**
      - a description of the scope, quantity or specification change (always required);
      - optionally a signed value change, a revised completion date, a revised due date for one deliverable, and an added deliverable.
    - **Lifecycle:** proposed → agreed or rejected by the other party, or withdrawn by the proposer. Termination lapses an open proposal.
    - **Recorded:** who proposed, who decided, server times and notes. Numbered V1, V2… under the lock.
  - **Agreement rule:**
    - **When:** variations can be proposed only while the agreement is in force. While it's being prepared, the agreement and its deliverables are edited directly. After termination, nothing.
    - **Proposals:** either party may propose; only one may be open at a time.
    - **Takes effect:** only when the other party agrees. A side can't agree to or reject its own proposal (403). Unilateral edits of in-force terms are refused.
  - **Current agreed state, derived and never stored over the original:**
    - **Value:** the award's amount plus agreed value changes, in order. Each agreed variation keeps the value before and after, and the value can't fall to zero or below.
    - **Completion date:** the latest agreed revised date, else the original planned completion (the winning offer's commitment, or the requirement's).
    - **Deliverable date:** a revised due date is applied to that deliverable, with its previous date kept on the variation. An accepted deliverable can't be rescheduled; if it's accepted while a proposal is open, agreeing to that proposal is refused.
    - **Added deliverable:** created pending and marked as added by the variation.
  - **Untouched:** the award record, the winning offer, the requirement and the original agreement are never modified.
  - **Reuse:**
    - **Papers:** change documents are agreement documents with a `variation_id`, which must be one of this agreement's variations. New types: change order, revised agreement, revised quotation, revised specification, approval.
    - **Audit:** `variation.propose`, `agree`, `reject` and `withdraw`, with before and after values.
    - **Notification:** `variation_updated` to the other party, best-effort, and unread notices merge.
  - **Concurrency:** every action runs under the requirement's lock with the variation's version. Simultaneous proposals result in exactly one. A double agreement, or agreement racing withdrawal, results in exactly one decision; the late ones get an explained 409.
  - **Access:** losing bidders, other organisations, other owners and other transactions' variation ids get 404. Admins can only read.
  - **UI:**
    - **Summary:** the agreement shows the current agreed value, with the originally awarded value beside it, and the completion date with the original.
    - **Changes section:** the list with from → to for each change, propose / agree / reject / withdraw, and change documents.

- **7.9 Execution documents & evidence:**
  - **Audit:**
    - **Already working:**
      - secure private storage keyed by unguessable ids;
      - the existing file-type, size and safe-name checks;
      - access checked on every open, then a one-minute signed link (tampered or unsigned links are refused);
      - deliverable evidence (7.7) and change papers (7.8);
      - the uploading side, member and time;
      - documents fixed once the agreement is in force;
      - orphan-free failures.
    - **Partly there:** execution evidence wasn't distinguishable from the agreement's own papers: no evidence types, one list.
    - **Missing:** evidence for one progress update.
    - **Invalid:** a file could be linked to a deliverable and a change at once.
  - **Fixed (migration 0053):**
    - **Evidence types:** progress photograph, site report, delivery record, completion report, inspection report and test results. They are values of the existing kind column.
    - **Progress-update link:** `agreement_documents.execution_update_id`, which must be one of this agreement's progress updates.
    - **One context per file:** a document relates to at most one deliverable, change or progress update.
    - **Timing:** execution evidence (an evidence type or a progress-update link) can be added only once the work has started.
    - **Response:** `evidence` marks each document, and progress-history entries carry their id.
  - **Rules kept:**
    - **Who:** either party may add evidence (the provider's progress and delivery records, the owner's inspection reports), including while on hold. None can be added after termination, and evidence stays readable by the parties only.
    - **Removal:** the existing rule: only the attaching side, only while the agreement is being prepared. Afterwards evidence is on record.
    - **No side effects:** uploading changes no status, history entry, deliverable, change, award or requirement.
    - **Notifications:** none for evidence, matching progress notes. A delivery already notifies the owner, and the evidence shows on the deliverable and the progress history.
  - **UI:**
    - **Execution evidence section:** evidence for the work as a whole, plus an upload form with type and an optional "relates to" progress update.
    - **Progress history:** each entry lists its own evidence.
    - **Deliverables:** keep their evidence, now typed as delivery records.
    - **Agreement documents:** now list only the agreement's own papers.

- **7.10 Owner acceptance / completion:**
  - **Audit:**
    - **Already working:** per-deliverable delivery and acceptance (7.7): delivered → accepted, or returned → delivered again, with server times, notes, evidence, history, audit and notifications.
    - **Missing:** a submission and owner acceptance of the work as a whole, which simple jobs need; any statement of what is outstanding; and guards so later actions can't contradict accepted work.
  - **Added (migration 0054): the whole work's completion on the agreement.**
    - **Fields:** `completion_status` (submitted / accepted / returned), with submission and decision times (server clock), who did each, and notes.
    - **History:** each step is an execution-history entry, reusing the delivered / accepted / returned kinds with no deliverable. Evidence (7.9) can be linked to the submission entry.
    - **Notifications:** `execution_updated` ("Work submitted as complete / accepted as complete / returned for correction").
    - **Audit:** `completion.submit`, `accept` and `return`.
  - **Rules:**
    - **Submitting:** only the winning provider's side submits. The work must have started and not be on hold, every deliverable must be accepted (one accepted and one pending is not complete), and no proposed change may be awaiting an answer.
    - **Deciding:** only the owner side accepts, or returns with a note; returned work can be submitted again. A provider can never accept its own work.
    - **Untouched:** the award, the offer, the requirement and the agreement's own status. Accepted is not closed (7.11).
  - **Guards:**
    - **While submitted:** the work can't be put on hold or resumed, and no change can be proposed or agreed.
    - **Once accepted:** no progress, hold, change, termination, resubmission or return.
    - **Late or repeated actions:** answered with an explained 409 under the requirement lock and the agreement version.
    - **Status:** the derived execution status shows "Work accepted".
  - **Access:** losing bidders, other organisations, other owners and never-awarded requirements get 404. Admins can only read.
  - **UI:** a Work completion section showing:
    - the status;
    - deliverables still outstanding;
    - an open change blocking submission;
    - the submission and the decision with their notes;
    - submit, accept and return actions.
    - The history labels whole-work entries, and the submission can be chosen as "relates to" for evidence.

- **7.11 Transaction completion / closure:**
  - **Audit:**
    - **Already working:** the owner's acceptance (7.10) is the explicit owner completion action, and its preconditions are the completion rules: an award, the winning provider, an agreement, a recorded start, every deliverable accepted, no correction outstanding, no open change, not terminated.
    - **Missing:** acceptance left the agreement "active", so there was no final state. Writes after acceptance were refused endpoint by endpoint, and some (evidence uploads, deliverables, papers) were not.
    - **Not applicable:** a second "complete" action or entity. It would compete with acceptance.
  - **Fixed (migration 0055):**
    - **Acceptance closes the transaction.** Owner acceptance of the whole work sets the agreement to `completed` with `completed_at` (server time), in the same transaction and under the same lock. Agreements whose work was already accepted are completed at their acceptance time.
    - **Final state:** "completed" (work accepted) stays distinct from "terminated" (stopped before completion). The requirement's own outcome stays "awarded". Cancelled, no award and expired stay the requirement's own endings, with no agreement.
    - **One refusal point:** every change to a completed transaction is refused at the agreement's single write entry point (`_load`) with an explained 409, whether a stale page, a browser retry or a direct request. That covers progress, hold, start, deliverables, evidence and papers, changes, termination, agreement details, and resubmission or a second decision.
    - **Still readable:** the record, documents, evidence, variations and history stay readable by the parties and admins.
    - **Execution status:** the derived status shows "completed".
    - **Audit and notification:** the audit entry records "accepted; transaction completed", and the provider's notification says the work was accepted and the transaction closed.
  - **UI:**
    - **Both parties:** the agreement shows "Completed" with its date, and the execution status shows "Completed".
    - **No edit controls** remain once completed: progress, evidence, papers, changes, termination, deliverables.

- **7.12 Financial status:**
  - **Audit:**
    - **Billing is subscription-only.** The existing billing (`routers/billing.py`, `services/stripe_service.py`) is the providers' U-Tender subscription: Stripe checkout, portal and webhook. Nothing records payments, invoices or settlement between owner and provider.
    - **Not applicable:** amounts paid, outstanding balance and payment status. They can't be derived truthfully, so none are shown.
    - **Already working:** the immutable awarded amount (award record); the current agreed value as the award plus agreed variations, each keeping its before and after (7.8); one marketplace currency with no conversion; access limited to the parties and admins; losing bidders get no amount.
    - **Partly there:** no net of agreed changes, and no statement about payments.
  - **Added:**
    - **`agreed_changes_total`:** the server-derived net of agreed variations. Original + this = current. Pending proposals don't count.
    - **`payment_tracking: "not_managed"`.**
    - **UI:** the agreement summary shows the current value (the "Final agreed value" once completed), the originally awarded value and the agreed changes when they differ. A Payments line says payments are not tracked by U-Tender and are settled directly between the parties.
  - **Unchanged by design:**
    - **Completion and payment are independent.** A completed transaction stays completed with no payment state invented.
    - **Subscription billing** never appears in a transaction response.
    - **No request can set a value.** Values are always derived, and extra fields are ignored.

- **7.13 Transaction history:**
  - **Audit:**
    - **Already working:**
      - requirement versions and amendments (Stage 3) and offer revisions (Stage 5), each readable by its own side;
      - the award record (winning offer, its revision, the requirement version answered, value, time, who awarded);
      - the agreement's write-once times;
      - the add-only execution history (start, progress, hold, resume, deliverable and whole-work delivered / accepted / returned);
      - variations with their before and after values;
      - document metadata;
      - the admin audit log.
    - **Partly there:** the parties' history covered execution only. The award, the agreement coming into force, its papers, changes, termination and completion lived in separate records with no shared order, and second-resolution timestamps from separate tables can't order same-second events.
  - **Fixed (migration 0056):**
    - **One ordered log.** The other business events (`in_force`, `document` for the agreement's own papers, `change_proposed` / `agreed` / `rejected` / `withdrawn` / `lapsed`, `terminated`, `completed`) are now written to the same execution-history log, in the same request as the event itself.
    - **Numbering:** the log is already numbered under the requirement's lock, so its order is the order the server applied events.
    - **Links:** `execution_updates.variation_id` and `document_id`.
    - **Backfill:** existing agreements get these events from the times already recorded, and each agreement's log is renumbered in time order.
    - **`timeline`** on the agreement response: the award first, with its original value, then the log. Each entry gives its server time, the party, the member's name (own side and admins only), the note, the deliverable, the change number with its value change and resulting value, or the document.
    - **What stays unchanged:** `execution_history` still lists execution entries only. Evidence stays on its entry or deliverable and doesn't become a timeline event.
  - **Integrity:**
    - Every entry is written once and never edited.
    - A retried or concurrent request that is refused (completed, already decided, stale) writes nothing, so the history has no duplicates.
    - Current values never rewrite it: the award entry keeps the original value.
    - The timeline is part of the agreement response, so only the parties and admins read it.
  - **UI:** the Execution section's list is now the full History. Each line shows the date, party and event (amounts for the award and changes, the document name), and progress entries keep their evidence.

- **7.14 Post-award access:**
  - **Audit (no gap found):**
    - **One gate for every endpoint.** Every agreement, document, execution, deliverable, change, completion and history endpoint goes through one server-side check, decided per request from current state:
      - the requirement is awarded and has its agreement;
      - the caller is the owner side (its organisation's current members) or the winning provider's side (its organisation's current members, account not suspended, requirement not suspended);
      - admins can read only.
    - **Child ids:** deliverable, change, document, progress-update and offer ids are each checked to belong to that same agreement or requirement.
    - **Files:** they open only through that check, then a one-minute signed link; storage keys are never public.
    - **Roles:** organisation members share one role (an invitation must match it), and each action checks the side as well as membership (owner-only, provider-only, the other party only).
    - **Stage 6 records:** the owner's offer inbox, offer pages, history, clarifications, notes, shortlist, comparison and offer files stay owner-side only after award. The winner never receives a losing offer's id, content or files.
    - **Losing bidders** see only "awarded to a successful bidder".
    - **Completion** (7.11) keeps reading and closes writing.
    - **Membership changes:** a removed member loses access from their next request. Organisations can't dissolve once anything is published, since leaving is only possible before verification.
    - **Suspension:** a suspended winner loses sight of the transaction. A suspended owner keeps read-only access, the existing owner policy.
  - **Added:** `tests/test_stage7_14_access.py`, a sweep of every post-award endpoint as:
    - the losing bidder, another owner organisation, another provider organisation, and a signed-out user;
    - every member of both sides, and an admin (read-only);
    - the winner against the Stage 6 owner endpoints and the losing offer's files;
    - a removed member, a suspended winner, a suspended owner, and after logout;
    - after completion.
  - **Known, unchanged (existing design):** an access token stays valid for its short lifetime (30 minutes) after logout if replayed outside the browser. Logout clears the browser's cookies and revokes the refresh token.

- **7.15 Post-award integrity under concurrent actions:**
  - **Audit:**
    - **Serialized decisions (working):** every post-award change (agreement, documents, start, progress, deliverables, changes, completion, termination) and every Stage 6 decision runs under one row lock on the requirement (`lock_project`, `SELECT … FOR UPDATE`), with the state checked under it. Stale pages get the agreement, deliverable or change version check (409), with the explanation and refresh from 7.6.
    - **Once-only records (working):** backed by unique constraints: one award per requirement, one agreement per award and per requirement, history numbers unique per agreement, change numbers unique per agreement.
    - **History in the same transaction (working):** each history entry and audit row commits together with its state change, so a refused or failed change writes none.
    - **Notifications (working):** best-effort after the commit, never undoing it, and unread ones merge.
    - **Background jobs (working):** the expiry sweep moves only open or draft requirements and skips locked rows; the cron job only sends reminders for open requirements. Neither touches awarded or post-award records.
    - **No payment records exist**, so there are none to duplicate (7.12).
    - **Gap — invalid in production:** the app's MySQL connections ran at the default REPEATABLE READ. InnoDB fixes a transaction's snapshot at its first plain read. A request that had read anything (its user, during authentication) before waiting for the requirement lock therefore went on reading the agreement, deliverables and changes from that earlier snapshot once it had the lock. It could judge "already accepted?" or "already completed?" on state another request had just committed, which allows a double acceptance, a decision on a settled change, or a duplicate history entry.
    - **Why tests missed it:** the MySQL test setup replaces the app's engine with a READ COMMITTED one, so tests never ran the production setting.
  - **Fixed:**
    - `app/db.py` now opens MySQL connections at READ COMMITTED (`engine_options`). Every statement sees the latest committed data, so a check made under the lock sees what the previous holder committed. Production now matches what the race tests verify. SQLite is unchanged.
  - **Tests (`tests/test_stage7_15_integrity.py`):**
    - **Regression:** a request built with the production settings reads first, waits for the lock while another owner accepts, then must see accepted and completed. It fails at REPEATABLE READ and passes with the fix.
    - **Races:** completion racing termination (three rounds), and a change proposal racing the completion submission. Exactly one stands, and the history records the one outcome.
    - **Background:** the expiry sweep leaves a completed transaction alone.
    - **Existing races still pass:** award and decision races (6.15), double start, hold/resume, accept/return/re-deliver, simultaneous proposals and answers, double completion.

- **7.16 Final Stage 7 audit (end to end):**
  - **The journey, as one test:** `tests/test_stage7_16_end_to_end.py` runs one real transaction through the actual API: annual MEP maintenance of a Sharq tower. A two-member owner organisation awards a two-member facilities company over a cheaper individual bidder.
    - **Owner and provider steps:** create → publish → provider discovers it in the feed and passes eligibility → two offers → close → review, including the loser's documents → private note → award.
    - **Handover:** both organisations' four members see the same award, offer, parties and value; the loser sees only the outcome.
    - **Agreement:** deliverables set out by both owner members, a signed paper and an insurance certificate, PO reference and effective date, in force.
    - **Execution:** a provider member (not the representative) starts the work and records progress with a photo. A deliverable carries a site report; it is delivered, returned for correction, delivered again and accepted. A change is proposed by the provider (+KWD 2,400, adding a deliverable) and agreed by the owner; the provider can't agree its own. The remaining deliverables are delivered and accepted.
    - **Closing:** the work is submitted, accepted and completed; the retry is refused.
  - **Checked at each boundary:**
    - **Identity:** the same requirement, award, offer, agreement and organisations throughout.
    - **Documents:** each kept in its own context: offer documents, agreement papers, progress evidence, deliverable evidence.
    - **Money:** original KWD 18,000, agreed changes +2,400, final 20,400, payments not tracked.
    - **History:** in order (awarded → in force → started … returned … change agreed … completed once), with the award entry at the original value.
    - **After completion:** every document still opens; every old action (progress, deliver, evidence, accept, change, submit) is refused.
    - **Access:** the losing bidder, another organisation and a signed-out user are refused, documents included. The winner can't reach the owner's notes or the losing offer's files, and its responses carry nothing of the losing price or notes. The admin can read.
    - **Database:** one agreement, one change, three deliverables, every document on this agreement, one unbroken history with no duplicates, and the award and winning offer unchanged.
  - **Result:** passes on SQLite and MySQL, together with every Stage 7 test (7.1–7.15) and the Stage 6 award and decision race tests.
  - **No code changes were needed:** the only cross-stage defect found in Stage 7 was the REPEATABLE READ isolation level, fixed in 7.15.

## Stage 8 — Trust and reputation

- **8.1 Completion boundary:**
  - **Audit:**
    - **Already working:** Stage 7 records one authoritative completion: the agreement is closed as `completed` by the owner side's acceptance of the whole work (7.10/7.11), with `completed_at` at server time, written once, never reopened. It appears in the history (7.13), notifies the provider, and is audit-logged.
    - **Invalid:** the existing owner review of the provider (`POST /owner/reviews`, the rating form on the owner's requirement page) opened as soon as the requirement was awarded, before any work had been done or accepted. The review also feeds the provider's public average rating.
  - **Fixed:**
    - **`app/services/transactions.py` → `completed_transaction(db, project_id)`:** the one definition of a completed transaction for Stage 8, namely the completed agreement. It is not a new state or record.
    - **Review endpoint:** now requires a completed transaction. Awarded, in force, executing, on hold, returned, delivered or submitted awaiting acceptance, terminated, cancelled, no award, expired and closed externally all stay ineligible.
    - **Owner page:** shows the rating form only once the transaction is completed (an existing review still shows).
    - **Older tests:** two tests that reviewed straight after the award now complete the transaction first (`tests/stage7_helpers.py`).
  - **Unchanged:** the review's provider still comes from the award, never the request; one review per requirement.
- **8.2 Transaction outcome:**
  - **No new record needed.** The completed Stage 7 transaction already holds the outcome, from authoritative, write-once data:
    - **requirement:** the agreement's requirement, and the version awarded on (`award_records.project_revision`, the offer's `based_on_material_revision`);
    - **parties:** the owner organisation (the requirement's) and the provider organisation (the winning offer's);
    - **winning offer and award;**
    - **value:** the original awarded value; each agreed variation with its before and after values; the final agreed value, derived and frozen once completed;
    - **ending and time:** the outcome (agreement `completed`, or `terminated` with its reason) and `completed_at`.
  - **Other endings:** cancelled, no award, closed externally (no award with its own closure reason) and expired have no agreement, so they can never be taken for completed business.
  - **Duplicates and staleness:** retries, stale pages and late changes are refused (7.11), so the outcome has no duplicate and can't be rewritten.
  - **Access:** the parties and admins (read-only) read it; the losing bidder and other organisations can't.
  - **Payments:** not tracked, and not part of the outcome.
  - **Tests:** `tests/test_stage8_1_completion_boundary.py` and `tests/test_stage8_2_outcome.py` prove these points.

- **8.3 Owner reviews the service provider:**
  - **Audit:**
    - **Already working:** the review (`reviews`: one per requirement, unique; whole-number rating 1–5 enforced by a database check; optional comment). The reviewed provider is always the award's, never the request's (the PASS 17 fix). It requires a completed transaction (8.1), and the provider's public average is recomputed from all its reviews. The owner page shows the review once recorded.
    - **Gaps found:**
      - **Authorization:** the endpoint needed only an owner role, so a suspended or unverified owner could record a review, unlike every other owner action.
      - **Duplicates:** two simultaneous submissions both passed the "already reviewed?" check and the second failed on the unique constraint with a 500.
      - **Atomicity:** the review and the provider's recomputed rating were two commits, with no audit entry.
      - **Input:** the comment had no length limit and wasn't trimmed. Callers had to send a `service_provider_id` the server ignores.
  - **Fixed (`app/routers/owner.py`, `app/schemas/review.py`):**
    - **Authorization:** the review now goes through `_get_owned_project(lock=True)`, which takes the requirement's lock and requires an active, verified account. Any member of the owner organisation can review; providers, other owners and the signed-out can't.
    - **Duplicates:** a second review (a retry, a colleague, another tab) is an explained 409.
    - **One transaction:** the review, the provider's recomputed rating and a `review.create` audit entry commit together; a failure records none of them.
    - **Input:** the rating is a strict whole number 1–5 (no coercion from text or decimals). The comment is trimmed, at most 2,000 characters, and a blank one becomes none. `service_provider_id` is optional, and still ignored. `created_at` is returned in UTC.
  - **UI:** the owner confirms before submitting ("A review can't be changed afterwards"). The comment box has the limit and a label. A refused submission reloads what's on record.
  - **Tests:** `tests/test_stage8_3_owner_review.py`.

_Stage 9 onwards is added as it is implemented._
