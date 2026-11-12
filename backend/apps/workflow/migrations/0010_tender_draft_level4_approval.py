from django.db import migrations


def ensure_tender_draft_level4_policy(apps, schema_editor):
    ApprovalPolicy = apps.get_model("workflow", "ApprovalPolicy")
    ApprovalPolicyLevel = apps.get_model("workflow", "ApprovalPolicyLevel")
    ApprovalRequest = apps.get_model("workflow", "ApprovalRequest")
    Role = apps.get_model("accounts", "Role")
    UserRole = apps.get_model("accounts", "UserRole")
    User = apps.get_model("accounts", "User")
    database = schema_editor.connection.alias

    Role.objects.using(database).get_or_create(
        name="UPPER_LEVEL_4",
        defaults={"description": "Tender draft approver"},
    )
    policy = ApprovalPolicy.objects.using(database).filter(
        submission_type="TENDER_DRAFT",
        is_active=True,
    ).first()
    if policy:
        levels = list(
            ApprovalPolicyLevel.objects.using(database).filter(policy_id=policy.pk)
        )
        if (
            len(levels) == 1
            and levels[0].approver_role == "UPPER_LEVEL_4"
            and not levels[0].approver_id
        ):
            return
        if ApprovalRequest.objects.using(database).filter(policy_id=policy.pk).exists():
            policy.is_active = False
            policy.save(using=database, update_fields=["is_active"])
            policy = None
        else:
            ApprovalPolicyLevel.objects.using(database).filter(
                policy_id=policy.pk,
            ).delete()

    if not policy:
        creator_id = ApprovalPolicy.objects.using(database).filter(
            submission_type="TSC_REPORT_LEVEL3",
            is_active=True,
        ).values_list("created_by_id", flat=True).first()
        if not creator_id:
            creator_id = UserRole.objects.using(database).filter(
                role__name__in=["ADMIN", "SUPER_ADMIN"],
            ).values_list("user_id", flat=True).first()
        if not creator_id:
            creator_id = User.objects.using(database).filter(
                is_superuser=True,
            ).values_list("id", flat=True).first()
        if not creator_id:
            return
        policy = ApprovalPolicy.objects.using(database).create(
            name="Tender Draft - Level 4 Approval",
            submission_type="TENDER_DRAFT",
            is_active=True,
            created_by_id=creator_id,
        )

    ApprovalPolicyLevel.objects.using(database).create(
        policy_id=policy.pk,
        sequence=1,
        approver_role="UPPER_LEVEL_4",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("workflow", "0009_stagesubmission_source_report_and_more"),
    ]

    operations = [
        migrations.RunPython(
            ensure_tender_draft_level4_policy,
            migrations.RunPython.noop,
        ),
    ]
