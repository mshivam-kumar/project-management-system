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

Wait for the database and backend to report healthy. The backend then generates and applies Django migrations and seeds sample departments, roles, users, and projects. The frontend starts after the backend is healthy.

- **Frontend:** http://localhost:5173/
- **Backend status page:** http://localhost:8000/
- **API browser:** http://localhost:8000/api/v1/
- **Django admin:** http://localhost:8000/admin/

Development sign-in: `admin@procurement.local` / `procurement-dev-2026`.

Other local development accounts use the password `procurement-demo-2026`:

- Verified regular user: `demo.user@procurement.local`
- Verified committee reviewer: `reviewer@procurement.local`
- Pending regular user: `pending.user@procurement.local` (cannot sign in until an admin verifies it)

These demo accounts are created only when Django `DEBUG` is enabled. Use either verified account to sign in immediately, or sign in as the admin and approve the pending user under **User Management**. Accounts and projects are seeded on backend startup. If the stack was running before you updated the repository, restart the backend to load its new code and rerun startup seeding:

```sh
docker compose restart backend
```

The development seed creates two manual-test projects: **District Hospital Diagnostic Equipment Procurement** in **Committee Review**, with its populated committee, verified vendor, stage history, and sample PDF; and **Full Workflow Test — Diagnostic Imaging Equipment** in **Draft**, ready to move through every stage, with a sample PDF and verified vendor. It also creates the reviewer and regular-user accounts. Seed data is added if missing and does not reset project progress or overwrite local test records on backend restart.

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

When changing backend models, restart the backend to generate and apply new migrations:

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

Stop the services with `docker compose down`. To remove the local database and uploaded documents, run `docker compose down -v` (this deletes local test data).

## End-to-end test walkthrough

1. Sign in as the seeded Super Admin (`admin@procurement.local` / `procurement-dev-2026`) and open the seeded in-progress project from the dashboard. All demo accounts use `procurement-demo-2026` as their password.
2. Inspect its activity timeline, open **Committees** to see the committee and member assignments, and check the associated verified vendor in the project drawer.
3. In the project drawer, click **View** beside `Diagnostic_Equipment_Requirements.pdf` to preview it in the browser. **Download** saves a copy; **New version** uploads another PDF and preserves the version history.
4. In **Stage actions**, click **Forward** to move Committee Review → Pending Approval. Add a note when prompted. Then use **Approve**, **Return**, or **Reject** to record a decision and see it in the project trail. A returned project can be submitted again. Only admin users can advance stages.
5. Sign out and sign in as `pending.user@procurement.local` / `procurement-demo-2026`; sign-in is blocked while the account is pending. Sign back in as the Super Admin, open **User Management**, and verify that account to try it.
6. Sign in as `demo.user@procurement.local` / `procurement-demo-2026` to create a separate project, post a message, and upload and preview a PDF. The admin can assign verified users, associate verified vendors, and create committees for it.
7. Check **Notifications** and **Audit Logs** for recorded operations. The stage actions update the project status and append a dated activity; they are a development workflow for exercising the trail.

Use a small valid PDF (up to 10 MB) when testing uploads.

## Implemented functionality

- Custom UUID user model, user roles, registration, login, refresh, logout, password change, backend role checks, and activation/verification history.
- Admin and Super Admin user management, department CRUD, vendor/category CRUD, vendor verification and vendor PDF records.
- Project creation, role-scoped listing, assignment to additional users, verified vendor association, searching, filtering, sorting, and pagination.
- Project detail drawer with chronology, messages, PDF upload/version records/protected download, and project team assignment.
- Committee creation and multiple member assignments.
- Private notifications and read status, plus read-only audit log endpoints and UI.
- Dashboard summary metrics and role-based navigation.
- Development workflow actions for submission, review, committee review, approval, return, and rejection, with each transition recorded in the project activity timeline and audit log.

## API routes

- Authentication: `POST /api/v1/auth/login/`, `POST /api/v1/auth/refresh/`, `POST /api/v1/auth/logout/`, `POST /api/v1/auth/register/`, `POST /api/v1/auth/password-change/`, `GET /api/v1/auth/me/`
- Dashboard: `GET /api/v1/dashboard/summary/`
- Departments and users: `/api/v1/departments/`, `/api/v1/users/`, user `verify`, `reject`, `deactivate`, and `assign_role` actions
- Procurement: `/api/v1/projects/`, project `activities`, `messages`, `documents`, `members`, and `vendors` actions
- Vendors: `/api/v1/vendors/`, `/api/v1/vendor-categories/`, vendor `verify`, `reject`, `suspend`, `documents`, and protected document download actions
- Committees: `/api/v1/committees/`, committee `members` action
- Notifications and audit: `/api/v1/notifications/`, notification `read` action, `/api/v1/audit-logs/`

DRF pagination, search, filters, validation, and backend permissions are enabled. Regular users can access projects they created, have been assigned to, or are committee members on; admins can view all projects. Committee membership grants access to that project and its protected details, while unrelated users cannot access it. Only active, verified vendors can be attached to projects. Historical verification and audit records are not exposed for modification.

## Storage and configuration

PostgreSQL is used in Compose. Uploaded files use Django's local file-storage abstraction under `backend/media`; database rows contain metadata and storage references. File retrieval is authenticated and checked against project access. Compose includes local development defaults, so a `.env` file is not required. To override the local database or bootstrap administrator values, create a `.env` file using `.env.example` as a reference.

## Tests

The backend test suite covers registration/login verification, admin permissions, department management, project scoping and assignment, project messages, PDF validation/upload, vendor verification and eligibility, committee membership, and private notifications/password updates. Run it with the Docker command above.
