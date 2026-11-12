from django.db import migrations


def ensure_tsc_report_policy(apps, schema_editor):
    ApprovalPolicy = apps.get_model("workflow", "ApprovalPolicy")
    ApprovalPolicyLevel = apps.get_model("workflow", "ApprovalPolicyLevel")
    UserRole = apps.get_model("accounts", "UserRole")
    User = apps.get_model("accounts", "User")
    database = schema_editor.connection.alias

    policy = ApprovalPolicy.objects.using(database).filter(
        submission_type="TSC_REPORT",
        is_active=True,
    ).first()
    if policy:
        ApprovalPolicyLevel.objects.using(database).filter(
            policy_id=policy.pk,
        ).delete()
    else:
        creator_id = ApprovalPolicy.objects.using(database).filter(
            submission_type="TSC_FORMATION",
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
            name="TSC Report - Level 2 Approval",
            submission_type="TSC_REPORT",
            is_active=True,
            created_by_id=creator_id,
        )

    ApprovalPolicyLevel.objects.using(database).create(
        policy_id=policy.pk,
        sequence=1,
        approver_role="UPPER_LEVEL_2",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0007_tsc_work_document_versions"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            ensure_tsc_report_policy,
            migrations.RunPython.noop,
        ),
    ]
