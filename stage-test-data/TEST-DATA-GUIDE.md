# U-Tender stage test data: which data to use for which test

One-time test data created by `seed_stage_test_data.py`. It is not part of application setup.
Run it against a **test/staging database** (take a backup first, e.g. `backup.sh`).

```
cd backend
source .venv/bin/activate
python ../stage-test-data/seed_stage_test_data.py --api-url http://localhost:8000
```

- Run it from a machine that has the backend's `.env` (it creates the admin and issues the e-mail verification token directly in the database; everything else goes through the API).
- It refuses to run twice. If it fails midway, restore the backup and run again.
- Every account uses the same password: **`UTender#Test2026`**
- E-mail addresses end in `@utender-test.example` (a reserved domain, nothing is delivered).
- `last_run_manifest.json` (git-ignored) lists all tender ids and the pending invitation link.

## 1. The 11 accounts

| Code | E-mail (before the @) | Role | State | Use it to test |
|---|---|---|---|---|
| ADMIN | `admin` | admin | | `/admin/*` pages |
| O1 | `owner.individual` | owner, individual | approved | owner side as a person |
| O2 | `owner.org` | owner, organization (Gulf Holdings Real Estate W.L.L.) | approved, no staff | owner side as a company |
| P1 | `provider.diyar` | provider, organization (Al Diyar General Contracting) | **active** (approved + payment override) | the main bidder / winner |
| P1 staff | `diyar.staff1`, `diyar.staff2` | members of P1 | joined | organization sharing (2 staff) |
| P2 | `provider.gulfmep` | provider, organization (Gulf Coast MEP) | **approved, unpaid** | payment gate |
| P2 staff | `gulfmep.staff1` | member of P2 | joined | unpaid state seen by a member (1 staff) |
| P3 | `provider.freelance` | provider, individual | **active** | individual bidder, org-only exclusion (0 staff) |
| P4 | `provider.bahar` | provider, organization (Al Bahar Interiors) | **pending admin review** | verification stage |
| P4 staff | `bahar.staff1` | invited, **not yet joined** | e-mail verified, invitation pending | accepting an invitation (1 staff) |

Staff counts: P1 = 2, P2 = 1, P3 = 0, P4 = 1 (invited).

## 2. Tenders (titles start with their code, e.g. `[T06]`)

| Code | Owner | Status | What is set up |
|---|---|---|---|
| T01 | O1 | draft | only title, location, deadline |
| T02 | O2 | draft | complete: per-item pricing, drawing, tender rules, response requirements |
| T03 | O2 | draft | restarted from cancelled T15 |
| T04 | O1 | open | no activity at all |
| T05 | O2 | open | organizations only + ISO 9001 + serves Hawalli + General Contracting |
| T06 | O1 | open, **sealed** | P1 submitted then revised (revision 2), P3 submitted |
| T07 | O2 | open | P1 offer submitted by staff `diyar.staff1`; P3 has an unsent draft offer |
| T08 | O1 | open | 1 answered + 1 unanswered question, then a material amendment; P1 offer awaits confirmation |
| T09 | O2 | open, paused | paused with a reason |
| T10 | O1 | under evaluation | offers from P1 and P3, private note, P1 shortlisted, 1 offer clarification answered (P3) and 1 unanswered (P1) |
| T11 | O2 | awarded to P3 | agreement `preparing`, one milestone drafted |
| T12 | O1 | awarded to P1 | agreement active, work started, milestones accepted / delivered / returned, one variation proposed |
| T13 | O2 | completed (P1) | owner gave 2 stars, P1 responded and reported the review, P1 gave owner 5 stars |
| T14 | O1 | no award | one offer kept (status closed) |
| T15 | O2 | cancelled | one offer kept |
| T16 | O1 | awarded to P3 | agreement terminated by the owner |
| T17 | O2 | open, **suspended by admin** | hidden from provider feed |

## 3. Stage by stage

Frontend routes: owner `/owner/dashboard`, `/owner/projects/:id`; provider `/service-provider/feed`, `/service-provider/projects/:id/offer`; admin `/admin/review`, `/admin/projects`, `/admin/review-reports`, `/admin/service-providers/:id`.

