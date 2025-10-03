import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from market.models import Market, LoginHistory
from received.models import Reception


@pytest.mark.django_db
def test_receptions_list_minimal_returns_only_id_and_image(auth_client, user, purchase_order):
    # Arrange: two markets, user logged into market_a
    market_a = Market.objects.create(name="Market A", latitude=0.0, longitude=0.0)
    market_b = Market.objects.create(name="Market B", latitude=0.0, longitude=0.0)
    LoginHistory.objects.create(
        user=user,
        market=market_a,
        latitude=0.0,
        longitude=0.0,
        event_type=LoginHistory.LOGIN,
        timestamp=timezone.now(),
    )

    # Create receptions on both markets
    r1 = Reception.objects.create(purchase_order=purchase_order, market=market_a, received_by=user,
                                  invoice_image_b64="data:image/jpeg;base64,AAA")
    r2 = Reception.objects.create(purchase_order=purchase_order, market=market_b, received_by=user,
                                  invoice_image_b64="data:image/jpeg;base64,BBB")

    url = reverse("api:reception-list")

    # Act
    resp = auth_client.get(url)

    # Assert
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    # Only receptions from market_a must be listed
    ids = [item["id"] for item in body]
    assert r1.id in ids
    assert r2.id not in ids

    # Each item contains only id and invoice_image_b64
    for item in body:
        assert set(item.keys()) == {"id", "invoice_image_b64"}


@pytest.mark.django_db
def test_reception_patch_update_invoice_fields_and_clean(auth_client, user, purchase_order):
    # Arrange: market and login history
    market = Market.objects.create(name="Main Market", latitude=0.0, longitude=0.0)
    LoginHistory.objects.create(
        user=user,
        market=market,
        latitude=0.0,
        longitude=0.0,
        event_type=LoginHistory.LOGIN,
        timestamp=timezone.now(),
    )

    reception = Reception.objects.create(purchase_order=purchase_order, market=market, received_by=user)

    url_detail = reverse("api:reception-detail", args=[reception.id])

    payload = {
        "invoice_image_b64": "data:image/jpeg;base64,/9j/4AAQSk...",
        "invoice_date": "2025-10-03",
        "invoice_time": "12:34:56",
        "invoice_total": "1234.50",
    }

    # Act: update
    resp = auth_client.patch(url_detail, payload, format="json")

    # Assert
    assert resp.status_code == status.HTTP_200_OK

    reception.refresh_from_db()
    assert reception.invoice_image_b64.startswith("data:image/jpeg;base64,")
    assert str(reception.invoice_date) == "2025-10-03"
    assert str(reception.invoice_time) == "12:34:56"
    assert str(reception.invoice_total) == "1234.50"

    # Act: clean fields with empty strings
    resp2 = auth_client.patch(url_detail, {
        "invoice_image_b64": "",
        "invoice_date": "",
        "invoice_time": "",
        "invoice_total": "",
    }, format="json")

    assert resp2.status_code == status.HTTP_200_OK

    reception.refresh_from_db()
    assert reception.invoice_image_b64 == ""
    assert reception.invoice_date is None
    assert reception.invoice_time is None
    assert reception.invoice_total is None


@pytest.mark.django_db
@pytest.mark.parametrize("bad_date", ["2025-13-01", "2025-12-32", "not-a-date"]) 
def test_reception_patch_rejects_bad_date(auth_client, user, purchase_order, bad_date):
    market = Market.objects.create(name="M1", latitude=0.0, longitude=0.0)
    LoginHistory.objects.create(
        user=user,
        market=market,
        latitude=0.0,
        longitude=0.0,
        event_type=LoginHistory.LOGIN,
        timestamp=timezone.now(),
    )
    reception = Reception.objects.create(purchase_order=purchase_order, market=market, received_by=user)
    url_detail = reverse("api:reception-detail", args=[reception.id])

    resp = auth_client.patch(url_detail, {"invoice_date": bad_date}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "invoice_date" in resp.json()["detail"].lower()


@pytest.mark.django_db
@pytest.mark.parametrize("bad_time", ["25:00:00", "12:60:00", "not-a-time"]) 
def test_reception_patch_rejects_bad_time(auth_client, user, purchase_order, bad_time):
    market = Market.objects.create(name="M1", latitude=0.0, longitude=0.0)
    LoginHistory.objects.create(
        user=user,
        market=market,
        latitude=0.0,
        longitude=0.0,
        event_type=LoginHistory.LOGIN,
        timestamp=timezone.now(),
    )
    reception = Reception.objects.create(purchase_order=purchase_order, market=market, received_by=user)
    url_detail = reverse("api:reception-detail", args=[reception.id])

    resp = auth_client.patch(url_detail, {"invoice_time": bad_time}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "invoice_time" in resp.json()["detail"].lower()


@pytest.mark.django_db
@pytest.mark.parametrize("bad_total", ["-1", -5, "abc"]) 
def test_reception_patch_rejects_bad_total(auth_client, user, purchase_order, bad_total):
    market = Market.objects.create(name="M1", latitude=0.0, longitude=0.0)
    LoginHistory.objects.create(
        user=user,
        market=market,
        latitude=0.0,
        longitude=0.0,
        event_type=LoginHistory.LOGIN,
        timestamp=timezone.now(),
    )
    reception = Reception.objects.create(purchase_order=purchase_order, market=market, received_by=user)
    url_detail = reverse("api:reception-detail", args=[reception.id])

    resp = auth_client.patch(url_detail, {"invoice_total": bad_total}, format="json")

    # '-1' and -5 should fail by range, 'abc' should fail by type/format
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "invoice_total" in resp.json()["detail"].lower()
