"""Tests for invoice image upload functionality."""

import pytest
import tempfile
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status

from received.models import Reception
from purchase_orders.models import PurchaseOrder


def create_test_image(format='JPEG', size=(100, 100), color='red'):
    """Create a test image file for upload testing."""
    image = Image.new('RGB', size, color)
    image_io = BytesIO()
    image.save(image_io, format=format)
    image_io.seek(0)
    return image_io


@pytest.mark.django_db
def test_upload_invoice_image_success(auth_client, purchase_order, market_a, user, user_login_history):
    """Test successful invoice image upload."""
    # Create a reception
    reception = Reception.objects.create(
        purchase_order=purchase_order,
        market=market_a,
        received_by=user
    )
    
    # Create test image
    image_file = create_test_image()
    uploaded_file = SimpleUploadedFile(
        "test_invoice.jpg",
        image_file.getvalue(),
        content_type="image/jpeg"
    )
    
    # Upload invoice image
    url = reverse("api:reception-upload-invoice", args=[reception.id])
    payload = {
        'invoice_image': uploaded_file,
        'invoice_date': '2025-10-23',
        'invoice_time': '14:30:00',
        'invoice_total': '150.75'
    }
    
    response = auth_client.post(url, payload, format='multipart')
    
    assert response.status_code == status.HTTP_200_OK
    
    # Verify response structure
    data = response.json()
    assert 'id' in data
    assert 'invoice_image_url' in data
    assert data['invoice_image_url'] is not None
    assert data['invoice_date'] == '2025-10-23'
    assert data['invoice_time'] == '14:30:00'
    assert data['invoice_total'] == '150.75'
    
    # Verify database
    reception.refresh_from_db()
    assert reception.invoice_image is not None
    assert str(reception.invoice_date) == '2025-10-23'
    assert str(reception.invoice_time) == '14:30:00'
    assert str(reception.invoice_total) == '150.75'


@pytest.mark.django_db
def test_upload_invoice_image_only(auth_client, purchase_order, market_a, user, user_login_history):
    """Test uploading only image without optional fields."""
    # Create a reception
    reception = Reception.objects.create(
        purchase_order=purchase_order,
        market=market_a,
        received_by=user
    )
    
    # Create test image
    image_file = create_test_image()
    uploaded_file = SimpleUploadedFile(
        "test_invoice.jpg",
        image_file.getvalue(),
        content_type="image/jpeg"
    )
    
    # Upload only image
    url = reverse("api:reception-upload-invoice", args=[reception.id])
    payload = {
        'invoice_image': uploaded_file
    }
    
    response = auth_client.post(url, payload, format='multipart')
    
    assert response.status_code == status.HTTP_200_OK
    
    # Verify response
    data = response.json()
    assert data['invoice_image_url'] is not None
    assert data['invoice_date'] is None
    assert data['invoice_time'] is None
    assert data['invoice_total'] is None
    
    # Verify database
    reception.refresh_from_db()
    assert reception.invoice_image is not None


@pytest.mark.django_db
def test_upload_invoice_image_png_format(auth_client, purchase_order, market_a, user, user_login_history):
    """Test uploading PNG image."""
    # Create a reception
    reception = Reception.objects.create(
        purchase_order=purchase_order,
        market=market_a,
        received_by=user
    )
    
    # Create PNG test image
    image_file = create_test_image(format='PNG')
    uploaded_file = SimpleUploadedFile(
        "test_invoice.png",
        image_file.getvalue(),
        content_type="image/png"
    )
    
    # Upload image
    url = reverse("api:reception-upload-invoice", args=[reception.id])
    payload = {
        'invoice_image': uploaded_file,
        'invoice_total': '99.99'
    }
    
    response = auth_client.post(url, payload, format='multipart')
    
    assert response.status_code == status.HTTP_200_OK
    
    # Verify database
    reception.refresh_from_db()
    assert reception.invoice_image is not None
    assert str(reception.invoice_total) == '99.99'


@pytest.mark.django_db
def test_upload_invoice_image_reception_not_found(auth_client):
    """Test upload to non-existent reception."""
    # Create test image
    image_file = create_test_image()
    uploaded_file = SimpleUploadedFile(
        "test_invoice.jpg",
        image_file.getvalue(),
        content_type="image/jpeg"
    )
    
    # Try to upload to non-existent reception
    url = reverse("api:reception-upload-invoice", args=[99999])
    payload = {
        'invoice_image': uploaded_file
    }
    
    response = auth_client.post(url, payload, format='multipart')
    
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()['detail'] == "Reception not found."


@pytest.mark.django_db
def test_upload_invoice_image_wrong_market(auth_client, purchase_order, market_b, user, user_login_history):
    """Test upload to reception from different market."""
    # Create reception in different market
    reception = Reception.objects.create(
        purchase_order=purchase_order,
        market=market_b,  # User belongs to market_a
        received_by=user
    )
    
    # Create test image
    image_file = create_test_image()
    uploaded_file = SimpleUploadedFile(
        "test_invoice.jpg",
        image_file.getvalue(),
        content_type="image/jpeg"
    )
    
    # Try to upload
    url = reverse("api:reception-upload-invoice", args=[reception.id])
    payload = {
        'invoice_image': uploaded_file
    }
    
    response = auth_client.post(url, payload, format='multipart')
    
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()['detail'] == "Reception not available for user's market."


