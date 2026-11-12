from django.db import migrations
from django.db.models import F, Max


def place_report_after_financial_bids(apps, schema_editor):
    Committee = apps.get_model("committees", "Committee")
    ProjectStage = apps.get_model("workflow", "ProjectStage")

    project_ids = Committee.objects.filter(
        committee_type="TAC",
        status="ACTIVE",
    ).values_list("project_id", flat=True).distinct()
    for project_id in project_ids.iterator():
        stages = ProjectStage.objects.filter(project_id=project_id)
        financial_bids = stages.filter(stage_type="TAC_FINANCIAL_BIDS").first()
        final_report = stages.filter(stage_type="TAC_FINAL_REPORT").first()
        if not financial_bids or not final_report:
            continue

        selection = stages.filter(stage_type="VENDOR_SELECTION").first()
        if selection:
            selection.status = "CANCELLED"
            selection.save(update_fields=["status"])

        ordered_ids = list(stages.order_by("sequence", "id").values_list("id", flat=True))
        ordered_ids.remove(final_report.id)
        ordered_ids.insert(ordered_ids.index(financial_bids.id) + 1, final_report.id)

        max_sequence = stages.aggregate(max_sequence=Max("sequence"))["max_sequence"] or 0
        offset = max_sequence + len(ordered_ids) + 1
        stages.update(sequence=F("sequence") + offset)
        for sequence, stage_id in enumerate(ordered_ids, start=1):
            ProjectStage.objects.filter(id=stage_id).update(sequence=sequence)


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0021_alter_projectstage_stage_type_tacworkdocument"),
    ]

    operations = [
        migrations.RunPython(
            place_report_after_financial_bids,
            migrations.RunPython.noop,
        ),
    ]
