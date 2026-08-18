# MWB Internal Audit Manager — Current System Analysis

## Scope and baseline

This document completes Stage 1 of the production migration brief. It describes the behavior found in `MWB_Internal_Audit_Manager.html`; it does not propose that the current technical implementation be retained. The HTML remains the functional baseline and has not been modified.

The application is a single, self-contained browser page with inline CSS and JavaScript. All application records, users, credentials, configuration, and sequence state are stored together under the browser `localStorage` key `mwb_audit_full_system_v3`. Two older keys are checked for backward compatibility.

Seed content consists of 4 users, 34 entities, 16 audit areas, and 131 checklist questions. The configured firm is Hombal & Associates, Chartered Accountants; the client/group is Mutha Wagmal Bhuraji Group.

## Current functionality inventory

| Screen / facility | Current behavior |
|---|---|
| Login | User is selected from a list and authenticated against a plaintext PIN held in browser data. |
| Dashboard | Shows total observations, pending/repeated items, high/critical items, locked-report count, current-month completion for the first entity, due plans, and a combined high-risk/pending list. |
| Audit Calendar | Creates a single plan or all-area monthly plans; assigns staff and due dates; toggles Pending/Completed; carries prior-month pending/repeated observations forward. |
| Audit Entry | Selects entity, month, and area; renders every checklist item; requires an observation for each item; records risk, status, responsible person, and auditor remarks; reloads existing answers. |
| Client Replies | Lists pending/repeated observations and permits a management comment plus optional transition to Resolved. |
| Observation Register | Filters by entity, audit area, period, and status; displays/edit observations; exports CSV or Excel. |
| Reports & Approval | Generates seven report views, calculates checklist completion, shows missing items, exports Excel/Word/PDF, approves and locks a complete entity-period report, and lists locked reports. |
| Documents | Records document metadata/reference text and exports the register. It does not upload or retain actual files. |
| Masters | Edits firm/report settings, entity names, and audit-area names. Checklist questions remain hardcoded. |
| User Controls | Admin-only UI for adding/removing users and assigning a free-text role and plaintext PIN. |
| Backup / restore | Downloads the entire browser data object as JSON and replaces current browser data from a selected JSON file. |
| Print | Uses browser print styling and print/save-PDF behavior. |

Export details: CSV is generated from current in-memory rows; “Excel” is an HTML table downloaded with an `.xls` extension; “Word” is HTML downloaded with a `.doc` extension; PDF is browser print output from a newly opened report window.

## Current data model

All relationships are implicit string matches rather than foreign keys.

### Root object

| Property | Shape and meaning |
|---|---|
| `users` | Array of `{name, role, pin}`. |
| `entities` | Array of entity-name strings. |
| `areas` | Array of audit-area-name strings. |
| `obs` | Observation/checklist-response records. |
| `plans` | Audit plan records. |
| `docs` | Document-reference records. |
| `locks` | Approved/locked report records. |
| `settings` | `{firm, client, reportPrefix, logoText, financialYear}`. |
| `seq` | Next report-number integer. |

### Observation record

Observed fields are `id`, `date`, `entity`, `period`, `area`, `check`, `risk`, `observation`, `remark`, `management`, `responsible`, `due`, `status`, `createdBy`, `createdAt`, `approved`, `locked`, and `reportNo`.

Identity is effectively `(entity, period, area, checklist question text)`. Saving an area overwrites the matching record in place. IDs are derived from `Date.now()` plus a random number.

### Audit plan record

Fields are `id`, `entity`, `period`, `area`, `due`, `assigned`, `status`, `createdBy`, and `createdAt`. There is no uniqueness check, so duplicate plans can be created. An `All Areas` plan is supported, although full-month creation makes one plan per configured area.

### Document record

Fields are `id`, `date`, `entity`, `period`, `area`, `type`, `ref`, `remarks`, and `uploadedBy`. Despite the UI wording, this is metadata only: no file bytes, MIME type, checksum, storage key, or access policy exists.

### Lock/report record

Fields are `id`, `reportNo`, `entity`, `period`, `type`, `status`, `approvedBy`, and `approvedAt`. A lock is found by entity and period. Report content is regenerated from current browser records rather than preserved as a versioned artifact.

### Checklist configuration

Checklist questions are a JavaScript object keyed by audit-area name. There are 131 questions across 16 areas:

| Audit area | Items |
|---|---:|
| Sales Audit | 8 |
| Purchases Audit | 6 |
| Purchases GST Compliance | 8 |
| Expenses Audit | 10 |
| Other Income Audit | 6 |
| Fixed Assets Audit | 9 |
| Other Assets Audit | 5 |
| Trade Receivables Audit | 7 |
| Cash Audit | 11 |
| Bank Account Audit | 8 |
| Loans and Liabilities Audit | 10 |
| Trade Payables Audit | 8 |
| Capital Audit | 7 |
| TDS Return Filing Assistance | 6 |
| GST Compliance Assistance | 7 |
| Other General Audit Points | 15 |

