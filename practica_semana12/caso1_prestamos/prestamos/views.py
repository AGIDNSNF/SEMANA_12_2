"""Vistas del Sistema de Gestión de Préstamos (Caso 1).

La lógica de negocio vive en services.py; aquí solo se orquesta HTTP.
"""
import csv
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .forms import (
    BusquedaEquipoForm,
    DevolucionForm,
    EquipoForm,
    FiltroPrestamoForm,
    LoginForm,
    PrestamoRapidoForm,
    PrestamoSolicitudForm,
    RechazoForm,
)
from .models import ESTADOS_QUE_OCUPAN, Auditoria, Devolucion, Equipo, Laboratorio, Prestamo
from .permissions import (
    GRUPO_ADMIN,
    es_administrador,
    es_asistente,
    es_docente,
    es_invitado,
    permiso_requerido,
    puede_ver_prestamo,
    rol_principal,
)
from .utils import obtener_ip, registrar_auditoria

logger = logging.getLogger("prestamos")
Usuario = get_user_model()


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------
def _paginar(request, queryset, por_pagina=10):
    return Paginator(queryset, por_pagina).get_page(request.GET.get("page"))


def _querystring_sin_pagina(request):
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return parametros.urlencode()


def _prestamos_visibles(usuario):
    consulta = Prestamo.objects.select_related("equipo", "docente", "asistente_responsable")
    if usuario.is_superuser or es_administrador(usuario) or es_asistente(usuario):
        return consulta
    return consulta.filter(docente=usuario)


# ---------------------------------------------------------------------------
# Catálogo público
# ---------------------------------------------------------------------------
def catalogo(request):
    formulario = BusquedaEquipoForm(request.GET or None)
    equipos = (
        Equipo.objects.select_related("laboratorio")
        .filter(laboratorio__activo=True)
        .exclude(estado=Equipo.Estado.BAJA)
    )
    if formulario.is_bound and formulario.is_valid():
        datos = formulario.cleaned_data
        if datos.get("q"):
            equipos = equipos.filter(
                Q(codigo_patrimonial__icontains=datos["q"])
                | Q(nombre__icontains=datos["q"])
                | Q(categoria__icontains=datos["q"])
            )
        if datos.get("laboratorio"):
            equipos = equipos.filter(laboratorio=datos["laboratorio"])
        if datos.get("estado"):
            equipos = equipos.filter(estado=datos["estado"])
        if datos.get("categoria"):
            equipos = equipos.filter(categoria__icontains=datos["categoria"])

    pagina = _paginar(request, equipos, 9)
    return render(
        request,
        "prestamos/catalogo.html",
        {"form": formulario, "page_obj": pagina, "equipos": pagina.object_list,
         "querystring": _querystring_sin_pagina(request)},
    )


def equipo_detalle(request, pk):
    equipo = get_object_or_404(
        Equipo.objects.select_related("laboratorio"),
        pk=pk,
        laboratorio__activo=True,
    )
    if equipo.estado == Equipo.Estado.BAJA:
        raise PermissionDenied("El equipo está dado de baja.")
    return render(
        request,
        "prestamos/equipo_detalle.html",
        {"equipo": equipo, "prestamos_activos": equipo.prestamos.filter(
            estado__in=ESTADOS_QUE_OCUPAN).count()},
    )


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------
def iniciar_sesion(request):
    if request.user.is_authenticated:
        return redirect("prestamos:dashboard")

    formulario = LoginForm(request, data=request.POST or None)
    if request.method == "POST":
        if formulario.is_valid():
            usuario = formulario.get_user()
            auth_login(request, usuario)
            request.session["ultima_actividad"] = timezone.now().isoformat()
            registrar_auditoria(
                usuario=usuario,
                accion=Auditoria.Accion.LOGIN,
                entidad="Sesion",
                entidad_id=usuario.pk,
                descripcion="Inicio de sesión correcto.",
                ip=obtener_ip(request),
            )
            messages.success(request, f"Bienvenido(a), {usuario.get_full_name() or usuario.username}.")
            return redirect("prestamos:dashboard")
        usuario_intentado = (request.POST.get("username") or "")[:60]
        registrar_auditoria(
            usuario=None,
            accion=Auditoria.Accion.LOGIN_FALLIDO,
            entidad="Sesion",
            descripcion=f"Intento de inicio de sesión fallido para: {usuario_intentado}",
            ip=obtener_ip(request),
        )
        logger.warning("Login fallido para %s desde %s", usuario_intentado, obtener_ip(request))
        messages.error(request, "Usuario o contraseña incorrectos.")
    if request.GET.get("expirada"):
        messages.warning(request, "La sesión anterior expiró. Ingrese nuevamente.")
    return render(request, "prestamos/login.html", {"form": formulario})


