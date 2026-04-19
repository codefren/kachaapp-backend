from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html

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

    readonly_fields = ("photo_preview",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("name", "email", "photo", "photo_preview")}),
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

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "name",
                    "organization",
                    "role",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )

    list_display = [
        "id",
        "username",
        "name",
        "email",
        "organization",
        "role",
        "is_active",
        "is_staff",
        "is_superuser",
    ]
    list_filter = ["is_active", "is_staff", "is_superuser", "organization", "role"]
    search_fields = ["username", "name", "email"]
    autocomplete_fields = ["organization"]

    def photo_preview(self, obj):
        if obj and obj.photo:
            return format_html(
                '<img src="{}" style="width:60px;height:60px;border-radius:30px;object-fit:cover;border:1px solid #ddd;" />',
                obj.photo.url,
            )
        return "Sin foto"

    photo_preview.short_description = "Vista previa"

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
