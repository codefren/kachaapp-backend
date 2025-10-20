# Generated manually for extra product fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("received", "0003_reception_invoice_date_reception_invoice_image_b64_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="receivedproduct",
            name="is_not_in_order",
            field=models.BooleanField(
                default=False,
                help_text="True if this product was received but not in the original purchase order",
            ),
        ),
        migrations.AddField(
            model_name="receivedproduct",
            name="reason_extra",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PROMOTIONAL", "Promotional/Gift"),
                    ("SUBSTITUTE", "Product Substitute"),
                    ("ERROR", "Provider Error"),
                    ("OTHER", "Other"),
                ],
                help_text="Reason why this extra product was received",
                max_length=20,
                null=True,
            ),
        ),
    ]
