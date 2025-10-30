# Invoice Parser App

Aplicación Django para parsear facturas PDF utilizando la API de OpenAI.

## Descripción

Esta app proporciona un endpoint REST para procesar facturas en formato PDF y extraer las líneas de productos en formato CSV. Utiliza el modelo GPT-4o de OpenAI para analizar el contenido del PDF y estructurar los datos.

## Endpoint

### POST /api/invoice-parser/parse/

Parsea una factura PDF y devuelve los datos extraídos en formato CSV.

**Autenticación:** Requerida (JWT, Session o Token)

**Parámetros:**
- `file` (archivo, requerido): Archivo PDF de la factura a procesar (máx. 10MB)

**Respuesta exitosa (200 OK):**
```
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="factura_parseada.csv"

codigo,cajas,uc,iva,articulo,udes,unidad,precio,precio_iva,importe,contenedor
12345,10,2,21,Producto A,20,KG,5.50,6.66,133.20,Contenedor 1
...
```

**Errores:**
- `400 Bad Request`: Archivo inválido o no es PDF
- `500 Internal Server Error`: Error al procesar el PDF o problemas con OpenAI API

## Formato CSV Extraído

El CSV contiene las siguientes columnas:
- **codigo**: Código del producto
- **cajas**: Número de cajas
- **uc**: Unidades por caja
- **iva**: Porcentaje de IVA
- **articulo**: Nombre del artículo
- **udes**: Unidades totales
- **unidad**: Unidad de medida
- **precio**: Precio unitario sin IVA
- **precio_iva**: Precio unitario con IVA
- **importe**: Importe total
- **contenedor**: Contenedor de origen (si aplica)

## Configuración

### Variables de Entorno

Agrega la siguiente variable a tu archivo `.env`:

```bash
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxx
```

### Instalación de Dependencias

La librería `openai` está incluida en `requirements/base.txt`:

```bash
pip install -r requirements/local.txt
```

## Uso desde el Frontend

### Ejemplo con JavaScript/Fetch

```javascript
const formData = new FormData();
formData.append('file', pdfFile); // pdfFile es un objeto File

const response = await fetch('/api/invoice-parser/parse/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
  },
  body: formData
});

if (response.ok) {
  const csvBlob = await response.blob();
  // Descargar el archivo CSV
  const url = window.URL.createObjectURL(csvBlob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'factura_parseada.csv';
  a.click();
}
```

### Ejemplo con cURL

```bash
curl -X POST http://localhost:8000/api/invoice-parser/parse/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@factura.pdf" \
  -o factura_parseada.csv
```

## Estructura de la App

```
invoice_parser/
├── __init__.py
├── apps.py              # Configuración de la app
├── models.py            # Sin modelos (no almacena datos)
├── serializers.py       # Serializers para validación
├── views.py             # ViewSet con lógica de parseo
├── admin.py             # Sin admin necesario
└── README.md            # Esta documentación
```

## Detalles Técnicos

### Flujo de Procesamiento

1. **Recepción del archivo**: El PDF se recibe mediante multipart/form-data
2. **Validación**: Se valida que sea un PDF y no supere 10MB
3. **Guardado temporal**: El archivo se guarda temporalmente en el servidor
4. **Subida a OpenAI**: Se sube el PDF a la API de OpenAI
5. **Procesamiento**: Se envía un prompt a GPT-4o para extraer las líneas
6. **Respuesta**: Se devuelve el CSV como archivo descargable
7. **Limpieza**: Se elimina el archivo temporal

### Consideraciones

- **Modelo usado**: `gpt-4o` (puede cambiarse en `views.py`)
- **Límite de archivo**: 10MB (configurable en `serializers.py`)
- **Timeout**: Las tareas de Celery tienen un límite de 5 minutos (suficiente para este proceso)
- **Archivos temporales**: Se limpian automáticamente después del procesamiento
- **Costos**: Cada petición consume tokens de OpenAI (verificar pricing)

## Logging

Los logs se generan con el módulo `logging` de Python:
- **Info**: Cuando se sube un archivo exitosamente a OpenAI
- **Error**: Si falta la API key o hay problemas con OpenAI
- **Exception**: Para errores generales durante el procesamiento

## Mejoras Futuras

- [ ] Soporte para otros formatos (imágenes, Excel)
- [ ] Caché de resultados para facturas repetidas
- [ ] Procesamiento asíncrono con Celery para PDFs grandes
- [ ] Almacenamiento de historial de parseos en base de datos
- [ ] Validación adicional de la estructura CSV extraída
- [ ] Soporte para múltiples prompts/formatos de factura
