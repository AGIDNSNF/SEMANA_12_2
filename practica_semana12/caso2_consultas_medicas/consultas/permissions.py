"""Autorización del caso 2: roles, permisos y acceso a historiales.

La comprobación de propiedad se realiza siempre en el servidor.
"""
import logging
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import Cita, Consulta
from .horarios import ESTADOS_CITA_ACTIVOS

logger = logging.getLogger("consultas")

GRUPO_ADMIN = "Admins"
GRUPO_MEDICO = "Médicos"
GRUPO_RECEPCION = "Recepcionistas"
GRUPO_PACIENTE = "Pacientes"


def _tiene_relacion(user, nombre):
    try:
        return getattr(user, nombre) is not None
    except Exception:
        return False


def es_administrador(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name=GRUPO_ADMIN).exists())


def es_medico(user):
    return user.is_authenticated and _tiene_relacion(user, "medico")


def es_recepcionista(user):
    return user.is_authenticated and user.groups.filter(name=GRUPO_RECEPCION).exists()


def es_paciente(user):
    return user.is_authenticated and _tiene_relacion(user, "paciente")


def rol_principal(user):
    if not user.is_authenticated:
        return None
    if es_administrador(user):
        return GRUPO_ADMIN
    if es_medico(user):
        return GRUPO_MEDICO
    if es_recepcionista(user):
        return GRUPO_RECEPCION
    if es_paciente(user):
        return GRUPO_PACIENTE
    return "Sin rol"


def permiso_requerido(permiso):
    """Exige login + permiso; el 403 lo audita AuditoriaMedicaMiddleware."""

    def decorador(vista):
        @wraps(vista)
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser or request.user.has_perm(permiso):
                return vista(request, *args, **kwargs)
            logger.warning(
                "Acceso denegado usuario=%s ruta=%s permiso=%s",
                getattr(request.user, "pk", None), request.path, permiso,
            )
            raise PermissionDenied

        return login_required(wrapper)

    return decorador


def medico_de(user):
    try:
        return user.medico
    except Exception:
        return None


def paciente_de(user):
    try:
        return user.paciente
    except Exception:
        return None


def puede_ver_historial(user, paciente) -> bool:
    """Paciente dueño, admins o médico con relación asistencial autorizada."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or es_administrador(user):
        return True
    paciente_propio = paciente_de(user)
    if paciente_propio is not None:
        return paciente_propio.pk == paciente.pk
    medico = medico_de(user)
    if medico is not None:
        if not user.has_perm("consultas.ver_historial_clinico"):
            return False
        # Relación asistencial: cita confirmada/completada o consulta previa.
        return (
            Cita.objects.filter(
                medico=medico, paciente=paciente, estado__in=(Cita.Estado.CONFIRMADA, Cita.Estado.COMPLETADA)
            ).exists()
            or Consulta.objects.filter(medico=medico, cita__paciente=paciente).exists()
        )
    return False


def puede_agendar_para(user, paciente=None) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser or es_administrador(user) or es_recepcionista(user):
        return True
    propio = paciente_de(user)
    if propio is not None:
        return paciente is None or propio.pk == paciente.pk
    return False


def puede_cancelar_cita(user, cita) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser or es_administrador(user):
        return cita.es_activa
    if es_recepcionista(user):
        return cita.es_activa and user.has_perm("consultas.cancelar_cita")
    propio = paciente_de(user)
    if propio is not None:
        return cita.paciente_id == propio.pk and cita.es_activa
    medico = medico_de(user)
    if medico is not None:
        return cita.medico_id == medico.pk and cita.es_activa
    return False


def puede_ver_cita(user, cita) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser or es_administrador(user) or es_recepcionista(user):
        return True
    propio = paciente_de(user)
    if propio is not None:
        return cita.paciente_id == propio.pk
    medico = medico_de(user)
    if medico is not None:
        return cita.medico_id == medico.pk
    return False


def medico_tiene_cita_con(medico, paciente) -> bool:
    return Cita.objects.filter(
        medico=medico, paciente=paciente, estado__in=ESTADOS_CITA_ACTIVOS
    ).exists()