@pytest.mark.django_db
def test_upload_invoice_image_missing_file(auth_client, purchase_order, market_a, user, user_login_history):
    """Test upload without image file."""
    # Create a reception
    reception = Reception.objects.create(
        purchase_order=purchase_order,
        market=market_a,
        received_by=user
    )
    
    # Try to upload without image
    url = reverse("api:reception-upload-invoice", args=[reception.id])
    payload = {
        'invoice_date': '2025-10-23'
    }
    
    response = auth_client.post(url, payload, format='multipart')
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'invoice_image' in response.json()


@pytest.mark.django_db
def test_upload_invoice_image_invalid_date(auth_client, purchase_order, market_a, user, user_login_history):
    """Test upload with invalid date format."""
    # Create a reception
    reception = Reception.objects.create(
        purchase_order=purchase_order,
        market=market_a,
        received_by=user
    )
    
    # Create test image
    image_file = create_test_image()
    uploaded_file = SimpleUploadedFile(
        "test_invoice.jpg",
        image_file.getvalue(),
        content_type="image/jpeg"
    )
    
    # Upload with invalid date
    url = reverse("api:reception-upload-invoice", args=[reception.id])
    payload = {
        'invoice_image': uploaded_file,
        'invoice_date': 'invalid-date'
    }
    
    response = auth_client.post(url, payload, format='multipart')
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'invoice_date' in response.json()


@pytest.mark.django_db
def test_reception_retrieve_with_image_url(auth_client, purchase_order, market_a, user, user_login_history):
    """Test retrieving reception with image URL."""
    # Create reception with image
    reception = Reception.objects.create(
        purchase_order=purchase_order,
        market=market_a,
        received_by=user
    )
    
    # Upload image first
    image_file = create_test_image()
    uploaded_file = SimpleUploadedFile(
        "test_invoice.jpg",
        image_file.getvalue(),
        content_type="image/jpeg"
    )
    
    upload_url = reverse("api:reception-upload-invoice", args=[reception.id])
    upload_payload = {
        'invoice_image': uploaded_file,
        'invoice_date': '2025-10-23',
        'invoice_total': '200.00'
    }
    
    upload_response = auth_client.post(upload_url, upload_payload, format='multipart')
    assert upload_response.status_code == status.HTTP_200_OK
    
    # Now retrieve the reception
    retrieve_url = reverse("api:reception-detail", args=[reception.id])
    response = auth_client.get(retrieve_url)
    
    assert response.status_code == status.HTTP_200_OK
    
    data = response.json()
    assert 'invoice_image_url' in data
    assert data['invoice_image_url'] is not None
    assert data['invoice_image_url'].startswith('http')
    assert data['invoice_date'] == '2025-10-23'
    assert data['invoice_total'] == '200.00'


@pytest.mark.django_db
def test_reception_list_with_image_urls(auth_client, purchase_order, market_a, user, user_login_history):
    """Test listing receptions with image URLs."""
    # Create reception with image
    reception = Reception.objects.create(
        purchase_order=purchase_order,
        market=market_a,
        received_by=user
    )
    
    # Upload image
    image_file = create_test_image()
    uploaded_file = SimpleUploadedFile(
        "test_invoice.jpg",
        image_file.getvalue(),
        content_type="image/jpeg"
    )
    
    upload_url = reverse("api:reception-upload-invoice", args=[reception.id])
    upload_payload = {
        'invoice_image': uploaded_file
    }
    
    upload_response = auth_client.post(upload_url, upload_payload, format='multipart')
    assert upload_response.status_code == status.HTTP_200_OK
    
    # List receptions
    list_url = reverse("api:reception-list")
    response = auth_client.get(list_url)
    
    assert response.status_code == status.HTTP_200_OK
    
    data = response.json()
    assert len(data) >= 1
    
    # Find our reception in the list
    our_reception = next((r for r in data if r['id'] == reception.id), None)
    assert our_reception is not None
    assert 'invoice_image_url' in our_reception
    assert our_reception['invoice_image_url'] is not None
    assert our_reception['invoice_image_url'].startswith('http')


@pytest.mark.django_db
def test_reception_completed_list_with_image_urls(auth_client, purchase_order, market_a, user, user_login_history):
    """Test completed receptions list with image URLs."""
    # Create completed reception with image
    reception = Reception.objects.create(
        purchase_order=purchase_order,
        market=market_a,
        received_by=user,
        status=Reception.Status.COMPLETED
    )
    
    # Upload image
    image_file = create_test_image()
    uploaded_file = SimpleUploadedFile(
        "test_invoice.jpg",
        image_file.getvalue(),
        content_type="image/jpeg"
    )
    
    upload_url = reverse("api:reception-upload-invoice", args=[reception.id])
    upload_payload = {
        'invoice_image': uploaded_file
    }
    
    upload_response = auth_client.post(upload_url, upload_payload, format='multipart')
    assert upload_response.status_code == status.HTTP_200_OK
    
    # List completed receptions
    list_url = reverse("api:reception-completed")
    response = auth_client.get(list_url)
    
    assert response.status_code == status.HTTP_200_OK
    
    data = response.json()
    assert len(data) >= 1
    
    # Find our reception in the list
    our_reception = next((r for r in data if r['id'] == reception.id), None)
    assert our_reception is not None
    assert 'invoice_image_url' in our_reception
    assert our_reception['invoice_image_url'] is not None
    assert our_reception['invoice_image_url'].startswith('http')
