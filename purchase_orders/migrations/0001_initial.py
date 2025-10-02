"""Initial migration for purchase_orders - moves models from proveedores."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import simple_history.models


class Migration(migrations.Migration):
    """Move PurchaseOrder and PurchaseOrderItem from proveedores to purchase_orders."""

    initial = True

    dependencies = [
        ("proveedores", "0013_provider_order_available_weekdays_and_more"),  # Última migración antes de la separación
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    # Database operations to handle the table moves
    database_operations = [
        # Rename the tables to the new app using raw SQL
        migrations.RunSQL(
            sql=[
                'ALTER TABLE proveedores_purchaseorder RENAME TO purchase_orders_purchaseorder;',
                'ALTER TABLE proveedores_purchaseorderitem RENAME TO purchase_orders_purchaseorderitem;',
                'ALTER TABLE proveedores_historicalpurchaseorder RENAME TO purchase_orders_historicalpurchaseorder;',
            ],
            reverse_sql=[
                'ALTER TABLE purchase_orders_purchaseorder RENAME TO proveedores_purchaseorder;',
                'ALTER TABLE purchase_orders_purchaseorderitem RENAME TO proveedores_purchaseorderitem;',
                'ALTER TABLE purchase_orders_historicalpurchaseorder RENAME TO proveedores_historicalpurchaseorder;',
            ],
        ),
    ]

    # State operations to update Django's migration state
    state_operations = [
        migrations.CreateModel(
            name="PurchaseOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(
                    choices=[
                        ("DRAFT", "Draft"),
                        ("PLACED", "Placed"),
                        ("RECEIVED", "Received"),
                        ("SHIPPED", "Shipped"),
                        ("CANCELED", "Canceled"),
                    ],
                    db_index=True,
                    default="DRAFT",
                    max_length=16,
                )),
                ("notes", models.CharField(blank=True, max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("ordered_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="purchase_orders",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("provider", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="purchase_orders",
                    to="proveedores.provider",
                )),
            ],
            options={
                "verbose_name": "Purchase order",
                "verbose_name_plural": "Purchase orders",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PurchaseOrderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity_units", models.PositiveIntegerField(default=0, help_text="Units to order")),
                ("purchase_unit", models.CharField(
                    choices=[("boxes", "boxes")],
                    db_index=True,
                    default="boxes",
                    help_text="Unit expressed by the purchaser (boxes only)",
                    max_length=10,
                )),
                ("notes", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="items",
                    to="purchase_orders.purchaseorder",
                )),
                ("product", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="purchase_order_items",
                    to="proveedores.product",
                )),
            ],
            options={
                "verbose_name": "Purchase order item",
                "verbose_name_plural": "Purchase order items",
            },
        ),
        migrations.AddIndex(
            model_name="purchaseorder",
            index=models.Index(fields=["provider", "status"], name="idx_po_provider_status"),
        ),
        migrations.AddIndex(
            model_name="purchaseorder",
            index=models.Index(fields=["created_at"], name="idx_po_created_at"),
        ),
        migrations.AddIndex(
            model_name="purchaseorderitem",
            index=models.Index(fields=["order"], name="idx_poi_order"),
        ),
        migrations.AddIndex(
            model_name="purchaseorderitem",
            index=models.Index(fields=["product"], name="idx_poi_product"),
        ),
        migrations.AddIndex(
            model_name="purchaseorderitem",
            index=models.Index(fields=["order", "product"], name="idx_poi_order_product"),
        ),
        migrations.AddConstraint(
            model_name="purchaseorderitem",
            constraint=models.CheckConstraint(condition=models.Q(("quantity_units__gt", 0)), name="chk_poi_qty_gt_0"),
        ),
        migrations.AddConstraint(
            model_name="purchaseorderitem",
            constraint=models.UniqueConstraint(
                fields=("order", "product", "purchase_unit"),
                name="uq_poi_order_product_purchase_unit",
            ),
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=database_operations,
            state_operations=state_operations,
        )
    ]
