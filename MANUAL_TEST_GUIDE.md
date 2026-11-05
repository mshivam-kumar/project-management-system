# Manual Functionality Test Guide

Use the clean seeded project to exercise the process in the browser. Start the stack from the repository root:

```sh
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 backend
```

Open [http://localhost:5173/](http://localhost:5173/). Wait for the backend and database to start and apply migrations.

## 1. Verify accounts and access

- Sign in as `admin@procurement.local` / `procurement-dev-2026`.
- Verify that **Full Workflow Test — Diagnostic Imaging Equipment** is Draft and has its sample PDF.
- There is no vendor sign-in. Vendors are entries managed by admins; committee and project users handle all vendor communication and files.
- `reviewer@procurement.local` / `procurement-demo-2026` is a TSC reviewer. Other seeded user password is `procurement-demo-2026`.

## 2. Run the stage path

Use the clean project in this order. Stage controls appear in the project drawer's **Procurement workflow** section. Add a note when prompted.

1. Admin opens the clean seeded project. In **Committees**, create **TSC** and assign `reviewer@procurement.local` as a TSC member.
2. Admin submits the requirement, then records TSC approval. TSC committee must exist before approval is accepted.
3. After approval, create a committee named **TSC Board** in **Committees**. Advance using **Form board and submit TSC report**; the board must exist before the stage can advance. The reviewer can perform the TSC report action using the `TSC` designation.
4. Change or create accounts with designations `AS (IA)`, `DG`, `HQ`, `CS (SR)`, and `IA` in **User Management**. Verify them, then sign in as the corresponding user to perform their stage action. Admin may perform any stage while setting up a local walkthrough.
5. At **HQ Review**, raise a query routed to `HQ`. Sign in as the HQ user, answer it, and then advance. Repeat at **CS (SR) Review** routed to `CS (SR)`. An open query blocks advancing.
6. At **Draft Tender to IA**, upload the draft PDF; IA acknowledges correctness and issues the tender.
7. Admin associates the verified Aster vendor with the project. At **Vendor Response**, a member of the procurement/tender committee uploads the response received from the vendor, selects the Aster vendor in the query panel, and records any vendor query and reply. No vendor account is used.
8. Admin closes the response period. In **Committees**, form **Technical Bid Opening Board** before advancing that stage. Then create a **TEC** and assign a verified TEC member. SS approves TEC formation only after the TEC committee exists.
9. Upload the TEC report. Raise and answer an HQ query if needed, then forward to price bid opening.
10. Open the price bid, create a **TAC**, and assign a user representative (`User Representative`) plus TAC members. TAC acceptance is blocked until both the TAC and user representative are assigned. Record review/negotiation through stage queries and the activity trail; accept the tender.
11. Have IFD or CFA approve to finish at **Approved**.

Stage actions require the matching designation or committee membership. Admin and Super Admin can perform all actions for a manual demonstration. Uploads, stage changes, and discussion are recorded in the activity timeline. Uploaded PDFs are stored in the repository-root `media/` folder.

## 3. Check documents and query history

- In each project drawer, open **Documents**, click **View**, then **Download**.
- Upload a revised PDF with **New version** and confirm the version number increments.
- Check query status and replies in **Stage queries and replies**. The next stage remains blocked while a query is unanswered.
- The administrator can review recorded actions in **Audit Logs**.

## 4. Existing sample project and reset

**District Hospital Diagnostic Equipment Procurement** is an in-progress sample with committee, vendor, and a requirements PDF. Use the clean Draft project for a fresh walkthrough. The seed command does not reset existing projects. `docker compose down -v` erases the local database and test progress, but uploaded files remain in the repository-root `media/` folder.

## Troubleshooting

- A project is visible only to its creator, assigned members, committee members, and administrators. Vendors have no system accounts or access.
- If a stage action is rejected, check the signed-in user's designation, the committee name/member designation where relevant, and unanswered queries.
- After updating code, rebuild/restart with `docker compose up --build -d` and inspect `docker compose logs --tail=100 backend`.
