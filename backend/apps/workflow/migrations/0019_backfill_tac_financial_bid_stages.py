from django.db import migrations
from django.db.models import F, Max


def backfill_tac_financial_bid_stages(apps, schema_editor):
    Committee = apps.get_model("committees", "Committee")
    ProjectStage = apps.get_model("workflow", "ProjectStage")
    TACVendorShortlist = apps.get_model("workflow", "TACVendorShortlist")

    for committee in Committee.objects.filter(
        committee_type="TAC",
        status="ACTIVE",
    ).iterator():
        stages = ProjectStage.objects.filter(project_id=committee.project_id)
        if stages.filter(stage_type="TAC_FINANCIAL_BIDS").exists():
            continue

        formation = stages.filter(stage_type="TAC_FORMATION").first()
        if not formation:
            continue

        selection = stages.filter(stage_type="VENDOR_SELECTION").first()
        insertion_sequence = (
            selection.sequence if selection else formation.sequence + 1
        )
        max_sequence = stages.aggregate(max_sequence=Max("sequence"))["max_sequence"] or 0
        offset = max_sequence + 1
        later_stages = stages.filter(sequence__gte=insertion_sequence)
        later_stages.update(sequence=F("sequence") + offset)
        later_stages.update(sequence=F("sequence") - offset + 1)

        shortlist = TACVendorShortlist.objects.filter(
            committee_id=committee.id,
        ).order_by("-selected_at").first()
        stage_values = {
            "project_id": committee.project_id,
            "stage_type": "TAC_FINANCIAL_BIDS",
            "sequence": insertion_sequence,
            "created_by_id": committee.formed_by_id,
        }
        if shortlist:
            stage_values.update({
                "status": "COMPLETED",
                "actual_start": shortlist.selected_at,
                "completed_at": shortlist.selected_at,
            })
        ProjectStage.objects.create(
            **stage_values,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0018_alter_projectstage_stage_type"),
        ("committees", "0002_committee_chair_committee_committee_type_and_more"),
    ]

    operations = [
        migrations.RunPython(
            backfill_tac_financial_bid_stages,
            migrations.RunPython.noop,
        ),
    ]
