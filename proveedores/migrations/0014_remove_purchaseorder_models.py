"""Remove PurchaseOrder and PurchaseOrderItem models - moved to purchase_orders app."""

from django.db import migrations


class Migration(migrations.Migration):
    """Remove PurchaseOrder and PurchaseOrderItem models from proveedores."""

    dependencies = [
        ("proveedores", "0013_provider_order_available_weekdays_and_more"),
        ("purchase_orders", "0001_initial"),
    ]

    # State operations - Tell Django these models no longer exist in proveedores
    state_operations = [
        migrations.RemoveField(
            model_name="purchaseorderitem",
            name="order",
        ),
        migrations.RemoveField(
            model_name="purchaseorderitem",
            name="product",
        ),
        migrations.RemoveField(
            model_name="purchaseorder",
            name="ordered_by",
        ),
        migrations.RemoveField(
            model_name="purchaseorder",
            name="provider",
        ),
        migrations.DeleteModel(
            name="HistoricalPurchaseOrder",
        ),
        migrations.DeleteModel(
            name="PurchaseOrderItem",
        ),
        migrations.DeleteModel(
            name="PurchaseOrder",
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # No database operations - tables were already moved by purchase_orders.0001_initial
            database_operations=[],
            # State operations to update Django's migration state
            state_operations=state_operations,
        )
    ]
