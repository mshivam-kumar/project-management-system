# Core Business Workflows

This procurement workspace coordinates project intake, technical committees, tender preparation, bid evaluation, and vendor negotiation. The system records approvals, questions, responses, decisions, files, and planned dates; vendor communication and tender distribution remain offline activities recorded by staff.

## Domain Entities

| Entity | Service / Bounded Context | Description | Key Relationships |
|---|---|---|---|
| Project | Procurement | Procurement request and overall lifecycle | Has stages, committees, tender, activities, and documents |
| ProjectStage | Procurement workflow | Dated, ordered phase of a project | Belongs to a project; has submissions and approval requests |
| Committee | Committee management | Project TSC, TEC, or TAC and its lifecycle | Belongs to a project; has members and may submit reports |
| CommitteeMember | Committee management | User's project-scoped committee appointment and committee role | Connects a user to a committee |
| StageSubmission | Workflow | A report, tender draft, or other item submitted for review | Belongs to a stage; has document versions and approval requests |
| ApprovalPolicy | Approvals | Configurable ordered approval levels for a submission type | Defines approval policy levels |
| ApprovalRequest | Approvals | One submitted revision moving through its approval route | Belongs to a stage submission and contains approval steps |
| ApprovalStep | Approvals | One assigned level in an approval request | Has events and query threads |
| ApprovalEvent | Approvals and audit | Append-only record of approval, query, response, rejection, or resubmission actions | Belongs to an approval step and identifies the actor |
| ReviewThread / ReviewMessage | Collaboration | Query and response discussion associated with an approval step | Preserves the full exchange and authors |
| Tender / TenderDispatch | Tender management | Tender details and record of offline distribution to vendors | Tender belongs to a project; dispatch connects a tender and vendor |
| VendorBid / BidDocument | Bid management | Staff-recorded bid receipt and separate technical and financial files | Connects a vendor to a tender and its files |
| TACVote / VendorSelection | Evaluation | Individual votes and the committee's recorded selected vendor | Connects TAC members, bids, and vendor |
| NegotiationThread / NegotiationMessage | Negotiation | Post-selection questions, answers, and decisions | Connects a project, selected vendor, and authors |
| ProjectActivity | Project timeline | Human-readable project-level activity feed | Belongs to project and may identify actor and stage |

## Service-to-Domain Mapping

The application is a modular Django system with one PostgreSQL database. These are logical module boundaries, not independent deployable services.

| Service / Module | Domain Context | Owned Entities | External Dependencies |
|---|---|---|---|
| Accounts | Identity and authorization | User, Role, UserRole, UserVerification | Department |
| Departments | Organization | Department | Accounts |
| Procurement | Project intake and lifecycle | Project, ProjectStage, ProjectActivity, ProjectMessage, ProjectMember | Accounts, Departments, Documents, Audit |
| Committees | Project governance | Committee, CommitteeMember | Procurement, Accounts |
| Workflow and Approvals | Stage submissions and review routing | StageSubmission, ApprovalPolicy, ApprovalPolicyLevel, ApprovalRequest, ApprovalStep, ApprovalEvent, ReviewThread, ReviewMessage | Procurement, Committees, Accounts, Documents |
| Tender and Bids | Vendor distribution and bid records | Tender, TenderDispatch, VendorBid, BidDocument | Procurement, Vendors, Documents |
| Evaluation and Negotiation | TAC selection and negotiation record | TACVote, VendorSelection, NegotiationThread, NegotiationMessage | Committees, Vendors, Accounts |
| Vendors | Vendor registry | Vendor, VendorCategory, VendorVerification | Accounts, Audit |
| Documents | File storage and version history | Document, DocumentVersion | Procurement, workflow submissions, bids |
| Notifications and Audit | User alerts and accountability | Notification, AuditLog | All modules |

## Primary Workflows

### Workflow 1: Project, TSC formation, and specification report

1. An Admin creates a project, selects its department, enters its attributes, and sets planned dates and due dates for stages.
2. The Admin selects employees for a TSC and designates one selected member as the TSC chair. Committee membership is project-scoped; it is not a permanent global user role.
3. The Admin submits TSC formation for approval. The system snapshots the applicable ordered approval route and records every decision.
4. Approvers act in sequence. Approval advances to the next level. A query pauses the request and opens a recorded thread for the submitter's response and revised submission. A rejection closes that submission; a later attempt is a new revision/request, preserving the earlier trail.
5. Once formation is approved, TSC members see the project in their dashboard. An authorized TSC member uploads a versioned PDF specification report.
6. The TSC chair reviews the report and approves or returns it with a query. After chair approval, the report enters the configured upper-level approval route.
7. The Admin dashboard shows the outcome, next action, due dates, overdue status, and complete approval/query history.

### Workflow 2: Tender draft, offline distribution, and bid intake

1. After TSC report approval, the Admin prepares a tender draft within the planned tender stage dates and submits it to the approval route.
2. On final approval, the Admin distributes the tender outside the application. The Admin records each recipient vendor and dispatch time, method, and any reference or note; the application does not send tenders to vendors.
3. Staff record received technical and financial bids by uploading their PDFs against the vendor's tender record. The system retains upload/version history and who recorded each file.
4. Bid documents are visible only to Admins and assigned TEC members. They are not available to TSC members, vendors, or other users by default.

