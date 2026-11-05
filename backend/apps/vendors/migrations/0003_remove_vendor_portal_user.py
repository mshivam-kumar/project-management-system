from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('vendors', '0002_vendor_portal_user')]
    operations = [migrations.RemoveField(model_name='vendor', name='portal_user')]
