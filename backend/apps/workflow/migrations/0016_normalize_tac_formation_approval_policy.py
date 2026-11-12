from django.db import migrations


def normalize_tac_formation_policy(apps, schema_editor):
    ApprovalPolicy = apps.get_model("workflow", "ApprovalPolicy")
    ApprovalPolicyLevel = apps.get_model("workflow", "ApprovalPolicyLevel")
    database = schema_editor.connection.alias

    active_policies = ApprovalPolicy.objects.using(database).filter(
        submission_type="TAC_FORMATION",
        is_active=True,
    )
    for policy in active_policies.iterator():
        ApprovalPolicyLevel.objects.using(database).filter(
            policy_id=policy.pk,
        ).delete()
        ApprovalPolicyLevel.objects.using(database).create(
            policy_id=policy.pk,
            sequence=1,
            approver_role="SS",
        )
        if policy.name != "TAC Formation - SS Approval":
            ApprovalPolicy.objects.using(database).filter(pk=policy.pk).update(
                name="TAC Formation - SS Approval",
            )


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0015_alter_projectstage_stage_type"),
    ]

    operations = [
        migrations.RunPython(
            normalize_tac_formation_policy,
            migrations.RunPython.noop,
        ),
    ]
