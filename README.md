# Procurement Project Management System

A procurement project management application for managing projects, staged tender workflows, committee reviews, approval trails, vendor dispatches, bid records, and award negotiations.

## Run the current application

Prerequisites: Docker Desktop (or Docker Engine) with the Docker Compose plugin.

From the project root, run:

```sh
docker compose up --build
```

The first startup builds the Django and React environments, waits for PostgreSQL, creates the app migrations, applies them, and seeds approval ranks, sample departments, fictional employee records, 50 categorized demo vendors, and a development Super Admin. Open:

- Frontend: http://localhost:5173
- Backend status/links: http://localhost:8000/
- API: http://localhost:8000/api/v1/
- Django admin: http://localhost:8000/admin/

Development sign-in:

- Email: `admin@procurement.local`
- Password: `admin123`

These fictional demo credentials and the Django secret in `docker-compose.yml` are for local testing only. Do not expose this Compose configuration to a public network or reuse those values in a deployment.

### Demo accounts

The seed command creates or updates these local demo sign-ins:

| Role | Email |
|---|---|
| Super Admin | `admin@procurement.local` / `admin123` |
| AS approver | `as@procurement.local` / `as123` |
| HQ approver | `hq@procurement.local` / `hq123` |
| SS approver | `ss@procurement.local` / `ss123` |
| DGS approver | `dgs@procurement.local` / `dgs123` |
| IA Wing approver | `iawing@procurement.local` / `ia123` |
| Demo employees | `<first>.<last>@procurement.local` / `demo123` |

Employees have fictional names and employee IDs (`EMP-1001` through `EMP-1010`). For example, Aarav Sharma signs in as `aarav.sharma@procurement.local`. Seeded vendor names, registrations, contact details, and product catalogs are also fictional demo data.

Approvals use rank roles rather than named authority records: SS approves TSC formation; AS and then HQ approve the TSC report as separate sequential steps; DGS reviews that report in a separate final step; and IA Wing approves the tender draft. Existing authority demo accounts are renamed to rank-based emails by the seed command, and their approval trails remain intact.

To set a new password for a local development account without putting it in the repository, run:

```powershell
docker exec -it project-management-system-backend-1 python manage.py shell
```

Then enter:

```python
from getpass import getpass
from apps.accounts.models import User

user = User.objects.get(email=input("Account email: ").strip())
user.set_password(getpass("New password: "))
user.save(update_fields=["password"])
```

These passwords are deliberately simple for demo testing. Never use these accounts or credentials in a deployment.

To stop the application, press Ctrl+C. To stop and remove the database volume and all local data, run `docker compose down -v`.

## Create a regular user

Registration is enabled by the API, but new accounts start pending and cannot sign in until verified. To create a development user, send a request:

```sh
curl -X POST http://localhost:8000/api/v1/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{"name":"Demo User","email":"user@example.org","password":"change-this-password","department":"<department-uuid>"}'
```

The seed command prints department names through the Django shell/admin; find department UUIDs from `GET /api/v1/departments/` while signed in as the seeded admin. Verify a user through the API with a Super Admin or Admin access token:

```sh
curl -X POST http://localhost:8000/api/v1/users/<user-uuid>/verify/ \
  -H 'Authorization: Bearer <access-token>'
```

Log in at `/login` after verification. The API login endpoint is `POST /api/v1/auth/login/` with `email` and `password` fields.

## What is implemented

