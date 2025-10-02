# Generated manually to fix temperature data before constraint

from django.db import migrations


def fix_temperature_data(apps, schema_editor):
    """Eliminar registros con temperaturas fuera del rango permitido."""
    TemperatureRecord = apps.get_model('market', 'TemperatureRecord')
    
    # Obtener registros con temperaturas fuera del rango
    invalid_records = TemperatureRecord.objects.filter(
        temperature__lt=-30.0
    ) | TemperatureRecord.objects.filter(
        temperature__gt=10.0
    )
    
    count = invalid_records.count()
    if count > 0:
        print(f"Eliminando {count} registros con temperaturas inválidas")
        invalid_records.delete()
        print(f"Eliminados {count} registros exitosamente")
    else:
        print("No se encontraron registros con temperaturas inválidas")


def reverse_fix_temperature_data(apps, schema_editor):
    """No hay reversión para esta migración de datos."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('market', '0003_alter_temperaturerecord_options_and_more'),
    ]

    operations = [
        migrations.RunPython(
            fix_temperature_data,
            reverse_fix_temperature_data,
        ),
    ]
