"""Vistas de la Plataforma de Asistencia y Permisos (Caso 3)."""
import logging
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .forms import (
    BusquedaRegistroForm,
    BusquedaSolicitudForm,
    CorreccionForm,
    EmpleadoForm,
    LoginForm,
    ResolucionForm,
    SolicitudForm,
)
from .models import (
    Area,
    AuditoriaAsistencia,
    Empleado,
    RegistroAsistencia,
    Solicitud,
)
from .permissions import (
    areas_del_usuario,
    empleado_de,
    empleados_visibles,
    es_administrador,
    es_contador,
    es_jefe,
    es_rrhh,
    puede_cancelar_solicitud,
    puede_corregir,
    puede_editar_empleados,
    puede_resolver_solicitud,
    puede_ver_empleado,
    puede_ver_registro,
    puede_ver_solicitud,
    registros_visibles,
    rol_principal,
    solicitudes_visibles,
)
from .reglas import saldo_anual_dias
from .utils import obtener_ip, registrar_auditoria

logger = logging.getLogger("asistencia")


def _paginar(request, queryset, por_pagina=25):
    return Paginator(queryset, por_pagina).get_page(request.GET.get("page"))


def _sumar(registros, atributo):
    total = Decimal("0.00")
    for registro in registros:
        total += getattr(registro, atributo)
    return total.quantize(Decimal("0.01"))


def inicio(request):
    if request.user.is_authenticated:
        return redirect("asistencia:dashboard")
    return redirect("asistencia:login")


def iniciar_sesion(request):
    if request.user.is_authenticated:
        return redirect("asistencia:dashboard")
    formulario = LoginForm(request, data=request.POST or None)
    if request.method == "POST":
        if formulario.is_valid():
            usuario = formulario.get_user()
            auth_login(request, usuario)
            request.session["ultima_actividad"] = timezone.now().isoformat()
            registrar_auditoria(
                usuario=usuario, accion=AuditoriaAsistencia.Accion.LOGIN,
                empleado=empleado_de(usuario), ip=obtener_ip(request),
                detalle="Inicio de sesión",
            )
            messages.success(
                request, f"Bienvenido(a), {usuario.get_full_name() or usuario.username}."
            )
            return redirect("asistencia:dashboard")
        registrar_auditoria(
            usuario=None, accion=AuditoriaAsistencia.Accion.OTRO,
            ip=obtener_ip(request),
            detalle=f"Login fallido: {(request.POST.get('username') or '')[:60]}",
        )
        messages.error(request, "Usuario o contraseña incorrectos.")
    if request.GET.get("expirada"):
        messages.warning(request, "La sesión anterior expiró por inactividad.")
    return render(request, "asistencia/login.html", {"form": formulario})


@login_required
@require_POST
def cerrar_sesion(request):
    registrar_auditoria(
        usuario=request.user, accion=AuditoriaAsistencia.Accion.LOGOUT,
        empleado=empleado_de(request.user), ip=obtener_ip(request),
        detalle="Cierre de sesión manual",
    )
    auth_logout(request)
    messages.info(request, "Sesión cerrada correctamente.")
    return redirect("asistencia:login")