@login_required
@require_POST
def cerrar_sesion(request):
    registrar_auditoria(
        usuario=request.user,
        accion=Auditoria.Accion.LOGOUT,
        entidad="Sesion",
        entidad_id=request.user.pk,
        descripcion="Cierre de sesión manual.",
        ip=obtener_ip(request),
    )
    auth_logout(request)
    messages.info(request, "Ha cerrado sesión correctamente.")
    return redirect("prestamos:catalogo")


# ---------------------------------------------------------------------------
# Dashboard y préstamos
# ---------------------------------------------------------------------------
@login_required
def dashboard(request):
    usuario = request.user
    if es_invitado(usuario) and not (es_docente(usuario) or es_asistente(usuario) or es_administrador(usuario)):
        return redirect("prestamos:catalogo")

    hoy = timezone.localdate()
    visibles = _prestamos_visibles(usuario)
    estadisticas = {
        "activos": visibles.filter(estado=Prestamo.Estado.ACTIVO).count(),
        "pendientes": visibles.filter(estado=Prestamo.Estado.PENDIENTE).count(),
        "vencidos": visibles.filter(
            estado__in=(Prestamo.Estado.ACTIVO, Prestamo.Estado.VENCIDO),
            fecha_prevista_devolucion__lt=hoy,
        ).count(),
        "devueltos": visibles.filter(estado=Prestamo.Estado.DEVUELTO).count(),
    }
    equipos_operativos = Equipo.objects.filter(
        estado=Equipo.Estado.OPERATIVO, laboratorio__activo=True
    )
    stock_total = equipos_operativos.aggregate(total=Sum("stock_total"))["total"] or 0
    comprometido = Prestamo.objects.filter(estado__in=ESTADOS_QUE_OCUPAN).aggregate(
        total=Sum("cantidad")
    )["total"] or 0
    contexto = {
        "estadisticas": estadisticas,
        "rol": rol_principal(usuario),
        "equipos_operativos": equipos_operativos.count(),
        "unidades_disponibles": max(stock_total - comprometido, 0),
        "proximos_vencer": visibles.filter(
            estado__in=(Prestamo.Estado.ACTIVO, Prestamo.Estado.VENCIDO)
        ).order_by("fecha_prevista_devolucion")[:5],
        "ultimos": visibles.order_by("-fecha_creacion")[:5],
        "laboratorios": Laboratorio.objects.filter(activo=True).count(),
    }
    if es_administrador(usuario):
        contexto["auditoria_reciente"] = Auditoria.objects.select_related("usuario")[:5]
        contexto["total_usuarios"] = Usuario.objects.filter(is_active=True).count()
    return render(request, "prestamos/dashboard.html", contexto)


@login_required
def mis_prestamos(request):
    formulario = FiltroPrestamoForm(request.GET or None)
    consulta = Prestamo.objects.filter(docente=request.user).select_related(
        "equipo", "equipo__laboratorio"
    )
    if formulario.is_bound and formulario.is_valid():
        if formulario.cleaned_data.get("estado"):
            consulta = consulta.filter(estado=formulario.cleaned_data["estado"])
        if formulario.cleaned_data.get("desde"):
            consulta = consulta.filter(fecha_prestamo__gte=formulario.cleaned_data["desde"])
        if formulario.cleaned_data.get("hasta"):
            consulta = consulta.filter(fecha_prestamo__lte=formulario.cleaned_data["hasta"])
    return render(
        request,
        "prestamos/mis_prestamos.html",
        {"form": formulario, "page_obj": _paginar(request, consulta, 10),
         "querystring": _querystring_sin_pagina(request)},
    )


