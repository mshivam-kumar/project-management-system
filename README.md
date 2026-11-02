# Procurement Project Management System

Local development foundation for procurement projects, user verification, vendor registry, document collaboration, audit history, and committee setup.

## Start the application

Prerequisite: Docker Engine with Docker Compose.

From the project root:

```sh
docker compose up --build
```

The first startup builds the services, waits for PostgreSQL, generates and applies Django migrations, seeds sample departments and roles, and creates a development Super Admin.

- **Frontend:** http://localhost:5173/
- **Backend status page:** http://localhost:8000/
- **API browser:** http://localhost:8000/api/v1/
- **Django admin:** http://localhost:8000/admin/

Development sign-in: `admin@procurement.local` / `procurement-dev-2026`.

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

Stop the services with Ctrl+C. To remove services and the local database volume, run `docker compose down -v` (this deletes local test data).

## End-to-end test walkthrough

1. Sign in as the seeded Super Admin.
2. Open **Departments** and create or edit a department.
3. Open **Vendor Categories**, add a category, then add a vendor from **Vendor Management** and verify it.
4. Sign out and register a new account from the sign-in page. The account remains pending until an administrator verifies it.
5. Sign back in as the Super Admin, open **User Management**, verify the registration, and assign its department. Super Admins can create administrator accounts from **Admin Management**.
6. Sign in as the verified user, create a project, open it with the eye action, post a message, upload a PDF, and inspect the timeline.
7. As an administrator, assign another verified user to the project, associate a verified active vendor, and form a committee. Assigned users can sign in and see the shared project.
8. Check **Notifications** and **Audit Logs** for recorded operations. Workflow approval buttons remain disabled because no workflow transitions are implemented.

Use a small valid PDF (up to 10 MB) when testing uploads.

## Implemented functionality

- Custom UUID user model, user roles, registration, login, refresh, logout, password change, backend role checks, and activation/verification history.
- Admin and Super Admin user management, department CRUD, vendor/category CRUD, vendor verification and vendor PDF records.
- Project creation, role-scoped listing, assignment to additional users, verified vendor association, searching, filtering, sorting, and pagination.
- Project detail drawer with chronology, messages, PDF upload/version records/protected download, and project team assignment.
- Committee creation and multiple member assignments.
- Private notifications and read status, plus read-only audit log endpoints and UI.
- Dashboard summary metrics and role-based navigation.
- Workflow template, stage, rule, task, action, and project workflow model foundation. Approval/forward/return/reject transitions are intentionally not simulated.

## API routes

- Authentication: `POST /api/v1/auth/login/`, `POST /api/v1/auth/refresh/`, `POST /api/v1/auth/logout/`, `POST /api/v1/auth/register/`, `POST /api/v1/auth/password-change/`, `GET /api/v1/auth/me/`
- Dashboard: `GET /api/v1/dashboard/summary/`
- Departments and users: `/api/v1/departments/`, `/api/v1/users/`, user `verify`, `reject`, `deactivate`, and `assign_role` actions
- Procurement: `/api/v1/projects/`, project `activities`, `messages`, `documents`, `members`, and `vendors` actions
- Vendors: `/api/v1/vendors/`, `/api/v1/vendor-categories/`, vendor `verify`, `reject`, `suspend`, `documents`, and protected document download actions
- Committees: `/api/v1/committees/`, committee `members` action
- Notifications and audit: `/api/v1/notifications/`, notification `read` action, `/api/v1/audit-logs/`

DRF pagination, search, filters, validation, and backend permissions are enabled. Regular users can access projects they created or have been assigned to; admins can view all projects. Only active, verified vendors can be attached to projects. Historical verification and audit records are not exposed for modification.

## Storage and configuration

PostgreSQL is used in Compose. Uploaded files use Django's local file-storage abstraction under `backend/media`; database rows contain metadata and storage references. File retrieval is authenticated and checked against project access. Compose includes local development defaults, so a `.env` file is not required. To override the local database or bootstrap administrator values, create a `.env` file using `.env.example` as a reference.

## Tests

The backend test suite covers registration/login verification, admin permissions, department management, project scoping and assignment, project messages, PDF validation/upload, vendor verification and eligibility, committee membership, and private notifications/password updates. Run it with the Docker command above.