- Django REST API with modular apps for accounts, departments, procurement, vendors, documents, workflow foundation, committees, notifications, and audit.
- Custom UUID user model, roles, pending account verification, JWT sign-in, and backend role checks.
- Project creation and creator-scoped project listing for regular users; admin roles can see all projects.
- Project search, status/department filters, pagination, project codes, and activity timeline.
- Project ID links open the project's single workspace, with project information, workflow actions, schedule, submissions, approvals, query responses, and complete approval history. Admin and approver controls are role-specific; SS handles TSC formation, while AS and DGS see only projects with the corresponding TSC report awaiting their decision.
- Vendor CRUD and verification endpoints; audit and notification foundations.
- New projects start with a sequence-1 TSC formation stage. Admins form the TSC from the project page by selecting employees and a chair, and may optionally attach a PDF (up to 10 MB). SS approvers can preview or download it on that project's approval inbox.
- The project page supports TSC formation and reports, sequential AS/DGS reviews, IA Wing tender-draft review, vendor matching and selection, offline tender dispatch, SS-approved TEC formation, technical bid upload, TEC report collaboration, final report submission by the TEC chair, Admin qualification of vendors, and SS-approved TAC formation.
- The project workspace presents the process as a gated sequence: create the project → form the TSC and obtain SS approval → obtain AS approval of the TSC report → submit that approved report for DGS approval → submit the tender draft for IA Wing approval → select vendors → record offline tender dispatch → form the TEC and obtain SS approval → upload technical bids → submit the TEC final report → qualify vendors → form the TAC and obtain SS approval → have Admin select the top three qualified vendors (or all if fewer than three) and upload their financial-bid PDFs → have the TAC chair upload the final TAC report for Admin. TAC formation is locked until qualification is complete and at least one selected vendor is qualified; the proposed TAC must include exactly one active, verified IA Wing user plus at least one other member, and the chair must be a member. Admin is not added automatically. Financial bids are visible only to Admin and active TAC members, not TEC members. A completed step's action is closed; its submitted document and approval events remain in the history. A query or rejection reopens only the revision action for that step, and later steps remain locked until approval.
- Before submitting a tender draft to IA Wing, Admins must record the expected date the tender will be sent to vendors, the bid-receipt deadline, and the expected product-arrival date. Dates must be in sequence and are retained on each revision, shown to IA Wing during review, and displayed in the project approval trail.
- SS reviews project and committee details for TSC formation. AS reviews the TSC chair's submitted report and its PDF, with explicit approve/query/reject actions on that report; after AS approval, the TSC chair sends the approved report to DGS for the same review process. DGS can act only after AS approves, and can query, approve, or reject the report. After DGS approval, the tender-draft stage is created and the Admin can submit a draft PDF with an optional comment to IA Wing. IA Wing can approve, query, or reject the draft; an Admin responds to a query with a revised PDF and response comment. AS, DGS, and IA Wing approvers see their pending submissions in the main dashboard approval inbox. Committee formation is not presented as a report approval. Project notifications link directly to the associated project.
- When SS queries a TSC formation, the Admin can edit the committee name, selected members, and chair directly on the project page, add a response, optionally attach a supporting PDF (up to 10 MB), and resend the updated TSC for approval. The edits, attachment, and response remain available with the approval trail.
- Active TSC members can upload versioned working-report PDFs from their project page; earlier versions remain available to view/download for all members of that committee. The TSC chair has an additional final-report upload that routes to the single AS approval step, with an optional comment. Only after AS approves can the chair send the approved report to the single DGS approval step. Both report stages are created automatically if needed. When AS or DGS queries the report, the chair responds by uploading a revised PDF and a required response comment together; the revision returns to that rank, and the response and resubmission remain in the approval trail.
- After IA Wing approves the latest tender draft, Admins can search active, verified vendors by their product/service offerings and vendor-category names/descriptions. Local fuzzy token matching ranks results. Admins can save a project-specific vendor shortlist; selections persist in the existing project-vendor records. Once selected, Admins can record that the approved draft was sent to each vendor offline; the system stores the server timestamp, actor, method, and activity/audit trail. Vendors do not sign in and the app does not send the tender externally.
- Admins can upload a technical bid PDF for each dispatched vendor after TEC approval. Files are PDF-validated (maximum 10 MB), accessible to active TEC members, and downloadable in the project workflow; financial bids remain hidden from TEC members.
- Active TEC members can share working-report PDFs with the committee. Only the TEC chair can submit a final report, and only after technical bids are recorded for every selected vendor. The final report is recorded in the project stage timeline, notifies Admin, and is downloadable by Admin from the project workflow.
- After Admin completes vendor qualification, Admin forms the TAC from the project workspace. Exactly one active, verified IA Wing user must be selected as a TAC member, alongside at least one other member; Admin may be selected but is not added automatically. The chair may also be the IA Wing member, but must be included in the committee. The TAC formation is submitted to SS for approval; committee access remains gated until SS approves. Formation queries can be answered and resubmitted from the project with the revised membership and an optional supporting PDF, with the full trail retained.
- Admin's TAC financial-bid step follows SS approval of TAC formation. The shortlist submission must include exactly three eligible vendors, or all eligible vendors if fewer than three qualify, with a financial-bid PDF for each.
- After Admin submits the financial bids, only the TAC chair can upload the final report PDF. Reports are versioned, logged in project activity/audit history, and available for download to Admin and active TAC members from the project workflow. TAC voting has been removed.
- After the TAC chair submits the final report, Admin selects one final vendor from the submitted TAC shortlist. The choice completes the final-vendor stage, appears to Admin and active TAC members, and is recorded in project activity, audit history, and committee notifications.
- The frontend project dashboard links to a project workspace and displays separate "My committee duties" and "My approval duties" sections. An IA Wing user serving on a TAC sees TAC membership in the committee section and tender-draft approvals in the approver section; these duties are not conflated. The workspace shows each unlocked workflow stage, relevant committee documents, and the approval trail without generic workflow setup or later-stage placeholders.

Opening the backend root at http://localhost:8000/ shows a status page with links. Use http://localhost:5173/ to test the actual frontend; the API is not the frontend.

This is an initial workflow implementation, not a complete procurement platform. Vendor dispatch is recorded after an offline action; vendors do not log in. Bids are entered by staff. Contract award, purchase-order creation, and comprehensive role/permission administration are not yet implemented. Configure approval policies before submitting work that requires upper-level approval.

