from django.db import migrations, models
import django.core.validators


def assign_existing_versions(apps, schema_editor):
    TSCWorkDocument = apps.get_model("workflow", "TSCWorkDocument")
    database = schema_editor.connection.alias
    latest_by_committee = {}
    documents = TSCWorkDocument.objects.using(database).order_by(
        "committee_id", "uploaded_at", "id"
    )
    for document in documents.iterator():
        version = latest_by_committee.get(document.committee_id, 0) + 1
        latest_by_committee[document.committee_id] = version
        TSCWorkDocument.objects.using(database).filter(pk=document.pk).update(
            version=version
        )


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0006_tsc_work_documents_and_level2_policy"),
    ]

    operations = [
        migrations.AddField(
            model_name="tscworkdocument",
            name="version",
            field=models.PositiveIntegerField(
                default=1,
                validators=[django.core.validators.MinValueValidator(1)],
            ),
            preserve_default=False,
        ),
        migrations.RunPython(assign_existing_versions, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="tscworkdocument",
            constraint=models.UniqueConstraint(
                fields=("committee", "version"),
                name="unique_tsc_work_document_version",
            ),
        ),
    ]
