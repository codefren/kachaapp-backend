"""Comando para verificar que las tareas de Celery estén registradas."""

from django.core.management.base import BaseCommand
from config.celery_app import app


class Command(BaseCommand):
    """Comando para verificar el registro de tareas de Celery."""
    
    help = "Verifica que las tareas de Celery estén registradas correctamente"

    def handle(self, *args, **options):
        """Ejecuta la verificación de tareas."""
        self.stdout.write(self.style.SUCCESS("Verificando tareas registradas en Celery..."))
        
        # Obtener todas las tareas registradas
        registered_tasks = list(app.tasks.keys())
        
        self.stdout.write(f"\nTotal de tareas registradas: {len(registered_tasks)}")
        
        # Filtrar tareas de purchase_orders
        purchase_order_tasks = [
            task for task in registered_tasks 
            if task.startswith('purchase_orders.')
        ]
        
        if purchase_order_tasks:
            self.stdout.write(
                self.style.SUCCESS(f"\n✅ Tareas de purchase_orders encontradas ({len(purchase_order_tasks)}):")
            )
            for task in purchase_order_tasks:
                self.stdout.write(f"  - {task}")
        else:
            self.stdout.write(
                self.style.ERROR("\n❌ No se encontraron tareas de purchase_orders")
            )
        
        # Verificar tareas específicas
        expected_tasks = [
            'purchase_orders.tasks.update_expired_purchase_orders',
            'purchase_orders.tasks.check_single_purchase_order'
        ]
        
        self.stdout.write("\nVerificando tareas específicas:")
        for task_name in expected_tasks:
            if task_name in registered_tasks:
                self.stdout.write(
                    self.style.SUCCESS(f"  ✅ {task_name}")
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"  ❌ {task_name} - NO ENCONTRADA")
                )
        
        # Mostrar todas las tareas si hay pocas
        if len(registered_tasks) <= 20:
            self.stdout.write("\nTodas las tareas registradas:")
            for task in sorted(registered_tasks):
                self.stdout.write(f"  - {task}")
        
        self.stdout.write(self.style.SUCCESS("\nVerificación completada."))
