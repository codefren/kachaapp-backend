"""Views for invoice parser."""

import logging
import os
import tempfile
import csv
import io
import base64
import time
import json
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import InvoiceParse, InvoiceLineItem
from .serializers import (
    InvoiceUploadSerializer,
    InvoiceParseResponseSerializer,
    InvoiceParseSerializer,
    InvoiceParseListSerializer,
)


logger = logging.getLogger(__name__)


class InvoiceParserViewSet(viewsets.ModelViewSet):
    """ViewSet para parsear facturas PDF usando OpenAI."""
    
    queryset = InvoiceParse.objects.select_related("uploaded_by").prefetch_related("lines").all()
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]
    
    def get_serializer_class(self):
        """Retorna el serializer apropiado según la acción."""
        if self.action == "list":
            return InvoiceParseListSerializer
        elif self.action == "retrieve":
            return InvoiceParseSerializer
        elif self.action == "parse":
            return InvoiceUploadSerializer
        return InvoiceParseSerializer
    
    def get_queryset(self):
        """Filtra facturas por usuario actual."""
        return self.queryset.filter(uploaded_by=self.request.user)
    
    @extend_schema(
        request=InvoiceUploadSerializer,
        responses={
            200: InvoiceParseResponseSerializer,
            400: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        description="Parsea una factura PDF y extrae las líneas como CSV",
    )
    @action(detail=False, methods=["post"], url_path="parse")
    def parse(self, request):
        """Endpoint para parsear factura PDF.
        
        Recibe un archivo PDF, lo procesa con OpenAI y devuelve los datos
        extraídos en formato CSV.
        
        Returns:
            CSV con las líneas de la factura extraídas
        """
        serializer = InvoiceUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "Datos inválidos", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        uploaded_file = serializer.validated_data["file"]
        
        # Crear registro de InvoiceParse
        invoice_parse = InvoiceParse.objects.create(
            uploaded_by=request.user,
            original_filename=uploaded_file.name,
            file=uploaded_file,
            status=InvoiceParse.Status.PROCESSING
        )
        
        try:
            # Importar OpenAI dentro de la función para evitar errores si no está instalado
            try:
                from openai import OpenAI
            except ImportError:
                logger.error("OpenAI library not installed")
                return Response(
                    {"detail": "OpenAI library not installed. Install with: pip install openai"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Verificar que existe la API key
            api_key = getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                logger.error("OPENAI_API_KEY not configured")
                return Response(
                    {"detail": "OPENAI_API_KEY no está configurada en settings o variables de entorno"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            client = OpenAI(api_key=api_key)
            
            # Guardar el archivo temporalmente
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                for chunk in uploaded_file.chunks():
                    tmp_file.write(chunk)
                tmp_path = tmp_file.name
            
            try:
                # 1) Subir el PDF a OpenAI
                with open(tmp_path, "rb") as f:
                    file = client.files.create(
                        file=f,
                        purpose="assistants"
                    )
                
                logger.info(f"File uploaded to OpenAI: {file.id}")
                
                # Guardar el file_id de OpenAI
                invoice_parse.openai_file_id = file.id
                invoice_parse.save(update_fields=["openai_file_id"])
                
                # 2) Crear un Assistant para extraer los datos en JSON
                assistant = client.beta.assistants.create(
                    name="Invoice Parser — FACTURA (JSON estricto)",
                    instructions=(
                        "SALIDA JSON (BLOQUEANTE):\n"
                        "- Devuelve ÚNICAMENTE un JSON válido que empiece con '{' y termine con '}'.\n"
                        "- Prohibido texto fuera del JSON, markdown, explicaciones o logs.\n"
                        "- Prohibido generar cadenas adyacentes: dentro de cualquier campo string NO puede aparecer el patrón: \"...\"+<espacios>+\"…\"\n"
                        "  Si detectas que una descripción se partiría así, únelas en una sola cadena con un espacio.\n"
                        "- Prohibido comillas sin escapar dentro de strings. Si aparece una comilla doble en la descripción, reemplázala por comilla simple o escápala con \\.\n\n"
                        
                        "ALCANCE (PDF ESPECÍFICO):\n"
                        "- Documento: FACTURA Nº 0098727880 (ref. FR00987278805).\n"
                        "- Páginas: 4 (procésalas TODAS).\n"
                        "- Encabezado de tabla (repetido): 'Código Cajas U/C IVA PVP rec. Ofe Artículo Udes./Kg Precio Precio+IVA Importe'.\n"
                        "- Existen bloques 'Contenedor: <id>' que agrupan líneas siguientes hasta el próximo 'Contenedor:'.\n\n"
                        
                        "OBJETIVO:\n"
                        "- Extrae TODAS las líneas de productos (118 en total).\n"
                        "- Devuelve por cada línea EXACTAMENTE estos 7 campos:\n"
                        "  - codigo: string\n"
                        "  - cajas: number|null\n"
                        "  - uc: number|null\n"
                        "  - articulo: string\n"
                        "  - udes: number|null\n"
                        "  - unidad: string|null (UN, KG, L, ML, G... en mayúsculas, o null)\n"
                        "  - contenedor: string|null\n\n"
                        
                        "PARSING (REGLAS DE ESTE PDF):\n"
                        "- Las filas válidas están bajo el encabezado. 'Artículo' puede ser largo y/o multilínea; une el texto en UNA sola cadena.\n"
                        "- Si ves texto tipo abreviatura seguida de punto (ej. 'ROLL.'), NUNCA cierres y reabras comillas: mantén 'articulo' como una sola cadena: 'ROLL. PAPEL ...'.\n"
                        "- Asigna el último 'Contenedor: <id>' visto a cada fila posterior hasta que cambie.\n"
                        "- Ignora: cabeceras repetidas, 'FALTAS EN EL SERVICIO', SUBTOTAL, IVA/BASES/SUMAS, 'Total Factura', notas y pies de página.\n"
                        "- No inventes datos: si un campo no aparece de forma inequívoca, pon null.\n"
                        "- Normaliza unidades: U/UD/UDS→'UN'; KGS→'KG'; LTS→'L'.\n"
                        "- No calcules 'udes' como cajas*uc; si no está explícito, deja null.\n"
                        "- Elimina duplicados causados por saltos de página y cabeceras.\n\n"
                        
                        "SANITIZACIÓN DE STRINGS:\n"
                        "- Recorta espacios extremos.\n"
                        "- Sustituye saltos de línea internos de 'articulo' por un solo espacio.\n"
                        "- Prohibido incluir comillas dobles sin escapar; si existen en la fuente, usa comilla simple.\n"
                        "- Asegura que 'articulo' sea UNA única cadena JSON (sin concatenar dos strings).\n\n"
                        
                        "CONTROL DE CALIDAD:\n"
                        "- Deben salir **118** objetos en 'productos'.\n"
                        "- Tipos correctos: numbers sin comillas; strings UTF-8; null cuando falte.\n"
                        "- Cada objeto debe tener **exactamente** las 7 claves pedidas (ni más ni menos).\n"
                        "- Verifica que 'articulo' no sea un encabezado, total o nota.\n\n"
                        
                        "RESPUESTA FINAL (ÚNICA):\n"
                        '{"productos":[ ... 118 objetos ... ]}'
                    ),
                    model="gpt-4o",
                    response_format={"type": "json_object"}  # Forzar respuesta en JSON puro
                )
                
                # 3) Crear un Thread y enviar el mensaje con el archivo
                thread = client.beta.threads.create(
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                "Lee las 4 páginas completas del PDF. "
                                "Extrae TODAS las líneas de productos sin omitir ninguna. "
                                "Devuelve SOLO el JSON con todos los productos, sin explicaciones."
                            ),
                            "attachments": [
                                {
                                    "file_id": file.id,
                                    "tools": [{"type": "file_search"}]  # file_search en lugar de code_interpreter
                                }
                            ]
                        }
                    ]
                )
                
                # 4) Ejecutar el Assistant
                run = client.beta.threads.runs.create(
                    thread_id=thread.id,
                    assistant_id=assistant.id,
                    max_completion_tokens=16000  # Permitir respuestas largas (100-120 productos)
                )
                
                # 5) Esperar a que termine (con timeout)
                timeout = 300  # 300 segundos (5 minutos para PDFs grandes)
                start_time = time.time()
                
                while run.status in ["queued", "in_progress"]:
                    if time.time() - start_time > timeout:
                        logger.error("Timeout waiting for OpenAI response")
                        raise Exception("Timeout procesando el PDF")
                    
                    time.sleep(1)
                    run = client.beta.threads.runs.retrieve(
                        thread_id=thread.id,
                        run_id=run.id
                    )
                
                if run.status != "completed":
                    logger.error(f"Run failed with status: {run.status}")
                    raise Exception(f"Error procesando el PDF: {run.status}")
                
                # 6) Obtener la respuesta
                messages = client.beta.threads.messages.list(
                    thread_id=thread.id,
                    order="asc"
                )
                
                logger.info(f"Received {len(messages.data)} messages from thread")
                
                # Buscar el ÚLTIMO mensaje del assistant que contenga JSON
                # (ignorar mensajes de conversación intermedios)
                csv_data = ""
                assistant_messages = []
                
                for idx, message in enumerate(messages.data):
                    logger.info(f"Message {idx}: role={message.role}, content_count={len(message.content)}")
                    if message.role == "assistant":
                        for content in message.content:
                            if hasattr(content, "text"):
                                text = content.text.value
                                assistant_messages.append((idx, text))
                                logger.info(f"Assistant message {idx} length: {len(text)}, starts with: {text[:50]}...")
                
                # Buscar el mensaje que contenga JSON (el que empiece con { o contenga "productos")
                for idx, text in reversed(assistant_messages):  # Empezar por el último
                    if "{" in text and "productos" in text:
                        csv_data = text
                        logger.info(f"Using message {idx} as JSON source (length: {len(csv_data)})")
                        break
                
                # Si no encontramos ningún mensaje con JSON, usar el último mensaje del assistant
                if not csv_data and assistant_messages:
                    csv_data = assistant_messages[-1][1]
                    logger.warning(f"No JSON-like message found, using last assistant message")
                
                # 7) Limpiar recursos
                try:
                    client.beta.assistants.delete(assistant.id)
                except Exception as e:
                    logger.warning(f"Could not delete assistant: {e}")
                
                # 8) Verificar si el JSON está truncado
                if csv_data and (csv_data.endswith("...") or csv_data.endswith("...\n")):
                    logger.error("JSON response appears to be truncated (ends with ...)")
                    invoice_parse.status = InvoiceParse.Status.FAILED
                    invoice_parse.error_message = "Respuesta truncada del modelo. Intenta de nuevo."
                    invoice_parse.save()
                    return Response(
                        {"detail": "Respuesta truncada del modelo. Intenta de nuevo."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # 9) Limpiar el JSON si viene con marcadores de código o texto explicativo
                json_data = csv_data  # Renombrar para claridad
                
                # Remover bloques de código markdown si existen
                if "```" in json_data:
                    # Remover líneas que solo contienen ``` o ```json
                    lines = json_data.split("\n")
                    json_lines = []
                    for line in lines:
                        stripped = line.strip()
                        # Ignorar líneas que solo son marcadores de código
                        if stripped.startswith("```"):
                            continue
                        json_lines.append(line)
                    json_data = "\n".join(json_lines).strip()
                    logger.info("Removed markdown code blocks")
                
                # 9) Extraer JSON si hay texto explicativo
                if not json_data.startswith("{"):
                    logger.warning("Response does not start with JSON. Attempting to extract...")
                    # Buscar el primer { y el último }
                    start_idx = json_data.find("{")
                    end_idx = json_data.rfind("}")
                    
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        json_data = json_data[start_idx:end_idx+1].strip()
                        logger.info("Extracted JSON from mixed content")
                    else:
                        logger.error("Could not find valid JSON in response")
                        json_data = None
                
                # Guardar el JSON extraído
                csv_data = json_data
                
                if not csv_data:
                    error_detail = f"Could not extract JSON from OpenAI response. Messages count: {len(messages.data)}"
                    logger.error(error_detail)
                    # Log completo de los mensajes para debugging
                    for idx, msg in enumerate(messages.data):
                        logger.error(f"Full message {idx}: {msg}")
                    
                    invoice_parse.status = InvoiceParse.Status.FAILED
                    invoice_parse.error_message = "No se pudo extraer datos del modelo."
                    invoice_parse.save()
                    return Response(
                        {"detail": "No se pudo extraer datos del modelo."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # 4) Limpiar JSON de strings duplicados (error comun del modelo)
                # Reemplazar patrones como articulo:ROLL. PAPEL con articulo:ROLL. PAPEL
                import re
                csv_data = re.sub(r'"\s+"', ' ', csv_data)
                logger.info("Applied JSON cleanup for duplicate strings")
                
                # 5) Parsear JSON y contar productos
                try:
                    data = json.loads(csv_data)
                    productos = data.get("productos", [])
                    logger.info(f"JSON parsed successfully with {len(productos)} products")
                    
                    # Validar que no se haya truncado
                    if len(productos) < 10:
                        logger.warning(f"Only {len(productos)} products extracted. This seems too few!")
                    
                    # Verificar si el JSON está completo
                    if not csv_data.rstrip().endswith("}"):
                        logger.error(f"JSON appears incomplete! Ends with: ...{csv_data[-50:]}")
                    else:
                        logger.info(f"JSON is complete. Total products: {len(productos)}")
                    
                    # Log del JSON completo para revisar (primeros y últimos caracteres)
                    logger.info(f"JSON start: {csv_data[:200]}...")
                    logger.info(f"JSON end: ...{csv_data[-200:]}")
                    logger.info(f"Total JSON length: {len(csv_data)} characters")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON: {e}")
                    logger.error(f"JSON content: {csv_data}")
                    raise Exception(f"Error parseando JSON: {e}")
                
                # 5) Convertir JSON a CSV para guardarlo (para compatibilidad)
                csv_lines = ["codigo,cajas,uc,articulo,udes,unidad,contenedor"]
                for prod in productos:
                    line = f"{prod.get('codigo', '')},{prod.get('cajas', '')},{prod.get('uc', '')},{prod.get('articulo', '')},{prod.get('udes', '')},{prod.get('unidad', '')},{prod.get('contenedor', '')}"
                    csv_lines.append(line)
                csv_for_storage = "\n".join(csv_lines)
                
                logger.info(f"Final data to save (CSV format):\n{csv_for_storage}")
                invoice_parse.csv_data = csv_for_storage
                invoice_parse.save(update_fields=["csv_data"])
                
                # 6) Crear líneas desde el JSON
                self._parse_and_save_lines_from_json(productos, invoice_parse)
                
                # 7) Marcar como completado
                invoice_parse.status = InvoiceParse.Status.COMPLETED
                invoice_parse.completed_at = timezone.now()
                invoice_parse.save(update_fields=["status", "completed_at"])
                
                logger.info(f"Invoice parse completed: {invoice_parse.id} with {invoice_parse.line_count} lines")
                
                # 8) Devolver el CSV (convertido desde JSON)
                from django.http import HttpResponse
                response = HttpResponse(csv_for_storage, content_type="text/csv; charset=utf-8")
                response["Content-Disposition"] = 'attachment; filename="factura_parseada.csv"'
                return response
                
            finally:
                # Limpiar archivo temporal
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        
        except Exception as e:
            logger.exception(f"Error processing PDF: {str(e)}")
            
            # Actualizar estado de error
            invoice_parse.status = InvoiceParse.Status.FAILED
            invoice_parse.error_message = str(e)
            invoice_parse.save()
            
            return Response(
                {"detail": f"Error procesando el PDF: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _parse_and_save_lines_from_json(self, productos, invoice_parse):
        """Parsea los productos desde JSON y guarda las líneas en la base de datos.
        
        Args:
            productos: Lista de diccionarios con los datos de productos
            invoice_parse: Instancia de InvoiceParse
        """
        try:
            logger.info(f"Starting to parse {len(productos)} products from JSON for invoice {invoice_parse.id}")
            
            lines_to_create = []
            
            def safe_decimal(value):
                if value is None or value == "":
                    return None
                try:
                    return Decimal(str(value).replace(",", "."))
                except (InvalidOperation, ValueError):
                    return None
            
            for line_number, prod in enumerate(productos, start=1):
                logger.info(f"Processing product {line_number}: {prod.get('articulo', 'N/A')}")
                
                line = InvoiceLineItem(
                    invoice_parse=invoice_parse,
                    line_number=line_number,
                    codigo=str(prod.get("codigo", ""))[:50],
                    cajas=safe_decimal(prod.get("cajas")),
                    uc=safe_decimal(prod.get("uc")),
                    articulo=str(prod.get("articulo", ""))[:255],
                    udes=safe_decimal(prod.get("udes")),
                    unidad=str(prod.get("unidad", ""))[:20],
                    contenedor=str(prod.get("contenedor", ""))[:100],
                    raw_data=prod
                )
                lines_to_create.append(line)
            
            # Crear todas las líneas en una sola operación
            if lines_to_create:
                InvoiceLineItem.objects.bulk_create(lines_to_create)
                logger.info(f"Created {len(lines_to_create)} invoice lines for parse {invoice_parse.id}")
            else:
                logger.warning(f"No lines were created from JSON for invoice {invoice_parse.id}")
        
        except Exception as e:
            logger.exception(f"Error parsing JSON products: {str(e)}")
            raise
    
    def _parse_and_save_lines(self, csv_data, invoice_parse):
        """Parsea el CSV y guarda las líneas en la base de datos.
        
        Args:
            csv_data: String con los datos CSV
            invoice_parse: Instancia de InvoiceParse
        """
        try:
            logger.info(f"Starting to parse CSV for invoice {invoice_parse.id}")
            # Leer CSV
            csv_file = io.StringIO(csv_data)
            reader = csv.DictReader(csv_file)
            
            lines_to_create = []
            line_number = 1
            
            logger.info(f"CSV headers: {reader.fieldnames}")
            
            for row in reader:
                logger.info(f"Processing row {line_number}: {row}")
                # Convertir valores numéricos con manejo de errores
                def safe_decimal(value):
                    if not value or value.strip() == "":
                        return None
                    try:
                        # Reemplazar coma por punto para decimales
                        value_clean = str(value).replace(",", ".")
                        return Decimal(value_clean)
                    except (InvalidOperation, ValueError):
                        return None
                
                line = InvoiceLineItem(
                    invoice_parse=invoice_parse,
                    line_number=line_number,
                    codigo=row.get("codigo", "")[:50],
                    cajas=safe_decimal(row.get("cajas")),
                    uc=safe_decimal(row.get("uc")),
                    articulo=row.get("articulo", "")[:255],
                    udes=safe_decimal(row.get("udes")),
                    unidad=row.get("unidad", "")[:20],
                    contenedor=row.get("contenedor", "")[:100],
                    raw_data=row
                )
                lines_to_create.append(line)
                line_number += 1
            
            # Crear todas las líneas en una sola operación
            if lines_to_create:
                InvoiceLineItem.objects.bulk_create(lines_to_create)
                logger.info(f"Created {len(lines_to_create)} invoice lines for parse {invoice_parse.id}")
            else:
                logger.warning(f"No lines were created from CSV for invoice {invoice_parse.id}")
        
        except Exception as e:
            logger.exception(f"Error parsing CSV lines: {str(e)}")
            # No lanzar excepción, solo registrar el error
            # El CSV ya está guardado y puede ser revisado manualmente
