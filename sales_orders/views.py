from rest_framework import permissions, viewsets

from .models import CustomerOrder, CustomerOrderItem
from .serializers import CustomerOrderSerializer, CustomerOrderItemSerializer


class CustomerOrderViewSet(viewsets.ModelViewSet):
    queryset = (
        CustomerOrder.objects
        .select_related("client", "created_by")
        .prefetch_related("items", "items__product")
        .order_by("-created_at")
    )
    serializer_class = CustomerOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class CustomerOrderItemViewSet(viewsets.ModelViewSet):
    queryset = (
        CustomerOrderItem.objects
        .select_related("order", "product")
        .order_by("-created_at")
    )
    serializer_class = CustomerOrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]
