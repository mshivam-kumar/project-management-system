# Procurement Project Management System

Local development foundation for procurement projects, user verification, vendor registry, document collaboration, audit history, and committee setup.

Guides: [How to use the software](USAGE_GUIDE.md) · [Manual functionality test guide](MANUAL_TEST_GUIDE.md).

## Fresh PC setup

Install Docker Desktop on [Windows](https://docs.docker.com/desktop/setup/install/windows-install/), [macOS](https://docs.docker.com/desktop/setup/install/mac-install/), or [Linux](https://docs.docker.com/desktop/setup/install/linux/). On Linux, you can also install Docker Engine and the [Docker Compose plugin](https://docs.docker.com/compose/install/linux/). Start Docker Desktop or the Docker service before continuing. On Windows, use Linux containers (the Docker Desktop default).

No host installation of Python, Node.js, or PostgreSQL is needed. Docker builds the backend image and installs Python packages from `backend/requirements.txt`; the frontend container installs npm dependencies from `frontend/package-lock.json`; PostgreSQL runs in its own container.

Check Docker and Compose are available:

```sh
docker --version
docker compose version
```

Download or clone the repository, open a terminal in its root directory (the folder containing `docker-compose.yml`), then build and start the stack:

```sh
docker compose up --build -d
```

The first run needs an internet connection to download the container images and install packages. Check startup:

```sh
docker compose ps
docker compose logs --tail=100 backend
```

Wait for the database and backend to report healthy. The backend applies the Django migrations included in the repository and seeds sample departments, roles, users, and projects. The frontend starts after the backend is healthy.

- **Frontend:** http://localhost:5173/
- **Backend status page:** http://localhost:8000/
- **API browser:** http://localhost:8000/api/v1/
- **Django admin:** http://localhost:8000/admin/

Development sign-in: `admin@procurement.local` / `procurement-dev-2026`.

Other local development accounts use the password `procurement-demo-2026`:

- Verified regular user: `demo.user@procurement.local`
- Verified TSC reviewer: `reviewer@procurement.local`
- Pending regular user: `pending.user@procurement.local` (cannot sign in until an admin verifies it)

These demo accounts are created only when Django `DEBUG` is enabled. Use either verified account to sign in immediately, or sign in as the admin and approve the pending user under **User Management**. Accounts and projects are seeded on backend startup. New stakeholder accounts are created by an administrator; vendors do not sign in. If the stack was running before you updated the repository, recreate the services so Compose applies the local media mount and the backend applies migrations and startup seeding:

```sh
docker compose up --build -d
```

The development seed creates two manual-test projects: **District Hospital Diagnostic Equipment Procurement** in **TEC Report**, with its populated committee, verified vendor, stage history, and sample PDF; and **Full Workflow Test — Diagnostic Imaging Equipment** in **Draft**, ready to move through every stage, with a sample PDF and verified vendor. It also creates the reviewer and regular-user accounts. Seed data is added if missing and does not reset project progress or overwrite local test records on backend restart.

If the containers are already running and you want to add any missing seed records, run:

```sh
docker compose exec backend python manage.py seed_initial_data
```

If dependency installation fails, confirm Docker has internet access, then rebuild and recreate the services:

```sh
docker compose down
docker compose build --no-cache backend
docker compose up --build -d
docker compose logs --tail=100 backend frontend
```

The backend image build runs `pip install -r requirements.txt`. The frontend startup runs `npm ci` against the committed lockfile. `docker compose restart` only restarts existing containers; use `docker compose up --build -d` after changing Dockerfiles or backend Python requirements.

These credentials and the Django secret in Compose are local development defaults only. Do not expose this configuration to a public network or reuse the values for deployment.

When changing backend models, generate a migration and then apply it:

```sh
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
```

Commit the generated migration file with the model change so a fresh checkout can build the database schema. The backend applies committed migrations automatically at startup.

If this is a brand-new local database and a previous failed startup left a partially created schema, remove the local test database and restart:

```sh
docker compose down -v
docker compose up --build -d
```

`docker compose down -v` deletes the local PostgreSQL database. Uploaded files in the repository-root `media/` bind mount remain in place.

For a normal backend restart (which applies migrations and runs the seed command):

```sh
docker compose restart backend
```

Run the backend checks and tests:

```sh
docker compose exec backend python manage.py check
docker compose exec backend python manage.py test
```

Build-check the frontend:

```sh
docker compose exec frontend npm run build
```

Stop services with `docker compose down`. `docker compose down -v` removes PostgreSQL data; uploaded documents remain in the repository-root `media/` folder.

## Procurement workflow and committee handoffs

The system digitizes the procurement trail from the initial requirement through final CFA approval. Work moves forward one stage at a time: the committee or office responsible for the current stage records its decision, documents, and any query/reply, then hands the project to the next stage. Set up the next stage's committee and assign its members before that handoff. The project timeline records the stage transitions and related activity.

1. **Requirement — Admin:** An administrator creates the project and records the procurement requirement.
2. **TSC approval — Admin / TSC:** The administrator creates the TSC committee and assigns its members. The TSC reviews and approves the committee proposal.
3. **Board formation — Admin / Board:** After TSC approval, the administrator forms the required board and records its membership.
4. **TSC report for AS (IA) perusal — TSC:** The TSC prepares and uploads its report, then forwards it for review by AS (IA).
5. **DG/SS approval — AS (IA), then ARC Admin / DG/SS:** AS (IA) reviews and approves the report. ARC Admin routes it for DG/SS approval.
6. **HQ review — HQ:** HQ may raise a query on a topic. The responsible committee records the query and reply before forwarding the file.
7. **CS (SR) review — TSC / CS (SR):** The TSC report is forwarded to CS (SR); record any query and reply at this stage.
8. **Draft tender — IA Wing:** The draft tender is sent to the IA Wing for review.
9. **Tender issue — IA Wing:** IA acknowledges the draft's correctness and issues the tender within the prescribed time.
10. **Vendor responses — Responsible committee:** During the tender response period, the committee receives vendor submissions and records vendor queries and replies in the project. Vendors do not have system accounts or log in.
11. **Technical bid opening board — Admin / Board:** After tender finalization, the administrator forms the technical bid opening board and assigns its members.
12. **TEC formation and approval — TEC / SS:** The TEC is formed subject to SS approval. Record and resolve queries and replies involving HQ or vendors through the committee.
13. **TEC report — TEC / HQ:** The TEC submits its report. HQ queries and the committee's replies are recorded before the report advances.
14. **Price bid opening — Authorized committee:** Once the technical stage is complete, the price bid is opened and the action is recorded.
15. **TAC review and negotiation — TAC:** TAC reviews the TEC report, records acceptance and vendor negotiation, and includes one member representing the user.
16. **CFA approval through IFD — IFD / CFA:** The file is sent through IFD for CFA approval. Recording approval completes the workflow.

Each stage's committee handles its own work, then responsibility passes to the next committee or office. Administrators create stakeholder accounts by designation, create committees, and assign verified users as membership changes. Vendors are selected only from the administrator-managed verified vendor list. Committee members handle vendor correspondence on their behalf: upload received documents and record vendor updates, questions, and replies against the relevant project stage. Queries must be answered before the workflow can advance.

## End-to-end test walkthrough

1. Sign in as the seeded Super Admin (`admin@procurement.local` / `procurement-dev-2026`) and open the seeded in-progress project from the dashboard. All demo accounts use `procurement-demo-2026` as their password.
2. Inspect its activity timeline, open **Committees** to see the committee and member assignments, and check the associated verified vendor in the project drawer.
3. In the project drawer, click **View** beside `Diagnostic_Equipment_Requirements.pdf` to preview it in the browser. **Download** saves a copy; **New version** uploads another PDF and preserves the version history.
4. Use **Procurement workflow** on the clean Draft project to follow the [stage-by-stage workflow above](#procurement-workflow-and-committee-handoffs). Set up each committee and its members before its stage takes responsibility. Raise stage queries and record replies; an unanswered query blocks advancement. See [USAGE_GUIDE.md](USAGE_GUIDE.md) and [MANUAL_TEST_GUIDE.md](MANUAL_TEST_GUIDE.md) for the full walkthrough.
5. Sign out and sign in as `pending.user@procurement.local` / `procurement-demo-2026`; sign-in is blocked while the account is pending. Sign back in as the Super Admin, open **User Management**, and verify that account to try it.
6. Admins manage stakeholder accounts and designations, assign verified users, associate verified vendor records, and create stage-specific committees. Vendors do not sign in; committee members upload received vendor documents and record vendor updates and query/reply history.
7. Check **Notifications** and **Audit Logs** for recorded operations. The stage actions update the project status and append a dated activity; they are a development workflow for exercising the trail.

Use a valid PDF (up to 10 MB) when testing uploads. Compose stores uploads in `media/` at the repository root, so files persist across container rebuilds.

## Implemented functionality

- Custom UUID user model, admin-created accounts with roles/designations, login, refresh, logout, password change, backend role checks, and activation/verification history.
- Admin and Super Admin user management, department CRUD, vendor/category CRUD, vendor verification and vendor PDF records.
- Project creation, role-scoped listing, assignment to additional users, verified vendor association, searching, filtering, sorting, and pagination.
- Project detail drawer with chronology, messages, PDF upload/version records/protected download, and project team assignment.
- Committee creation and multiple member assignments.
- Private notifications and read status, plus read-only audit log endpoints and UI.
- Dashboard summary metrics and role-based navigation.
- Stage workflow for the complete procurement process, designation and committee based approvals, stage query/reply threads, committee-managed vendor correspondence, and recorded transitions in activity and audit history.

## API routes

- Authentication: `POST /api/v1/auth/login/`, `POST /api/v1/auth/refresh/`, `POST /api/v1/auth/logout/`, `POST /api/v1/auth/password-change/`, `GET /api/v1/auth/me/`
- Dashboard: `GET /api/v1/dashboard/summary/`
- Departments and users: `/api/v1/departments/`, `/api/v1/users/`, user `verify`, `reject`, `deactivate`, and `assign_role` actions
- Procurement: `/api/v1/projects/`, project `activities`, `messages`, `documents`, `members`, and `vendors` actions
- Vendors: `/api/v1/vendors/`, `/api/v1/vendor-categories/`, vendor `verify`, `reject`, `suspend`, `documents`, and protected document download actions
- Committees: `/api/v1/committees/`, committee `members` action
- Notifications and audit: `/api/v1/notifications/`, notification `read` action, `/api/v1/audit-logs/`

DRF pagination, search, filters, validation, and backend permissions are enabled. Regular users can access projects they created, have been assigned to, or are committee members on; admins can view all projects. Committee membership grants access to that project and its protected details, while unrelated users cannot access it. Only active, verified vendors from the admin-managed vendor list can be attached to projects; vendors have no accounts or system access. Historical verification and audit records are not exposed for modification.

## Storage and configuration

PostgreSQL is used in Compose. Uploaded files use Django's local file-storage abstraction under the repository-root `media/` directory; Compose mounts this directory into the backend container and database rows store file references. The folder is local-only and ignored by Git. File retrieval is authenticated and checked against project access. Compose includes local development defaults, so a `.env` file is not required. To override the local database or bootstrap administrator values, create a `.env` file using `.env.example` as a reference.

## Manual walkthrough

Use [MANUAL_TEST_GUIDE.md](MANUAL_TEST_GUIDE.md) for the stage-by-stage local walkthrough and [USAGE_GUIDE.md](USAGE_GUIDE.md) for account, committee, vendor, and document instructions.
