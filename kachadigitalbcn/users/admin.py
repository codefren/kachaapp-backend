from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from market.models import LoginHistory
from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import User, FtpClient, Organization

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("name", "email")}),
        (
            _("Organization & Role"),
            {
                "fields": (
                    "organization",
                    "role",
                ),
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    list_display = ["username", "name", "email", "organization", "role", "is_active", "is_superuser"]
    list_filter = ["is_active", "is_staff", "is_superuser", "organization", "role"]
    search_fields = ["username", "name", "email"]
    autocomplete_fields = ["organization"]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Admin para gestionar organizaciones."""
    list_display = (
        "name",
        "slug",
        "is_active",
        "user_count",
        "market_count",
        "max_users",
        "max_markets",
        "created_at",
    )
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "slug", "contact_email")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at", "user_count", "market_count")
    
    fieldsets = (
        (_("Información Básica"), {
            "fields": ("name", "slug", "is_active")
        }),
        (_("Contacto"), {
            "fields": ("contact_email", "contact_phone")
        }),
        (_("Límites"), {
            "fields": ("max_users", "max_markets")
        }),
        (_("Estadísticas"), {
            "fields": ("user_count", "market_count"),
            "classes": ("collapse",),
        }),
        (_("Fechas"), {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
    
    def user_count(self, obj):
        """Muestra el conteo de usuarios de la organización."""
        return f"{obj.get_user_count()} / {obj.max_users}"
    user_count.short_description = "Usuarios"
    
    def market_count(self, obj):
        """Muestra el conteo de mercados de la organización."""
        return f"{obj.get_market_count()} / {obj.max_markets}"
    market_count.short_description = "Mercados"


@admin.register(FtpClient)
class FtpClientAdmin(admin.ModelAdmin):
    list_display = ("ftp_username", "user", "home_dir", "is_active", "created_at")
    search_fields = ("ftp_username", "user__username")
    list_filter = ("is_active",)


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    """Admin para ver el historial de logins y refresh tokens."""
    list_display = (
        "user",
        "market",
        "event_type",
        "timestamp",
        "latitude",
        "longitude",
    )
    list_filter = ("event_type", "timestamp", "market")
    search_fields = ("user__username", "user__email", "market__name")
    readonly_fields = ("user", "market", "latitude", "longitude", "event_type", "timestamp")
    date_hierarchy = "timestamp"
    
    def has_add_permission(self, request):
        """No permitir agregar manualmente, solo se crean automáticamente."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Solo lectura."""
        return False


@admin.register(OutstandingToken)
class OutstandingTokenAdmin(admin.ModelAdmin):
    """Admin para ver tokens JWT activos."""
    list_display = (
        "user",
        "jti",
        "token_type",
        "created_at",
        "expires_at",
        "is_blacklisted",
    )
    list_filter = ("created_at", "expires_at")
    search_fields = ("user__username", "user__email", "jti")
    readonly_fields = ("user", "jti", "token", "created_at", "expires_at")
    date_hierarchy = "created_at"
    
    def is_blacklisted(self, obj):
        """Verifica si el token está en la lista negra."""
        return hasattr(obj, 'blacklistedtoken')
    is_blacklisted.boolean = True
    is_blacklisted.short_description = "Revocado"
    
    def token_type(self, obj):
        """Muestra el tipo de token (access o refresh)."""
        # Los OutstandingToken son generalmente refresh tokens
        return "refresh"
    token_type.short_description = "Tipo"
    
    def has_add_permission(self, request):
        """No permitir agregar manualmente."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Solo lectura."""
        return False


@admin.register(BlacklistedToken)
class BlacklistedTokenAdmin(admin.ModelAdmin):
    """Admin para ver tokens JWT revocados/blacklisted."""
    list_display = (
        "token_user",
        "token_jti",
        "blacklisted_at",
    )
    list_filter = ("blacklisted_at",)
    search_fields = ("token__user__username", "token__user__email", "token__jti")
    readonly_fields = ("token", "blacklisted_at")
    date_hierarchy = "blacklisted_at"
    
    def token_user(self, obj):
        """Muestra el usuario del token."""
        return obj.token.user if obj.token else None
    token_user.short_description = "Usuario"
    
    def token_jti(self, obj):
        """Muestra el JTI del token."""
        return obj.token.jti if obj.token else None
    token_jti.short_description = "JTI"
    
    def has_add_permission(self, request):
        """No permitir agregar manualmente."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Solo lectura."""
        return False
