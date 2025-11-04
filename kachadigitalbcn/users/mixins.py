# -*- coding: utf-8 -*-
"""
Mixins y utilidades para multi-tenancy basado en organizaciones.
"""
from django.core.exceptions import PermissionDenied
from rest_framework import serializers


class OrganizationQuerySetMixin:
    
    organization_field_path = None  # Sobreescribir en subclases si es necesario
    
    def get_queryset(self):
        """Filtra el queryset por la organización del usuario autenticado."""
        from django.db.models import Q
        
        queryset = super().get_queryset()
        
        # Si el usuario no está autenticado, retornar queryset vacío
        if not self.request.user.is_authenticated:
            return queryset.none()
        
        # Si el usuario es superadmin, puede ver todo
        if self.request.user.is_superuser:
            return queryset
        
        # Filtrar por organización del usuario
        if hasattr(self.request.user, 'organization') and self.request.user.organization:
            # Determinar el path del campo organization
            if self.organization_field_path:
                # Usar path personalizado (para relaciones anidadas)
                filter_kwargs = {self.organization_field_path: self.request.user.organization}
                return queryset.filter(**filter_kwargs)
            elif hasattr(queryset.model, 'organization'):
                # Modelo tiene campo organization directo
                return queryset.filter(organization=self.request.user.organization)
            elif hasattr(queryset.model, 'market'):
                # Intentar a través de market (común en este proyecto)
                return queryset.filter(market__organization=self.request.user.organization)
        
        # Si no tiene organización o el modelo no tiene el campo, retornar vacío
        return queryset.none()


class OrganizationSerializerMixin(serializers.Serializer):
    """
    Mixin para Serializers que asigna automáticamente la organización del usuario.
    
    Uso:
        class MySerializer(OrganizationSerializerMixin, serializers.ModelSerializer):
            class Meta:
                model = MyModel
                fields = ['name', 'organization', ...]
    """
    
    def create(self, validated_data):
        """Asigna automáticamente la organización del usuario si no está presente."""
        user = self.context['request'].user
        
        # Si el modelo tiene campo organization y no se proporcionó
        if hasattr(self.Meta.model, 'organization') and 'organization' not in validated_data:
            if hasattr(user, 'organization') and user.organization:
                validated_data['organization'] = user.organization
        
        return super().create(validated_data)
    
    def validate(self, attrs):
        """Valida que no se intente crear objetos en otra organización."""
        user = self.context['request'].user
        
        # Si se proporciona organization explícitamente, validar que sea la del usuario
        if 'organization' in attrs:
            if not user.is_superuser:
                if hasattr(user, 'organization') and user.organization:
                    if attrs['organization'] != user.organization:
                        raise serializers.ValidationError(
                            "No puedes crear objetos en otra organización"
                        )
        
        return super().validate(attrs)


class OrganizationPermissionMixin:
    """
    Mixin para verificar permisos basados en organización.
    
    Uso:
        class MyViewSet(OrganizationPermissionMixin, ModelViewSet):
            ...
    """
    
    def check_organization_permission(self, obj):
        """
        Verifica que el usuario tenga permiso para acceder al objeto.
        Lanza PermissionDenied si no tiene permiso.
        """
        user = self.request.user
        
        # Superusers pueden acceder a todo
        if user.is_superuser:
            return True
        
        # Verificar que el objeto pertenezca a la organización del usuario
        if hasattr(obj, 'organization'):
            if hasattr(user, 'organization') and user.organization:
                if obj.organization != user.organization:
                    raise PermissionDenied("No tienes permiso para acceder a este recurso")
                return True
        
        # Si no hay forma de verificar, denegar por seguridad
        raise PermissionDenied("No tienes permiso para acceder a este recurso")
    
    def perform_create(self, serializer):
        """Asigna la organización al crear."""
        user = self.request.user
        
        # Si el modelo tiene organization y el usuario tiene organización
        if hasattr(serializer.Meta.model, 'organization'):
            if hasattr(user, 'organization') and user.organization:
                serializer.save(organization=user.organization)
            else:
                # Usuario sin organización no puede crear recursos
                raise PermissionDenied("Tu usuario no tiene una organización asignada")
        else:
            serializer.save()
    
    def perform_update(self, serializer):
        """Verifica permisos antes de actualizar."""
        self.check_organization_permission(serializer.instance)
        serializer.save()
    
    def perform_destroy(self, instance):
        """Verifica permisos antes de eliminar."""
        self.check_organization_permission(instance)
        instance.delete()


def get_user_organization(user):
    """
    Obtiene la organización del usuario.
    
    Args:
        user: Usuario de Django
    
    Returns:
        Organization o None
    """
    if not user or not user.is_authenticated:
        return None
    
    if hasattr(user, 'organization'):
        return user.organization
    
    return None


def filter_by_organization(queryset, user):
    """
    Filtra un queryset por la organización del usuario.
    
    Args:
        queryset: QuerySet de Django
        user: Usuario de Django
    
    Returns:
        QuerySet filtrado
    """
    # Superusers ven todo
    if user.is_superuser:
        return queryset
    
    organization = get_user_organization(user)
    
    if organization and hasattr(queryset.model, 'organization'):
        return queryset.filter(organization=organization)
    
    return queryset.none()
