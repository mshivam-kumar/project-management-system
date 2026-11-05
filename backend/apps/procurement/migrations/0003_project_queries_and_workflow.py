import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def map_legacy_statuses(apps, schema_editor):
    Project = apps.get_model('procurement', 'ProcurementProject')
    for old, new in {'SUBMITTED':'TSC_APPROVAL','UNDER_REVIEW':'TSC_APPROVAL','COMMITTEE_FORMATION':'BOARD_FORMATION','COMMITTEE_REVIEW':'TSC_REPORT_AS_IA','PENDING_APPROVAL':'DG_SS_APPROVAL'}.items():
        Project.objects.filter(current_status=old).update(current_status=new)


class Migration(migrations.Migration):
    dependencies = [
        ('procurement', '0002_projectmember_projectactivity_project_message_and_more'),
        ('vendors', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(map_legacy_statuses, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='procurementproject', name='current_status',
            field=models.CharField(choices=[
                ('DRAFT','Draft'),('TSC_APPROVAL','Tsc Approval'),('BOARD_FORMATION','Board Formation'),
                ('TSC_REPORT_AS_IA','Tsc Report As Ia'),('AS_IA_APPROVAL','As Ia Approval'),('DG_SS_APPROVAL','Dg Ss Approval'),
                ('HQ_REVIEW','Hq Review'),('CS_SR_REVIEW','Cs Sr Review'),('DRAFT_TENDER_IA','Draft Tender Ia'),
                ('TENDER_ISSUED','Tender Issued'),('VENDOR_RESPONSE','Vendor Response'),('TECH_BID_BOARD','Tech Bid Board'),
                ('TEC_FORMATION','Tec Formation'),('TEC_REPORT','Tec Report'),('PRICE_BID_OPEN','Price Bid Open'),
                ('TAC_REVIEW','Tac Review'),('IFD_CFA_APPROVAL','Ifd Cfa Approval'),('APPROVED','Approved'),
                ('RETURNED','Returned'),('REJECTED','Rejected'),('CANCELLED','Cancelled')], default='DRAFT', max_length=32),
        ),
        migrations.CreateModel(
            name='ProjectQuery',
            fields=[('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('stage',models.CharField(max_length=40)),('subject',models.CharField(max_length=240)),('body',models.TextField()),('target_designation',models.CharField(blank=True,max_length=80)),('status',models.CharField(choices=[('OPEN','Open'),('ANSWERED','Answered'),('CLOSED','Closed')],default='OPEN',max_length=16)),('created_at',models.DateTimeField(auto_now_add=True)),('project',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='queries',to='procurement.procurementproject')),('raised_by',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='raised_project_queries',to=settings.AUTH_USER_MODEL)),('target_vendor',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,related_name='project_queries',to='vendors.vendor'))],
            options={'ordering':['created_at']},
        ),
        migrations.CreateModel(
            name='ProjectQueryReply',
            fields=[('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('body',models.TextField()),('created_at',models.DateTimeField(auto_now_add=True)),('actor',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),('query',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='replies',to='procurement.projectquery'))],
            options={'ordering':['created_at']},
        ),
    ]