### Stage 1-2: accounts, verification, organizations
| Test | Use | Expect |
|---|---|---|
| Admin review queue | ADMIN, P4 | P4 is pending review. Test request changes, reject, reopen, approve. |
| Payment gate | P2, `gulfmep.staff1` | Approved, but "activate marketplace access"; cannot open requirements or bid. Then grant/revoke a payment override as ADMIN. |
| Accept an invitation | link from the run output / manifest, `bahar.staff1` | Joins Al Bahar Interiors. (Provider counts drop from 5 to 4 in admin overview.) |
| Organization sharing | `diyar.staff1`, `diyar.staff2` | They see P1's offers (T06, T07, T08, T10-T13). |
| Individual vs organization | O1 vs O2, P3 vs P1 | Different stakeholder types and checklists. |
| Deactivate / reactivate a person | ADMIN on `gulfmep.staff1` | Cannot sign in; reactivation restores access. |

### Stage 3: owner builds a requirement
| Test | Use | Expect |
|---|---|---|
| Resume a draft, quality check blocks publishing | O1, T01 | Errors listed. |
| Preview, audience count, publish | O2, T02 | Passes quality check; publish once. |
| Start a new draft from an ended one | O2, T15 / T03 | T03 shows the link back. |
| Pause / resume | O2, T09 | Providers see the reason. |
| Material amendment | O1, T08 | Amendment 1 is material. |

### Stage 4: provider discovery and access
| Test | Use | Expect |
|---|---|---|
| Feed | P1, P3 | Drafts and T17 absent. P3 does not see T05. |
| Eligibility | P1 vs P3 vs P2 on T05 | P1 eligible. P3: organization only + qualification missing. P2: qualification missing + category not offered. |
| Questions | P3 / P1 on T08, O1 answers | One answered, one open. |
| Save and participate | P1 (has T04 saved), P3 (T07 draft) | Appear under saved / preparing. |

### Stage 5: offers
| Test | Use | Expect |
|---|---|---|
| First offer from scratch | P1 or P3 on T04 | Draft, documents, quality gate, submit. |
| Save and resume | P3 on T07 | Draft offer is waiting. |
| Revise, history | P1 on T06 | Revision 2, history shows revision 1. |
| Confirm after a material change | P1 on T08 | Offer asks for confirmation. |
| Withdraw | any open tender with your own offer | Recorded in history. |
| Sealed confidentiality | O1 on T06 | Amounts and identities hidden until the deadline. |

### Stage 6: evaluation and award
| Test | Use | Expect |
|---|---|---|
| Compare, notes, shortlist, award | O1, T10 | P1 already shortlisted; award either offer. |
| Offer clarification | P1 / P3 on T10 | P1 still has to answer. |
| No award, cancellation | T14, T15 | Offers kept and closed; no award record. |

### Stage 7: agreement, execution, completion
| Test | Use | Expect |
|---|---|---|
| Agreement preparing | O2 + P3, T11 | Set effective date, provider confirms, owner activates. |
| Execution | O1 + P1 / staff, T12 | Decide the proposed variation; accept the delivered milestone; re-deliver the returned one; submit completion. |
| Completed record | T13 | Both sides see the closed record. |
| Terminated record | T16 | Terminated by owner, nothing can be reopened. |

### Stage 8: reviews and reputation
| Test | Use | Expect |
|---|---|---|
| Review, response | T13 | 2-star owner review with P1's response. |
| Moderation | ADMIN `/admin/review-reports` | One open report from P1. Uphold or dismiss. |

### Stage 9: admin and operations
| Test | Use | Expect |
|---|---|---|
| Suspended requirement | ADMIN, T17 | Reactivate to bring it back to the feed. |
| Suspend an offer | ADMIN on any submitted offer | Offer hidden from the owner. |
| Overview, audit trail | ADMIN | Entries for everything above. |

## 4. Known quirks seen while building this

- The admin overview's "approved without payment" can show 0 even with P2 in that state: the app counts it with `NOT IN` on a subscription status that is empty for accounts that never started one.
- A staff member who has not accepted their invitation counts as a separate provider in admin lists.
- A sealed tender cannot be closed before its deadline, and an open tender cannot be closed early while any provider has an unsent draft offer. That is why T07 and T08 stay open.