### Workflow 3: TEC evaluation, TAC selection, and negotiation

1. The Admin forms a TEC, selects members and a chair, and submits its formation through the configured approval route.
2. After approval, assigned TEC members review the received bid documents and upload the versioned TEC report. The TEC chair approves it before it enters the upper-level approval route.
3. After the required approvals, the Admin forms a TAC that includes the Admin as a member. TAC members record votes against eligible vendors; the system records the decision and selected vendor.
4. The Admin records negotiation messages and responses with the selected vendor. Negotiation is recorded in the system; vendor login or live vendor messaging is not part of this scope.
5. The project timeline records stage dates, late stages, approval events, uploads, votes, and negotiation exchanges.

## Cross-Service Data Flows

The modules share a PostgreSQL database and call one another through Django model relationships and application services; there is no cross-service network messaging in the current design. Project-stage records provide the common timeline. Committee, submission, approval, tender, bid, and negotiation records link back to the project and user identities. Files are stored as versioned documents, while metadata, ownership, access scope, and audit events remain in the database. Dashboard views aggregate stage, approval, membership, due-date, and activity data for the signed-in user.

## Business Workflow Sequence

<!-- mermaid-checked: every participant uses `participant Id as "Label"`, no \n in aliases/messages/notes, every alt/opt/loop closed by end, no `:` inside any alias -->
~~~mermaid
sequenceDiagram
    participant Admin as "Admin"
    participant App as "Procurement App"
    participant DB as "Project Database"
    participant Approver as "Approval Level"
    participant Member as "Committee Member"
    participant Chair as "Committee Chair"
    participant Vendor as "Vendor"

    Admin->>App: Create project and set stage dates
    Admin->>App: Form TSC and submit formation
    loop Each configured approval level
        App->>Approver: Request decision
        alt Approved
            Approver->>App: Approve this level
        else Query raised
            Approver->>App: Ask question
            App->>DB: Store query thread and pause request
            App->>Admin: Notify submitter
            Admin->>App: Respond and submit revision
        else Rejected
            Approver->>App: Reject submission
        end
    end
    App->>Member: Show approved TSC project
    Member->>App: Upload specification report PDF
    App->>Chair: Request TSC chair review
    alt Chair approves
        Chair->>App: Approve report
        App->>DB: Record chair decision and start approvals
        loop Each configured approval level
            App->>Approver: Request report decision
            Approver->>App: Approve or query
        end
    else Chair requests revision
        Chair->>App: Return with query
        Member->>App: Upload revised report
    end
    Admin->>App: Submit tender draft for approval
    App->>DB: Store draft and approval request
    Approver->>App: Approve tender draft
    Admin->>Vendor: Distribute tender offline
    Admin->>App: Record tender dispatch to vendor
    Vendor->>Admin: Deliver bids outside the app
    Admin->>App: Upload technical and financial bid PDFs
    Admin->>App: Form TEC and submit formation
    Member->>App: Upload TEC report PDF
    App->>Chair: Request TEC chair review
    Chair->>App: Approve TEC report
    App->>Approver: Request upper-level approval
    Approver->>App: Approve or query TEC report
    Admin->>App: Form TAC including Admin
    Member->>App: Record TAC vote
    App->>DB: Store votes and selected vendor
    Admin->>App: Record negotiation message
    Vendor->>Admin: Respond offline
    Admin->>App: Record vendor response and closeout
~~~

## Business Rules & Decision Logic

- Approval routes are ordered and configurable by submission type. Each request stores a snapshot of its approvers/levels so later policy changes do not rewrite history.
- A request advances only after the current level approves. A query pauses the route until response and resubmission. A rejection closes that submission; a new attempt gets a new revision/request linked to the prior one.
- TSC and TEC chairs are selected by the Admin from their committee members. A chair approval is required before the report enters upper-level approval.
- TSC, TEC, and TAC memberships are project-specific. TAC includes the Admin as a member.
- The application records tender dispatch but does not send tender documents to vendors. Vendors do not sign in.
- Staff record vendor bids. Technical and financial files are distinct, versioned, and restricted to Admins and assigned TEC members.
- TAC uses majority voting. The precise threshold, treatment of abstentions, and tie/no-majority resolution must be confirmed before implementation; a simple majority of eligible votes with an explicit tie/runoff rule is a reasonable starting proposal.
- Planned start and due dates are entered per stage. Actual start/completion times are recorded separately so late and completed stages can be reported accurately.
- Approval decisions, queries, replies, revisions, document uploads, dispatch records, votes, and negotiations are append-only historical events. Corrections should be new events rather than silent edits.
- Existing project-level access rules remain in force, with additional committee membership and bid-document access checks applied at every read/download.
- The workflow as described ends with TAC vendor selection and negotiation tracking. Contract award, purchase-order creation, and final post-negotiation approval are outside the stated scope unless added explicitly.