@permiso_requerido("prestamos.change_prestamo")
def lista_prestamos(request):
    formulario = FiltroPrestamoForm(request.GET or None)
    consulta = Prestamo.objects.select_related("equipo", "docente").order_by(
        "-fecha_prestamo", "-id"
    )
    if formulario.is_bound and formulario.is_valid():
        if formulario.cleaned_data.get("estado"):
            consulta = consulta.filter(estado=formulario.cleaned_data["estado"])
        if formulario.cleaned_data.get("desde"):
            consulta = consulta.filter(fecha_prestamo__gte=formulario.cleaned_data["desde"])
        if formulario.cleaned_data.get("hasta"):
            consulta = consulta.filter(fecha_prestamo__lte=formulario.cleaned_data["hasta"])
    return render(
        request,
        "prestamos/lista_prestamos.html",
        {"form": formulario, "page_obj": _paginar(request, consulta, 12),
         "querystring": _querystring_sin_pagina(request)},
    )


@login_required
def prestamo_detalle(request, pk):
    prestamo = get_object_or_404(
        Prestamo.objects.select_related("equipo", "docente", "asistente_responsable"), pk=pk
    )
    if not puede_ver_prestamo(request.user, prestamo):
        raise PermissionDenied("No tiene acceso a préstamos de otros usuarios.")
    devolucion = Devolucion.objects.filter(prestamo=prestamo).first()
    return render(
        request,
        "prestamos/prestamo_detalle.html",
        {"prestamo": prestamo, "devolucion": devolucion,
         "puede_gestionar": request.user.has_perm("prestamos.change_prestamo")},
    )


@login_required
def solicitar_prestamo(request):
    if not (es_docente(request.user) or es_administrador(request.user)):
        raise PermissionDenied("Solo los docentes pueden solicitar préstamos.")
    formulario = PrestamoSolicitudForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            prestamo = services.crear_prestamo(
                docente=request.user,
                equipo=formulario.cleaned_data["equipo"],
                cantidad=formulario.cleaned_data["cantidad"],
                fecha_prestamo=formulario.cleaned_data["fecha_prestamo"],
                fecha_prevista_devolucion=formulario.cleaned_data["fecha_prevista_devolucion"],
                observaciones=formulario.cleaned_data["observaciones"],
                estado=Prestamo.Estado.PENDIENTE,
                usuario_accion=request.user,
                ip=obtener_ip(request),
            )
        except ValidationError as exc:
            formulario.add_error(None, exc.messages)
        else:
            messages.success(
                request,
                f"Solicitud #{prestamo.pk} registrada. Queda pendiente de aprobación.",
            )
            return redirect("prestamos:mis_prestamos")
    return render(
        request,
        "prestamos/prestamo_form.html",
        {"form": formulario, "titulo": "Solicitar préstamo", "es_rapido": False},
    )


@permiso_requerido("prestamos.registrar_prestamo")
def prestamo_rapido(request):
    formulario = PrestamoRapidoForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            prestamo = services.crear_prestamo(
                docente=formulario.cleaned_data["docente"],
                equipo=formulario.cleaned_data["equipo"],
                cantidad=formulario.cleaned_data["cantidad"],
                fecha_prestamo=formulario.cleaned_data["fecha_prestamo"],
                fecha_prevista_devolucion=formulario.cleaned_data["fecha_prevista_devolucion"],
                observaciones=formulario.cleaned_data["observaciones"],
                estado=Prestamo.Estado.ACTIVO,
                asistente=request.user,
                usuario_accion=request.user,
                ip=obtener_ip(request),
            )
        except ValidationError as exc:
            formulario.add_error(None, exc.messages)
        else:
            messages.success(request, f"Préstamo #{prestamo.pk} registrado y activado.")
            return redirect("prestamos:prestamo_detalle", pk=prestamo.pk)
    return render(
        request,
        "prestamos/prestamo_form.html",
        {"form": formulario, "titulo": "Registrar préstamo en ventanilla", "es_rapido": True},
    )


