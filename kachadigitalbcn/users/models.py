from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CharField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


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

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"username": self.username})


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
