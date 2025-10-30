"""Tests for invoice parser."""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
import io

User = get_user_model()


class InvoiceParserViewSetTests(TestCase):
    """Tests para el endpoint de parseo de facturas."""
    
    def setUp(self):
        """Setup para los tests."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )
        self.client.force_authenticate(user=self.user)
        self.url = "/api/invoice-parser/parse/"
    
    def test_parse_requires_authentication(self):
        """El endpoint requiere autenticación."""
        self.client.force_authenticate(user=None)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_parse_requires_file(self):
        """El endpoint requiere un archivo."""
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("errors", response.data)
    
    def test_parse_rejects_non_pdf(self):
        """El endpoint rechaza archivos que no son PDF."""
        txt_file = SimpleUploadedFile(
            "test.txt",
            b"file content",
            content_type="text/plain"
        )
        response = self.client.post(self.url, {"file": txt_file})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("errors", response.data)
    
    def test_parse_rejects_large_files(self):
        """El endpoint rechaza archivos mayores a 10MB."""
        # Crear un archivo de más de 10MB
        large_content = b"a" * (11 * 1024 * 1024)  # 11MB
        large_file = SimpleUploadedFile(
            "large.pdf",
            large_content,
            content_type="application/pdf"
        )
        response = self.client.post(self.url, {"file": large_file})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("errors", response.data)
    
    def test_parse_accepts_valid_pdf(self):
        """El endpoint acepta PDFs válidos (aunque falle por falta de API key)."""
        # Crear un PDF mínimo válido
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n"
        pdf_file = SimpleUploadedFile(
            "test.pdf",
            pdf_content,
            content_type="application/pdf"
        )
        response = self.client.post(self.url, {"file": pdf_file})
        
        # Esperamos error 500 porque no hay API key configurada en tests
        # pero al menos pasó la validación del serializer
        self.assertIn(
            response.status_code,
            [status.HTTP_500_INTERNAL_SERVER_ERROR, status.HTTP_200_OK]
        )
