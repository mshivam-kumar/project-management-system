from django.db import migrations


ROLE_MAPPING = {
    "UPPER_LEVEL_1": ("SS", "Secretary-level authority"),
    "UPPER_LEVEL_2": ("AS", "Additional Secretary-level authority"),
    "UPPER_LEVEL_3": ("DGS", "Director General of Supplies-level authority"),
    "UPPER_LEVEL_4": ("IA_WING", "Integrated Acquisition Wing tender authority"),
}


def migrate_role_assignments(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    UserRole = apps.get_model("accounts", "UserRole")
    database = schema_editor.connection.alias

    for old_name, (new_name, description) in ROLE_MAPPING.items():
        old_role = Role.objects.using(database).filter(name=old_name).first()
        if old_role is None:
            continue
        new_role, _ = Role.objects.using(database).get_or_create(
            name=new_name,
            defaults={"description": description},
        )
        assignments = UserRole.objects.using(database).filter(role_id=old_role.pk)
        for assignment in assignments.iterator():
            UserRole.objects.using(database).get_or_create(
                user_id=assignment.user_id,
                role_id=new_role.pk,
                defaults={
                    "assigned_by_id": assignment.assigned_by_id,
                    "assigned_at": assignment.assigned_at,
                },
            )
        assignments.delete()
        old_role.delete()


def migrate_approval_role_strings(apps, schema_editor):
    ApprovalPolicyLevel = apps.get_model("workflow", "ApprovalPolicyLevel")
    ApprovalStep = apps.get_model("workflow", "ApprovalStep")
    database = schema_editor.connection.alias
    for old_name, (new_name, _) in ROLE_MAPPING.items():
        ApprovalPolicyLevel.objects.using(database).filter(
            approver_role=old_name,
        ).update(approver_role=new_name)
        ApprovalStep.objects.using(database).filter(
            approver_role=old_name,
        ).update(approver_role=new_name)


def forwards(apps, schema_editor):
    migrate_role_assignments(apps, schema_editor)
    migrate_approval_role_strings(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_user_employee_id"),
        ("workflow", "0011_backfill_tender_draft_stages"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
