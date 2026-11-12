from django.db import migrations, models
import django.db.models.deletion
from django.db.models import F, Max


def restore_final_vendor_selection_stage(apps, schema_editor):
    Committee = apps.get_model("committees", "Committee")
    ProjectStage = apps.get_model("workflow", "ProjectStage")
    VendorSelection = apps.get_model("workflow", "VendorSelection")

    active_tacs = Committee.objects.filter(
        committee_type="TAC",
        status="ACTIVE",
    ).values("project_id", "formed_by_id").distinct()
    for tac in active_tacs.iterator():
        project_id = tac["project_id"]
        report = ProjectStage.objects.filter(
            project_id=project_id,
            stage_type="TAC_FINAL_REPORT",
        ).first()
        if not report:
            continue

        selection_stage = ProjectStage.objects.filter(
            project_id=project_id,
            stage_type="VENDOR_SELECTION",
        ).first()
        has_final_selection = VendorSelection.objects.filter(
            committee__project_id=project_id,
            status="SELECTED",
            vendor__isnull=False,
            selected_by__isnull=False,
        ).exists()
        if not selection_stage:
            max_sequence = ProjectStage.objects.filter(
                project_id=project_id,
            ).aggregate(max_sequence=Max("sequence"))["max_sequence"] or 0
            selection_stage = ProjectStage.objects.create(
                project_id=project_id,
                stage_type="VENDOR_SELECTION",
                sequence=max_sequence + 1,
                status="COMPLETED" if has_final_selection else "NOT_STARTED",
                created_by_id=tac["formed_by_id"],
            )
        selection_stage.status = (
            "COMPLETED" if has_final_selection else "NOT_STARTED"
        )
        if not has_final_selection:
            selection_stage.actual_start = None
            selection_stage.completed_at = None
            selection_stage.save(update_fields=[
                "status", "actual_start", "completed_at",
            ])
        else:
            selection_stage.save(update_fields=["status"])

        stages = list(
            ProjectStage.objects.filter(project_id=project_id)
            .order_by("sequence", "id")
            .values_list("id", flat=True)
        )
        stages.remove(selection_stage.id)
        stages.insert(stages.index(report.id) + 1, selection_stage.id)
        max_sequence = ProjectStage.objects.filter(
            project_id=project_id,
        ).aggregate(max_sequence=Max("sequence"))["max_sequence"] or 0
        offset = max_sequence + len(stages) + 1
        ProjectStage.objects.filter(project_id=project_id).update(
            sequence=F("sequence") + offset
        )
        for sequence, stage_id in enumerate(stages, start=1):
            ProjectStage.objects.filter(id=stage_id).update(sequence=sequence)


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0022_reorder_tac_final_report"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendorselection",
            name="selected_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="vendor_selections",
                to="accounts.user",
            ),
        ),
        migrations.RunPython(
            restore_final_vendor_selection_stage,
            migrations.RunPython.noop,
        ),
    ]
