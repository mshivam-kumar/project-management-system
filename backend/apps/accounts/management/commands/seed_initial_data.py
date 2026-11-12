import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role, UserRole, UserVerification
from apps.departments.models import Department
from apps.vendors.models import Vendor, VendorCategory, VendorCategoryMapping
from apps.workflow.models import ApprovalPolicy, ApprovalPolicyLevel, StageSubmission


ROLE_DESCRIPTIONS = {
    "SUPER_ADMIN": "System-wide administration",
    "ADMIN": "Operational administration",
    "USER": "Regular employee",
    "SS": "Secretary-level authority",
    "AS": "Additional Secretary-level authority",
    "HQ": "Headquarters approval authority",
    "DGS": "Director General of Supplies-level authority",
    "IA_WING": "Integrated Acquisition Wing tender authority",
}

EMPLOYEES = [
    ("Aarav Sharma", "EMP-1001", "Procurement Officer"),
    ("Ananya Iyer", "EMP-1002", "Finance Officer"),
    ("Vihaan Patel", "EMP-1003", "Technical Officer"),
    ("Diya Nair", "EMP-1004", "Project Officer"),
    ("Arjun Mehta", "EMP-1005", "Procurement Analyst"),
    ("Ishita Rao", "EMP-1006", "Senior Technical Officer"),
    ("Kabir Singh", "EMP-1007", "Quality Assurance Officer"),
    ("Meera Das", "EMP-1008", "Finance Analyst"),
    ("Advik Kumar", "EMP-1009", "Systems Engineer"),
    ("Saanvi Gupta", "EMP-1010", "Administrative Officer"),
]

DEMO_EMPLOYEE_PASSWORD = "demo123"
DEMO_APPROVERS = {
    "SS": ("SS Demo Approver", "ss@procurement.local", "ss123"),
    "AS": ("AS Demo Approver", "as@procurement.local", "as123"),
    "HQ": ("HQ Demo Approver", "hq@procurement.local", "hq123"),
    "DGS": ("DGS Demo Approver", "dgs@procurement.local", "dgs123"),
    "IA_WING": ("IA Wing Demo Approver", "iawing@procurement.local", "ia123"),
}

VENDOR_CATEGORIES = {
    "IT Hardware": "Computers, servers, networking and peripherals",
    "Software": "Enterprise software, licensing and software services",
    "Office Supplies": "Stationery, printing and general office supplies",
    "Furniture": "Office furniture, seating and storage",
    "Electrical Equipment": "Electrical systems, components and equipment",
    "Civil Works": "Construction, maintenance and civil engineering",
    "Vehicles": "Passenger and utility vehicles and related services",
    "Medical Equipment": "Medical devices, diagnostic and clinical equipment",
    "Security Systems": "Access control, surveillance and security services",
    "Consulting Services": "Professional, technical and management consulting",
}

VENDOR_OFFERINGS = {
    "IT Hardware": "Laptops, desktop computers, servers, network switches and printers",
    "Software": "Business software, cybersecurity tools, cloud licenses and implementation",
    "Office Supplies": "Stationery, paper, printer consumables and office supplies",
    "Furniture": "Office desks, ergonomic chairs, storage cabinets and conference furniture",
    "Electrical Equipment": "Power distribution, cables, lighting and electrical components",
    "Civil Works": "Building construction, facility repair and civil maintenance",
    "Vehicles": "Utility vehicles, fleet supply, vehicle servicing and spare parts",
    "Medical Equipment": "Diagnostic devices, patient monitoring and clinical equipment",
    "Security Systems": "CCTV, access control, alarm systems and security installation",
    "Consulting Services": "Engineering, procurement, IT and project management consulting",
}


