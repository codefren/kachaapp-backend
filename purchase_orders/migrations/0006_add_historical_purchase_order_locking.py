from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("purchase_orders", "0005_add_purchase_order_locking"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalpurchaseorder",
            name="locked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="historicalpurchaseorder",
            name="locked_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                db_constraint=False,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
