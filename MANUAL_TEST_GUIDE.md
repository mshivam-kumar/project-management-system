# Manual End-to-End Procurement Test

This guide walks one new procurement project from requirement to CFA approval. It includes one real login per stakeholder stage so you can check committee access, handoffs, documents, queries, and the audit trail. Vendors are represented by records in the system; they never log in. Committee members enter vendor submissions and correspondence that they receive outside the system.

> **Execution status:** This is a step-by-step test script traced against the current app workflow. I could not execute it in this environment because the Docker CLI fails with a Snap permission error and neither app service is running here. Do not treat the results below as an executed test report. Once Docker builds and runs on your PC, follow the script and record the actual outcome in the checklist at the end.

## 1. Start the local app

To start with the exact seeded state described here, reset the local database first. This permanently deletes local PostgreSQL records and test progress; uploaded files in `media/` remain:

```sh
docker compose down -v
```

From the repository root, start the services and check that the backend is healthy. Startup applies migrations and seeds the accounts and populated reference project:

```sh
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 backend
```

Open [http://localhost:5173/](http://localhost:5173/) and sign in as the seeded administrator:

- Email: `admin@procurement.local`
- Password: `procurement-dev-2026`

If the backend image fails to build or the backend is unhealthy, stop here and resolve that first. The app must be available at `http://localhost:8000/` before the workflow can be tested.

## 2. Inspect the seeded scenario and prepare a fresh one

After a database reset and seed, the database contains one populated reference project: **District Hospital Diagnostic Equipment Procurement**. It is in **TEC Report**, has stage accounts assigned to the project, stage committees, a verified vendor, sample PDFs, query/reply threads, and a timeline through TEC report preparation. Sign in with the accounts below and confirm the project appears in each dashboard. Use it to inspect a populated project and continue the workflow from TEC Report if desired.

The rest of this guide creates a second project, **Manual Procurement Scenario B**, from Draft so you can practice the whole process yourself. The second project is not preseeded; you will assign the existing stage accounts and form its committees as you reach each stage.

### Create the second project

As the administrator, open the dashboard, choose **New project**, and create:

- **Title:** `Manual Procurement Scenario B — Diagnostic Imaging`
- **Department:** Procurement
- **Description:** `End-to-end manual test of committee handoffs, tender documents, vendor correspondence, and approvals.`
- **Estimated amount:** `7200000`

Save it in **Draft**. Open the project drawer and upload a valid PDF named `A-Requirement.pdf` using the paperclip control. Confirm that it appears under **Documents** and can be viewed and downloaded.

To prepare files for the new scenario, open the seeded District Hospital project as admin, download `Diagnostic_Equipment_Requirements.pdf`, and make copies named as the stages below request. The same sample PDF can be reused for this upload/version walkthrough; the file content is not evaluated by the workflow. Alternatively, use your own valid PDFs.

### Use the seeded stage accounts

These active, verified accounts are created by `seed_initial_data` when the backend starts with `DEBUG=true`. No manual account creation is needed. All stage accounts use password `StageWalk!4826a`.

| Stage role | Account name | Designation | Email |
| --- | --- | --- | --- |
| TSC | TSC Reviewer | `TSC Member` | `tsc.a@procurement.local` |
| AS (IA) | AS IA Reviewer | `AS IA` | `as.ia.a@procurement.local` |
| DG/SS | DG SS Approver | `DG SS` | `dg.ss.a@procurement.local` |
| HQ | HQ Reviewer | `HQ` | `hq.a@procurement.local` |
| CS (SR) | CS SR Reviewer | `CS SR` | `cs.sr.a@procurement.local` |
| IA Wing | IA Reviewer | `IA` | `ia.a@procurement.local` |
| Procurement/tender committee | Tender Committee Member | `Procurement Member` | `tender.a@procurement.local` |
| SS for TEC formation | SS Approver | `SS` | `ss.a@procurement.local` |
| TEC | TEC Member | `TEC Member` | `tec.a@procurement.local` |
| TAC | TAC Member | `TAC Member` | `tac.a@procurement.local` |
| User representative | User Representative | `User Representative` | `user.rep.a@procurement.local` |
| IFD/CFA | IFD CFA Approver | `IFD CFA` | `ifd.cfa.a@procurement.local` |

If the stack was already running when this code was added, run the seed command once from the repository root:

```sh
docker compose exec backend python manage.py seed_initial_data
```

Then sign in as admin and confirm the accounts appear in **User Management**. The seed command creates missing accounts without resetting existing accounts or project progress. This only runs in the local DEBUG setup. Vendors remain vendor records, not login accounts.

For this test, use the project drawer's **Project team** section to assign each created stakeholder to the test project. This makes the project visible to each test login. Committee membership is still set up stage by stage below. You may instead add users to the project when forming each committee, but make sure the next stage's assignee can open the project before their turn.

### Add a verified vendor

Use **Vendor Management** to add a vendor record for the scenario, mark it verified, and keep it active. For example:

- **Vendor:** `Scenario A Imaging Supplier`
- **Email:** `tenders@example.invalid`
- **Registration number:** `SCENARIO-A-001`

The email is contact information only; no invitation or vendor login is sent. Return to the project drawer and add this vendor under **Verified vendors**. Confirm it is listed before recording tender responses.

## 3. Walk the procurement stages

Use the project drawer's **Procurement workflow** panel. Only use the button shown for the current status. When a note prompt appears, add the sample note shown below. After each handoff, sign out and sign in as the next responsible stakeholder. Verify the stage label and activity timeline after every transition.

**Permission note:** The current app allows administrators to perform every transition. Some formal setup transitions are admin-only even when a committee carries out the review. The table marks those explicitly. Use the named committee user to review, upload documents, or handle correspondence, then sign in as admin for the marked transition. This follows the current implementation and avoids mistaking an authorization error for a failed workflow.

### Login handoff quick map

After the current account clicks a workflow button, sign out and log in as the account in the **Next login** column. All stage accounts use `StageWalk!4826a`; the admin uses `admin@procurement.local` / `procurement-dev-2026`. The stage account email list is in section 2. The app does not switch users automatically.

| Current status | Sign in as and do this | Next login |
| --- | --- | --- |
| Draft | **Admin:** Submit requirement. | TSC Reviewer (then Admin for TSC approval) |
| TSC Approval | **TSC Reviewer:** Review and add recommendation. **Admin:** Click Approve TSC. | Admin |
| Board Formation | **Admin:** Form TSC Board, then click Form board and submit TSC report. | TSC Reviewer |
| TSC Report As IA | **TSC Reviewer:** Upload report and forward it. | AS IA Reviewer |
| AS IA Approval | **AS IA Reviewer:** Approve. | DG SS Approver |
| DG SS Approval | **DG SS Approver:** Record approval. | HQ Reviewer |
| HQ Review | **HQ Reviewer:** Raise query. **TSC Reviewer:** Reply. **HQ Reviewer:** Forward. | CS SR Reviewer |
| CS SR Review | **CS SR Reviewer:** Raise query. **TSC Reviewer:** Reply. **CS SR Reviewer:** Forward. | IA Reviewer |
| Draft Tender IA | **IA Reviewer:** Upload draft and acknowledge/issue tender. | Admin |
| Tender Issued | **Admin:** Open vendor response period. | Tender Committee Member |
| Vendor Response | **Tender Committee Member:** Upload vendor response and record/reply to vendor correspondence. **Admin:** Close tender. | Admin |
| Technical Bid Board | **Admin:** Form Technical Bid Opening Board, then click Form TEC. | SS Approver |
| TEC Formation | **SS Approver:** Approve TEC formation. | TEC Member |
| TEC Report | **TEC Member:** Upload report. **HQ Reviewer:** Raise report query. **TEC Member:** Reply and submit report. | Admin |
| Price Bid Open | **Admin:** Open price bid. | TAC Member |
| TAC Review | **TAC Member:** Record negotiation and accept tender. TAC must include the User Representative. | IFD CFA Approver |
| IFD CFA Approval | **IFD CFA Approver:** Approve CFA. | Workflow complete |

If you are just checking the stage without making a change, stay signed in as the current stakeholder. At each handoff, the expected status appears in the project drawer; use that status to confirm you are at the right point before switching accounts.

| # | Project stage and owner | What to do and expected result |
| --- | --- | --- |
| 1 | **Draft — Admin** | Upload `A-Requirement.pdf` as above. Click **Submit requirement to TSC** and note `Requirement complete; submit for TSC approval.` Expect **TSC Approval**. |
| 2 | **TSC Approval — TSC reviews; Admin records the gate** | In **Committees**, form `TSC Committee` for this project and add the TSC Reviewer. Sign in as the TSC Reviewer, open the project, inspect the requirement, and add a project message noting the TSC recommendation. Sign in as admin and click **Approve TSC** with note `TSC approval recorded.` Expect **Board Formation**. (This transition is admin-only in the current app.) |
| 3 | **Board Formation — Admin / Board** | Form `TSC Board` and assign the TSC Reviewer. As admin, click **Form board and submit TSC report** with note `Board formed; TSC report sent for AS (IA) perusal.` Expect **TSC Report As IA**. The app requires a committee whose name contains `BOARD` or `TECHNICAL`. |
| 4 | **TSC Report for AS (IA) — TSC** | Sign in as the TSC Reviewer. Upload `A-TSC-Report.pdf`, add a message recording the report submission, then click **Forward report to AS (IA)**. Expect **AS IA Approval**. |
| 5 | **AS (IA), then ARC Admin / DG-SS — AS (IA) and DG/SS** | Sign in as AS IA Reviewer, review the report, and click **Approve AS (IA)**. Expect **DG SS Approval**. Sign in as DG SS Approver and click **Seek DG / SS approval** with a note recording the approval. Expect **HQ Review**. |
| 6 | **HQ review — HQ** | Sign in as HQ Reviewer and raise a query on the file, for example subject `Confirm equipment compatibility` and body `Please confirm the requested interface standard.` Sign in as TSC Reviewer, reply `Confirmed against the requirement.`, then sign in as HQ Reviewer again. Confirm the query shows **ANSWERED**, then click **Forward to CS (SR)**. Expect **CS SR Review**. |
| 7 | **CS (SR) review — CS (SR)** | Sign in as CS SR Reviewer and raise a query, for example subject `Confirm service coverage` and body `Please confirm the service period.` Sign in as TSC Reviewer and reply `Three-year coverage is included.` Sign back in as CS SR Reviewer; once answered, click **Forward to IA wing**. Expect **Draft Tender IA**. |
| 8 | **Draft tender — IA Wing** | Sign in as IA Reviewer. Upload `A-Draft-Tender.pdf` and add a note that it is sent for correctness review. This stage's action moves directly to tender issue after acknowledgement. |
| 9 | **Tender issue — IA Wing** | Click **Acknowledge draft and issue tender** and note `Draft checked; tender issued within the notified response window.` Expect **Tender Issued**. |
| 10 | **Vendor responses — Procurement/tender committee; Admin opens/closes the window** | Before entering this stage, form `Procurement Tender Committee` and add Tender Committee Member. Associate the verified Scenario A vendor if not already attached. At **Tender Issued**, sign in as admin and click **Open vendor response period**. Expect **Vendor Response**. Now sign in as Tender Committee Member; upload `A-Vendor-Technical-Response.pdf` (received outside this system). Raise a query, select the Scenario A vendor, and record the vendor's question; reply with the committee's response after handling it. Confirm the thread is **ANSWERED**. Sign in as admin and click **Close tender and form technical board**. Expect **Technical Bid Board**. (Both response-window transitions are admin-only in the current app.) |
| 11 | **Technical bid opening board — Admin / Board** | At **Technical Bid Board**, form `Technical Bid Opening Board` and add Tender Committee Member. Sign in as admin and click **Form TEC** with note `Technical bid opening board formed.` Expect **TEC Formation**. The app requires a committee name containing `BOARD` or `TECHNICAL`. |
| 12 | **TEC formation — TEC / SS** | Form `TEC` and add TEC Member. Sign in as TEC Member to review the response document and add a note recording technical evaluation assignment. Sign in as SS Approver and click **Approve TEC formation**. Expect **TEC Report**. (This action checks the `SS` designation and that a TEC committee exists.) |
| 13 | **TEC report — TEC; HQ query/reply** | Sign in as TEC Member. Upload `A-TEC-Report.pdf`. Sign in as HQ Reviewer and raise a query on the report, for example `Clarify evaluation criterion` / `Please confirm the interpretation of criterion 4.` Sign back in as TEC Member and reply with the clarification. Confirm the query is answered, then click **Submit TEC report**. Expect **Price Bid Open**. |
| 14 | **Price bid opening — Admin** | Sign in as admin and click **Open price bid** with note `Price bid opened after technical evaluation.` Expect **TAC Review**. (This transition is admin-only in the current app.) |
| 15 | **TAC review and negotiation — TAC** | Form `TAC` and add both TAC Member and User Representative. Confirm the member list includes the User Representative; the committee-member designation is copied from the user's designation when they are added. Sign in as TAC Member, review the TEC report, and record negotiation with the vendor in a stage query routed to the associated vendor; reply with the agreed outcome. After all queries are answered, click **Accept tender and send to IFD / CFA**. Expect **IFD CFA Approval**. |
| 16 | **CFA through IFD — IFD/CFA** | Sign in as IFD CFA Approver and click **Approve CFA** with a note such as `CFA approval recorded through IFD.` Expect **Approved**. |

### Important correction for step 10

The vendor response sequence has two separate transitions. At **Tender Issued**, admin first clicks **Open vendor response period** to enter **Vendor Response**. The committee then records submissions and correspondence. When the response window has ended, admin clicks **Close tender and form technical board** to enter **Technical Bid Board**. Do not click both actions before recording the vendor material.

## 4. Verify the completed scenario

After reaching **Approved**, sign in as admin and check:

- The project status is **Approved** and every handoff appears in the activity timeline with actor, time, and note.
- **Documents** lists the requirement, TSC report, draft tender, vendor response, and TEC report PDFs. Use **View** and **Download** on at least one file; upload a new version and confirm its version number changes.
- The HQ, CS (SR), vendor, TEC/HQ, and TAC/vendor query threads show their replies and **ANSWERED** status.
- **Committees** lists TSC, TSC Board, Procurement Tender Committee, Technical Bid Opening Board, TEC, and TAC with the assigned members. TAC includes the User Representative.
- The project drawer's vendor list contains the verified supplier. There is no vendor account or vendor login.
- **Audit Logs** includes the stage actions and document/query operations.

Record the run here after actually completing it:

- Run date:
- Project code:
- Last completed stage:
- Any failed action and the exact message:
- Documents uploaded and viewed:
- Queries answered:
- Audit/timeline verified (yes/no):

## 5. Reset for another complete run

The seed command does not reset a project's status or history. For another scenario, create a new project and use a new scenario title and document names. To erase all local database records and start over, run:

```sh
docker compose down -v
docker compose up --build -d
```

This deletes the local PostgreSQL database and all test progress. Uploaded PDFs in the repository-root `media/` folder remain, so remove those manually only if you also want to clear uploaded files.

## Troubleshooting

- **Cannot log in:** Admin-created users should be active and verified. Check the email, temporary password, and account status under **User Management**.
- **Project is missing:** Sign in as admin and assign that user in the project's **Project team** section, or add them to a committee for the project.
- **Stage action denied:** Confirm the current project status, the signed-in designation, and any required committee name/member. Several transitions are admin-only as marked above.
- **Cannot advance:** Open **Stage queries and replies** and answer every open query for this project. Open queries block any stage change.
- **Committee form error:** Select the test project first, create the committee with the stage name above, then select it and add a verified user.
- **PDF upload fails:** Use a real PDF no larger than 10 MB. Confirm the repository-root `media/` folder is mounted by Compose and inspect `docker compose logs --tail=100 backend`.
- **Backend does not start:** Check `docker compose ps` and backend logs. A Docker Hub image pull/build error must be resolved before browser workflow testing can begin.
