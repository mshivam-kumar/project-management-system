# Data Architecture & Persistence Layer

The application currently uses PostgreSQL through Django's ORM and migrations. The proposed procurement workflow extends the existing project, committee, document, vendor, notification, and audit records with dated stages, revisioned submissions, configurable approval routes, tender dispatch, restricted bid files, TAC voting, and negotiation history.

## Database Configuration

| Service / Module | DB Type | Profile | Driver | Connection | Migration Tool |
|---|---|---|---|---|---|
| Django application | PostgreSQL | Docker local development | psycopg 3 | Environment-configured PostgreSQL connection | Django migrations |
| Django application | PostgreSQL | Local development | psycopg 3 | PostgreSQL host and credentials supplied by environment | Django migrations |

The repository currently has no separate SQLite/test profile. Test database configuration is delegated to Django's test runner. Development seed data is created by a management command.

## Data Ownership per Service

| Service / Module | Tables / Entities Owned | ORM Framework | Caching | Notes |
|---|---|---|---|---|
| Accounts | User, Role, UserRole, UserVerification | Django ORM | No server-side cache found | UUID user identifiers; Django password hashing |
| Departments | Department | Django ORM | No server-side cache found | Referenced by users and projects |
| Procurement | ProcurementProject, ProjectActivity, ProjectMessage, ProjectMember | Django ORM | No server-side cache found | Project is the root for project-scoped records |
| Committees | Committee, CommitteeMember | Django ORM | No server-side cache found | Current models need committee type, chair, and project-scoped role semantics |
| Documents | Document, DocumentVersion | Django ORM | No server-side cache found | Versioned project file storage |
| Vendors | Vendor, VendorCategory, VendorCategoryMapping, VendorDocument, VendorVerification, ProjectVendor | Django ORM | No server-side cache found | Vendor identities are internal records; vendors have no application login |
| Workflow | WorkflowTemplate, WorkflowStage, WorkflowRule, ProjectWorkflow, WorkflowTask, WorkflowAction | Django ORM | No server-side cache found | Current models are a foundation; no workflow API or execution is wired in |
| Notifications | Notification | Django ORM | No server-side cache found | Recipient-scoped records |
| Audit | AuditLog | Django ORM | No server-side cache found | JSON snapshots for selected operations |
| Proposed approvals and tender modules | ProjectStage, StageSubmission, ApprovalPolicy, ApprovalPolicyLevel, ApprovalRequest, ApprovalStep, ApprovalEvent, ReviewThread, ReviewMessage, Tender, TenderDispatch, VendorBid, BidDocument, TACVote, VendorSelection, NegotiationThread, NegotiationMessage | Django ORM | No server-side cache proposed | Add as models/migrations within existing Django app boundaries or new focused apps |

## Entity Model

The diagram shows the proposed target schema's central records. Existing entities are retained where appropriate; names and relationships for proposed entities are design recommendations, not claims that those tables already exist.

