# Guía de Migración: Purchase Orders Module

Este documento explica cómo completar la separación del módulo `purchase_orders` desde `proveedores`.

## ✅ Cambios Realizados

### 1. Estructura del Nuevo Módulo
```
purchase_orders/
├── __init__.py
├── apps.py
├── models.py              # PurchaseOrder, PurchaseOrderItem
├── serializers.py         # PurchaseOrderSerializer, PurchaseOrderItemSerializer
├── views.py               # PurchaseOrderViewSet, PurchaseOrderItemViewSet
├── admin.py               # Admin para PurchaseOrder y PurchaseOrderItem
├── migrations/
│   ├── __init__.py
│   └── 0001_initial.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_purchase_orders_crud.py
    ├── test_purchase_orders_actions.py
    └── test_purchase_order_items.py
```

### 2. Modelos Movidos
- `PurchaseOrder` → `purchase_orders.models.PurchaseOrder`
- `PurchaseOrderItem` → `purchase_orders.models.PurchaseOrderItem`

### 3. Relaciones Mantenidas
- `PurchaseOrder.provider` → ForeignKey a `proveedores.Provider`
- `PurchaseOrder.ordered_by` → ForeignKey a `users.User`
- `PurchaseOrderItem.product` → ForeignKey a `proveedores.Product`
- `PurchaseOrderItem.order` → ForeignKey a `purchase_orders.PurchaseOrder`

### 4. APIs Actualizadas
**Antes:**
- `/api/proveedores/purchase-orders/`
- `/api/proveedores/purchase-order-items/`

**Ahora:**
- `/api/purchase-orders/`
- `/api/purchase-order-items/`

### 5. Endpoints Disponibles
```
GET    /api/purchase-orders/                      # Listar órdenes
POST   /api/purchase-orders/                      # Crear orden
GET    /api/purchase-orders/{id}/                 # Ver orden
PUT    /api/purchase-orders/{id}/                 # Actualizar orden
PATCH  /api/purchase-orders/{id}/                 # Actualizar parcial
GET    /api/purchase-orders/has-ordered-today/   # Verificar si ordenó hoy
GET    /api/purchase-orders/by-day/?date=YYYY-MM-DD  # Órdenes por día
POST   /api/purchase-orders/received-products/   # Marcar productos recibidos
GET    /api/purchase-orders/last-shipped/        # Última orden enviada

GET    /api/purchase-order-items/                # Listar items
POST   /api/purchase-order-items/                # Crear item
GET    /api/purchase-order-items/{id}/           # Ver item
PUT    /api/purchase-order-items/{id}/           # Actualizar item
PATCH  /api/purchase-order-items/{id}/           # Actualizar parcial
```

## 🔧 Pasos para Completar la Migración

### Paso 1: Ejecutar Migraciones (REQUERIDO)

Activa tu entorno virtual y ejecuta las migraciones en el orden correcto:

```bash
# Activar entorno virtual
source venv/bin/activate

# 1. Primero migrar purchase_orders para crear las referencias en Django
python manage.py migrate purchase_orders

# 2. Luego migrar proveedores para eliminar los modelos antiguos
python manage.py migrate proveedores

# 3. Verificar que no hay conflictos
python manage.py check
```

**IMPORTANTE:** Las tablas de base de datos NO se mueven físicamente. La migración solo actualiza el estado de Django para que sepa que los modelos están en `purchase_orders` en lugar de `proveedores`.

### Paso 2: Actualizar Imports en Tu Código (Si Aplica)

Si tienes código personalizado que importa desde `proveedores.models`:

**Antes:**
```python
from proveedores.models import PurchaseOrder, PurchaseOrderItem
```

**Ahora:**
```python
from purchase_orders.models import PurchaseOrder, PurchaseOrderItem
```

### Paso 3: Actualizar Referencias en Frontend (Si Aplica)

Si tu frontend llama directamente a las APIs de purchase orders:

**Antes:**
```javascript
fetch('/api/proveedores/purchase-orders/')
```

**Ahora:**
```javascript
fetch('/api/purchase-orders/')
```

### Paso 4: Ejecutar Tests

Verifica que todo funcione correctamente:

```bash
# Tests del módulo purchase_orders
pytest purchase_orders/tests/ -v

# Tests del módulo proveedores (deberían seguir funcionando)
pytest proveedores/tests/ -v

# Tests de integración
pytest -v
```

## 📋 Verificación Post-Migración

### 1. Verificar Admin
- Accede a `/admin/`
- Verifica que `Purchase Orders` aparezca como su propia sección
- Verifica que `Providers` y `Products` sigan en `Proveedores`

### 2. Verificar APIs
```bash
# Listar purchase orders
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/api/purchase-orders/

# Crear purchase order
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": 1, "status": "DRAFT", "items": []}' \
  http://localhost:8000/api/purchase-orders/
```

### 3. Verificar Modelos
```python
# En Django shell
python manage.py shell

>>> from purchase_orders.models import PurchaseOrder, PurchaseOrderItem
>>> from proveedores.models import Provider, Product
>>> 
>>> # Verificar que existan datos
>>> PurchaseOrder.objects.count()
>>> PurchaseOrderItem.objects.count()
>>> 
>>> # Verificar relaciones
>>> po = PurchaseOrder.objects.first()
>>> po.provider  # Debe funcionar
>>> po.items.all()  # Debe funcionar
```

## ⚠️ Troubleshooting

### Error: "No module named 'purchase_orders'"
**Solución:** Asegúrate de que `purchase_orders` está en `INSTALLED_APPS` en `config/settings/base.py`

### Error: "Table doesn't exist"
**Solución:** Ejecuta las migraciones en orden:
```bash
python manage.py migrate purchase_orders
python manage.py migrate proveedores
```

### Error: "Reverse accessor clashes"
**Solución:** Los modelos antiguos en `proveedores` deben estar eliminados. Verifica que `proveedores/models.py` no contenga `PurchaseOrder` ni `PurchaseOrderItem`.

### Error en Tests
**Solución:** Actualiza los imports en los tests de proveedores si hacen referencia a PurchaseOrder.

## 📦 Rollback (Solo si es Necesario)

Si necesitas revertir los cambios:

```bash
# 1. Revertir migración de proveedores
python manage.py migrate proveedores 0013_provider_order_available_weekdays_and_more

# 2. Revertir migración de purchase_orders
python manage.py migrate purchase_orders zero

# 3. Eliminar purchase_orders de INSTALLED_APPS

# 4. Restaurar código original de proveedores desde git
git checkout proveedores/
```

## ✨ Beneficios de la Separación

1. **Mejor Organización**: Módulos claramente separados por responsabilidad
2. **Escalabilidad**: Más fácil agregar funcionalidades específicas de órdenes
3. **Mantenibilidad**: Código más limpio y fácil de entender
4. **Testing**: Tests más focalizados y organizados
5. **APIs Claras**: Endpoints más semánticos

## 🎯 Próximos Pasos Recomendados

1. Considera crear un módulo `receiver` si tienes lógica de recepción
2. Documenta las APIs con Swagger/OpenAPI
3. Agrega más tests de integración entre módulos
4. Considera agregar permisos específicos por módulo
