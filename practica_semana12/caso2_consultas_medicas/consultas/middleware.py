"""Middleware del caso 2: sesión, alertas, horario y auditoría médica."""
import logging
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time

from .horarios import validar_horario_general
from .models import AuditoriaMedica, Cita
from .permissions import medico_de
from .utils import obtener_ip, registrar_auditoria_medica

logger = logging.getLogger("consultas")


class ActividadSesionMiddleware:
    """Cierra la sesión tras 20 minutos reales de inactividad."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = getattr(settings, "SESSION_TIMEOUT", 20 * 60)

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
                registrar_auditoria_medica(
                    usuario=usuario, accion=AuditoriaMedica.Accion.LOGOUT,
                    ip=obtener_ip(request), recurso="Sesión expirada por inactividad",
                )
                messages.warning(request, "Su sesión expiró por inactividad.")
                return redirect(f"{reverse('consultas:login')}?expirada=1")
            if not ultima or (ahora - ultima).total_seconds() > 60:
                request.session["ultima_actividad"] = ahora.isoformat()
        return self.get_response(request)


class AlertaCitasMiddleware:
    """Adjunta al request el número de citas pendientes del médico."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.citas_pendientes_medico = 0
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            medico = medico_de(user)
            if medico is not None:
                request.citas_pendientes_medico = Cita.objects.filter(
                    medico=medico,
                    estado__in=(Cita.Estado.PENDIENTE, Cita.Estado.CONFIRMADA),
                    fecha__gte=timezone.localdate(),
                ).count()
        return self.get_response(request)


class ValidacionHorarioMiddleware:
    """Valida el horario general en el POST de agendamiento (defensa en capas).

    Reutiliza la función centralizada que también usan el formulario y el
    servicio. Devuelve 400 ante un horario imposible, antes de tocar la BD.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != "POST" or view_func.__name__ != "agendar_cita":
            return None
        fecha = parse_date(request.POST.get("fecha") or "")
        hora = parse_time(request.POST.get("hora") or "")
        if not fecha or not hora:
            return None
        valido, mensaje = validar_horario_general(fecha, hora)
        if not valido:
            logger.warning("Horario rechazado por middleware: %s", mensaje)
            return render(
                request, "consultas/400.html", {"mensaje": mensaje}, status=400
            )
        return None


class AuditoriaMedicaMiddleware:
    """Audita accesos a historiales y respuestas 403.

    Registra únicamente usuario, paciente (id), acción, fecha, IP y ruta.
    Jamás vuelca diagnósticos, tratamientos ni contenido de notas.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._auditar(request, response)
        except Exception:
            logger.exception("Fallo al auditar acceso médico")
        return response

    def _auditar(self, request, response):
        match = getattr(request, "resolver_match", None)
        vista = getattr(match, "view_name", "") if match else ""
        kwargs = getattr(match, "kwargs", {}) if match else {}
        ip = obtener_ip(request)

        if response.status_code in (401, 403):
            paciente_id = kwargs.get("pk") if vista == "consultas:historial" else None
            registrar_auditoria_medica(
                usuario=getattr(request, "user", None),
                accion=AuditoriaMedica.Accion.ACCESO_DENEGADO,
                paciente_id=paciente_id,
                ip=ip,
                recurso=request.path,
            )
            logger.warning(
                "Acceso denegado status=%s usuario=%s ruta=%s",
                response.status_code, getattr(request.user, "pk", None), request.path,
            )
            return

        if response.status_code < 400 and vista == "consultas:historial":
            registrar_auditoria_medica(
                usuario=getattr(request, "user", None),
                accion=AuditoriaMedica.Accion.VER_HISTORIAL,
                paciente_id=kwargs.get("pk"),
                ip=ip,
                recurso=request.path,
            )
