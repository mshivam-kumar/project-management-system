from django.db import migrations


def ensure_tsc_report_approval_sequence(apps, schema_editor):
    ApprovalPolicy = apps.get_model("workflow", "ApprovalPolicy")
    ApprovalPolicyLevel = apps.get_model("workflow", "ApprovalPolicyLevel")
    User = apps.get_model("accounts", "User")
    database = schema_editor.connection.alias

    policy = ApprovalPolicy.objects.using(database).filter(
        submission_type="TSC_REPORT",
        is_active=True,
    ).first()
    if policy is None:
        creator_id = User.objects.using(database).order_by("created_at").values_list(
            "id", flat=True,
        ).first()
        if creator_id is None:
            return
        policy = ApprovalPolicy.objects.using(database).create(
            name="TSC Report - AS then HQ Approval",
            submission_type="TSC_REPORT",
            is_active=True,
            created_by_id=creator_id,
        )

    ApprovalPolicyLevel.objects.using(database).filter(
        policy_id=policy.pk,
    ).delete()
    ApprovalPolicyLevel.objects.using(database).bulk_create([
        ApprovalPolicyLevel(
            policy_id=policy.pk,
            sequence=1,
            approver_role="AS",
        ),
        ApprovalPolicyLevel(
            policy_id=policy.pk,
            sequence=2,
            approver_role="HQ",
        ),
    ])
    ApprovalPolicy.objects.using(database).filter(pk=policy.pk).update(
        name="TSC Report - AS then HQ Approval",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0024_hq_report_approvals"),
    ]

    operations = [
        migrations.RunPython(
            ensure_tsc_report_approval_sequence,
            migrations.RunPython.noop,
        ),
    ]
