"""Views for invoice parser with corrected OpenAI integration."""

import logging
import json
import time
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema
from openai import OpenAI

from .models import InvoiceParse, InvoiceLineItem
from .serializers import (
    InvoiceUploadSerializer,
    InvoiceParseResponseSerializer,
    InvoiceParseSerializer,
    InvoiceParseListSerializer,
)


logger = logging.getLogger(__name__)


class InvoiceParserViewSet(viewsets.ModelViewSet):
    """ViewSet para parsear facturas PDF usando OpenAI con JSON Schema estricto."""
    
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
        """Filtra facturas por usuario."""
        return self.queryset.filter(uploaded_by=self.request.user)
    
    @extend_schema(
        request=InvoiceUploadSerializer,
        responses={200: InvoiceParseResponseSerializer},
        description="Parsea un PDF de factura usando OpenAI y extrae líneas de productos"
    )
    @action(detail=False, methods=["post"])
    def parse(self, request):
        """
        Parsea un PDF de factura usando OpenAI con JSON Schema estricto.
        
        Mejoras implementadas:
        - Thread nuevo por factura (no reutiliza threads)
        - PDF adjunto directamente en el mensaje
        - JSON Schema con minItems/maxItems para validar conteo
        - tool_choice="none" para evitar conversación
        - Lee SOLO mensajes del run actual (no del thread completo)
        - Validación estricta del conteo esperado
        """
        serializer = InvoiceUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        uploaded_file = serializer.validated_data['file']
        expected_lines = serializer.validated_data.get('expected_lines', 118)
        
        # Validar que sea PDF
        if not uploaded_file.name.lower().endswith('.pdf'):
            return Response(
                {"detail": "El archivo debe ser un PDF"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Crear registro de factura
        invoice_parse = InvoiceParse.objects.create(
            uploaded_by=request.user,
            original_filename=uploaded_file.name,
            file=uploaded_file,
            status=InvoiceParse.Status.PROCESSING
        )
        
        try:
            # Inicializar cliente OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
            logger.info(f"Starting invoice parse {invoice_parse.id} for file: {uploaded_file.name}")
            
            # 1) Subir PDF para assistants
            uploaded_file.seek(0)  # Volver al inicio
            openai_file = client.files.create(
                file=uploaded_file,
                purpose="assistants"
            )
            
            logger.info(f"File uploaded to OpenAI: {openai_file.id}")
            invoice_parse.openai_file_id = openai_file.id
            invoice_parse.save(update_fields=["openai_file_id"])
            
            # 2) Crear Assistant con instrucciones estrictas
            assistant = client.beta.assistants.create(
                name="Invoice Parser — JSON estricto",
                model="gpt-4o",
                instructions=self._get_parsing_instructions(expected_lines),
            )
            
            # 3) Crear thread NUEVO con el PDF adjunto (CRÍTICO: thread limpio)
            thread = client.beta.threads.create(
                messages=[
                    {
                        "role": "user",
                        "content": f"Lee las 4 páginas del PDF adjunto y devuelve SOLO el JSON con TODOS los {expected_lines} productos.",
                        "attachments": [
                            {
                                "file_id": openai_file.id,
                                "tools": []  # Sin herramientas
                            }
                        ],
                    }
                ]
            )
            
            logger.info(f"Thread created: {thread.id}")
            invoice_parse.openai_thread_id = thread.id
            invoice_parse.save(update_fields=["openai_thread_id"])
            
            # 4) JSON Schema estricto con min/max items
            json_schema = self._get_json_schema(expected_lines)
            
            # 5) Ejecutar run con validación estricta
            run = client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant.id,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "productos_schema",
                        "schema": json_schema,
                        "strict": True
                    }
                },
                tool_choice="none",  # NO usar herramientas
                max_completion_tokens=16000,
            )
            
            logger.info(f"Run created: {run.id}")
            invoice_parse.openai_run_id = run.id
            invoice_parse.save(update_fields=["openai_run_id"])
            
            # 6) Esperar a que termine (con timeout)
            timeout = 300  # 5 minutos
            start_time = time.time()
            
            while True:
                r = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
                
                if r.status in ("completed", "failed", "cancelled", "expired"):
                    break
                
                if time.time() - start_time > timeout:
                    logger.error("Timeout waiting for OpenAI response")
                    raise Exception("Timeout procesando el PDF")
                
                time.sleep(2)
            
            if r.status != "completed":
                logger.error(f"Run failed with status: {r.status}")
                raise Exception(f"Error procesando el PDF: {r.status}")
            
            # 7) Leer SOLO los mensajes de este run (CRÍTICO: no del thread completo)
            msgs = client.beta.threads.messages.list(
                thread_id=thread.id,
                run_id=run.id  # Filtrar por run_id
            )
            
            logger.info(f"Received {len(msgs.data)} messages from this run")
            
            # 8) Obtener el último mensaje del assistant de este run
            assistant_msgs = [m for m in msgs.data if m.role == "assistant"]
            if not assistant_msgs:
                raise Exception("No se encontró mensaje del assistant para este run")
            
            # El primer mensaje es el más reciente (list ordena desc)
            msg = assistant_msgs[0]
            
            # 9) Extraer texto (JSON puro)
            parts = []
            for c in msg.content:
                if c.type == "text":
                    parts.append(c.text.value)
            json_text = "".join(parts).strip()
            
            logger.info(f"Extracted JSON length: {len(json_text)} characters")
            
            # 10) Parsear y validar JSON
            try:
                data = json.loads(json_text)
                productos = data.get("productos", [])
                
                logger.info(f"JSON parsed successfully with {len(productos)} products")
                
                # Validación estricta del conteo
                if len(productos) != expected_lines:
                    logger.error(f"Product count mismatch: {len(productos)} != {expected_lines}")
                    raise ValueError(
                        f"Conteo inesperado: {len(productos)} productos extraídos, "
                        f"se esperaban {expected_lines}"
                    )
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}")
                logger.error(f"JSON content preview: {json_text[:500]}")
                raise Exception(f"Error parseando JSON: {e}")
            
            # 11) Guardar como CSV (para compatibilidad)
            csv_lines = ["codigo,cajas,uc,articulo,udes,unidad,contenedor"]
            for prod in productos:
                line = ",".join([
                    str(prod.get('codigo', '')),
                    str(prod.get('cajas', '')),
                    str(prod.get('uc', '')),
                    str(prod.get('articulo', '')).replace(',', ' '),  # Escapar comas
                    str(prod.get('udes', '')),
                    str(prod.get('unidad', '')),
                    str(prod.get('contenedor', '')),
                ])
                csv_lines.append(line)
            
            csv_data = "\n".join(csv_lines)
            
            logger.info(f"CSV data generated: {len(csv_lines)} lines")
            
            # 12) Guardar en BD
            invoice_parse.csv_data = csv_data
            invoice_parse.save(update_fields=["csv_data"])
            
            # 13) Crear líneas individuales
            with transaction.atomic():
                logger.info(f"Starting to create {len(productos)} invoice lines for parse {invoice_parse.id}")
                
                for idx, prod in enumerate(productos, start=1):
                    InvoiceLineItem.objects.create(
                        invoice_parse=invoice_parse,
                        line_number=idx,
                        codigo=str(prod.get('codigo', ''))[:50],
                        cajas=self._parse_decimal(prod.get('cajas')),
                        uc=self._parse_decimal(prod.get('uc')),
                        articulo=str(prod.get('articulo', ''))[:255],
                        udes=self._parse_decimal(prod.get('udes')),
                        unidad=str(prod.get('unidad', '')) if prod.get('unidad') else None,
                        contenedor=str(prod.get('contenedor', '')) if prod.get('contenedor') else None,
                        raw_data=prod,
                    )
                
                logger.info(f"Created {len(productos)} invoice lines for parse {invoice_parse.id}")
            
            # 14) Marcar como completado
            invoice_parse.status = InvoiceParse.Status.COMPLETED
            invoice_parse.completed_at = timezone.now()
            invoice_parse.save(update_fields=["status", "completed_at"])
            
            # 15) Limpiar recursos de OpenAI
            try:
                client.beta.assistants.delete(assistant.id)
                logger.info(f"Deleted assistant: {assistant.id}")
            except Exception as e:
                logger.warning(f"Could not delete assistant: {e}")
            
            logger.info(f"Invoice parse completed: {invoice_parse.id} with {len(productos)} lines")
            
            response_serializer = InvoiceParseResponseSerializer(invoice_parse)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error processing PDF: {str(e)}", exc_info=True)
            
            invoice_parse.status = InvoiceParse.Status.FAILED
            invoice_parse.error_message = str(e)
            invoice_parse.save(update_fields=["status", "error_message"])
            
            return Response(
                {"detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_parsing_instructions(self, expected_lines):
        """Genera las instrucciones para el Assistant."""
        return f"""
SALIDA JSON (BLOQUEANTE):
- Devuelve ÚNICAMENTE un JSON válido que empiece con "{{" y termine con "}}".
- Prohibido texto fuera del JSON, markdown, explicaciones o logs.
- Prohibido generar cadenas adyacentes: dentro de cualquier campo string NO puede aparecer el patrón: "..."+<espacios>+"..."
  Si una descripción se partiría así, únelas en una sola cadena con un espacio.
- Prohibido comillas sin escapar en strings (escapa \\" o usa comilla simple).

ALCANCE (PDF ESPECÍFICO):
- Documento: FACTURA Nº 0098727880 (ref. FR00987278805).
- Páginas: 4 (procésalas TODAS).
- Encabezado repetido: "Código Cajas U/C IVA PVP rec. Ofe Artículo Udes./Kg Precio Precio+IVA Importe".
- Bloques "Contenedor: <id>" agrupan filas siguientes hasta el próximo "Contenedor:".

OBJETIVO:
- Extrae TODAS las líneas de productos ({expected_lines} en total).
- Devuelve por cada línea EXACTAMENTE estos 7 campos:
  - codigo: string
  - cajas: number|null
  - uc: number|null
  - articulo: string
  - udes: number|null
  - unidad: string|null (UN, KG, L, ML, G... en mayúsculas, o null)
  - contenedor: string|null

REGLAS:
- "Artículo" puede ser largo/multilínea: devuélvelo como UNA sola cadena.
- Asigna el último "Contenedor: <id>" visto a cada fila posterior hasta cambiar.
- Ignora cabeceras, "FALTAS EN EL SERVICIO", SUBTOTAL/IVA/BASES/SUMAS/"Total Factura", notas y pies.
- No inventes: si un campo no aparece inequívoco, usa null.
- Normaliza unidades: U/UD/UDS→"UN"; KGS→"KG"; LTS→"L".
- No calcules udes como cajas*uc; si no está explícito, deja null.
- Elimina duplicados por saltos de página/cabeceras.

CONTROL:
- Deben salir {expected_lines} objetos en "productos".
- Tipos correctos: numbers sin comillas; strings UTF-8; null cuando falte.
- Cada objeto debe tener exactamente las 7 claves pedidas.

RESPUESTA FINAL (ÚNICA):
{{"productos":[ ... {expected_lines} objetos ... ]}}
""".strip()
    
    def _get_json_schema(self, expected_lines):
        """Genera el JSON Schema con validación estricta."""
        return {
            "type": "object",
            "properties": {
                "productos": {
                    "type": "array",
                    "minItems": expected_lines,
                    "maxItems": expected_lines,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["codigo", "cajas", "uc", "articulo", "udes", "unidad", "contenedor"],
                        "properties": {
                            "codigo": {"type": "string"},
                            "cajas": {"type": ["number", "null"]},
                            "uc": {"type": ["number", "null"]},
                            "articulo": {"type": "string"},
                            "udes": {"type": ["number", "null"]},
                            "unidad": {"type": ["string", "null"]},
                            "contenedor": {"type": ["string", "null"]},
                        },
                    },
                }
            },
            "required": ["productos"],
            "additionalProperties": False,
        }
    
    def _parse_decimal(self, value):
        """Convierte un valor a Decimal de forma segura."""
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None
