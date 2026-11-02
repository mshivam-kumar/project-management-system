# Manual Functionality Test Guide

Use this checklist to exercise the application through the browser. It includes a clean end-to-end workflow and a shorter check of the preloaded sample project.

## 1. Start and confirm the application

From the repository root:

```sh
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 backend
```

Wait until the `backend` and `db` containers are healthy. The backend applies repository migrations and seeds the admin, demo users, and both demo projects. Check backend logs if startup does not complete. Open [http://localhost:5173/](http://localhost:5173/).

If the stack was already running when code changed, restart the backend to run its startup seed and restart frontend if the browser still shows the old UI:

```sh
docker compose restart backend frontend
```

You can also apply any missing seed records directly without restarting:

```sh
docker compose exec backend python manage.py seed_initial_data
```

Refresh the browser and sign out/in if you already had a session open.

## 2. Verify the accounts and permissions

1. On a fresh local database, sign in as `pending.user@procurement.local` with `procurement-demo-2026`. Expected: sign-in is refused because the account is pending. If you already verified this seeded account, register a different account from the sign-in page and use that new account for the pending-to-verified check.
2. Sign in as `admin@procurement.local` with `procurement-dev-2026`.
3. Open **User Management**, find the pending demo user, and verify it.
4. Sign out and sign in as the pending account again. Expected: the account can now sign in.
5. Sign in as `demo.user@procurement.local` with `procurement-demo-2026`. Expected: the user can create projects but does not see admin navigation or project stage controls.

## 3. Create a project and progress every stage

Use the seeded **Full Workflow Test — Diagnostic Imaging Equipment** project. It starts in Draft with a sample PDF and a verified vendor. No separate project setup is needed.

1. Sign in as `admin@procurement.local`.
2. Find **Full Workflow Test — Diagnostic Imaging Equipment** in the dashboard and click its eye icon. Confirm its status is **Draft** and the activity timeline contains project creation.
3. In the project drawer, open **Stage actions** and click **Submit**. Enter a note such as `Manual test submission`. Expected: status becomes **Submitted** and the note appears in the timeline.
4. Click **Forward** and enter a review note. Expected: **Under Review**.
5. Click **Forward** again. Expected: **Committee Formation**.
6. Open **Committees** in the left navigation. Form a committee for this project, such as **Manual Test Technical Committee**. Select its row and add `reviewer@procurement.local` as a member. Expected: the reviewer appears in the committee member list.
7. Sign out and sign in as `reviewer@procurement.local`. Expected: the project now appears on the reviewer dashboard, and its drawer, timeline, and documents are accessible without a separate project-team assignment. Sign in as an unrelated regular account (or register and verify another account) to confirm that account cannot see or open this project.
8. Sign back in as the admin. Return to the project drawer and click **Forward**. Expected: **Committee Review**.
9. Click **Forward** again. Expected: **Pending Approval**.
10. Click **Approve** and add a decision note. Expected: **Approved**, with the final stage change visible in the activity timeline. This completes the happy-path workflow.

## 4. Exercise return and rejection paths

Create separate projects for these paths because Approved and Rejected are final statuses. If the seeded Draft project has already been progressed, create a new Draft project as the demo user and use that instead.

- **Return path:** progress a project to Under Review, click **Return**, then confirm its status is **Returned**. Click **Submit** to send it back to Submitted and continue forwarding it.
- **Reject path:** progress another project to Pending Approval, click **Reject**, and confirm its status is **Rejected**.

Each action should include its optional note in the project timeline and have a corresponding entry in **Audit Logs**.

## 5. Upload, view, and version a document

1. Open any accessible project drawer.
2. Use the paperclip control near the message box to upload a valid PDF under 10 MB.
3. Confirm the document appears under **Documents** and the timeline says it was uploaded.
4. Click **View**. Expected: the PDF opens in an in-app preview. Close the preview and click **Download** to save it.
5. Click **New version** and upload another PDF. Expected: the listed document version increments (for example, v1 to v2), and the timeline records the update.

The seeded **District Hospital Diagnostic Equipment Procurement** project already includes `Diagnostic_Equipment_Requirements.pdf`; the full-workflow Draft project includes `Workflow_Test_Specification.pdf` for the preview check.

## 6. Check the seeded sample project

As Super Admin, open **District Hospital Diagnostic Equipment Procurement**. It starts at **Committee Review**, so it is a quick check rather than a clean run from Draft. Confirm:

- The timeline shows earlier submission, review, committee formation, and vendor association events.
- **Committees** shows the Technical Evaluation Committee and three members.
- The project drawer lists the verified medical equipment vendor.
- The sample requirements PDF previews and downloads.
- **Forward** moves it to Pending Approval; then test Approve, Return, or Reject.

The seed creates this project once. Restarting the backend does not reset project status or erase test changes. For a fresh full path, create a new project as the demo user. `docker compose down -v` deletes the local database and all local test records and uploaded documents.

## Troubleshooting: I cannot see or use Stage actions

- Stage actions are only shown to accounts with ADMIN or SUPER_ADMIN roles. Sign in as `admin@procurement.local`; the verified demo user is a regular user.
- A regular account sees a project if it created the project, was assigned to the project, or is a member of one of its committees. Adding someone to a committee grants access to that project automatically.
- Open the project with its eye icon. The action controls are inside the project details drawer under **Stage actions**.
- Check the status. The controls change by status: Draft has Submit; Submitted through Committee Review have Forward, Return, and Reject; Pending Approval has Approve, Return, and Reject; terminal statuses have no actions.
- If the project is not in the expected state, reload the page and open it again. The status should match the latest action.
- Restart services after updating code with `docker compose restart backend frontend`, then refresh the browser. Check `docker compose logs --tail=100 backend` for startup or request errors.
- A workflow action is not allowed if it does not match the current status. For a complete sequence, create a new Draft project instead of starting with the seeded Committee Review project.