@require_POST
@permiso_requerido("prestamos.change_prestamo")
def aprobar_prestamo(request, pk):
    prestamo = get_object_or_404(Prestamo, pk=pk)
    try:
        services.aprobar_prestamo(prestamo, asistente=request.user, ip=obtener_ip(request))
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, f"Préstamo #{prestamo.pk} aprobado y activo.")
    return redirect("prestamos:prestamo_detalle", pk=prestamo.pk)


@require_POST
@permiso_requerido("prestamos.change_prestamo")
def rechazar_prestamo(request, pk):
    prestamo = get_object_or_404(Prestamo, pk=pk)
    formulario = RechazoForm(request.POST)
    if not formulario.is_valid():
        messages.error(request, "Indique un motivo de rechazo válido (mínimo 10 caracteres).")
        return redirect("prestamos:prestamo_detalle", pk=prestamo.pk)
    try:
        services.rechazar_prestamo(
            prestamo, asistente=request.user,
            motivo=formulario.cleaned_data["motivo"], ip=obtener_ip(request),
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.info(request, f"Solicitud #{prestamo.pk} rechazada.")
    return redirect("prestamos:prestamo_detalle", pk=prestamo.pk)


# ---------------------------------------------------------------------------
# Devoluciones
# ---------------------------------------------------------------------------
@permiso_requerido("prestamos.add_devolucion")
def devoluciones_pendientes(request):
    consulta = Prestamo.objects.filter(
        estado__in=(Prestamo.Estado.ACTIVO, Prestamo.Estado.VENCIDO)
    ).select_related("equipo", "docente").order_by("fecha_prevista_devolucion")
    return render(
        request,
        "prestamos/devoluciones.html",
        {"page_obj": _paginar(request, consulta, 12)},
    )


@permiso_requerido("prestamos.add_devolucion")
def registrar_devolucion(request, pk):
    prestamo = get_object_or_404(Prestamo.objects.select_related("equipo", "docente"), pk=pk)
    if not prestamo.puede_devolverse:
        messages.warning(request, "Este préstamo no está disponible para devolución.")
        return redirect("prestamos:devoluciones_pendientes")

    formulario = DevolucionForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            services.registrar_devolucion(
                prestamo,
                asistente=request.user,
                estado_equipo=formulario.cleaned_data["estado_equipo"],
                observaciones=formulario.cleaned_data["observaciones"],
                ip=obtener_ip(request),
            )
        except ValidationError as exc:
            formulario.add_error(None, exc.messages)
        else:
            messages.success(request, f"Devolución del préstamo #{prestamo.pk} registrada.")
            return redirect("prestamos:devoluciones_pendientes")
    return render(
        request,
        "prestamos/devolucion_form.html",
        {"form": formulario, "prestamo": prestamo},
    )


# ---------------------------------------------------------------------------
# Reportes y auditoría
# ---------------------------------------------------------------------------
@permiso_requerido("prestamos.ver_reportes")
def reportes(request):
    hoy = timezone.localdate()
    por_estado = (
        Prestamo.objects.values("estado").annotate(total=Count("id")).order_by("estado")
    )
    por_laboratorio = (
        Laboratorio.objects.annotate(
            num_equipos=Count("equipos", distinct=True),
            stock=Sum("equipos__stock_total"),
        )
        .order_by("nombre")
    )
    top_equipos = (
        Equipo.objects.annotate(total_prestamos=Count("prestamos"))
        .filter(total_prestamos__gt=0)
        .order_by("-total_prestamos")[:5]
    )
    top_docentes = (
        Usuario.objects.annotate(total=Count("prestamos_solicitados"))
        .filter(total__gt=0)
        .order_by("-total")[:5]
    )
    vencidos = Prestamo.objects.filter(
        estado__in=(Prestamo.Estado.ACTIVO, Prestamo.Estado.VENCIDO),
        fecha_prevista_devolucion__lt=hoy,
    ).select_related("equipo", "docente")
    return render(
        request,
        "prestamos/reportes.html",
        {
            "por_estado": por_estado,
            "por_laboratorio": por_laboratorio,
            "top_equipos": top_equipos,
            "top_docentes": top_docentes,
            "vencidos": vencidos,
            "total_prestamos": Prestamo.objects.count(),
            "total_devoluciones": Devolucion.objects.count(),
        },
    )


@permiso_requerido("prestamos.ver_reportes")
def exportar_reporte(request):
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="prestamos_uncp.csv"'
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta)
    escritor.writerow(
        ["ID", "Docente", "Equipo", "Cantidad", "Fecha préstamo",
         "Fecha prevista", "Fecha real", "Estado", "Días de retraso"]
    )
    for prestamo in Prestamo.objects.select_related("docente", "equipo").order_by("id"):
        escritor.writerow([
            prestamo.pk,
            prestamo.docente.get_full_name() or prestamo.docente.username,
            prestamo.equipo.codigo_patrimonial,
            prestamo.cantidad,
            prestamo.fecha_prestamo.isoformat(),
            prestamo.fecha_prevista_devolucion.isoformat(),
            prestamo.fecha_real_devolucion.isoformat() if prestamo.fecha_real_devolucion else "",
            prestamo.get_estado_display(),
            prestamo.dias_retraso,
        ])
    registrar_auditoria(
        usuario=request.user, accion=Auditoria.Accion.OTRO, entidad="Reporte",
        descripcion="Exportación CSV del listado de préstamos.", ip=obtener_ip(request),
    )
    return respuesta


