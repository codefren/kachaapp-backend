from rest_framework.permissions import BasePermission


class IsMasterUser(BasePermission):
    """
    Permite acceso solo a usuarios MASTER.
    """

    message = "No tienes permisos para acceder a este recurso."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, "can_access_master")
            and request.user.can_access_master()
        )
