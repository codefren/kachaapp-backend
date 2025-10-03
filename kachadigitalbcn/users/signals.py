import os
import secrets
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, FtpClient


@receiver(post_save, sender=User)
def create_ftp_client_for_client_group(sender, instance: User, created: bool, **kwargs):
    """
    Al crear un usuario y si pertenece al grupo "Client",
    crear automáticamente su FtpClient, directorio y credenciales.
    """
    if not created:
        return

    # ¿El usuario pertenece al grupo "Client"?
    if not instance.groups.filter(name="Client").exists():
        return

    # Evitar duplicados por si existe
    if hasattr(instance, "ftp_client"):
        return

    # Directorio base para FTP (por defecto junto al script actual)
    base_dir = Path(getattr(settings, "FTP_BASE_DIR", settings.BASE_DIR / "ftp_server"))
    user_dir = base_dir / instance.username
    os.makedirs(user_dir, exist_ok=True)

    # Generar credenciales
    ftp_username = instance.username
    ftp_password = secrets.token_urlsafe(12)

    FtpClient.objects.create(
        user=instance,
        ftp_username=ftp_username,
        ftp_password=ftp_password,
        home_dir=str(user_dir.resolve()),
    )