## API routes

- Authentication: `POST /api/v1/auth/login/`, `POST /api/v1/auth/refresh/`, `POST /api/v1/auth/register/`, `GET /api/v1/auth/me/`
- Departments: `/api/v1/departments/`
- Users and verification: `/api/v1/users/`, `/api/v1/users/{id}/verify/`, `/reject/`, `/assign_role/`
- Projects: `/api/v1/projects/`, `/api/v1/projects/{id}/activities/`, `/messages/`, `/documents/`, and `/api/v1/projects/{id}/vendors/` to list, select, or remove project vendor selections after tender approval
- Vendor qualification: `/api/v1/projects/{id}/qualified-vendors/` (Admin-only GET/POST); decisions require a completed TEC final report and a technical bid for every selected vendor
- Vendors: `/api/v1/vendors/`, `/verify/`, `/reject/`
- Workflow dashboard: `GET /api/v1/workflow/dashboard/`
- Workflow resources: `/api/v1/workflow/stages/`, `/committees/`, `/submissions/`, `/approval-policies/`, `/approval-policy-levels/`, `/tenders/`, `/bids/`, `/tec-documents/`, `/tac-documents/`, and `/negotiations/`
- TAC final-vendor decision: `POST /api/v1/workflow/tac-shortlist/final-selection/` (Admin only; accepts `project` and a shortlisted `vendor`); `GET` on the same route returns the decision to Admin and active TAC members.
- TSC shared PDFs: `/api/v1/workflow/tsc-documents/` (committee members only), with protected `/api/v1/workflow/tsc-documents/{id}/download/`
- Audit and notifications: `/api/v1/audit-logs/`, `/api/v1/notifications/`

Workflow API resources are mounted under `/api/v1/workflow/`. Approval policies define ordered user- or role-based approvers for each submission type: SS approves committee formation; TSC reports require AS then HQ approval, followed by a separate DGS review; TEC final reports require HQ approval; and IA Wing approves tender drafts. Approval queries and chair responses are retained in the submission history, with revised reports uploaded as new revisions. SS approval activates each committee and grants its members project access. Tender-draft submission and tender creation are rejected by the API until DGS approves the latest TSC report. The Admin vendor-selection endpoint is enabled only after IA Wing approves that tender draft. The tender draft requires expected vendor-dispatch, bid-receipt, and product-arrival dates; the project timeline tracks dispatch and bid receipt, reports overdue and late completion, and shows product arrival as informational because delivery tracking is outside the current workflow. Bid receipt is dated when Admin uploads its technical bid. After every selected vendor has a recorded offline tender dispatch, Admin can propose a TEC for SS approval. Once the TEC is active, Admin uploads each vendor's technical bid through `POST /api/v1/workflow/bids/receive/`; the active TEC can view and download technical files but cannot see financial bid files. TEC members share working reports through `/api/v1/workflow/tec-documents/`, and only the TEC chair can upload a final report after all selected vendors' technical bids are recorded. The report is routed to HQ; Admin can download it in the project workspace, while vendor qualification remains locked until HQ approves it. Each qualification decision stores its status, deciding Admin, and timestamp; the API records a project audit/activity entry and completes the vendor-qualification stage. After completion, the qualification decision is read-only and remains visible in project history. The project workspace closes a stage's action after completion while preserving submissions and approval history; later stages remain locked until their prerequisites are complete. Approver project visibility is limited to projects with the corresponding pending review. The `POST /api/v1/vendors/match/` endpoint ranks active, verified vendors by their product/service descriptions, category names, and category descriptions. Vendor matches use local fuzzy token similarity (not an external or AI search service). Admins can record offline dispatches with server-generated timestamps and audit entries. `GET /api/v1/workflow/tenders/?project={id}` and `GET /api/v1/workflow/bids/?project={id}` provide project-scoped records. TSC working documents are visible only to TSC members. Regular users can see projects they created or are members of; admins and Super Admins can see all projects.

## Local development without Docker

Install Python 3.12, PostgreSQL, and Node.js 20 or newer. Create a Python virtual environment, install `backend/requirements.txt`, configure PostgreSQL environment values, and from `backend/` run:

```sh
python manage.py makemigrations accounts departments procurement vendors documents workflow committees notifications audit
python manage.py migrate
python manage.py seed_initial_data
python manage.py runserver
```

In a separate terminal, from `frontend/` run:

```sh
npm install
npm run dev
```

Local settings use `POSTGRES_HOST=db` by default; set it to `localhost` for a locally installed PostgreSQL server. Set `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` to select local bootstrap credentials.

## Tests

With dependencies installed, run `python manage.py test` from `backend/`. Tests cover project access and the procurement workflow, including TSC AS → HQ → DGS approvals, TEC HQ query/revision history, bid access, and TAC final-report uploads. Frontend production build can be checked with `npm run build` from `frontend/`.