@login_required
def dashboard(request):
    usuario = request.user
    hoy = timezone.localdate()
    propio = empleado_de(usuario)
    contexto = {
        "rol": rol_principal(usuario),
        "hoy": hoy,
        "saldo_anual": saldo_anual_dias(),
        "propio": propio,
        "registro_hoy": None,
        "solicitudes_propias": Solicitud.objects.none(),
        "ultimos_registros": RegistroAsistencia.objects.none(),
        "areas": areas_del_usuario(usuario),
        "solicitudes_por_resolver": Solicitud.objects.none(),
        "equipo": Empleado.objects.none(),
    }

    if propio is not None:
        contexto["registro_hoy"] = RegistroAsistencia.objects.filter(
            empleado=propio, fecha=hoy
        ).first()
        contexto["solicitudes_propias"] = propio.solicitudes.select_related(
            "revisado_por"
        )[:6]
        contexto["ultimos_registros"] = propio.registros.order_by("-fecha")[:7]
        contexto["saldo_disponible"] = propio.saldo_disponible()

    if es_rrhh(usuario) or es_administrador(usuario):
        consulta_hoy = RegistroAsistencia.objects.filter(fecha=hoy)
        contexto.update({
            "total_empleados": Empleado.objects.filter(activo=True).count(),
            "total_areas": Area.objects.count(),
            "presentes_hoy": consulta_hoy.exclude(hora_entrada__isnull=True).count(),
            "sin_registro_hoy": max(
                Empleado.objects.filter(activo=True).count() - consulta_hoy.count(), 0
            ),
            "pendientes_total": Solicitud.objects.filter(
                estado=Solicitud.Estado.PENDIENTE
            ).count(),
            "auditoria_reciente": AuditoriaAsistencia.objects.select_related(
                "usuario", "empleado"
            )[:6],
        })
    elif es_jefe(usuario) and propio is not None:
        areas = propio.areas_dirigidas.all()
        contexto["equipo"] = Empleado.objects.filter(area__in=areas, activo=True)
        contexto["solicitudes_por_resolver"] = Solicitud.objects.filter(
            estado=Solicitud.Estado.PENDIENTE, empleado__area__in=areas,
        ).exclude(empleado=propio).select_related("empleado", "empleado__area")[:8]
        contexto["registros_equipo_hoy"] = RegistroAsistencia.objects.filter(
            empleado__area__in=areas, fecha=hoy
        ).select_related("empleado")[:10]
    elif es_contador(usuario):
        inicio_mes = hoy.replace(day=1)
        registros_mes = RegistroAsistencia.objects.filter(
            fecha__gte=inicio_mes, fecha__lte=hoy
        )
        contexto.update({
            "total_empleados": Empleado.objects.filter(activo=True).count(),
            "horas_mes": _sumar(registros_mes, "total_horas"),
            "extra_mes": _sumar(registros_mes, "total_extra"),
        })
    return render(request, "asistencia/dashboard.html", contexto)


@login_required
@require_POST
def marcar_asistencia(request):
    propio = empleado_de(request.user)
    if propio is None:
        raise PermissionDenied("Su usuario no tiene un empleado asociado.")
    hoy = timezone.localdate()
    registro = RegistroAsistencia.objects.filter(empleado=propio, fecha=hoy).first()
    try:
        if registro is not None and registro.hora_salida:
            raise services.ErrorAsistencia(
                "Ya completó su registro de asistencia de hoy."
            )
        if registro is not None and registro.hora_entrada:
            registro = services.marcar_salida(
                propio, usuario=request.user, ip=obtener_ip(request)
            )
            messages.success(
                request,
                f"Salida registrada a las {registro.hora_salida:%H:%M}. "
                f"Horas trabajadas: {registro.total_horas}.",
            )
        else:
            registro = services.marcar_entrada(
                propio, usuario=request.user, ip=obtener_ip(request)
            )
            messages.success(
                request, f"Entrada registrada a las {registro.hora_entrada:%H:%M}."
            )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("asistencia:dashboard")


@login_required
def mis_registros(request):
    propio = empleado_de(request.user)
    if propio is None:
        raise PermissionDenied("Su usuario no tiene un empleado asociado.")
    registros = propio.registros.order_by("-fecha")
    return render(
        request,
        "asistencia/mis_registros.html",
        {
            "empleado": propio,
            "page_obj": _paginar(request, registros, 30),
            "saldo_disponible": propio.saldo_disponible(),
        },
    )


