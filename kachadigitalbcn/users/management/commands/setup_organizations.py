# -*- coding: utf-8 -*-
"""
Comando para configurar organizaciones y asignar datos existentes.

Uso:
    python manage.py setup_organizations --create-default
    python manage.py setup_organizations --assign-to-default
    python manage.py setup_organizations --org-name "Mi Empresa" --org-slug "mi-empresa"
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify


class Command(BaseCommand):
    help = 'Configura organizaciones y asigna datos existentes a una organización por defecto'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-default',
            action='store_true',
            help='Crear una organización por defecto si no existe'
        )
        
        parser.add_argument(
            '--assign-to-default',
            action='store_true',
            help='Asignar todos los datos sin organización a la organización por defecto'
        )
        
        parser.add_argument(
            '--org-name',
            type=str,
            default='Organización Principal',
            help='Nombre de la organización (default: Organización Principal)'
        )
        
        parser.add_argument(
            '--org-slug',
            type=str,
            default=None,
            help='Slug de la organización (default: generado automáticamente)'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from kachadigitalbcn.users.models import Organization, User
        from market.models import Market
        from proveedores.models import Provider, Product
        
        org_name = options['org_name']
        org_slug = options['org_slug'] or slugify(org_name)
        
        # 1. Crear organización por defecto si se solicita
        if options['create_default']:
            org, created = Organization.objects.get_or_create(
                slug=org_slug,
                defaults={
                    'name': org_name,
                    'is_active': True,
                    'max_users': 100,
                    'max_markets': 200,
                }
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Organización creada: {org.name} (slug: {org.slug})')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'⚠️  Organización ya existe: {org.name}')
                )
        else:
            # Obtener la organización por defecto
            try:
                org = Organization.objects.get(slug=org_slug)
                self.stdout.write(f'📦 Usando organización: {org.name}')
            except Organization.DoesNotExist:
                raise CommandError(
                    f'No existe organización con slug "{org_slug}". '
                    f'Usa --create-default para crearla.'
                )
        
        # 2. Asignar datos sin organización a la organización por defecto
        if options['assign_to_default']:
            self.stdout.write('\n' + '='*70)
            self.stdout.write('ASIGNANDO DATOS A LA ORGANIZACIÓN POR DEFECTO')
            self.stdout.write('='*70 + '\n')
            
            # Asignar usuarios
            users_updated = User.objects.filter(organization__isnull=True).update(
                organization=org,
                role=User.Role.STORE_USER  # Rol por defecto
            )
            self.stdout.write(f'👥 Usuarios asignados: {users_updated}')
            
            # Asignar mercados
            markets_updated = Market.objects.filter(organization__isnull=True).update(
                organization=org
            )
            self.stdout.write(f'🏪 Mercados asignados: {markets_updated}')
            
            # Asignar proveedores
            providers_updated = Provider.objects.filter(organization__isnull=True).update(
                organization=org
            )
            self.stdout.write(f'🚚 Proveedores asignados: {providers_updated}')
            
            # Asignar productos
            products_updated = Product.objects.filter(organization__isnull=True).update(
                organization=org
            )
            self.stdout.write(f'📦 Productos asignados: {products_updated}')
            
            self.stdout.write('\n' + '='*70)
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Proceso completado. Todos los datos asignados a: {org.name}'
                )
            )
            self.stdout.write('='*70 + '\n')
        
        # 3. Mostrar estadísticas
        self.stdout.write('\n📊 ESTADÍSTICAS DE LA ORGANIZACIÓN:\n')
        self.stdout.write(f'   Nombre: {org.name}')
        self.stdout.write(f'   Slug: {org.slug}')
        self.stdout.write(f'   Activa: {"Sí" if org.is_active else "No"}')
        self.stdout.write(f'   Usuarios: {org.get_user_count()} / {org.max_users}')
        self.stdout.write(f'   Mercados: {org.get_market_count()} / {org.max_markets}')
        self.stdout.write(f'   Proveedores: {org.providers.count()}')
        self.stdout.write(f'   Productos: {org.products.count()}')
        
        self.stdout.write('\n' + self.style.SUCCESS('✅ Comando ejecutado exitosamente!\n'))
