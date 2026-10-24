from django.db import migrations


def forwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("shop", "0005_initial")]
    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.RunSQL("UPDATE shop_product SET slug = '' WHERE slug IS NULL", reverse_sql=migrations.RunSQL.noop),
    ]
