import pytest
from rest_framework import status
from django.utils import timezone
from datetime import datetime, timedelta

from market.models import Market, LoginHistory
from received.models import Reception


@pytest.mark.django_db
def test_receptions_completed_requires_login_history(auth_client, user, purchase_order):
    # Sin LoginHistory => 400
    url = "/api/receptions/completed/"
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "no market" in res.data["detail"].lower()


@pytest.mark.django_db
def test_receptions_completed_filters_by_market_status_and_date(auth_client, user, purchase_order):
    # Arrange: dos markets, el usuario está en mkt_a
    mkt_a = Market.objects.create(name="MKT A", latitude=41.0, longitude=2.0)
    mkt_b = Market.objects.create(name="MKT B", latitude=41.5, longitude=2.1)

    LoginHistory.objects.create(
        user=user,
        market=mkt_a,
        latitude=mkt_a.latitude,
        longitude=mkt_a.longitude,
        event_type=LoginHistory.LOGIN,
    )

    # Fechas
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    # Crear recepciones en distintos estados/markets
    r1 = Reception.objects.create(purchase_order=purchase_order, market=mkt_a, received_by=user, status=Reception.Status.COMPLETED)
    r2 = Reception.objects.create(purchase_order=purchase_order, market=mkt_a, received_by=user, status=Reception.Status.DRAFT)
    r3 = Reception.objects.create(purchase_order=purchase_order, market=mkt_b, received_by=user, status=Reception.Status.COMPLETED)
    r4 = Reception.objects.create(purchase_order=purchase_order, market=mkt_a, received_by=user, status=Reception.Status.COMPLETED)

    # Ajustar created_at de r1 a today y r4 a yesterday para probar el filtro de fecha
    Reception.objects.filter(id=r1.id).update(created_at=datetime.combine(today, datetime.min.time(), tzinfo=timezone.get_current_timezone()))
    Reception.objects.filter(id=r4.id).update(created_at=datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.get_current_timezone()))

    url = "/api/receptions/completed/"

    # Act 1: sin fecha => solo COMPLETED del market del usuario (mkt_a) => r1 y r4
    res = auth_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    ids = {item["id"] for item in res.data}
    assert r1.id in ids
    assert r4.id in ids
    assert r2.id not in ids  # DRAFT
    assert r3.id not in ids  # otro market

    # Act 2: con fecha == today => solo r1
    res2 = auth_client.get(url + f"?date={today.isoformat()}")
    assert res2.status_code == status.HTTP_200_OK
    ids2 = {item["id"] for item in res2.data}
    assert ids2 == {r1.id}

    # Act 3: con fecha == yesterday => solo r4
    res3 = auth_client.get(url + f"?date={yesterday.isoformat()}")
    assert res3.status_code == status.HTTP_200_OK
    ids3 = {item["id"] for item in res3.data}
    assert ids3 == {r4.id}