A newly added area without a hardcoded entry receives one fallback question: “General verification completed”. The exact 131 seed questions must be migrated without silent wording changes.

## Current roles and effective access

Authorization is entirely client-side and based on substring checks against free-text roles.

| Role | Effective access |
|---|---|
| Admin / Partner | All navigation, masters, user controls, observation entry/editing, planning, reports, approval/lock, documents, replies, backup/restore. |
| Audit Manager | Same general operational screens and approval/lock, but User Controls is hidden. |
| Article / Audit Staff | Planning, observation entry/editing, reports and documents; cannot approve/lock and cannot access User Controls. |
| Client / Management View | Dashboard, observation register, reports, documents, and reply UI remain navigable; planning, audit entry, and masters render denial messages. Client reply actions are available. |

Important exposure: navigation visibility is not a security boundary. All data is already present in the browser, there is no organization/entity scoping, and the client role can reach more screens than the label “view and management reply only” suggests.

## Current business rules

1. Periods use `YYYY-MM`; new forms default to the current browser month/date.
2. Risks are controlled in the entry UI as Low, Medium, High, or Critical.
3. Observation statuses are Pending, Resolved, Repeated, or Closed.
4. Every checklist question in the selected area requires nonblank observation text. The UI recommends “No adverse observation” for a completed check with no finding.
5. Saving a complete area upserts one observation record per checklist item and marks the first matching entity/period plan for that area (or `All Areas`) Completed.
6. Checklist completion for approval covers every configured area and every question, not merely planned areas. A response counts as complete when matching observation text is nonblank.
7. Final approval requires an Admin/Partner or Manager, one entity, one period, 100% checklist completion, and no existing lock for that entity-period.
8. Approval creates a lock, increments the sequence, and flags all matching observations approved/locked with the report number.
9. Audit-entry and register-edit paths reject changes to a locked entity-period. Other mutation paths are not uniformly protected by a central policy.
10. Report numbers follow `{prefix}/{first 8 alphanumeric entity characters}/{period}/{4-digit sequence}`, for example `IA/MWB/MURALIIN/2026-08/0001`.
11. Carry-forward copies prior-month Pending/Repeated observations into the selected period, prefixes the observation text with its origin, and sets status Repeated.
12. Management reply overwrites the single `management` field. If selected, it directly changes status to Resolved; no reply or transition history is retained.
13. Plan status is a two-state toggle between Pending and Completed.
14. Report filters are defined by string rules: exception = High/Critical; pending action = Pending/Repeated; GST and TDS reports use audit-area name matching; management discussion = high/critical or pending/repeated.
15. Removing a user is allowed unless only one user remains; referential impacts are not checked.

## Current workflows

### Monthly audit execution

1. Auditor/manager creates one plan, all-area plans, or carries forward prior exceptions.
2. Staff selects entity, month, and area in Audit Entry.
3. The application displays all questions for that area.
4. Staff supplies a response for every question and optionally risk/status/responsible/remarks.
5. Saving upserts responses and marks a matching plan complete.
6. Register and dashboard immediately read the same browser object.

### Management response and closure

1. Client Replies lists Pending and Repeated observations globally.
2. A user enters one management comment.
3. The user may mark the observation Resolved.
4. An auditor can later edit comment, status, and remark through browser prompts, including setting Closed.

There is no explicit Management Responded or Auditor Review state, no reply history, and no immutable status history.

### Report generation, approval, and locking

1. User selects report type, entity scope, and month.
2. Report content is calculated from in-browser observations.
3. For a single entity-period, the application calculates all 131 configured checklist points and displays gaps.
4. An authorized user approves only if no point is missing and no lock exists.
5. The application creates the report number and lock and marks matching observations locked.
6. Output may be printed or downloaded in the browser-generated formats.

### Backup and restore

1. Backup serializes the complete root object, including plaintext user PINs, to JSON.
2. Restore parses a selected JSON file and replaces the application object without schema, referential, role, or integrity validation.
3. The restored object is written to localStorage; the original file itself is not changed.

## Migration risks and required safeguards

