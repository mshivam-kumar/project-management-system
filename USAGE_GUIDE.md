# How to Use the Procurement Project Management System

This guide covers the local development application. Start the services from the repository root with `docker compose up --build`, then open [http://localhost:5173/](http://localhost:5173/). See [README.md](README.md) for prerequisites and service URLs.

## Sign in

Use one of the development accounts below. The regular user accounts share the same password.

| Account | Email | Password | Use |
| --- | --- | --- | --- |
| Super Admin | `admin@procurement.local` | `procurement-dev-2026` | Manage users, departments, vendors, committees, and project stages |
| Project user | `demo.user@procurement.local` | `procurement-demo-2026` | Create projects, post messages, and upload project documents |
| Committee reviewer | `reviewer@procurement.local` | `procurement-demo-2026` | Join projects and committees as a reviewer |
| Pending user | `pending.user@procurement.local` | `procurement-demo-2026` | Try sign-in before and after administrator verification |

The pending user cannot sign in until an admin verifies the account from **User Management**. These accounts are created only in development mode (`DEBUG=True`).

## Work with projects

1. Sign in with a verified account and open **Dashboard** or **Projects**.
2. Click **New project**, enter a title, department, estimated amount, and description, then create it. New projects start in **Draft**.
3. Select the eye icon in the project row to open its details drawer.
4. Use the drawer to read the activity timeline, send a message, upload a PDF, assign project members (admin only), and associate verified vendors.
5. To view a PDF, use **View** in the Documents list. **Download** saves a copy. **New version** uploads a replacement as the next version of the same document.

PDF uploads must be valid PDFs smaller than 10 MB.

## Manage committees

Admins open **Committees** from the left navigation. Select a project, enter a committee name, and click **Form**. Select the committee row to see its members and assign active, verified users. The sample `reviewer@procurement.local` account is available for this.

Once added to a committee, a user can see that project on their dashboard and open its activity, messages, and documents. They do not need a separate project-team assignment. Users who are not project creators, assigned project members, committee members, or admins cannot see the project.

The seeded **District Hospital Diagnostic Equipment Procurement** project already has a Technical Evaluation Committee with three members. Its row appears in **Committees** after the development seed has run. A separate **Full Workflow Test — Diagnostic Imaging Equipment** project starts at Draft so you can run the complete workflow yourself.

## Advance a project through stages

Only ADMIN and SUPER_ADMIN users can advance stages. Open the project with the eye icon and use **Stage actions** in its details drawer. Each action asks for an optional note and adds a dated entry to the activity timeline and audit log.

| Current status | Available action | Result |
| --- | --- | --- |
| Draft | Submit | Submitted |
| Returned | Submit | Submitted |
| Submitted | Forward | Under Review |
| Under Review | Forward | Committee Formation |
| Committee Formation | Forward | Committee Review |
| Committee Review | Forward | Pending Approval |
| Pending Approval | Approve | Approved |
| Submitted through Pending Approval | Return | Returned |
| Submitted through Pending Approval | Reject | Rejected |

To complete committee work, move the project to **Committee Formation**, form the committee and assign members in **Committees**, then return to the project drawer and click **Forward** to enter **Committee Review**.

## Notifications and profile

Open **Notifications** to see project assignments and document updates. Open your name in the top bar to change your password or view profile details. Sign out from the bottom of the left navigation.

