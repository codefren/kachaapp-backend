# Proveedores – Módulos, Funciones, Serializadores y Validaciones

Fecha: 2025-09-15
Ámbito: aplicación `proveedores/`

## Resumen ejecutivo
- Proveedor: gestiona proveedores y relación con productos.
- Producto: soporta múltiples proveedores y códigos de barras. Guarda la última cantidad de cajas compradas.
- Órdenes de compra: cabecera con estados y líneas. Las líneas solo permiten unidad "boxes" y aplican reglas de negocio y constraints.
- Serializers: exponen campos calculados, consolidan ítems por producto y actualizan `Product.amount_boxes`.
- Vistas: viewsets para CRUD y acciones específicas (consulta por día, favoritos, etc.).
- Admin: filtros útiles (tiene barcode / barcode primario), inlines y acciones rápidas de estado.
- Tests: cubren endpoints, consolidación, validaciones de parámetros, URLs absolutas para imágenes, favoritos y filtros por barcode.

---

## Módulo: `proveedores/models.py`

### Clase `Provider`
- Campos: `name` (único), `created_at`, `updated_at`.
- Meta: `ordering=["name"]` y verbose names.
- Métodos: `__str__()` devuelve `name`.

### Clase `ProductFavorite`
- Propósito: relación de favorito entre `user` y `product`.
- Campos: `user` (FK a `AUTH_USER_MODEL`), `product` (FK `Product`), timestamps.
- Meta:
  - `unique_together=("user", "product")`.
  - Índices: `idx_fav_user_product (user, product)`, `idx_fav_product (product)`.
- Métodos: `__str__()` como `"<user> - <product>"`.

### Clase `Product`
- Campos: `name`, `sku` (único), `providers` (M2M), `amount_boxes` (int, últimas cajas pedidas), `units_per_box`, `image`, timestamps, `history` (simple_history).
- Meta: `ordering=["name"]`.
- Métodos: `__str__()` devuelve `name`.

### Clase `ProductBarcode`
- Propósito: múltiples códigos de barras por producto y tipo, con uno primario.
- Campos:
  - `product` (FK), `code` (único + `db_index=True`), `type` (`TextChoices`), `is_primary` (bool), `notes`, timestamps.
- Meta:
  - `ordering=["product_id", "-is_primary", "code"]`.
  - Índices: `idx_barcode_code (code)`, `idx_barcode_primary (product, is_primary)`.
- Métodos:
  - `__str__()`: etiqueta el tipo de barcode legible.
  - `save()`: si `is_primary=True`, apaga otros `is_primary` del mismo `product`.

### Clase `PurchaseOrder`
- Estados (`Status`): `DRAFT`, `PLACED`, `RECEIVED`, `CANCELED`.
- Campos: `provider` (PROTECT), `ordered_by` (SET_NULL, opcional), `status` (choices, `db_index=True`), `notes`, timestamps, `history`.
- Meta:
  - `ordering=["-created_at"]`.
  - Índices: `idx_po_provider_status (provider, status)`, `idx_po_created_at (created_at)`.
- Métodos: `__str__()` formatea `PO #<id> - <provider> (<status>)`.

### Clase `PurchaseOrderItem`
- Propósito: líneas de órdenes de compra.
- Campos:
  - `order` (FK, `related_name="items"`).
  - `product` (FK, PROTECT, `related_name="purchase_order_items"`).
  - `quantity_units` (`PositiveIntegerField`, `help_text="Units to order"`).
  - `purchase_unit` (`CharField`, `choices=["boxes"]`, default `"boxes"`, `db_index=True`).
  - `notes`, timestamps.
- Meta:
  - Índices: `idx_poi_order (order)`, `idx_poi_product (product)`, `idx_poi_order_product (order, product)`.
  - Constraints:
    - `CheckConstraint(quantity_units__gt=0, name="chk_poi_qty_gt_0")`.
    - `UniqueConstraint(fields=["order", "product", "purchase_unit"], name="uq_poi_order_product_purchase_unit")`.
- Validaciones/Métodos:
  - `clean()`: si `order.status == RECEIVED` -> `ValidationError` (no crear/modificar ítems).
  - `save()`: ejecuta `full_clean()`; si existe y la orden está `RECEIVED` -> `ValidationError` (no modificar).
  - `delete()`: si orden `RECEIVED` -> `ValidationError` (no eliminar).
  - `__str__()`: `"<product.name> x <quantity_units>"`.

---

## Módulo: `proveedores/serializers.py`

### `PurchaseOrderItemSerializer`
- Campos:
  - Modelo: `product`, `quantity_units`, `purchase_unit` (choices: `"boxes"`), `notes`, `created_at`, `updated_at`.
  - Calculados/auxiliares:
    - `product_name` (RO, `product.name`).
    - `product_image` (RO, método; URL absoluta y forzada a https).
    - `amount_boxes` (WO; no está en el modelo; se persiste en `Product.amount_boxes` y se incluye en salida desde el producto).
