#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para actualizar el archivo Excel con datos de PurchaseOrderItem.

Compara productos del PurchaseOrder con la columna "Descripcion" del Excel
y actualiza la columna J con quantity_units.
"""
import os
import sys
import django
from difflib import SequenceMatcher

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

try:
    from openpyxl import load_workbook
except ImportError:
    print("❌ Error: openpyxl no está instalado")
    print("Instala con: pip install --break-system-packages openpyxl")
    sys.exit(1)

from purchase_orders.models import PurchaseOrder, PurchaseOrderItem


def similarity_ratio(a, b):
    """Calcula similitud entre dos strings (0-1)"""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def update_excel_from_purchase_order(purchase_order_id, excel_file='miquel.xlsx', output_file=None, similarity_threshold=0.8):
    """
    Actualiza el Excel con datos del PurchaseOrder.
    
    Args:
        purchase_order_id: ID del PurchaseOrder
        excel_file: Ruta al archivo Excel
        output_file: Archivo de salida (si None, sobreescribe el original)
        similarity_threshold: Umbral de similitud (0-1) para considerar coincidencia
    """
    
    print(f"\n{'='*70}")
    print(f"ACTUALIZANDO EXCEL CON DATOS DE PURCHASE ORDER #{purchase_order_id}")
    print(f"{'='*70}\n")
    
    # 1. Obtener el PurchaseOrder y sus items
    try:
        po = PurchaseOrder.objects.prefetch_related('items__product').get(pk=purchase_order_id)
    except PurchaseOrder.DoesNotExist:
        print(f"❌ Error: No existe PurchaseOrder con ID {purchase_order_id}")
        return False
    
    print(f"📦 Purchase Order: {po}")
    print(f"   Proveedor: {po.provider.name}")
    print(f"   Status: {po.status}")
    print(f"   Items: {po.items.count()}\n")
    
    # Crear diccionario de productos {nombre: quantity_units}
    po_items = {}
    for item in po.items.all():
        product_name = item.product.name
        po_items[product_name] = {
            'quantity_units': item.quantity_units,
            'product_id': item.product.id,
            'sku': item.product.sku,
        }
    
    print(f"📋 Productos en el Purchase Order:")
    for name, data in po_items.items():
        print(f"   • {name}: {data['quantity_units']} unidades (SKU: {data['sku']})")
    
    # 2. Cargar el archivo Excel
    try:
        wb = load_workbook(excel_file)
        ws = wb.active
    except FileNotFoundError:
        print(f"\n❌ Error: No se encontró el archivo {excel_file}")
        return False
    except Exception as e:
        print(f"\n❌ Error al abrir Excel: {e}")
        return False
    
    print(f"\n📄 Archivo Excel: {excel_file}")
    print(f"   Hoja activa: {ws.title}")
    print(f"   Filas: {ws.max_row}, Columnas: {ws.max_column}")
    
    # 3. Encontrar la columna "Descripción" EXACTAMENTE (buscar en fila 2)
    descripcion_col = None
    header_row = 2  # El encabezado está en la fila 2
    data_start_row = 4  # Los datos empiezan en la fila 4
    
    for col in range(1, ws.max_column + 1):
        cell_value = ws.cell(header_row, col).value
        if cell_value and str(cell_value).strip() == "Descripción":
            descripcion_col = col
            break
    
    if not descripcion_col:
        print("\n❌ Error: No se encontró la columna 'Descripción' (con tilde) en la fila 2")
        print("\nColumnas encontradas en fila 2:")
        for col in range(1, min(15, ws.max_column + 1)):
            val = ws.cell(header_row, col).value
            if val:
                print(f"   Columna {chr(64+col)}: '{val}'")
        return False
    
    print(f"\n🔍 Columna 'Descripción' encontrada: Columna {descripcion_col} ({chr(64+descripcion_col)})")
    print(f"   Columna J (destino): Columna 10")
    print(f"   Fila de encabezados: {header_row}")
    print(f"   Fila inicio de datos: {data_start_row}")
    
    # 4. INICIALIZAR COLUMNA J EN 0 (desde fila de datos hasta el final)
    print(f"\n🔄 Inicializando columna J en 0...")
    initialized = 0
    for row in range(data_start_row, ws.max_row + 1):
        ws.cell(row, 10).value = 0  # Columna J = 10
        initialized += 1
    print(f"   ✓ {initialized} celdas inicializadas en 0")
    
    # 5. Comparar y actualizar
    print(f"\n{'='*70}")
    print("COMPARANDO Y ACTUALIZANDO...")
    print(f"{'='*70}\n")
    
    updated = 0
    not_found = []
    low_similarity = []
    
    for row in range(data_start_row, ws.max_row + 1):  # Empezar desde fila 4 (datos)
        descripcion = ws.cell(row, descripcion_col).value
        
        if not descripcion:
            continue
        
        descripcion = str(descripcion).strip()
        
        # Buscar coincidencia exacta primero
        if descripcion in po_items:
            quantity = po_items[descripcion]['quantity_units']
            ws.cell(row, 10).value = quantity  # Columna J = 10
            print(f"✓ Fila {row}: '{descripcion}' → {quantity} (coincidencia exacta)")
            updated += 1
        else:
            # Buscar coincidencia por similitud
            best_match = None
            best_ratio = 0
            
            for product_name in po_items.keys():
                ratio = similarity_ratio(descripcion, product_name)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = product_name
            
            if best_ratio >= similarity_threshold:
                quantity = po_items[best_match]['quantity_units']
                ws.cell(row, 10).value = quantity
                print(f"≈ Fila {row}: '{descripcion}' → {quantity}")
                print(f"  (similitud {best_ratio:.2%} con '{best_match}')")
                updated += 1
            elif best_ratio > 0.5:  # Similitud media, reportar pero no actualizar
                low_similarity.append({
                    'row': row,
                    'excel': descripcion,
                    'match': best_match,
                    'ratio': best_ratio
                })
                print(f"⚠ Fila {row}: '{descripcion}' (similitud baja: {best_ratio:.2%} con '{best_match}')")
            else:
                not_found.append({'row': row, 'descripcion': descripcion})
                print(f"✗ Fila {row}: '{descripcion}' (no encontrado)")
    
    # 6. Guardar el archivo
    output_path = output_file or excel_file
    try:
        wb.save(output_path)
        print(f"\n{'='*70}")
        print(f"✅ Archivo guardado exitosamente: {output_path}")
        print(f"{'='*70}")
    except Exception as e:
        print(f"\n❌ Error al guardar archivo: {e}")
        return False
    
    # 7. Resumen
    print(f"\n📊 RESUMEN:")
    print(f"   ✓ Actualizados: {updated} productos")
    print(f"   ⚠ Similitud baja: {len(low_similarity)} productos")
    print(f"   ✗ No encontrados: {len(not_found)} productos")
    
    if low_similarity:
        print(f"\n⚠️  PRODUCTOS CON SIMILITUD BAJA (no actualizados):")
        for item in low_similarity:
            print(f"   Fila {item['row']}: '{item['excel']}'")
            print(f"      Mejor coincidencia ({item['ratio']:.2%}): '{item['match']}'")
    
    if not_found:
        print(f"\n❌ PRODUCTOS NO ENCONTRADOS:")
        for item in not_found:
            print(f"   Fila {item['row']}: '{item['descripcion']}'")
    
    print(f"\n{'='*70}\n")
    return True


if __name__ == "__main__":
    # Obtener el ID del PurchaseOrder
    if len(sys.argv) > 1:
        try:
            po_id = int(sys.argv[1])
        except ValueError:
            print("❌ Error: El ID del PurchaseOrder debe ser un número")
            sys.exit(1)
    else:
        # Mostrar órdenes disponibles
        print("\n📦 PURCHASE ORDERS DISPONIBLES:\n")
        orders = PurchaseOrder.objects.select_related('provider').all()[:20]
        for order in orders:
            items_count = order.items.count()
            print(f"   ID {order.id}: {order.provider.name} - {order.status} ({items_count} items)")
        
        print("\n" + "="*70)
        po_id_input = input("Ingresa el ID del PurchaseOrder: ").strip()
        try:
            po_id = int(po_id_input)
        except ValueError:
            print("❌ Error: Debes ingresar un número válido")
            sys.exit(1)
    
    # Ejecutar actualización
    success = update_excel_from_purchase_order(
        purchase_order_id=po_id,
        excel_file='miquel.xlsx',
        output_file='miquel_actualizado.xlsx',  # Guardar en archivo nuevo
        similarity_threshold=0.8  # 80% de similitud mínima
    )
    
    if success:
        print("✅ Proceso completado exitosamente!\n")
    else:
        print("❌ El proceso terminó con errores\n")
        sys.exit(1)