def ensure_role_policy(user, submission_type, role_names, policy_name):
    if isinstance(role_names, str):
        role_names = [role_names]
    else:
        role_names = list(role_names)
    active_policy = ApprovalPolicy.objects.filter(
        submission_type=submission_type,
        is_active=True,
    ).first()
    if active_policy:
        levels = list(active_policy.levels.all())
        if active_policy.name != policy_name:
            active_policy.name = policy_name
            active_policy.save(update_fields=["name"])
        if levels and [
            level.approver_role for level in levels
        ] == role_names and all(not level.approver_id for level in levels):
            return active_policy
        with transaction.atomic():
            active_policy.levels.all().delete()
            ApprovalPolicyLevel.objects.bulk_create([
                ApprovalPolicyLevel(
                    policy=active_policy,
                    sequence=sequence,
                    approver_role=role_name,
                )
                for sequence, role_name in enumerate(role_names, start=1)
            ])
        return active_policy

    with transaction.atomic():
        policy = ApprovalPolicy.objects.create(
            name=policy_name,
            submission_type=submission_type,
            is_active=True,
            created_by=user,
        )
        ApprovalPolicyLevel.objects.bulk_create([
            ApprovalPolicyLevel(
                policy=policy,
                sequence=sequence,
                approver_role=role_name,
            )
            for sequence, role_name in enumerate(role_names, start=1)
        ])
    return policy