- Métodos:
  - `get_product_image(obj)`: obtiene `product.image.url`, construye absoluta con `request`, fuerza https.
  - `create(validated_data)`: extrae `amount_boxes` y actualiza `Product.amount_boxes` del producto asociado.
  - `update(instance, validated_data)`: idem `create`.
  - `to_representation(instance)`: reinyecta `amount_boxes` desde `instance.product.amount_boxes`.
- Validación: delega en el modelo (`full_clean()` se llama en `PurchaseOrderItem.save`).

### `ProviderSerializer`
- Campos: `id`, `name`, `created_at`, `updated_at`, `products_count` (RO, `source="products.count"`).

### `ProductBarcodeSerializer`
- Campos: `id`, `code`, `type`, `is_primary`.

### `ProviderMiniSerializer`
- Campos: `id`, `name`.

### `ProductSerializer`
- Campos: `id`, `name`, `sku`, `units_per_box`, `image` (URL https absoluta), `providers` (mini), `barcodes`, `current_user_favorite`, `amount_boxes`, timestamps.
- Métodos:
  - `get_current_user_favorite(obj)`: comprueba si el usuario autenticado tiene el producto como favorito.
  - `get_image(obj)`: construye URL absoluta y fuerza https.

### `PurchaseOrderSerializer`
- Campos: `id`, `provider`, `provider_name`, `ordered_by` (RO), `ordered_by_username` (RO), `status`, `notes`, `items` (nested), timestamps.
- `create(validated_data)`:
  - Fuerza `ordered_by` desde `request.user` si está autenticado.
  - Normaliza y consolida `items` por clave `(product_id, "boxes")` para respetar la unicidad del modelo.
  - Registra último `amount_boxes` por producto y lo persiste en `Product.amount_boxes`.
- `update(instance, validated_data)`:
  - Actualiza cabecera; si `items` viene, borra/recrea consolidando como en `create`.
  - Aplica `amount_boxes` en `Product` si vino en payload.
- `_normalize_item(item)`:
  - Convierte `quantity_units` a `int`.
  - Acepta `purchase_unit` o `unit_type` en el payload.
  - Fuerza `purchase_unit = "boxes"` (única unidad soportada hoy).

---

## Módulo: `proveedores/views.py`

### `load_products_from_ftp` (POST)
- Descarga JSON por FTP (`FTP_HOST`, `FTP_USER`, `FTP_PASS`, `FTP_JSON_PATH`).
- `Provider.get_or_create` por nombre y `Product.update_or_create` por `sku`.
- Asigna M2M `product.providers` y devuelve `{created, updated}`.

### `proveedores_root` (GET)
- `AllowAny`. Respuesta fija `{ "message": "Proveedores API root" }`.

### `PurchaseOrderViewSet` (ModelViewSet)
- Queryset: `select_related(provider, ordered_by)` y `Prefetch(items->product)`.
- Permisos: autenticado. Métodos: GET, POST, PUT, PATCH, HEAD, OPTIONS.
- Acciones:
  - `has_ordered_today` (GET): `{"has_ordered_today": bool}`. Acepta `?provider=<id>` con validación de entero.
  - `by_day` (GET): requiere `?date=YYYY-MM-DD`; filtra por día exacto y opcional `?provider=<id>`. Si no hay resultados, retorna objeto `{detail: ...}`.

### `PurchaseOrderItemViewSet` (ModelViewSet)
- CRUD de ítems. Permisos: autenticado. Métodos: GET, POST, PUT, PATCH, HEAD, OPTIONS.

### `ProductViewSet` (ReadOnlyModelViewSet)
- `get_queryset()` con prefetch de `providers`, `barcodes`, `favorites`.
- Filtros:
  - `?barcode=<code>`: exacto por `barcodes__code`.
  - `?name=<q>` o `?q=<q>`: `name__icontains`.
- Acciones:
  - `favorite` (POST): crea `ProductFavorite`.
  - `unfavorite` (POST): elimina favorito.
  - `my-favorites` (GET): lista productos favoritos del usuario (paginado si aplica).

### `ProviderViewSet` (ReadOnlyModelViewSet)
- Lista/detalle de proveedores.

---

## Módulo: `proveedores/admin.py`

### `ProviderAdmin`
- `list_display=(id, name)`, `search_fields=(name,)`, `ordering=(name,)`.

### `ProductBarcodeInline`
- Inline tabular en `Product`. Campos: `code`, `type`, `is_primary`, `notes`.

### Filtros personalizados en `ProductAdmin`
- `HasBarcodeFilter`: filtra productos con/sin barcodes.
- `HasPrimaryBarcodeFilter`: filtra por existencia de barcode primario.

