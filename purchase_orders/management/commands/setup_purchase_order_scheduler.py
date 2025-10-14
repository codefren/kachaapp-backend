"""Comando para configurar la tarea periódica de actualización de órdenes de compra."""

from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json


class Command(BaseCommand):
    help = 'Configura la tarea periódica para actualizar órdenes de compra expiradas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=15,
            help='Intervalo en minutos para ejecutar la tarea (default: 15)'
        )
        parser.add_argument(
            '--disable',
            action='store_true',
            help='Deshabilitar la tarea periódica'
        )

    def handle(self, *args, **options):
        task_name = 'update_expired_purchase_orders'
        
        if options['disable']:
            # Deshabilitar tarea existente
            try:
                task = PeriodicTask.objects.get(name=task_name)
                task.enabled = False
                task.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Tarea "{task_name}" deshabilitada')
                )
            except PeriodicTask.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'Tarea "{task_name}" no existe')
                )
            return

        interval_minutes = options['interval']
        
        # Crear o actualizar el schedule de intervalo
        schedule, created = IntervalSchedule.objects.get_or_create(
            every=interval_minutes,
            period=IntervalSchedule.MINUTES,
        )
        
        if created:
            self.stdout.write(f'Creado nuevo schedule: cada {interval_minutes} minutos')
        else:
            self.stdout.write(f'Usando schedule existente: cada {interval_minutes} minutos')

        # Crear o actualizar la tarea periódica
        task, created = PeriodicTask.objects.get_or_create(
            name=task_name,
            defaults={
                'task': 'purchase_orders.tasks.update_expired_purchase_orders',
                'interval': schedule,
                'enabled': True,
                'description': 'Actualiza automáticamente órdenes de compra expiradas de DRAFT/PLACED a RECEIVED'
            }
        )
        
        if not created:
            # Actualizar tarea existente
            task.task = 'purchase_orders.tasks.update_expired_purchase_orders'
            task.interval = schedule
            task.enabled = True
            task.save()
            self.stdout.write(
                self.style.SUCCESS(f'Tarea "{task_name}" actualizada')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Tarea "{task_name}" creada')
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Configuración completada:\n'
                f'  - Tarea: {task.task}\n'
                f'  - Intervalo: cada {interval_minutes} minutos\n'
                f'  - Estado: {"Habilitada" if task.enabled else "Deshabilitada"}\n'
                f'  - Próxima ejecución: {task.last_run_at or "Inmediatamente"}'
            )
        )
        
        self.stdout.write(
            self.style.WARNING(
                '\nRECUERDA:\n'
                '1. Ejecutar migraciones si es necesario: python manage.py migrate\n'
                '2. Iniciar Celery worker: celery -A config.celery_app worker -l info\n'
                '3. Iniciar Celery beat: celery -A config.celery_app beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler'
            )
        )
