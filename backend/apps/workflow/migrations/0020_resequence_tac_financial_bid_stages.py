from django.db import migrations
from django.db.models import F, Max


def resequence_active_tac_projects(apps, schema_editor):
    Committee = apps.get_model("committees", "Committee")
    ProjectStage = apps.get_model("workflow", "ProjectStage")

    project_ids = Committee.objects.filter(
        committee_type="TAC",
        status="ACTIVE",
    ).values_list("project_id", flat=True).distinct()
    for project_id in project_ids.iterator():
        stages = ProjectStage.objects.filter(project_id=project_id)
        ordered_ids = list(stages.order_by("sequence", "id").values_list("id", flat=True))
        if not ordered_ids:
            continue

        max_sequence = stages.aggregate(max_sequence=Max("sequence"))["max_sequence"] or 0
        offset = max_sequence + len(ordered_ids) + 1
        stages.update(sequence=F("sequence") + offset)
        for sequence, stage_id in enumerate(ordered_ids, start=1):
            ProjectStage.objects.filter(id=stage_id).update(sequence=sequence)


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0019_backfill_tac_financial_bid_stages"),
    ]

    operations = [
        migrations.RunPython(
            resequence_active_tac_projects,
            migrations.RunPython.noop,
        ),
    ]