### `ProductAdmin` (SimpleHistoryAdmin)
- `list_display=(id, name, sku, units_per_box, amount_boxes)`.
- Búsqueda: `name`, `sku`, `providers__name`, `barcodes__code`.
- Filtros: `providers`, `HasBarcodeFilter`, `HasPrimaryBarcodeFilter`.
- `filter_horizontal=(providers,)`.
- `readonly_fields=(image_preview,)` y `fields` incluyendo `image` y `image_preview`.
- `image_preview(obj)`: renderiza `<img>` si hay imagen.

### `PurchaseOrderItemInline`
- Inline en `PurchaseOrder`. Campos: `product`, `quantity_units`, `purchase_unit`, `notes`.

### `PurchaseOrderAdmin` (SimpleHistoryAdmin)
- `list_display=(id, provider, status, ordered_by, created_at)`.
- Filtros: `provider`, `status`, `created_at`.
- Acciones: `mark_as_draft|placed|received|canceled` (actualizan `status`).

### `PurchaseOrderItemAdmin`
- `list_display=(id, order, product, quantity_units, purchase_unit, created_at)`.
- Filtros, búsquedas y `list_select_related=(order, product)`.

---

## Módulo: `proveedores/tests/test_api.py`

Cubre:
- Root de la app.
- Listado de productos y proveedores.
- Creación y detalle de órdenes.
- Asignación de `ordered_by` automática desde `request.user`.
- Persistencia y respuesta de `purchase_unit = "boxes"`.
- Consolidación de líneas repetidas del mismo producto.
- Actualización de órdenes (recreación de ítems consolidando).
- Persistencia y reflejo de `amount_boxes` en `Product` tras create/update.
- Listado de ítems de órdenes.
- Favoritos: marcar, desmarcar y obtener "mis favoritos".
- `image` absoluto y https en `ProductSerializer` y `product_image` en `PurchaseOrderItemSerializer`.
- Filtro `products/?barcode=` con y sin resultados.
- `has-ordered-today` con y sin `provider` (y validación de parámetro inválido).
- Acción `by-day`: fecha requerida, validación de formato, respuesta de mensaje si no hay resultados, y retorno de un único objeto si hay resultados.
- Consultas de listado: sin `date` -> todas; `date` inválido en queryset -> todas.

---

## Validaciones clave y reglas de negocio

- Modelo `PurchaseOrderItem`:
  - Cantidad debe ser > 0 (`chk_poi_qty_gt_0`).
  - Unicidad `(order, product, purchase_unit)`; los serializers consolidan para cumplirla.
  - No se pueden crear/modificar/eliminar ítems si la orden está `RECEIVED`.

- Serializers:
  - `PurchaseOrderSerializer` fuerza `ordered_by` desde `request.user` y consolida ítems; mapea `amount_boxes` al `Product`.
  - `PurchaseOrderItemSerializer` restringe `purchase_unit` a `"boxes"`; `amount_boxes` es write-only y se reexpone desde el `Product`.

- Vistas:
  - Validación de query params en `has_ordered_today` y `by_day` con respuestas 400 si corresponde.
  - `by_day` devuelve objeto con `detail` cuando no hay resultados, no una lista vacía.

---

## Notas de mejora sugeridas

- Validadores adicionales:
  - `Product.units_per_box` podría usar `MinValueValidator(1)`.
  - `Product.amount_boxes` ya es `PositiveIntegerField` con `default=0`; si se aceptan 0, está bien; si no, usar validador > 0.

- Integridad de `ProductBarcode`:
  - La lógica de `save()` garantiza un único `is_primary` por producto. Mantener pruebas si se cambia a señales o constraints más estrictos.

- Transiciones de estado en `PurchaseOrder`:
  - Considerar validar transiciones (FSM) para evitar pasar de `CANCELED` a `PLACED`, etc.

- Extensibilidad de `purchase_unit`:
  - Hoy solo `"boxes"`. Si se añaden otras unidades, revisar consolidación y constraints.

- Robustez de `load_products_from_ftp`:
  - Manejar errores de conexión y validar esquema JSON para respuestas 4xx/5xx claras.

---

## Endpoints principales (referencia rápida)

- `POST /api/proveedores/load-products-from-ftp/` – carga productos/proveedores desde FTP.
- `GET /api/proveedores/` – root.
- `GET /api/proveedores/products/` – lista y filtros (`barcode`, `name`/`q`).
- `POST /api/proveedores/products/{id}/favorite/` – marca favorito.
- `POST /api/proveedores/products/{id}/unfavorite/` – quita favorito.
- `GET /api/proveedores/products/my-favorites/` – lista mis favoritos.
- `GET|POST|PATCH /api/proveedores/purchase-orders/` – CRUD de órdenes; consolidación de ítems.
- `GET /api/proveedores/purchase-orders/has-ordered-today/?provider=<id>` – consulta rápida por usuario.
- `GET /api/proveedores/purchase-orders/by-day/?date=YYYY-MM-DD[&provider=<id>]` – última orden del día.

---

## Mantenimiento
- Mantener este documento actualizado al modificar modelos o serializers.
- Añadir nuevas secciones si se crean señales, tareas de Celery u otros módulos relacionados.
