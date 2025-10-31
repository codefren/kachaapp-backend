"""Views for invoice parser."""

import logging
import os
import tempfile
import csv
import io
import base64
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
                        purpose="user_data"
                    )
                
                logger.info(f"File uploaded to OpenAI: {file.id}")
                
                # Guardar el file_id de OpenAI
                invoice_parse.openai_file_id = file.id
                invoice_parse.save(update_fields=["openai_file_id"])
                
                # 2) Pedir a GPT-4 Vision que extraiga las tablas como CSV
                # Leer el PDF como bytes para enviarlo
                with open(tmp_path, "rb") as pdf_file:
                    pdf_bytes = pdf_file.read()
                    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Eres un extractor de líneas de factura. Analiza este PDF y devuélveme SOLO un CSV válido con estos encabezados:\n"
                                        "codigo,cajas,uc,iva,articulo,udes,unidad,precio,precio_iva,importe,contenedor\n"
                                        "\n"
                                        "Instrucciones:\n"
                                        "- Extrae TODAS las líneas de productos de la factura\n"
                                        "- Si hay varios 'Contenedor:', incluye la columna 'contenedor' para cada línea\n"
                                        "- Usa punto (.) como separador decimal, no coma\n"
                                        "- No incluyas texto adicional, solo el CSV\n"
                                        "- Primera línea debe ser el encabezado\n"
                                        "- Cada línea posterior es un producto"
                                    )
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:application/pdf;base64,{pdf_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=4096
                )
                
                # 3) Extraer el CSV de la respuesta
                csv_data = ""
                if response.choices and len(response.choices) > 0:
                    message = response.choices[0].message
                    if message.content:
                        csv_data = message.content.strip()
                        
                        # Limpiar el CSV si viene con marcadores de código
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
                
                if not csv_data:
                    logger.error("Could not extract CSV from OpenAI response")
                    invoice_parse.status = InvoiceParse.Status.FAILED
                    invoice_parse.error_message = "No se pudo extraer CSV del modelo."
                    invoice_parse.save()
                    return Response(
                        {"detail": "No se pudo extraer CSV del modelo."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # 4) Guardar CSV y parsear líneas
                invoice_parse.csv_data = csv_data
                invoice_parse.save(update_fields=["csv_data"])
                
                # 5) Parsear CSV y crear líneas
                self._parse_and_save_lines(csv_data, invoice_parse)
                
                # 6) Marcar como completado
                invoice_parse.status = InvoiceParse.Status.COMPLETED
                invoice_parse.completed_at = timezone.now()
                invoice_parse.save(update_fields=["status", "completed_at"])
                
                logger.info(f"Invoice parse completed: {invoice_parse.id} with {invoice_parse.line_count} lines")
                
                # 7) Devolver el CSV
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
            # Leer CSV
            csv_file = io.StringIO(csv_data)
            reader = csv.DictReader(csv_file)
            
            lines_to_create = []
            line_number = 1
            
            for row in reader:
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
                    iva=safe_decimal(row.get("iva")),
                    articulo=row.get("articulo", "")[:255],
                    udes=safe_decimal(row.get("udes")),
                    unidad=row.get("unidad", "")[:20],
                    precio=safe_decimal(row.get("precio")),
                    precio_iva=safe_decimal(row.get("precio_iva")),
                    importe=safe_decimal(row.get("importe")),
                    contenedor=row.get("contenedor", "")[:100],
                    raw_data=row
                )
                lines_to_create.append(line)
                line_number += 1
            
            # Crear todas las líneas en una sola operación
            if lines_to_create:
                InvoiceLineItem.objects.bulk_create(lines_to_create)
                logger.info(f"Created {len(lines_to_create)} invoice lines for parse {invoice_parse.id}")
        
        except Exception as e:
            logger.exception(f"Error parsing CSV lines: {str(e)}")
            # No lanzar excepción, solo registrar el error
            # El CSV ya está guardado y puede ser revisado manualmente