@login_required
def registros(request):
    usuario = request.user
    if not (
        es_jefe(usuario) or es_rrhh(usuario) or es_contador(usuario)
        or es_administrador(usuario)
    ):
        raise PermissionDenied("Su rol no puede consultar la asistencia general.")
    formulario = BusquedaRegistroForm(request.GET or None)
    consulta = registros_visibles(usuario)
    if formulario.is_bound and formulario.is_valid():
        if formulario.cleaned_data.get("fecha"):
            consulta = consulta.filter(fecha=formulario.cleaned_data["fecha"])
        if formulario.cleaned_data.get("area"):
            consulta = consulta.filter(empleado__area=formulario.cleaned_data["area"])
    else:
        consulta = consulta.filter(fecha__gte=timezone.localdate() - timedelta(days=30))
    consulta = consulta.order_by("-fecha", "empleado__apellidos")
    pagina = _paginar(request, consulta, 30)
    return render(
        request,
        "asistencia/registros.html",
        {
            "form": formulario,
            "page_obj": pagina,
            "total_horas": _sumar(pagina.object_list, "total_horas"),
            "total_extra": _sumar(pagina.object_list, "total_extra"),
            "puede_corregir": puede_corregir(usuario),
        },
    )


@login_required
def corregir_registro(request, pk):
    if not puede_corregir(request.user):
        raise PermissionDenied("Solo Recursos Humanos puede corregir asistencias.")
    registro = get_object_or_404(
        RegistroAsistencia.objects.select_related("empleado"), pk=pk
    )
    if not puede_ver_registro(request.user, registro):
        raise PermissionDenied("No tiene acceso a este registro.")
    formulario = CorreccionForm(
        request.POST or None,
        initial={
            "hora_entrada": registro.hora_entrada,
            "hora_salida": registro.hora_salida,
        },
    )
    if request.method == "POST" and formulario.is_valid():
        try:
            services.corregir_asistencia(
                registro,
                usuario=request.user,
                hora_entrada=formulario.cleaned_data["hora_entrada"],
                hora_salida=formulario.cleaned_data["hora_salida"],
                justificacion=formulario.cleaned_data["justificacion"],
                ip=obtener_ip(request),
            )
        except ValidationError as exc:
            formulario.add_error(None, exc.messages)
        else:
            messages.success(request, "Registro corregido y auditoría registrada.")
            return redirect("asistencia:registros")
    return render(
        request,
        "asistencia/correccion_form.html",
        {"form": formulario, "registro": registro},
    )


@login_required
def solicitudes(request):
    formulario = BusquedaSolicitudForm(request.GET or None)
    consulta = solicitudes_visibles(request.user)
    if formulario.is_bound and formulario.is_valid():
        if formulario.cleaned_data.get("estado"):
            consulta = consulta.filter(estado=formulario.cleaned_data["estado"])
        if formulario.cleaned_data.get("tipo"):
            consulta = consulta.filter(tipo=formulario.cleaned_data["tipo"])
        if formulario.cleaned_data.get("area"):
            consulta = consulta.filter(empleado__area=formulario.cleaned_data["area"])
    consulta = consulta.order_by("-creado_en")
    return render(
        request,
        "asistencia/solicitudes.html",
        {
            "form": formulario,
            "page_obj": _paginar(request, consulta, 20),
            "puede_crear": empleado_de(request.user) is not None
            or es_rrhh(request.user) or es_administrador(request.user),
        },
    )


@login_required
def solicitud_crear(request):
    usuario = request.user
    propio = empleado_de(usuario)
    if propio is None and not (es_rrhh(usuario) or es_administrador(usuario)):
        raise PermissionDenied("Su usuario no puede registrar solicitudes.")
    formulario = SolicitudForm(request.POST or None, usuario=usuario)
    if request.method == "POST" and formulario.is_valid():
        empleado = formulario.cleaned_data.get("empleado") or propio
        if empleado is None:
            formulario.add_error(None, "Debe indicar el empleado solicitante.")
        else:
            try:
                solicitud = services.crear_solicitud(
                    empleado=empleado,
                    tipo=formulario.cleaned_data["tipo"],
                    fecha_inicio=formulario.cleaned_data["fecha_inicio"],
                    fecha_fin=formulario.cleaned_data["fecha_fin"],
                    motivo=formulario.cleaned_data["motivo"],
                    usuario=usuario,
                    ip=obtener_ip(request),
                )
            except ValidationError as exc:
                formulario.add_error(None, exc.messages)
            else:
                messages.success(
                    request, "Solicitud registrada y pendiente de revisión."
                )
                return redirect("asistencia:solicitud_detalle", pk=solicitud.pk)
    return render(
        request,
        "asistencia/solicitud_form.html",
        {"form": formulario, "saldo_disponible": propio.saldo_disponible() if propio else None},
    )


