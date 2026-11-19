"""Control de acceso por grupos/permisos del caso 1."""
import logging
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import Prestamo

logger = logging.getLogger("prestamos")

GRUPO_ADMIN = "Administrador"
GRUPO_DOCENTE = "Docente"
GRUPO_ASISTENTE = "Asistente"
GRUPO_INVITADO = "Invitado"


def usuario_en_grupo(user, *nombres):
    return user.is_authenticated and user.groups.filter(name__in=nombres).exists()


def es_administrador(user):
    return user.is_authenticated and (user.is_superuser or usuario_en_grupo(user, GRUPO_ADMIN))


def es_docente(user):
    return usuario_en_grupo(user, GRUPO_DOCENTE)


def es_asistente(user):
    return usuario_en_grupo(user, GRUPO_ASISTENTE)


def es_invitado(user):
    return usuario_en_grupo(user, GRUPO_INVITADO)


def rol_principal(user):
    if es_administrador(user):
        return GRUPO_ADMIN
    if es_asistente(user):
        return GRUPO_ASISTENTE
    if es_docente(user):
        return GRUPO_DOCENTE
    if es_invitado(user):
        return GRUPO_INVITADO
    return "Sin rol"


def permiso_requerido(permiso):
    """Exige autenticación + permiso; audita y devuelve 403 si falta."""

    def decorador(vista):
        @wraps(vista)
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser or request.user.has_perm(permiso):
                return vista(request, *args, **kwargs)
            # El registro en base de datos lo realiza AuditoriaMiddleware al
            # detectar la respuesta 403 (así se evita duplicar eventos).
            logger.warning(
                "Acceso denegado usuario=%s ruta=%s permiso=%s",
                request.user.pk, request.path, permiso,
            )
            raise PermissionDenied

        return login_required(wrapper)

    return decorador


def puede_ver_prestamo(user, prestamo):
    """Administrador/asistente ven todo; un docente solo lo propio."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or es_administrador(user) or es_asistente(user):
        return True
    return prestamo.docente_id == user.pk


def puede_gestionar_prestamo(user):
    return user.is_superuser or user.has_perm("prestamos.change_prestamo")
