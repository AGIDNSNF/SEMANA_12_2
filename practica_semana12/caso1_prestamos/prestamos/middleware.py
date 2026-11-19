"""Middleware del caso 1: sesión, alertas y auditoría de accesos."""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .models import Auditoria, Prestamo
from .utils import obtener_ip, registrar_auditoria

logger = logging.getLogger("prestamos")

# Rutas cuyo POST se considera crítico para la auditoría del middleware.
RUTAS_CRITICAS = {
    "prestamos:aprobar_prestamo",
    "prestamos:rechazar_prestamo",
    "prestamos:registrar_devolucion",
    "prestamos:equipo_eliminar",
}


class ActividadSesionMiddleware:
    """Cierra la sesión tras 30 minutos reales de inactividad.

    Complementa SESSION_COOKIE_AGE con una marca explícita en sesión, lo que
    permite probar el timeout sin esperar ni manipular la cookie.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = getattr(settings, "SESSION_TIMEOUT", 30 * 60)

    def __call__(self, request):
        if request.user.is_authenticated:
            ahora = timezone.now()
            marca = request.session.get("ultima_actividad")
            ultima = None
            if marca:
                from datetime import datetime

                try:
                    ultima = datetime.fromisoformat(marca)
                except (TypeError, ValueError):
                    ultima = None

            if ultima and (ahora - ultima).total_seconds() > self.timeout:
                usuario = request.user
                auth_logout(request)
                request.session.flush()
                registrar_auditoria(
                    usuario=usuario,
                    accion=Auditoria.Accion.LOGOUT,
                    entidad="Sesion",
                    descripcion="Sesión cerrada automáticamente por inactividad.",
                    ip=obtener_ip(request),
                )
                messages.warning(
                    request, "Su sesión expiró por inactividad. Vuelva a iniciar sesión."
                )
                return redirect(f"{reverse('prestamos:login')}?expirada=1")

            if not ultima or (ahora - ultima).total_seconds() > 60:
                request.session["ultima_actividad"] = ahora.isoformat()

        return self.get_response(request)


class AlertaPrestamosMiddleware:
    """Adjunta al request el número de préstamos vencidos visibles al usuario."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.prestamos_vencidos = 0
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            hoy = timezone.localdate()
            consulta = Prestamo.objects.filter(
                fecha_prevista_devolucion__lt=hoy,
                estado__in=(Prestamo.Estado.ACTIVO, Prestamo.Estado.VENCIDO),
            )
            if not (
                user.is_superuser
                or user.has_perm("prestamos.change_prestamo")
                or user.groups.filter(name="Asistente").exists()
            ):
                consulta = consulta.filter(docente=user)
            request.prestamos_vencidos = consulta.count()
        return self.get_response(request)


class AuditoriaMiddleware:
    """Audita accesos denegados, cierres de sesión y acciones del admin.

    No registra contraseñas, cookies, tokens ni cuerpos de formulario.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._auditar(request, response)
        except Exception:  # la auditoría nunca debe romper la respuesta
            logger.exception("Fallo al auditar la petición")
        return response

    def _auditar(self, request, response):
        ip = obtener_ip(request)
        if response.status_code in (401, 403):
            registrar_auditoria(
                usuario=getattr(request, "user", None),
                accion=Auditoria.Accion.ACCESO_DENEGADO,
                entidad="Ruta",
                entidad_id=request.path,
                descripcion=f"Acceso denegado ({response.status_code}) a {request.path}",
                ip=ip,
            )
            logger.warning(
                "Acceso denegado status=%s usuario=%s ruta=%s",
                response.status_code, getattr(request.user, "pk", None), request.path,
            )
            return

        if request.method == "POST" and response.status_code < 400:
            vista = getattr(request.resolver_match, "view_name", "")
            if vista.startswith("admin:"):
                registrar_auditoria(
                    usuario=getattr(request, "user", None),
                    accion=Auditoria.Accion.OTRO,
                    entidad="DjangoAdmin",
                    entidad_id=request.path,
                    descripcion=f"Acción administrativa: {vista}",
                    ip=ip,
                )