@login_required
def solicitud_detalle(request, pk):
    solicitud = get_object_or_404(
        Solicitud.objects.select_related(
            "empleado", "empleado__area", "revisado_por", "empleado__usuario"
        ),
        pk=pk,
    )
    if not puede_ver_solicitud(request.user, solicitud):
        raise PermissionDenied("No tiene acceso a esta solicitud.")
    return render(
        request,
        "asistencia/solicitud_detalle.html",
        {
            "solicitud": solicitud,
            "puede_resolver": puede_resolver_solicitud(request.user, solicitud),
            "puede_cancelar": puede_cancelar_solicitud(request.user, solicitud),
            "form": ResolucionForm(),
        },
    )


@login_required
@require_POST
def resolver_solicitud(request, pk):
    solicitud = get_object_or_404(Solicitud, pk=pk)
    if not puede_ver_solicitud(request.user, solicitud):
        raise PermissionDenied("No tiene acceso a esta solicitud.")
    if not puede_resolver_solicitud(request.user, solicitud):
        raise PermissionDenied(
            "Solo el jefe del área o RRHH puede resolverla, y nunca el solicitante."
        )
    formulario = ResolucionForm(request.POST)
    accion = request.POST.get("accion")
    if accion not in ("aprobar", "rechazar"):
        messages.error(request, "Acción no válida.")
        return redirect("asistencia:solicitud_detalle", pk=solicitud.pk)
    if not formulario.is_valid():
        messages.error(request, "Revise el comentario de revisión.")
        return redirect("asistencia:solicitud_detalle", pk=solicitud.pk)
    try:
        services.resolver_solicitud(
            solicitud,
            usuario=request.user,
            aprobar=accion == "aprobar",
            comentario=formulario.cleaned_data.get("comentario", ""),
            ip=obtener_ip(request),
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(
            request,
            "Solicitud aprobada." if accion == "aprobar" else "Solicitud rechazada.",
        )
    return redirect("asistencia:solicitud_detalle", pk=solicitud.pk)


@login_required
@require_POST
def cancelar_solicitud(request, pk):
    solicitud = get_object_or_404(Solicitud, pk=pk)
    if not puede_ver_solicitud(request.user, solicitud):
        raise PermissionDenied("No tiene acceso a esta solicitud.")
    if not puede_cancelar_solicitud(request.user, solicitud):
        raise PermissionDenied("No puede cancelar esta solicitud.")
    try:
        services.cancelar_solicitud(
            solicitud, usuario=request.user, ip=obtener_ip(request)
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.info(request, "Solicitud cancelada.")
    return redirect("asistencia:solicitud_detalle", pk=solicitud.pk)


@login_required
def empleados(request):
    usuario = request.user
    if not (
        es_jefe(usuario) or es_rrhh(usuario) or es_contador(usuario)
        or es_administrador(usuario)
    ):
        raise PermissionDenied("Su rol no puede consultar el listado de empleados.")
    consulta = empleados_visibles(usuario).order_by("apellidos", "nombres")
    q = (request.GET.get("q") or "").strip()
    if q:
        consulta = consulta.filter(
            Q(dni__icontains=q) | Q(nombres__icontains=q) | Q(apellidos__icontains=q)
        )
    return render(
        request,
        "asistencia/empleados.html",
        {
            "page_obj": _paginar(request, consulta, 20),
            "q": q,
            "puede_editar": puede_editar_empleados(usuario),
        },
    )


@login_required
def empleado_detalle(request, pk):
    empleado = get_object_or_404(
        Empleado.objects.select_related("area", "usuario", "area__jefe"), pk=pk
    )
    if not puede_ver_empleado(request.user, empleado):
        raise PermissionDenied("No tiene acceso a la información de este empleado.")
    return render(
        request,
        "asistencia/empleado_detalle.html",
        {
            "empleado": empleado,
            "registros": empleado.registros.order_by("-fecha")[:30],
            "solicitudes": empleado.solicitudes.select_related("revisado_por")[:20],
            "saldo_disponible": empleado.saldo_disponible(),
            "puede_editar": puede_editar_empleados(request.user),
        },
    )


@login_required
def empleado_crear(request):
    if not puede_editar_empleados(request.user):
        raise PermissionDenied("Solo RRHH puede registrar empleados.")
    formulario = EmpleadoForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        empleado = formulario.save()
        messages.success(request, "Empleado registrado correctamente.")
        return redirect("asistencia:empleado_detalle", pk=empleado.pk)
    return render(
        request,
        "asistencia/empleado_form.html",
        {"form": formulario, "titulo": "Registrar empleado"},
    )


@login_required
def empleado_editar(request, pk):
    if not puede_editar_empleados(request.user):
        raise PermissionDenied("Solo RRHH puede editar empleados.")
    empleado = get_object_or_404(Empleado, pk=pk)
    formulario = EmpleadoForm(request.POST or None, instance=empleado)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "Datos del empleado actualizados.")
        return redirect("asistencia:empleado_detalle", pk=empleado.pk)
    return render(
        request,
        "asistencia/empleado_form.html",
        {"form": formulario, "titulo": "Editar empleado", "empleado": empleado},
    )


@login_required
def reportes(request):
    usuario = request.user
    autorizado = (
        es_rrhh(usuario) or es_contador(usuario) or es_administrador(usuario)
        or usuario.has_perm("asistencia.ver_reportes_asistencia")
    )
    if not autorizado:
        raise PermissionDenied("Su rol no puede acceder a los reportes.")
    hoy = timezone.localdate()
    desde = hoy - timedelta(days=29)
    registros_rango = list(
        RegistroAsistencia.objects.filter(fecha__range=(desde, hoy)).select_related(
            "empleado", "empleado__area"
        )
    )
    resumen_areas = []
    for area in Area.objects.all():
        del_area = [r for r in registros_rango if r.empleado.area_id == area.pk]
        resumen_areas.append({
            "area": area,
            "empleados": area.empleados.filter(activo=True).count(),
            "registros": len(del_area),
            "horas": _sumar(del_area, "total_horas"),
            "extra": _sumar(del_area, "total_extra"),
        })
    por_empleado = {}
    for registro in registros_rango:
        clave = registro.empleado_id
        fila = por_empleado.setdefault(
            clave, {"empleado": registro.empleado, "horas": Decimal("0.00"),
                    "extra": Decimal("0.00"), "dias": 0}
        )
        fila["horas"] += registro.total_horas
        fila["extra"] += registro.total_extra
        fila["dias"] += 1
    top_extra = sorted(
        por_empleado.values(), key=lambda f: f["extra"], reverse=True
    )[:8]
    return render(
        request,
        "asistencia/reportes.html",
        {
            "desde": desde,
            "hasta": hoy,
            "resumen_areas": resumen_areas,
            "top_extra": top_extra,
            "total_horas": _sumar(registros_rango, "total_horas"),
            "total_extra": _sumar(registros_rango, "total_extra"),
            "total_registros": len(registros_rango),
            "pendientes": Solicitud.objects.filter(
                estado=Solicitud.Estado.PENDIENTE
            ).count(),
            "solicitudes_aprobadas": Solicitud.objects.filter(
                estado=Solicitud.Estado.APROBADA
            ).count(),
        },
    )


def acceso_denegado(request, exception=None):
    return render(request, "403.html", status=403)