class Command(BaseCommand):
    help = "Seed roles, departments, fictional employees, vendors and approval policies."

    def handle(self, *args, **options):
        for name, description in ROLE_DESCRIPTIONS.items():
            Role.objects.get_or_create(name=name, defaults={"description": description})

        departments = {}
        for name, code in [
            ("Information Technology", "IT"),
            ("Procurement", "PROC"),
            ("Finance", "FIN"),
        ]:
            department, _ = Department.objects.get_or_create(
                department_code=code,
                defaults={"department_name": name},
            )
            departments[code] = department

        User = get_user_model()
        email = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
        name = os.getenv("BOOTSTRAP_ADMIN_NAME", "System Administrator")
        if email and password:
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "name": name,
                    "is_active": True,
                    "is_staff": True,
                    "is_superuser": True,
                    "verification_status": "VERIFIED",
                },
            )
            user.name = name
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True
            user.verification_status = "VERIFIED"
            user.set_password(password)
            user.save(
                update_fields=[
                    "name",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "verification_status",
                    "password",
                    "updated_at",
                ]
            )
            role = Role.objects.get(name="SUPER_ADMIN")
            UserRole.objects.get_or_create(user=user, role=role)
            self.stdout.write(self.style.SUCCESS(f"Bootstrap administrator ready: {email}"))

        self.seed_employees(User, departments)
        self.seed_approvers(User, departments)
        self.seed_vendors()

        policy_creator = (
            User.objects.filter(is_active=True, verification_status="VERIFIED")
            .filter(roles__name__in=["ADMIN", "SUPER_ADMIN"])
            .distinct()
            .order_by("email")
            .first()
        )
        if not policy_creator:
            self.stdout.write(
                self.style.WARNING(
                    "Approval policies were not created because no active, verified administrator exists."
                )
            )
            return

        policies = [
            (
                StageSubmission.Type.TSC_FORMATION,
                "SS",
                "TSC Formation - SS Approval",
            ),
            (
                StageSubmission.Type.TEC_FORMATION,
                "SS",
                "TEC Formation - SS Approval",
            ),
            (
                StageSubmission.Type.TAC_FORMATION,
                "SS",
                "TAC Formation - SS Approval",
            ),
            (
                StageSubmission.Type.TSC_REPORT,
                ("AS", "HQ"),
                "TSC Report - AS then HQ Approval",
            ),
            (
                StageSubmission.Type.TSC_REPORT_LEVEL3,
                "DGS",
                "TSC Report - DGS Approval",
            ),
            (
                StageSubmission.Type.TEC_REPORT,
                "HQ",
                "TEC Report - HQ Approval",
            ),
            (
                StageSubmission.Type.TENDER_DRAFT,
                "IA_WING",
                "Tender Draft - IA Wing Approval",
            ),
        ]
        for submission_type, role_name, policy_name in policies:
            policy = ensure_role_policy(
                policy_creator,
                submission_type,
                role_name,
                policy_name,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Approval policy ready: {policy.name} -> {' -> '.join(
                        [role_name] if isinstance(role_name, str) else role_name
                    )}"
                )
            )

    def seed_employees(self, User, departments):
        updated_count = 0
        for index, (employee_name, employee_id, designation) in enumerate(EMPLOYEES, start=1):
            email = f"{employee_name.lower().replace(' ', '.')}@procurement.local"
            legacy_email = f"committee.member{index:02d}@procurement.local"
            user = User.objects.filter(email=email).first() or User.objects.filter(
                email=legacy_email
            ).first()
            if user is None:
                user = User.objects.create_user(
                    email=email,
                    password=None,
                    name=employee_name,
                    employee_id=employee_id,
                    designation=designation,
                    department=departments["PROC"] if index % 2 else departments["IT"],
                    is_active=True,
                    verification_status="VERIFIED",
                )
            user.email = email
            user.name = employee_name
            user.employee_id = employee_id
            user.designation = designation
            user.department = departments["PROC"] if index % 2 else departments["IT"]
            user.is_active = True
            user.verification_status = "VERIFIED"
            user.set_password(DEMO_EMPLOYEE_PASSWORD)
            user.save(
                update_fields=[
                    "email",
                    "name",
                    "employee_id",
                    "designation",
                    "department",
                    "is_active",
                    "verification_status",
                    "password",
                    "updated_at",
                ]
            )
            user_role, _ = Role.objects.get_or_create(
                name="USER",
                defaults={"description": ROLE_DESCRIPTIONS["USER"]},
            )
            UserRole.objects.get_or_create(user=user, role=user_role)
            UserVerification.objects.get_or_create(
                user=user,
                status="VERIFIED",
                remarks="Fictional demo employee seeded by the application.",
            )
            updated_count += 1
        self.stdout.write(self.style.SUCCESS(f"Demo employees ready: {updated_count}"))

    def seed_approvers(self, User, departments):
        for role_name, (display_name, email, password) in DEMO_APPROVERS.items():
            role = Role.objects.get(name=role_name)
            legacy_users = list(
                User.objects.filter(
                    roles__name=role_name,
                    email__startswith="upper.level",
                    email__endswith="@procurement.local",
                )
                .distinct()
                .order_by("email")
            )
            user = User.objects.filter(email=email).first()
            if user is None and legacy_users:
                user = legacy_users.pop(0)
            if user is None:
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    name=display_name,
                    designation=f"{role_name} demo approver",
                    department=departments["PROC"],
                    is_active=True,
                    verification_status="VERIFIED",
                )

            user.email = email
            user.name = display_name
            user.designation = f"{role_name} demo approver"
            user.department = departments["PROC"]
            user.is_active = True
            user.verification_status = "VERIFIED"
            user.set_password(password)
            user.save(
                update_fields=[
                    "email",
                    "name",
                    "designation",
                    "department",
                    "is_active",
                    "verification_status",
                    "password",
                    "updated_at",
                ]
            )
            UserRole.objects.get_or_create(user=user, role=role)

            for index, legacy_user in enumerate(legacy_users, start=2):
                legacy_user.email = f"{role_name.lower()}{index}@procurement.local"
                legacy_user.name = f"{role_name} Demo Approver {index}"
                legacy_user.designation = f"{role_name} demo approver"
                legacy_user.department = departments["PROC"]
                legacy_user.is_active = True
                legacy_user.verification_status = "VERIFIED"
                legacy_user.set_password(password)
                legacy_user.save(
                    update_fields=[
                        "email",
                        "name",
                        "designation",
                        "department",
                        "is_active",
                        "verification_status",
                        "password",
                        "updated_at",
                    ]
                )

            self.stdout.write(
                self.style.SUCCESS(f"Demo approver ready: {role_name} ({email})")
            )

    def seed_vendors(self):
        category_records = {
            name: VendorCategory.objects.get_or_create(
                name=name,
                defaults={"description": description},
            )[0]
            for name, description in VENDOR_CATEGORIES.items()
        }
        category_names = list(category_records)
        vendor_count = 0
        for index in range(1, 51):
            category_name = category_names[(index - 1) // 5]
            group_number = ((index - 1) % 5) + 1
            registration_number = f"DEMO-VND-2026-{index:03d}"
            vendor, _ = Vendor.objects.update_or_create(
                registration_number=registration_number,
                defaults={
                    "vendor_name": f"Demo {category_name} Supplier {group_number:02d}",
                    "email": f"vendor{index:03d}@example.test",
                    "phone": f"+91-90000-{index:05d}",
                    "address": f"Demo Industrial Estate, Sector {group_number}, India",
                    "products_services": VENDOR_OFFERINGS[category_name],
                    "verification_status": "VERIFIED",
                    "is_active": True,
                },
            )
            VendorCategoryMapping.objects.get_or_create(
                vendor=vendor,
                category=category_records[category_name],
            )
            vendor_count += 1
        self.stdout.write(self.style.SUCCESS(f"Demo vendors ready: {vendor_count}"))
