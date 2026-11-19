"""Autorización del caso 3: roles, alcance por área y aprobaciones."""
import logging
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import Empleado, RegistroAsistencia, Solicitud

logger = logging.getLogger("asistencia")

GRUPO_ADMIN = "Administradores"
GRUPO_RRHH = "Recursos Humanos"
GRUPO_JEFE = "Jefes de área"
GRUPO_EMPLEADO = "Empleados"
GRUPO_CONTADOR = "Contadores"


def _relacion(user, nombre):
    try:
        return getattr(user, nombre)
    except Exception:
        return None


def empleado_de(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return _relacion(user, "empleado")


def es_administrador(user):
    return getattr(user, "is_authenticated", False) and (
        user.is_superuser or user.groups.filter(name=GRUPO_ADMIN).exists()
    )


def es_rrhh(user):
    if not getattr(user, "is_authenticated", False):
        return False
    return user.is_superuser or user.groups.filter(name=GRUPO_RRHH).exists()


def es_jefe(user):
    empleado = empleado_de(user)
    return bool(empleado and (empleado.es_jefe or user.groups.filter(name=GRUPO_JEFE).exists()))


def es_contador(user):
    return getattr(user, "is_authenticated", False) and user.groups.filter(
        name=GRUPO_CONTADOR
    ).exists()


def rol_principal(user):
    if not getattr(user, "is_authenticated", False):
        return None
    if es_administrador(user):
        return "Administrador"
    if es_rrhh(user):
        return "Recursos Humanos"
    if es_jefe(user):
        return "Jefe de área"
    if es_contador(user):
        return "Contador"
    if empleado_de(user):
        return "Empleado"
    return "Sin rol"


def permiso_requerido(permiso):
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


def areas_del_usuario(user):
    empleado = empleado_de(user)
    if empleado is None:
        return []
    return list(empleado.areas_dirigidas.all())


def empleados_visibles(user):
    consulta = Empleado.objects.select_related("area", "usuario")
    if not getattr(user, "is_authenticated", False):
        return consulta.none()
    if es_administrador(user) or es_rrhh(user) or es_contador(user):
        return consulta
    empleado = empleado_de(user)
    if empleado is not None:
        if empleado.es_jefe:
            return consulta.filter(area__in=empleado.areas_dirigidas.all())
        return consulta.filter(pk=empleado.pk)
    return consulta.none()


def registros_visibles(user):
    consulta = RegistroAsistencia.objects.select_related("empleado", "empleado__area")
    if not getattr(user, "is_authenticated", False):
        return consulta.none()
    if es_administrador(user) or es_rrhh(user) or es_contador(user):
        return consulta
    empleado = empleado_de(user)
    if empleado is not None:
        if empleado.es_jefe:
            return consulta.filter(empleado__area__in=empleado.areas_dirigidas.all())
        return consulta.filter(empleado=empleado)
    return consulta.none()


def solicitudes_visibles(user):
    consulta = Solicitud.objects.select_related("empleado", "empleado__area", "revisado_por")
    if not getattr(user, "is_authenticated", False):
        return consulta.none()
    if es_administrador(user) or es_rrhh(user):
        return consulta
    empleado = empleado_de(user)
    if empleado is not None:
        if empleado.es_jefe:
            return consulta.filter(empleado__area__in=empleado.areas_dirigidas.all())
        return consulta.filter(empleado=empleado)
    if es_contador(user):
        return consulta
    return consulta.none()


def puede_ver_empleado(user, empleado) -> bool:
    return empleados_visibles(user).filter(pk=empleado.pk).exists()


def puede_ver_registro(user, registro) -> bool:
    return registros_visibles(user).filter(pk=registro.pk).exists()


def puede_ver_solicitud(user, solicitud) -> bool:
    return solicitudes_visibles(user).filter(pk=solicitud.pk).exists()


def puede_marcar(user, empleado) -> bool:
    propio = empleado_de(user)
    return bool(
        propio and propio.pk == empleado.pk and propio.activo
    ) or es_administrador(user)


def puede_corregir(user) -> bool:
    return es_rrhh(user)


def puede_editar_empleados(user) -> bool:
    return es_administrador(user) or es_rrhh(user)


def puede_resolver_solicitud(user, solicitud) -> bool:
    """Jefe del área o RRHH; nunca el propio solicitante."""
    if not getattr(user, "is_authenticated", False) or not solicitud.es_pendiente:
        return False
    propio = empleado_de(user)
    if propio is not None and propio.pk == solicitud.empleado_id:
        return False
    if es_rrhh(user):
        return True
    if propio is not None:
        return propio.areas_dirigidas.filter(pk=solicitud.empleado.area_id).exists()
    return False


def puede_cancelar_solicitud(user, solicitud) -> bool:
    if not solicitud.es_pendiente:
        return False
    propio = empleado_de(user)
    if propio is not None and propio.pk == solicitud.empleado_id:
        return True
    return es_rrhh(user)
