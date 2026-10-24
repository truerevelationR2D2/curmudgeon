from django.db import migrations


def fill_slugs(apps, schema_editor):
    Product = apps.get_model("shop", "Product")
    for p in Product.objects.filter(slug=""):
        p.slug = str(p.pk)
        p.save()


class Migration(migrations.Migration):
    dependencies = [("shop", "0006_product_slug")]
    operations = [
        migrations.RunPython(fill_slugs),
        migrations.RunSQL("UPDATE shop_product SET active = true WHERE active IS NULL"),
    ]