@login_required
def auditoria_lista(request):
    if not (request.user.is_superuser or es_administrador(request.user)):
        raise PermissionDenied("Solo el administrador puede consultar la auditoría.")
    consulta = Auditoria.objects.select_related("usuario")
    accion = request.GET.get("accion", "")
    if accion:
        consulta = consulta.filter(accion=accion)
    return render(
        request,
        "prestamos/auditoria.html",
        {
            "page_obj": _paginar(request, consulta, 20),
            "acciones": Auditoria.Accion.choices,
            "accion_actual": accion,
        },
    )


# ---------------------------------------------------------------------------
# Gestión de equipos (Administrador)
# ---------------------------------------------------------------------------
@permiso_requerido("prestamos.gestionar_equipos")
def equipo_crear(request):
    formulario = EquipoForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        equipo = formulario.save()
        registrar_auditoria(
            usuario=request.user, accion=Auditoria.Accion.EQUIPO, entidad="Equipo",
            entidad_id=equipo.pk,
            descripcion=f"Equipo {equipo.codigo_patrimonial} creado.", ip=obtener_ip(request),
        )
        messages.success(request, "Equipo registrado correctamente.")
        return redirect("prestamos:equipo_detalle", pk=equipo.pk)
    return render(
        request,
        "prestamos/equipo_form.html",
        {"form": formulario, "titulo": "Registrar equipo"},
    )


@permiso_requerido("prestamos.gestionar_equipos")
def equipo_editar(request, pk):
    equipo = get_object_or_404(Equipo, pk=pk)
    formulario = EquipoForm(request.POST or None, instance=equipo)
    if request.method == "POST" and formulario.is_valid():
        equipo = formulario.save()
        registrar_auditoria(
            usuario=request.user, accion=Auditoria.Accion.EQUIPO, entidad="Equipo",
            entidad_id=equipo.pk,
            descripcion=f"Equipo {equipo.codigo_patrimonial} actualizado.",
            ip=obtener_ip(request),
        )
        messages.success(request, "Equipo actualizado correctamente.")
        return redirect("prestamos:equipo_detalle", pk=equipo.pk)
    return render(
        request,
        "prestamos/equipo_form.html",
        {"form": formulario, "titulo": "Editar equipo", "equipo": equipo},
    )


@permiso_requerido("prestamos.gestionar_equipos")
def equipo_eliminar(request, pk):
    equipo = get_object_or_404(Equipo, pk=pk)
    if request.method == "POST":
        try:
            services.eliminar_equipo(
                equipo, usuario=request.user, ip=obtener_ip(request)
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("prestamos:equipo_detalle", pk=pk)
        messages.success(request, "Equipo eliminado del catálogo.")
        return redirect("prestamos:catalogo")
    return render(request, "prestamos/equipo_confirmar_eliminar.html", {"equipo": equipo})


def acceso_denegado(request, exception=None):
    return render(request, "403.html", status=403)
