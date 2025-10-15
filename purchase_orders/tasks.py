"""Tareas asíncronas para órdenes de compra."""

import logging
from datetime import datetime, time
from typing import List

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import PurchaseOrder

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def update_expired_purchase_orders(self):
    """
    Tarea asíncrona que verifica y actualiza órdenes de compra expiradas.
    
    Cambia el estado de DRAFT/PLACED a RECEIVED cuando:
    1. El día actual está en order_available_weekdays del proveedor
    2. La hora actual supera order_deadline_time del proveedor
    
    Returns:
        dict: Resumen de la ejecución con contadores y detalles
    """
    logger.info("Iniciando verificación de órdenes de compra expiradas")
    
    # Obtener fecha y hora actuales
    now = timezone.now()
    current_weekday = now.weekday()  # 0=Lunes, 6=Domingo
    current_time = now.time()
    
    logger.info(f"Verificando en día {current_weekday} a las {current_time}")
    
    # Obtener órdenes candidatas (DRAFT o PLACED)
    candidate_orders = PurchaseOrder.objects.filter(
        status__in=[PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.PLACED]
    ).select_related('provider')
    
    logger.info(f"Encontradas {candidate_orders.count()} órdenes candidatas")
    
    updated_orders = []
    skipped_orders = []
    errors = []
    
    for order in candidate_orders:
        try:
            provider = order.provider
            
            # Verificar si el proveedor tiene días configurados
            if not provider.order_available_weekdays:
                skipped_orders.append({
                    'order_id': order.pk,
                    'provider': provider.name,
                    'reason': 'Proveedor sin días configurados'
                })
                logger.warning(f"OC #{order.pk}: Proveedor {provider.name} sin días configurados")
                continue
            
            # Verificar si hoy es un día válido para pedidos
            if current_weekday not in provider.order_available_weekdays:
                skipped_orders.append({
                    'order_id': order.pk,
                    'provider': provider.name,
                    'reason': f'Hoy ({current_weekday}) no es día de pedidos'
                })
                logger.debug(f"OC #{order.pk}: Día {current_weekday} no válido para {provider.name}")
                continue
            
            # Verificar si ya pasó la hora límite
            if current_time <= provider.order_deadline_time:
                skipped_orders.append({
                    'order_id': order.pk,
                    'provider': provider.name,
                    'reason': f'Aún no pasó hora límite ({provider.order_deadline_time})'
                })
                logger.debug(f"OC #{order.pk}: Hora límite {provider.order_deadline_time} no superada")
                continue
            
            # Cambiar estado a RECEIVED
            old_status = order.status
            order.status = PurchaseOrder.Status.RECEIVED
            order.save(update_fields=['status', 'updated_at'])
            
            updated_orders.append({
                'order_id': order.pk,
                'provider': provider.name,
                'old_status': old_status,
                'new_status': order.status,
                'deadline_time': str(provider.order_deadline_time)
            })
            
            logger.info(f"OC #{order.pk} actualizada: {old_status} → {order.status}")
            
        except Exception as e:
            error_msg = f"Error procesando OC #{order.pk}: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg, exc_info=True)
    
    # Resumen de ejecución
    summary = {
        'execution_time': now.isoformat(),
        'current_weekday': current_weekday,
        'current_time': str(current_time),
        'total_candidates': candidate_orders.count(),
        'updated_count': len(updated_orders),
        'skipped_count': len(skipped_orders),
        'error_count': len(errors),
        'updated_orders': updated_orders,
        'skipped_orders': skipped_orders,
        'errors': errors
    }
    
    logger.info(f"Tarea completada: {len(updated_orders)} actualizadas, {len(skipped_orders)} omitidas, {len(errors)} errores")
    
    return summary


@shared_task(bind=True)
def check_single_purchase_order(self, order_id: int):
    """
    Verifica una orden de compra específica para testing.
    
    Args:
        order_id: ID de la orden a verificar
        
    Returns:
        dict: Resultado de la verificación
    """
    try:
        order = PurchaseOrder.objects.select_related('provider').get(pk=order_id)
        
        now = timezone.now()
        current_weekday = now.weekday()
        current_time = now.time()
        
        provider = order.provider
        
        result = {
            'order_id': order_id,
            'current_status': order.status,
            'provider_name': provider.name,
            'current_weekday': current_weekday,
            'current_time': str(current_time),
            'provider_deadline': str(provider.order_deadline_time),
            'provider_weekdays': provider.order_available_weekdays,
            'should_update': False,
            'reason': ''
        }
        
        # Verificar condiciones
        if order.status not in [PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.PLACED]:
            result['reason'] = f'Estado {order.status} no es DRAFT ni PLACED'
            return result
        
        if not provider.order_available_weekdays:
            result['reason'] = 'Proveedor sin días configurados'
            return result
        
        if current_weekday not in provider.order_available_weekdays:
            result['reason'] = f'Día {current_weekday} no está en días válidos {provider.order_available_weekdays}'
            return result
        
        if current_time <= provider.order_deadline_time:
            result['reason'] = f'Hora actual {current_time} <= hora límite {provider.order_deadline_time}'
            return result
        
        result['should_update'] = True
        result['reason'] = 'Todas las condiciones se cumplen para actualizar a RECEIVED'
        
        return result
        
    except PurchaseOrder.DoesNotExist:
        return {
            'order_id': order_id,
            'error': 'Orden no encontrada'
        }
    except Exception as e:
        return {
            'order_id': order_id,
            'error': str(e)
        }
