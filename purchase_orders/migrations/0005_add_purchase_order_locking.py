from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("purchase_orders", "0004_alter_historicalpurchaseorder_status_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorder",
            name="locked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="purchaseorder",
            name="locked_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="locked_purchase_orders",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="purchaseorder",
            index=models.Index(fields=["locked_at"], name="idx_po_locked_at"),
        ),
    ]