<!-- mermaid-checked: every attribute is `<type> <name> [<key>] ["<description>"]` with at most one of PK/FK/UK, no \n in descriptions, no {} in descriptions, every relationship label is double-quoted -->
~~~mermaid
erDiagram
    Department ||--o{ User : "organizes"
    User }o--o{ Role : "has roles"
    Department ||--o{ Project : "owns"
    User ||--o{ Project : "creates"
    Project ||--o{ ProjectStage : "has stages"
    Project ||--o{ Committee : "has committees"
    Committee ||--o{ CommitteeMember : "includes"
    User ||--o{ CommitteeMember : "serves on"
    ProjectStage ||--o{ StageSubmission : "receives"
    Committee o|--o{ StageSubmission : "authors"
    User ||--o{ StageSubmission : "submits"
    StageSubmission o|--o{ StageSubmission : "is revised by"
    StageSubmission ||--o{ Document : "has files"
    StageSubmission ||--o{ ApprovalRequest : "is reviewed through"
    ApprovalPolicy ||--o{ ApprovalPolicyLevel : "defines"
    ApprovalPolicy ||--o{ ApprovalRequest : "routes"
    ApprovalRequest ||--o{ ApprovalStep : "contains"
    ApprovalRequest o|--o{ ApprovalRequest : "is followed by"
    ApprovalStep ||--o{ ApprovalEvent : "records"
    ApprovalStep ||--o{ ReviewThread : "can raise"
    ReviewThread ||--o{ ReviewMessage : "contains"
    User ||--o{ ApprovalEvent : "acts"
    User ||--o{ ReviewMessage : "writes"
    Project ||--o| Tender : "may have"
    Tender ||--o{ TenderDispatch : "records dispatch"
    Vendor ||--o{ TenderDispatch : "receives"
    User ||--o{ TenderDispatch : "records"
    Tender ||--o{ VendorBid : "collects"
    Vendor ||--o{ VendorBid : "submits offline"
    User ||--o{ VendorBid : "records"
    VendorBid ||--o{ BidDocument : "contains"
    Document ||--o{ DocumentVersion : "versions"
    BidDocument }o--|| Document : "references"
    Committee ||--o{ TACVote : "casts"
    User ||--o{ TACVote : "records vote"
    Vendor ||--o{ TACVote : "receives votes"
    Project ||--o| VendorSelection : "records selection"
    Vendor ||--o{ VendorSelection : "may be selected"
    Project ||--o{ NegotiationThread : "tracks negotiation"
    Vendor ||--o{ NegotiationThread : "negotiates with"
    NegotiationThread ||--o{ NegotiationMessage : "contains"
    User ||--o{ NegotiationMessage : "writes"
    Project {
        uuid id PK
        string projectCode UK
        string title
        string status
    }
    ProjectStage {
        uuid id PK
        uuid projectId FK
        string stageType
        int sequence
        string status
        date plannedStart
        date dueDate
        dateTime actualStart
        dateTime completedAt
    }
    Committee {
        uuid id PK
        uuid projectId FK
        string committeeType
        string status
    }
    CommitteeMember {
        uuid id PK
        uuid committeeId FK
        uuid userId FK
        string memberRole
    }
    StageSubmission {
        uuid id PK
        uuid stageId FK
        uuid committeeId FK
        uuid previousSubmissionId FK
        uuid submittedById FK
        string submissionType
        int revision
        string status
    }
    ApprovalPolicy {
        uuid id PK
        string submissionType
        string name
        bool isActive
    }
    ApprovalPolicyLevel {
        uuid id PK
        uuid policyId FK
        int sequence
        string approverRole
    }
    ApprovalRequest {
        uuid id PK
        uuid submissionId FK
        uuid policyId FK
        uuid previousRequestId FK
        string status
        dateTime submittedAt
        dateTime closedAt
    }
    ApprovalStep {
        uuid id PK
        uuid requestId FK
        int sequence
        string approverRole
        uuid assignedUserId FK
        string status
    }
    ApprovalEvent {
        uuid id PK
        uuid stepId FK
        uuid actorId FK
        string action
        string comments
        dateTime createdAt
    }
    ReviewThread {
        uuid id PK
        uuid stepId FK
        uuid openedById FK
        string status
    }
    ReviewMessage {
        uuid id PK
        uuid threadId FK
        uuid authorId FK
        string body
        dateTime createdAt
    }
    ApprovalPolicy {
        uuid id PK
        string submissionType
        string name
        bool isActive
    }
    Tender {
        uuid id PK
        uuid projectId FK
        string reference
        string status
        dateTime bidDueAt
    }
    TenderDispatch {
        uuid id PK
        uuid tenderId FK
        uuid vendorId FK
        uuid recordedById FK
        dateTime dispatchedAt
        string method
    }
    Vendor {
        uuid id PK
        string vendorName
        string registrationNumber
        string verificationStatus
    }
    VendorBid {
        uuid id PK
        uuid tenderId FK
        uuid vendorId FK
        uuid recordedById FK
        dateTime receivedAt
        string status
    }
    BidDocument {
        uuid id PK
        uuid bidId FK
        uuid documentId FK
        string documentType
        string accessScope
    }
    Document {
        uuid id PK
        uuid projectId FK
        uuid submissionId FK
        uuid uploadedById FK
        string documentType
        string accessScope
    }
    DocumentVersion {
        uuid id PK
        uuid documentId FK
        int version
        string storagePath
        dateTime uploadedAt
    }
    TACVote {
        uuid id PK
        uuid committeeId FK
        uuid voterId FK
        uuid vendorId FK
        string choice
        dateTime castAt
    }
    VendorSelection {
        uuid id PK
        uuid projectId FK
        uuid vendorId FK
        uuid committeeId FK
        string decisionStatus
        dateTime decidedAt
    }
    NegotiationThread {
        uuid id PK
        uuid projectId FK
        uuid vendorId FK
        string status
    }
    NegotiationMessage {
        uuid id PK
        uuid threadId FK
        uuid authorId FK
        string body
        dateTime createdAt
    }
    User {
        uuid id PK
        uuid departmentId FK
        string email UK
        string verificationStatus
    }
    Role {
        uuid id PK
        string name UK
    }
    Department {
        uuid id PK
        string departmentCode UK
        string departmentName
    }
~~~

### Important schema constraints

- `ProjectStage` should have a unique `(project_id, sequence)` and a unique `(project_id, stage_type)` where only one instance of a stage is permitted. If stages can repeat, use a stage instance number instead of the second uniqueness constraint.
- `CommitteeMember` should be unique by `(committee_id, user_id)`. Enforce at most one active chair per committee. Validate that a TSC/TEC chair is a committee member and that the Admin belongs to the TAC.
- Create one approval request for each submitted revision. Link a revised `StageSubmission` to its prior submission and the new `ApprovalRequest` to the prior request. Approval-step sequence is unique within a request. Each request snapshots the approval policy levels and assigned approvers when submitted.
- `ApprovalEvent`, `ReviewMessage`, `DocumentVersion`, and negotiation messages are historical records; do not overwrite or delete them during revision. New activity is appended.
- A query pauses the active request. A response and resubmission create a new submission revision/request linked to the prior request. A rejection closes that request; it does not erase the submission or prior approvals.
- A tender should have at most one bid per vendor unless the procurement rules explicitly allow multiple bid envelopes. A bid may have one or more technical and financial document versions.
- Add database constraints preventing duplicate votes by a voter for the same TAC decision. Store the selected vendor separately from individual votes, with a unique project decision if only one final selection is allowed.
- Bid download authorization must check both the user's admin role or active TEC membership and the document's project/tender association. Hiding a link in the UI is not an access control.
- Every project stage stores planned dates separately from actual timestamps. A database check should prevent a due date earlier than its planned start.

## Key Repository Methods

The current code uses Django models and viewsets rather than repository interfaces. Existing project listing scopes records to project creators/members, while administrators can list all projects. The current code has no specialized query layer for the proposed approval and bid flows.

| Service | Repository / Query Layer | Notable Methods or Queries | Purpose |
|---|---|---|---|
| Procurement | `ProjectViewSet.get_queryset` in `backend/apps/procurement/views.py` | Filter projects to creator or project members; administrators see all | Enforce project visibility |
| Procurement | `ProjectViewSet.perform_create` and `perform_update` in `backend/apps/procurement/views.py` | Save project, then append activity and audit records transactionally | Keep core project actions traceable |
| Proposed workflow | Django ORM query/service layer | `ApprovalRequest` with ordered `ApprovalStep` rows | Return the active approval level and determine whether the request can advance |
| Proposed workflow | Django ORM query/service layer | `ProjectStage` filtered by project, ordered by sequence and due date | Build stage timelines and identify overdue work |
| Proposed bids | Django ORM query/service layer | `VendorBid` filtered by tender with related vendor and bid documents | Admin bid register; TEC-filtered review view |
| Proposed dashboards | Django ORM query/service layer | User's active committee memberships, assigned approval steps, and project stages | Show only projects and actions relevant to the signed-in user |

## Caching Strategy

No server-side cache provider or cache configuration was found in the current backend. The React frontend uses TanStack Query for short-lived client-side server-state caching; this is not a source of truth and does not replace authorization or persistence. The proposed approval and bid records should initially use database queries without a server-side cache so permissions and workflow state remain current.

## Data Ownership Boundaries

All current modules share one PostgreSQL database. Django apps provide logical ownership boundaries, but the application can directly follow relationships between apps. Keep project identity and stage lifecycle in Procurement; committee membership in Committees; approval history in Workflow/Approvals; vendor records in Vendors; and binary file version metadata in Documents. A project ID is the common link for dashboard aggregation and audit reporting.

Tender dispatch is an internal record of an offline action, not proof that the application sent a tender. Vendor bids are uploaded by staff, not by vendor accounts. Documents should be versioned and have explicit access scope. Admins and assigned TEC members may read/download bid documents; TSC members, vendors, and unassigned users may not. Approval configuration is copied into each submitted request so policy edits affect future submissions, not in-flight or historical decisions.

The current audit and activity models are useful foundations but should not be treated as the only evidence trail. Preserve domain-specific approval decisions, query messages, responses, revisions, votes, and negotiation messages as append-only records, and emit project activity entries for timeline rendering. Use a transaction around each state transition and its associated event/audit writes.

### Data Classification & Sensitivity

| Entity | Sensitive Fields | Classification | Controls in Place |
|---|---|---|---|
| User | Name, email, department, designation | PII | Authentication and role checks exist. Django stores passwords as hashes. No field-level encryption or masking was found. |
| Vendor | Contact email, phone, address, registration number, GSTIN | PII / business-sensitive | Admin-only vendor API. No field-level encryption or masking was found. |
| VendorBid / BidDocument | Technical and financial bid contents and pricing | Commercially sensitive | Proposed: restrict server-side reads and downloads to Admins and assigned TEC members; encrypt stored files and backups in the deployment environment. |
| ApprovalEvent / ReviewMessage / NegotiationMessage | Comments, decisions, staff names, possible commercial details | Internal / potentially commercially sensitive | Authenticated access and proposed project/stage authorization; no field-level encryption or masking found. |
| DocumentVersion | Tender, reports, bids, and supporting PDFs | Depends on document type | Current project-document permission derives from project access. Proposed explicit per-document access scope is required, especially for bid files. |

No payment-card data or health data is indicated by the current model or the proposed workflow. Encryption at rest, backup encryption, file malware scanning, and retention/deletion rules should be verified or specified for the actual deployment environment.
