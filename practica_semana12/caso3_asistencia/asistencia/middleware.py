"""Middleware del caso 3: sesión, alertas y auditoría."""
import logging
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .models import AuditoriaAsistencia, Solicitud
from .permissions import empleado_de, es_jefe, es_rrhh
from .utils import obtener_ip, registrar_auditoria

logger = logging.getLogger("asistencia")


class ActividadSesionMiddleware:
    """Cierra la sesión tras 45 minutos reales de inactividad."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = getattr(settings, "SESSION_TIMEOUT", 45 * 60)

    def __call__(self, request):
        if request.user.is_authenticated:
            ahora = timezone.now()
            marca = request.session.get("ultima_actividad")
            ultima = None
            if marca:
                try:
                    ultima = datetime.fromisoformat(marca)
                except (TypeError, ValueError):
                    ultima = None
            if ultima and (ahora - ultima).total_seconds() > self.timeout:
                usuario = request.user
                auth_logout(request)
                request.session.flush()
                registrar_auditoria(
                    usuario=usuario, accion=AuditoriaAsistencia.Accion.LOGOUT,
                    ip=obtener_ip(request), detalle="Sesión expirada por inactividad",
                )
                messages.warning(request, "Su sesión expiró por inactividad.")
                return redirect(f"{reverse('asistencia:login')}?expirada=1")
            if not ultima or (ahora - ultima).total_seconds() > 60:
                request.session["ultima_actividad"] = ahora.isoformat()
        return self.get_response(request)


class AlertaSolicitudesMiddleware:
    """Adjunta al request el número de solicitudes pendientes por resolver."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.solicitudes_pendientes = 0
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            consulta = Solicitud.objects.filter(
                estado=Solicitud.Estado.PENDIENTE
            ).select_related("empleado")
            propio = empleado_de(user)
            if es_rrhh(user):
                if propio is not None:
                    consulta = consulta.exclude(empleado=propio)
                request.solicitudes_pendientes = consulta.count()
            elif es_jefe(user) and propio is not None:
                request.solicitudes_pendientes = consulta.filter(
                    empleado__area__in=propio.areas_dirigidas.all()
                ).exclude(empleado=propio).count()
        return self.get_response(request)


class AuditoriaAsistenciaMiddleware:
    """Audita respuestas 403 con usuario, ruta, IP y fecha (sin datos sensibles)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code in (401, 403):
            try:
                registrar_auditoria(
                    usuario=getattr(request, "user", None),
                    accion=AuditoriaAsistencia.Accion.ACCESO_DENEGADO,
                    ip=obtener_ip(request),
                    detalle=request.path,
                )
                logger.warning(
                    "Acceso denegado status=%s usuario=%s ruta=%s",
                    response.status_code, getattr(request.user, "pk", None), request.path,
                )
            except Exception:  # pragma: no cover
                logger.exception("Fallo al auditar acceso denegado")
        return response
