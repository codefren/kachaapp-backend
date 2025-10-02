"""
Management command para importar catálogo de productos desde catalog_parsed.json
"""
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from proveedores.models import Provider, Product, ProductBarcode


class Command(BaseCommand):
    help = 'Importar catálogo de productos desde catalog_parsed.json'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='catalog_parsed.json',
            help='Ruta al archivo JSON con el catálogo'
        )
        parser.add_argument(
            '--provider-name',
            type=str,
            default='Miquel',
            help='Nombre del proveedor'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular importación sin guardar cambios'
        )

    def handle(self, *args, **options):
        file_path = options['file']
        provider_name = options['provider_name']
        dry_run = options['dry_run']

        # Códigos genéricos que marcaremos como is_primary=False
        GENERIC_CODES = ['8410700000000', '8000500000000']
        
        # Códigos inválidos que saltaremos
        INVALID_CODES = ['42310']  # Muy corto

        self.stdout.write(self.style.MIGRATE_HEADING(f'\n🚀 Importando catálogo desde: {file_path}\n'))

        # Buscar el archivo en el directorio del proyecto
        if not Path(file_path).is_absolute():
            file_path = Path(__file__).resolve().parent.parent.parent.parent / file_path

        # Leer el archivo JSON
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                catalog = json.load(f)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'❌ Archivo no encontrado: {file_path}'))
            return
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f'❌ Error al leer JSON: {e}'))
            return

        self.stdout.write(f'📦 Total de productos en el catálogo: {len(catalog)}\n')

        stats = {
            'provider_created': False,
            'products_created': 0,
            'products_updated': 0,
            'barcodes_created': 0,
            'barcodes_skipped': 0,
            'generic_codes': 0,
            'errors': []
        }

        with transaction.atomic():
            # 1. Crear o obtener el proveedor
            from datetime import time
            provider, created = Provider.objects.get_or_create(
                name=provider_name,
                defaults={
                    'contact_person': provider_name,
                    'phone': '',
                    'email': f'{provider_name.lower()}@example.com',
                    'order_deadline_time': time(12, 30),  # 12:30 (Martes)
                    'order_available_weekdays': [1],  # Solo Martes (1 = Martes)
                }
            )
            stats['provider_created'] = created
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'✅ Proveedor creado: {provider.name}'))
            else:
                self.stdout.write(self.style.WARNING(f'⚠️  Proveedor ya existe: {provider.name}'))

            # 2. Importar productos
            for item in catalog:
                nombre = item.get('nombre', '').strip()
                ref = item.get('ref', '').strip()
                barcode = item.get('barcode', '').strip()
                familia = item.get('familia')

                if not nombre or not ref:
                    stats['errors'].append(f'Producto sin nombre o ref: {item}')
                    continue

                try:
                    # Crear o actualizar producto
                    product, product_created = Product.objects.get_or_create(
                        sku=ref,
                        defaults={
                            'name': nombre,
                            'units_per_box': 1,
                            'amount_boxes': 0,
                        }
                    )

                    if product_created:
                        stats['products_created'] += 1
                        self.stdout.write(f'  ✓ Producto creado: {nombre} (SKU: {ref})')
                    else:
                        # Actualizar nombre si cambió
                        if product.name != nombre:
                            product.name = nombre
                            product.save()
                        stats['products_updated'] += 1
                        self.stdout.write(f'  ↻ Producto existente: {nombre} (SKU: {ref})')

                    # Asociar con el proveedor
                    if provider not in product.providers.all():
                        product.providers.add(provider)

                    # Crear código de barras si existe
                    if barcode and barcode not in INVALID_CODES:
                        # Determinar tipo de código
                        barcode_type = self._get_barcode_type(barcode)
                        
                        # Determinar si es primario (no es genérico)
                        is_primary = barcode not in GENERIC_CODES

                        # Verificar si ya existe
                        bc, bc_created = ProductBarcode.objects.get_or_create(
                            code=barcode,
                            defaults={
                                'product': product,
                                'type': barcode_type,
                                'is_primary': is_primary,
                                'notes': 'Catálogo genérico' if not is_primary else '',
                            }
                        )

                        if bc_created:
                            stats['barcodes_created'] += 1
                            primary_flag = '🔸' if not is_primary else '🔹'
                            self.stdout.write(f'    {primary_flag} Barcode: {barcode} ({barcode_type})')
                            
                            if not is_primary:
                                stats['generic_codes'] += 1
                        else:
                            stats['barcodes_skipped'] += 1

                    elif barcode in INVALID_CODES:
                        self.stdout.write(self.style.WARNING(
                            f'    ⚠️  Barcode inválido saltado: {barcode}'
                        ))
                        stats['barcodes_skipped'] += 1

                except Exception as e:
                    error_msg = f'Error con producto {nombre} (ref: {ref}): {str(e)}'
                    stats['errors'].append(error_msg)
                    self.stdout.write(self.style.ERROR(f'  ❌ {error_msg}'))

            # Si es dry-run, revertir la transacción
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('\n🔄 DRY RUN - Cambios revertidos\n'))

        # 3. Mostrar resumen
        self.stdout.write(self.style.MIGRATE_HEADING('\n📊 RESUMEN DE IMPORTACIÓN\n'))
        self.stdout.write(f'Proveedor: {"✅ Creado" if stats["provider_created"] else "⚠️  Ya existía"} - {provider.name}')
        self.stdout.write(f'Productos creados: {stats["products_created"]}')
        self.stdout.write(f'Productos actualizados: {stats["products_updated"]}')
        self.stdout.write(f'Códigos de barras creados: {stats["barcodes_created"]}')
        self.stdout.write(f'  - Códigos genéricos (is_primary=False): {stats["generic_codes"]}')
        self.stdout.write(f'Códigos de barras saltados: {stats["barcodes_skipped"]}')
        
        if stats['errors']:
            self.stdout.write(self.style.ERROR(f'\nErrores: {len(stats["errors"])}'))
            for error in stats['errors'][:5]:  # Mostrar solo los primeros 5
                self.stdout.write(self.style.ERROR(f'  - {error}'))

        self.stdout.write(self.style.SUCCESS('\n✅ Importación completada\n'))

    def _get_barcode_type(self, code):
        """Determinar el tipo de código de barras según su longitud."""
        length = len(code)
        
        if length == 13:
            return ProductBarcode.BarcodeType.EAN13
        elif length == 8:
            return ProductBarcode.BarcodeType.EAN8
        elif length == 12:
            return ProductBarcode.BarcodeType.UPC_A
        else:
            return ProductBarcode.BarcodeType.OTHER
