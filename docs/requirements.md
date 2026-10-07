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

_Later Stage 6 steps are added as they are implemented._
