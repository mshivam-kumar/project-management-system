# Procurement Project Management System

A local development foundation for procurement projects, collaboration, vendor records, and future workflow execution.

## Run the current application

Prerequisites: Docker Desktop (or Docker Engine) with the Docker Compose plugin.

From the project root, run:

```sh
docker compose up --build
```

The first startup builds the Django and React environments, waits for PostgreSQL, creates the app migrations, applies them, and seeds roles, sample departments, and a development Super Admin. Open:

- Frontend: http://localhost:5173
- Backend status/links: http://localhost:8000/
- API: http://localhost:8000/api/v1/
- Django admin: http://localhost:8000/admin/

Development sign-in:

- Email: `admin@procurement.local`
- Password: `procurement-dev-2026`

These credentials and the Django secret in `docker-compose.yml` are for local development only. Do not expose this Compose configuration to a public network or reuse those values in a deployment.

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
- Project detail drawer, message posting, and PDF upload/download endpoints with a 10 MB upload limit.
- Vendor CRUD and verification endpoints; audit and notification foundations.
- Frontend dashboard with project search, filters, pagination, creation, timeline, messaging, and PDF upload. Workflow action buttons are disabled placeholders and do not change project status.

Opening the backend root at http://localhost:8000/ shows a status page with links. Use http://localhost:5173/ to test the actual frontend; the API is not the frontend.

The current UI includes explicit placeholders for tasks, notifications, and admin modules where full management screens are not yet implemented. APIs for some of those modules exist, but this foundation is not yet the complete procurement system.

## API routes

- Authentication: `POST /api/v1/auth/login/`, `POST /api/v1/auth/refresh/`, `POST /api/v1/auth/register/`, `GET /api/v1/auth/me/`
- Departments: `/api/v1/departments/`
- Users and verification: `/api/v1/users/`, `/api/v1/users/{id}/verify/`, `/reject/`, `/assign_role/`
- Projects: `/api/v1/projects/`, `/api/v1/projects/{id}/activities/`, `/messages/`, `/documents/`
- Vendors: `/api/v1/vendors/`, `/verify/`, `/reject/`
- Audit and notifications: `/api/v1/audit-logs/`, `/api/v1/notifications/`

The backend applies pagination, search, filters, and permissions. Regular users can see projects they created; admins and Super Admins can see all projects. Approval and forwarding workflows are not simulated.

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

With dependencies installed, run `python manage.py test` from `backend/`. Tests currently cover project creation and project access scoping. Frontend production build can be checked with `npm run build` from `frontend/`.
