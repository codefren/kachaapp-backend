"""Views for invoice parser."""

import logging
import os
import tempfile
import csv
import io
import base64
import time
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
                
                # 2) Crear un Assistant para extraer el CSV
                assistant = client.beta.assistants.create(
                    name="Invoice Parser",
                    instructions=(
                        "Eres un extractor de líneas de productos de facturas en PDF. Debes leer el PDF y extraer TODAS las líneas de productos.\n\n"
                        "QUÉ BUSCAR EN LA FACTURA:\n"
                        "- Busca la tabla o lista de productos/artículos en la factura\n"
                        "- Cada producto/artículo tiene: código, cantidad de cajas, unidades por caja, nombre del artículo, unidades totales, tipo de unidad, y contenedor\n"
                        "- Extrae TODAS las líneas de productos que encuentres en el documento\n"
                        "- Lee el documento COMPLETO, no te detengas en la primera página\n\n"
                        "FORMATO DE SALIDA (CSV):\n"
                        "Primera línea (header): codigo,cajas,uc,articulo,udes,unidad,contenedor\n"
                        "Líneas siguientes: los datos de cada producto separados por comas\n\n"
                        "CAMPOS A EXTRAER:\n"
                        "- codigo: Código del producto\n"
                        "- cajas: Número de cajas\n"
                        "- uc: Unidades por caja (UC o Uc)\n"
                        "- articulo: Nombre del producto/artículo\n"
                        "- udes: Unidades totales\n"
                        "- unidad: Tipo de unidad (kg, ud, etc)\n"
                        "- contenedor: Número o nombre del contenedor\n\n"
                        "REGLAS IMPORTANTES:\n"
                        "1. NO escribas explicaciones, SOLO devuelve el CSV\n"
                        "2. NO uses bloques de código markdown (```csv)\n"
                        "3. Usa punto (.) para decimales\n"
                        "4. Si un campo no tiene valor, déjalo vacío\n"
                        "5. Extrae TODAS las líneas, no solo algunas\n\n"
                        "EJEMPLO DE SALIDA:\n"
                        "codigo,cajas,uc,articulo,udes,unidad,contenedor\n"
                        "12345,10,5,TOMATE CHERRY,50,kg,CONT-001\n"
                        "67890,5,10,LECHUGA ROMANA,50,ud,CONT-001\n"
                        "11111,8,6,PEPINO,48,kg,CONT-002"
                    ),
                    model="gpt-4o",
                    tools=[{"type": "code_interpreter"}]
                )
                
                # 3) Crear un Thread y enviar el mensaje con el archivo
                thread = client.beta.threads.create(
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                "Lee este PDF de factura y extrae TODAS las líneas de productos en formato CSV. "
                                "Busca la tabla de productos en el PDF y extrae cada línea con estos campos: "
                                "codigo,cajas,uc,articulo,udes,unidad,contenedor. "
                                "Devuelve SOLO el CSV completo, sin explicaciones."
                            ),
                            "attachments": [
                                {
                                    "file_id": file.id,
                                    "tools": [{"type": "code_interpreter"}]
                                }
                            ]
                        }
                    ]
                )
                
                # 4) Ejecutar el Assistant
                run = client.beta.threads.runs.create(
                    thread_id=thread.id,
                    assistant_id=assistant.id
                )
                
                # 5) Esperar a que termine (con timeout)
                timeout = 180  # 180 segundos (3 minutos)
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
                
                # Buscar el mensaje del assistant
                csv_data = ""
                for idx, message in enumerate(messages.data):
                    logger.info(f"Message {idx}: role={message.role}, content_count={len(message.content)}")
                    if message.role == "assistant":
                        for content_idx, content in enumerate(message.content):
                            logger.info(f"Content {content_idx}: type={type(content).__name__}, has_text={hasattr(content, 'text')}")
                            if hasattr(content, "text"):
                                csv_data = content.text.value
                                logger.info(f"Extracted CSV data length: {len(csv_data)}")
                                logger.debug(f"CSV data preview: {csv_data[:200]}...")
                                break
                        if csv_data:
                            break
                
                # 7) Limpiar recursos
                try:
                    client.beta.assistants.delete(assistant.id)
                except Exception as e:
                    logger.warning(f"Could not delete assistant: {e}")
                
                # 8) Limpiar el CSV si viene con marcadores de código o texto explicativo
                if csv_data.startswith("```"):
                    # Remover bloques de código markdown
                    lines = csv_data.split("\n")
                    csv_lines = []
                    in_code_block = False
                    for line in lines:
                        if line.startswith("```"):
                            in_code_block = not in_code_block
                            continue
                        if not in_code_block:
                            csv_lines.append(line)
                    csv_data = "\n".join(csv_lines).strip()
                
                # 9) Buscar el CSV real si hay texto explicativo
                # El CSV debe empezar con el header esperado
                expected_header = "codigo,cajas,uc,articulo,udes,unidad,contenedor"
                if not csv_data.startswith(expected_header) and expected_header in csv_data:
                    # Extraer desde el header hasta el final
                    start_idx = csv_data.index(expected_header)
                    csv_data = csv_data[start_idx:].strip()
                    logger.info("Extracted CSV from text with explanations")
                elif not csv_data.startswith(expected_header):
                    # Si no encontramos el header, buscar cualquier línea que parezca CSV
                    lines = csv_data.split("\n")
                    csv_lines = []
                    found_csv = False
                    for line in lines:
                        # Una línea CSV tiene comas y no es texto largo sin estructura
                        if "," in line and len(line.split(",")) >= 5:
                            found_csv = True
                            csv_lines.append(line)
                        elif found_csv and line.strip() == "":
                            # Línea vacía después del CSV, terminar
                            break
                        elif found_csv:
                            csv_lines.append(line)
                    
                    if csv_lines:
                        csv_data = "\n".join(csv_lines).strip()
                        logger.info(f"Extracted {len(csv_lines)} CSV lines from mixed content")
                
                if not csv_data:
                    error_detail = f"Could not extract CSV from OpenAI response. Messages count: {len(messages.data)}"
                    logger.error(error_detail)
                    # Log completo de los mensajes para debugging
                    for idx, msg in enumerate(messages.data):
                        logger.error(f"Full message {idx}: {msg}")
                    
                    invoice_parse.status = InvoiceParse.Status.FAILED
                    invoice_parse.error_message = "No se pudo extraer CSV del modelo."
                    invoice_parse.save()
                    return Response(
                        {"detail": "No se pudo extraer CSV del modelo."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # 4) Validar que el CSV no esté truncado
                csv_line_count = len([line for line in csv_data.split("\n") if line.strip()]) - 1  # -1 por el header
                logger.info(f"CSV extracted with {csv_line_count} product lines")
                
                # Detectar posibles truncamientos
                if csv_data.endswith("...") or "truncated" in csv_data.lower():
                    logger.warning("CSV appears to be truncated!")
                
                # 5) Guardar CSV y parsear líneas
                logger.info(f"Final CSV data to save:\n{csv_data}")
                invoice_parse.csv_data = csv_data
                invoice_parse.save(update_fields=["csv_data"])
                
                # 6) Parsear CSV y crear líneas
                self._parse_and_save_lines(csv_data, invoice_parse)
                
                # 7) Marcar como completado
                invoice_parse.status = InvoiceParse.Status.COMPLETED
                invoice_parse.completed_at = timezone.now()
                invoice_parse.save(update_fields=["status", "completed_at"])
                
                logger.info(f"Invoice parse completed: {invoice_parse.id} with {invoice_parse.line_count} lines")
                
                # 8) Devolver el CSV
                from django.http import HttpResponse
                response = HttpResponse(csv_data, content_type="text/csv; charset=utf-8")
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
