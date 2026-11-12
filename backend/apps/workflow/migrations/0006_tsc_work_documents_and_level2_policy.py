import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def route_tsc_reports_to_level_two(apps, schema_editor):
    ApprovalPolicy = apps.get_model("workflow", "ApprovalPolicy")
    ApprovalPolicyLevel = apps.get_model("workflow", "ApprovalPolicyLevel")
    for policy in ApprovalPolicy.objects.filter(submission_type="TSC_REPORT"):
        ApprovalPolicyLevel.objects.filter(policy_id=policy.pk).delete()
        ApprovalPolicyLevel.objects.create(
            policy_id=policy.pk,
            sequence=1,
            approver_role="UPPER_LEVEL_2",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0005_alter_vendorbid_options"),
        ("committees", "0002_committee_chair_committee_committee_type_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TSCWorkDocument",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "file",
                    models.FileField(upload_to="tsc_work_documents/%Y/%m/"),
                ),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "committee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="work_documents",
                        to="committees.committee",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tsc_work_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-uploaded_at"]},
        ),
        migrations.RunPython(route_tsc_reports_to_level_two, migrations.RunPython.noop),
    ]
