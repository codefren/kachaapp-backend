from collections.abc import Sequence
from typing import Any

import factory
from factory.django import DjangoModelFactory
from faker import Faker
from django.utils import timezone

from market.models import Market, Refrigerator, TemperatureRecord

fake = Faker()


class MarketFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Market {n}")
    latitude = factory.LazyFunction(lambda: fake.latitude())
    longitude = factory.LazyFunction(lambda: fake.longitude())

    class Meta:
        model = Market


class RefrigeratorFactory(DjangoModelFactory):
    market = factory.SubFactory(MarketFactory)
    name = factory.Sequence(lambda n: f"Fridge {n}")

    class Meta:
        model = Refrigerator


class TemperatureRecordFactory(DjangoModelFactory):
    refrigerator = factory.SubFactory(RefrigeratorFactory)
    date = factory.LazyFunction(lambda: timezone.localdate())
    temperature = 4.0

    class Meta:
        model = TemperatureRecord
        django_get_or_create = ("refrigerator", "date")
