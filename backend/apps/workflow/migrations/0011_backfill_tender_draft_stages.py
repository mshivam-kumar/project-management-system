from django.db import migrations, models


def create_missing_tender_draft_stages(apps, schema_editor):
    ProjectStage = apps.get_model("workflow", "ProjectStage")
    StageSubmission = apps.get_model("workflow", "StageSubmission")
    database = schema_editor.connection.alias

    latest_by_project = {}
    submissions = StageSubmission.objects.using(database).filter(
        submission_type="TSC_REPORT_LEVEL3",
    ).select_related("stage").order_by("stage__project_id", "-revision")
    for submission in submissions:
        project_id = submission.stage.project_id
        if project_id in latest_by_project:
            continue
        latest_by_project[project_id] = submission

    for project_id, submission in latest_by_project.items():
        if submission.status != "APPROVED":
            continue
        if ProjectStage.objects.using(database).filter(
            project_id=project_id,
            stage_type="TENDER_DRAFT",
        ).exists():
            continue

        sequence = submission.stage.sequence + 1
        stages_to_shift = ProjectStage.objects.using(database).filter(
            project_id=project_id,
            sequence__gte=sequence,
        )
        if stages_to_shift.exists():
            offset = (
                ProjectStage.objects.using(database)
                .filter(project_id=project_id)
                .aggregate(max_sequence=models.Max("sequence"))["max_sequence"] + 1
            )
            stages_to_shift.update(sequence=models.F("sequence") + offset)
            ProjectStage.objects.using(database).filter(
                project_id=project_id,
                sequence__gte=sequence + offset,
            ).update(sequence=models.F("sequence") - offset + 1)

        ProjectStage.objects.using(database).create(
            project_id=project_id,
            stage_type="TENDER_DRAFT",
            sequence=sequence,
            created_by_id=submission.stage.created_by_id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0010_tender_draft_level4_approval"),
    ]

    operations = [
        migrations.RunPython(
            create_missing_tender_draft_stages,
            migrations.RunPython.noop,
        ),
    ]
