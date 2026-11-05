# How to Use the Procurement Project Management System

Start the local stack with `docker compose up --build` from the repository root, then open [http://localhost:5173/](http://localhost:5173/). The backend is at [http://localhost:8000/api/](http://localhost:8000/api/). See [README.md](README.md) for initial setup.

## Local accounts

These accounts are created only when `DEBUG=True`:

| Account | Email | Password | Purpose |
| --- | --- | --- | --- |
| Super Admin | `admin@procurement.local` | `procurement-dev-2026` | Manage users, vendors, committees, projects, and all stages |
| Project user | `demo.user@procurement.local` | `procurement-demo-2026` | View assigned work and upload documents |
| TSC reviewer | `reviewer@procurement.local` | `procurement-demo-2026` | TSC committee participation |
| Pending user | `pending.user@procurement.local` | `procurement-demo-2026` | Try the account verification flow |

Administrators create all system accounts in **User Management** and set each user's designation (for example, `TSC`, `AS (IA)`, `DG`, `SS`, `HQ`, `CS (SR)`, `IA`, `TEC`, `TAC`, `IFD`, or `CFA`). Vendors are records only and never sign in. Admins add vendors in **Vendor Management**, verify them, then attach the verified vendors to projects. Internal committee members record vendor correspondence, responses, and queries in the project.

## Create and staff a project

Only ADMIN or SUPER_ADMIN accounts can create a procurement project. Create users and departments first, then create the project from **Dashboard**. Open it with the eye button to review its timeline, upload PDFs, assign project members, and associate verified vendors. A project appears to its creator, assigned members, committee members, and administrators. Vendors do not have accounts or project access.

Admins create committees in **Committees**: choose the project, enter a name containing its function (such as TSC, TEC, or TAC), form it, then assign active, verified users with the member designation. For example, assign the user representative to the TAC using the designation `User Representative`.

## Follow the procurement stages

Open a project drawer and use **Procurement workflow**. Each successful stage change is recorded in the activity timeline and audit history. The API checks the user's designation or membership in the committee responsible for that stage; admins can manage any stage.

| Stage | Action and next stage |
| --- | --- |
| Requirement / Draft | Admin creates project; **Submit** → TSC Approval |
| TSC Approval | Form a TSC committee, then admin records approval; **Approve** → Board Formation |
| Board Formation | Form a board committee, then submit the TSC report → TSC Report for AS (IA) |
| TSC Report for AS (IA) | TSC **Forward** → AS (IA) Approval |
| AS (IA) Approval | AS/IA **Approve** → DG/SS Approval |
| DG/SS Approval | DG or SS **Approve** → HQ Review |
| HQ Review | HQ asks/answers queries, then **Forward** → CS (SR) Review |
| CS (SR) Review | CS/SR handles queries, then **Forward** → Draft Tender to IA |
| Draft Tender to IA | IA checks correctness and **Acknowledges** → Tender Issued |
| Tender Issued | Admin opens response period → Vendor Response |
| Vendor Response | The responsible committee uploads vendor response PDFs and records vendor updates against the selected verified vendor; **Close Tender** → Technical Bid Board |
| Technical Bid Board | Form a technical bid opening board → TEC Formation |
| TEC Formation | Form the TEC committee; SS approves formation → TEC Report |
| TEC Report | TEC submits its report; HQ queries are answered; **Forward** → Price Bid Open |
| Price Bid Open | Admin opens the price bid → TAC Review |
| TAC Review | Form TAC and assign a `User Representative`; then TAC reviews, negotiates with vendor, and records decision; **Accept Tender** → IFD/CFA Approval |
| IFD/CFA Approval | IFD/CFA **Approve** → Approved |

The workflow area supports stage queries. Enter a subject, message, and the recipient's designation (for example `HQ` or `CS (SR)`). Project participants can associate a query with a verified vendor already attached to the project. The designated internal user or project committee replies on that query; vendor correspondence is recorded by the committee. Unanswered queries prevent advancing the project.

## Documents and records

Upload valid PDF files up to 10 MB from the drawer's paperclip control. Compose stores them in the repository-root `media/` directory, mounted into the backend container and ignored by Git. Use **View** for the in-app preview, **Download** to save the PDF, and **New version** to upload a revision. The activity timeline records document changes. Messages and stage queries provide the project discussion trail.

## Sample data

The local seed creates **District Hospital Diagnostic Equipment Procurement** as an in-progress sample and **Full Workflow Test — Diagnostic Imaging Equipment** as a clean Draft. It also creates a verified Aster vendor record that admins can associate with a project. Seed data runs on startup and can be refreshed with `docker compose exec backend python manage.py seed_initial_data`; this does not reset stage progress or test changes.
