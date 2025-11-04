from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CharField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


class Organization(models.Model):
    """Organización principal que agrupa usuarios y datos (Multi-tenancy).
    
    Cada organización representa un cliente/empresa independiente.
    Todos los datos (mercados, proveedores, productos, etc.) pertenecen a una organización.
    """
    
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Nombre de la organización"
    )
    slug = models.SlugField(
        max_length=255,
        unique=True,
        help_text="Identificador único de URL para la organización"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Si la organización está activa"
    )
    
    # Información de contacto
    contact_email = models.EmailField(
        blank=True,
        default='',
        help_text="Email de contacto principal"
    )
    contact_phone = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text="Teléfono de contacto"
    )
    
    # Límites y configuración
    max_users = models.PositiveIntegerField(
        default=50,
        help_text="Número máximo de usuarios permitidos"
    )
    max_markets = models.PositiveIntegerField(
        default=100,
        help_text="Número máximo de mercados permitidos"
    )
    
    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        indexes = [
            models.Index(fields=['slug'], name='idx_org_slug'),
            models.Index(fields=['is_active'], name='idx_org_active'),
        ]
    
    def __str__(self):
        return self.name
    
    def clean(self):
        """Validaciones de negocio."""
        super().clean()
        # Validar límites
        if self.max_users < 1:
            raise ValidationError({"max_users": "Debe ser al menos 1"})
        if self.max_markets < 1:
            raise ValidationError({"max_markets": "Debe ser al menos 1"})
    
    def get_user_count(self):
        """Retorna el número de usuarios activos en la organización."""
        return self.users.filter(is_active=True).count()
    
    def get_market_count(self):
        """Retorna el número de mercados en la organización."""
        return self.markets.count()
    
    def can_add_user(self):
        """Verifica si se puede agregar un nuevo usuario."""
        return self.get_user_count() < self.max_users
    
    def can_add_market(self):
        """Verifica si se puede agregar un nuevo mercado."""
        return self.get_market_count() < self.max_markets


class User(AbstractUser):
    """
    Default custom user model for kachadigitalbcn.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    name = CharField(_("Name of User"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    
    # Relación con organización (Multi-tenancy)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="users",
        null=True,  # Temporal para migración
        blank=True,
        help_text="Organización a la que pertenece el usuario"
    )
    
    # Rol dentro de la organización
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrador de organización"
        MANAGER = "MANAGER", "Gerente"
        STORE_USER = "STORE_USER", "Usuario de tienda"
        VIEWER = "VIEWER", "Solo lectura"
    
    role = models.CharField(
        max_length=15,
        choices=Role.choices,
        default=Role.STORE_USER,
        help_text="Rol del usuario dentro de su organización"
    )

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"username": self.username})
    
    def is_org_admin(self) -> bool:
        """Verifica si el usuario es administrador de su organización."""
        return self.role == self.Role.ADMIN
    
    def can_manage_users(self) -> bool:
        """Verifica si el usuario puede gestionar otros usuarios."""
        return self.role in [self.Role.ADMIN, self.Role.MANAGER]


class FtpClient(models.Model):
    """Modelo que almacena las credenciales y directorio del usuario FTP.

    Nota: Por simplicidad, la contraseña se guarda en texto plano ya que
    pyftpdlib.DummyAuthorizer requiere la contraseña sin hash. Considera
    en el futuro usar un authorizer personalizado o cifrado a nivel de base de datos.
    """

    user = models.OneToOneField(
        "users.User", on_delete=models.CASCADE, related_name="ftp_client"
    )
    ftp_username = models.CharField(max_length=150, unique=True)
    ftp_password = models.CharField(max_length=255)
    home_dir = models.CharField(max_length=500)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "FTP Client"
        verbose_name_plural = "FTP Clients"

    def __str__(self) -> str:  # pragma: no cover - repr simple
        return f"FTP({self.ftp_username}) -> {self.home_dir}"