| Risk | Impact | Migration safeguard |
|---|---|---|
| Plaintext PINs in source, browser data, and backups | Credential disclosure and impersonation | Never import PIN values as reusable credentials. Provision accounts securely, force password setup/reset, hash only on the backend, and quarantine sensitive legacy backups. |
| No stable IDs or foreign keys | Ambiguous joins and broken references when names differ or change | Create deterministic mapping tables during import; normalize names cautiously; report duplicates/unmatched references instead of guessing. |
| Checklist question text is identity | Wording changes can orphan historical responses | Seed immutable checklist IDs, retain exact legacy text, and map by area plus exact question with explicit versioning for future edits. |
| Duplicate plans/records possible | Counts and completion may differ after migration | Detect and report duplicates; define uniqueness constraints only after agreed reconciliation rules. |
| In-place overwrites | Missing observation, reply, and status history cannot be reconstructed | Preserve available timestamps/actors as legacy provenance; clearly mark unavailable history; start append-only history after cutover. |
| Carry-forward creates copies | Repeated items may lose ancestry or duplicate across runs | Import copies as separate observations with an explicit predecessor/origin relationship where it can be inferred; flag ambiguous chains. |
| Locks are client-side records | Browser data can be edited, and some paths lack centralized enforcement | Treat imported locks as claims requiring validation; enforce all locked-record rules transactionally on the backend. |
| Report snapshot is not stored | A regenerated historical report may not match what was approved | At migration, preserve available lock metadata; after cutover, store versioned report input/snapshot and generated artifact/checksum. |
| Local numeric/random IDs | Collision and type inconsistencies | Assign UUIDs and retain original IDs in migration provenance fields. |
| Dates are locale-formatted strings | Parsing ambiguity, especially `createdAt`/`approvedAt` | Parse with explicit legacy formats and timezone assumptions; report values that cannot be parsed. |
| One global client and unrestricted data | Data leakage in a multi-tenant system | Create an organization/client boundary first, map every entity and record to it, and require explicit user memberships/entity grants. |
| Free-text roles and substring checks | Privilege escalation or incorrect permissions | Map only recognized legacy roles to fixed backend roles; quarantine unknown roles for administrator review. |
| Document records are references only | Referenced evidence may be absent or inaccessible | Import metadata separately, flag paths/references for reconciliation, and upload/verify actual files through secured storage later. |
| Restore accepts arbitrary JSON | Invalid or malicious data can enter the system | Build a dry-run importer with schema validation, size limits, referential checks, per-record errors, transaction boundaries, and a migration report. |
| Report sequence is browser-local | Duplicate report numbers across backups/users | Import existing report numbers with uniqueness checks; initialize a database sequence safely above reconciled values. |
| Browser-generated export semantics | Users may expect exact legacy output despite non-native formats | Capture representative legacy outputs as acceptance fixtures and agree production templates before replacing exporters. |
| Checklist completion uses all configured areas | Changing to plan-based completion would alter approval eligibility | Preserve this rule initially; any later change must be a deliberate, tested business decision. |
| Current user removal and master edits lack referential controls | Historical attribution and matching can break | Use deactivation/soft deletion and stable IDs; do not physically remove referenced users, entities, areas, or checklist items. |

## Acceptance baseline for subsequent stages

The production system must preserve at least these observable behaviors while moving enforcement and storage to the backend:

- 34 existing entities, 16 areas, and the exact 131 checklist questions are available after seed/import.
- Monthly single-area and all-area planning, assignment, due dates, completion, and carry-forward remain possible.
- Staff can enter every checklist response with risk, status, responsibility, and remarks, and can reload prior values.
- Register filters and dashboard headline metrics produce equivalent results for the same authoritative dataset.
- Management can reply only to observations within its authorized organization/entities, with full reply history.
- The seven current report types remain available with equivalent filter semantics unless explicitly approved otherwise.
- Approval remains impossible unless one entity and period are selected, every mandatory point is completed, the actor is authorized, and no lock exists.
- Once locked, all applicable normal mutation endpoints reject changes; the approval, lock, and rejected attempts are auditable.
- Report numbers remain recognizable and unique while being allocated transactionally.
- CSV, Excel, Word, PDF, JSON import, and document-register workflows have a supported production replacement.

## Open decisions before implementation

These should be resolved during architecture/schema design without blocking preservation of the baseline:

1. Whether Admin/Partner and Audit Manager should both retain report approval/lock authority exactly as today, or approval should be Partner-only.
2. Whether completion should continue to require every active checklist item across all areas or only the areas included in an approved plan.
3. Whether imported legacy locks are trusted automatically or require partner verification.
4. Whether a controlled unlock process is required and which role may execute it.
5. Which real evidence files correspond to existing document references and where they currently reside.
6. The canonical organization/client/entity memberships for each migrated user.
7. The target report templates and whether generated reports require immutable PDF retention and digital signatures.
8. The timezone policy for stored timestamps and rendered business dates (the legacy browser uses the operator’s local timezone).

