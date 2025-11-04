"""
Comando para limpiar códigos de barras que tienen .0 al final.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from proveedores.models import ProductBarcode


class Command(BaseCommand):
    help = "Elimina el .0 de los códigos de barras que tienen formato decimal"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que se haría sin ejecutar cambios",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        
        # Encontrar todos los códigos con .0
        barcodes_with_decimal = ProductBarcode.objects.filter(code__contains=".0")
        total = barcodes_with_decimal.count()
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS("No hay códigos de barras con .0 para limpiar"))
            return
        
        self.stdout.write(f"Encontrados {total} códigos de barras con .0")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n=== MODO DRY-RUN (sin cambios reales) ===\n"))
        
        updated = 0
        skipped = 0
        errors = []
        
        with transaction.atomic():
            for barcode in barcodes_with_decimal:
                old_code = barcode.code
                
                # Eliminar .0 del final
                if old_code.endswith(".0"):
                    new_code = old_code[:-2]  # Eliminar los últimos 2 caracteres (.0)
                else:
                    # Si contiene .0 pero no al final, eliminar todos los .0
                    new_code = old_code.replace(".0", "")
                
                # Verificar si el nuevo código ya existe
                if ProductBarcode.objects.filter(code=new_code).exclude(pk=barcode.pk).exists():
                    msg = f"CONFLICTO: {old_code} -> {new_code} (ya existe)"
                    self.stdout.write(self.style.ERROR(f"  ✗ {msg}"))
                    errors.append(msg)
                    skipped += 1
                    continue
                
                if dry_run:
                    self.stdout.write(f"  • ID {barcode.id}: {old_code} -> {new_code}")
                else:
                    barcode.code = new_code
                    barcode.save()
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ ID {barcode.id}: {old_code} -> {new_code}")
                    )
                
                updated += 1
            
            if dry_run:
                # No guardar cambios en modo dry-run
                transaction.set_rollback(True)
        
        # Resumen
        self.stdout.write("\n" + "="*50)
        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY-RUN: Se actualizarían {updated} códigos"))
        else:
            self.stdout.write(self.style.SUCCESS(f"✓ Actualizados: {updated} códigos"))
        
        if skipped > 0:
            self.stdout.write(self.style.ERROR(f"✗ Omitidos (conflictos): {skipped} códigos"))
        
        if errors:
            self.stdout.write("\nCódigos con conflictos:")
            for error in errors:
                self.stdout.write(f"  - {error}")
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nEjecuta sin --dry-run para aplicar los cambios")
            )
