"""Vistas de la Plataforma de Consultas Médicas (Caso 2)."""
import logging

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .forms import (
    BusquedaCitaForm,
    BusquedaPacienteForm,
    CancelarCitaForm,
    CitaForm,
    ConsultaForm,
    LoginForm,
    MedicoForm,
    NotaClinicaForm,
    PacienteForm,
)
from .horarios import ESTADOS_CITA_ACTIVOS
from .models import (
    AuditoriaMedica, Cita, Consulta, Especialidad, Medico, NotaClinica, Paciente,
)
from .permissions import (
    es_administrador,
    es_medico,
    es_paciente,
    es_recepcionista,
    medico_de,
    paciente_de,
    permiso_requerido,
    puede_cancelar_cita,
    puede_ver_cita,
    puede_ver_historial,
    rol_principal,
)
from .utils import obtener_ip, registrar_auditoria_medica

logger = logging.getLogger("consultas")


def _paginar(request, queryset, por_pagina=15):
    return Paginator(queryset, por_pagina).get_page(request.GET.get("page"))


def inicio(request):
    if request.user.is_authenticated:
        return redirect("consultas:dashboard")
    return redirect("consultas:login")


def iniciar_sesion(request):
    if request.user.is_authenticated:
        return redirect("consultas:dashboard")
    formulario = LoginForm(request, data=request.POST or None)
    if request.method == "POST":
        if formulario.is_valid():
            usuario = formulario.get_user()
            auth_login(request, usuario)
            request.session["ultima_actividad"] = timezone.now().isoformat()
            registrar_auditoria_medica(
                usuario=usuario, accion=AuditoriaMedica.Accion.LOGIN,
                ip=obtener_ip(request), recurso="Inicio de sesión",
            )
            medico = medico_de(usuario)
            if medico is not None:
                pendientes = services.citas_pendientes_medico(usuario)
                if pendientes:
                    messages.info(
                        request,
                        f"Tiene {pendientes} cita(s) pendiente(s) o confirmada(s) en su agenda.",
                    )
            messages.success(request, f"Bienvenido(a), {usuario.get_full_name() or usuario.username}.")
            return redirect("consultas:dashboard")
        registrar_auditoria_medica(
            usuario=None, accion=AuditoriaMedica.Accion.OTRO,
            ip=obtener_ip(request),
            recurso=f"Login fallido: {(request.POST.get('username') or '')[:60]}",
        )
        messages.error(request, "Usuario o contraseña incorrectos.")
    if request.GET.get("expirada"):
        messages.warning(request, "La sesión anterior expiró por inactividad.")
    return render(request, "consultas/login.html", {"form": formulario})


@login_required
@require_POST
def cerrar_sesion(request):
    registrar_auditoria_medica(
        usuario=request.user, accion=AuditoriaMedica.Accion.LOGOUT,
        ip=obtener_ip(request), recurso="Cierre de sesión manual",
    )
    auth_logout(request)
    messages.info(request, "Sesión cerrada correctamente.")
    return redirect("consultas:login")


@login_required
def dashboard(request):
    usuario = request.user
    hoy = timezone.localdate()
    visibles = services.citas_para(usuario)
    consultas_visibles = Consulta.objects.all()
    if es_medico(usuario):
        consultas_visibles = consultas_visibles.filter(medico=medico_de(usuario))
    elif es_paciente(usuario):
        consultas_visibles = consultas_visibles.filter(cita__paciente=paciente_de(usuario))
    elif not (es_administrador(usuario) or es_recepcionista(usuario)):
        consultas_visibles = consultas_visibles.none()

    estadisticas = {
        "citas_hoy": visibles.filter(fecha=hoy).count(),
        "pendientes": visibles.filter(
            estado=Cita.Estado.PENDIENTE, fecha__gte=hoy
        ).count(),
        "confirmadas": visibles.filter(
            estado=Cita.Estado.CONFIRMADA, fecha__gte=hoy
        ).count(),
        "completadas": visibles.filter(estado=Cita.Estado.COMPLETADA).count(),
        "consultas": consultas_visibles.count() if not es_recepcionista(usuario) else 0,
    }
    proximas = visibles.filter(
        estado__in=ESTADOS_CITA_ACTIVOS, fecha__gte=hoy
    ).order_by("fecha", "hora")[:8]

    contexto = {
        "rol": rol_principal(usuario),
        "estadisticas": estadisticas,
        "proximas": proximas,
        "hoy": hoy,
    }
    if es_administrador(usuario):
        contexto.update({
            "total_pacientes": Paciente.objects.count(),
            "total_medicos": Medico.objects.filter(activo=True).count(),
            "por_especialidad": Especialidad.objects.annotate(total=Count("citas")).order_by("-total"),
            "auditoria_reciente": AuditoriaMedica.objects.select_related("usuario")[:5],
        })
    elif es_medico(usuario):
        contexto["total_pacientes"] = Paciente.objects.filter(
            citas__medico=medico_de(usuario)
        ).distinct().count()
        contexto["notas_recientes"] = NotaClinica.objects.filter(
            consulta__medico=medico_de(usuario)
        ).select_related("consulta", "autor")[:5]
    elif es_paciente(usuario):
        contexto["mis_consultas"] = consultas_visibles.select_related("cita", "medico")[:5]
    elif es_recepcionista(usuario):
        contexto["total_pacientes"] = Paciente.objects.count()
    return render(request, "consultas/dashboard.html", contexto)


@login_required
def agenda(request):
    formulario = BusquedaCitaForm(request.GET or None)
    consulta = services.citas_para(request.user)
    if formulario.is_bound and formulario.is_valid():
        datos = formulario.cleaned_data
        if datos.get("fecha"):
            consulta = consulta.filter(fecha=datos["fecha"])
        else:
            consulta = consulta.filter(fecha__gte=timezone.localdate())
        if datos.get("medico"):
            consulta = consulta.filter(medico=datos["medico"])
        if datos.get("especialidad"):
            consulta = consulta.filter(especialidad=datos["especialidad"])
        if datos.get("estado"):
            consulta = consulta.filter(estado=datos["estado"])
    else:
        consulta = consulta.filter(fecha__gte=timezone.localdate())
    consulta = consulta.select_related("paciente", "medico", "especialidad").order_by("fecha", "hora")
    return render(
        request,
        "consultas/agenda.html",
        {"form": formulario, "page_obj": _paginar(request, consulta, 20)},
    )


@login_required
def cita_detalle(request, pk):
    cita = get_object_or_404(
        Cita.objects.select_related("paciente", "medico", "especialidad"), pk=pk
    )
    if not puede_ver_cita(request.user, cita):
        raise PermissionDenied("No tiene acceso a esta cita.")
    consulta = Consulta.objects.filter(cita=cita).select_related("medico").prefetch_related(
        "notas__autor"
    ).first()
    # La recepción no debe ver información clínica.
    if consulta is not None and not puede_ver_historial(request.user, cita.paciente):
        consulta = None
    medico = medico_de(request.user)
    contexto = {
        "cita": cita,
        "consulta": consulta,
        "puede_cancelar": puede_cancelar_cita(request.user, cita),
        "puede_confirmar": request.user.has_perm("consultas.change_cita") and cita.estado == Cita.Estado.PENDIENTE,
        "puede_consulta": medico is not None
        and cita.medico_id == medico.pk
        and cita.estado == Cita.Estado.CONFIRMADA
        and consulta is None,
        "puede_nota": consulta is not None and medico is not None and consulta.medico_id == medico.pk,
    }
    return render(request, "consultas/cita_detalle.html", contexto)


@login_required
def agendar_cita(request):
    usuario = request.user
    if not (es_paciente(usuario) or es_recepcionista(usuario) or es_administrador(usuario)):
        raise PermissionDenied("Su rol no puede agendar citas.")
    if es_recepcionista(usuario) and not usuario.has_perm("consultas.agendar_cita"):
        raise PermissionDenied("No tiene el permiso para agendar citas.")

    formulario = CitaForm(request.POST or None, usuario=usuario)
    if request.method == "POST" and formulario.is_valid():
        paciente = formulario.cleaned_data.get("paciente") or paciente_de(usuario)
        if paciente is None:
            formulario.add_error(None, "Debe seleccionar un paciente.")
        else:
            try:
                cita = services.agendar_cita(
                    paciente=paciente,
                    medico=formulario.cleaned_data["medico"],
                    especialidad=formulario.cleaned_data["especialidad"],
                    fecha=formulario.cleaned_data["fecha"],
                    hora=formulario.cleaned_data["hora"],
                    motivo=formulario.cleaned_data["motivo"],
                    usuario=usuario,
                    ip=obtener_ip(request),
                )
            except ValidationError as exc:
                formulario.add_error(None, exc.messages)
            else:
                messages.success(
                    request,
                    f"Cita registrada para el {cita.fecha:%d/%m/%Y} a las {cita.hora:%H:%M}.",
                )
                return redirect("consultas:cita_detalle", pk=cita.pk)
    return render(
        request,
        "consultas/cita_form.html",
        {"form": formulario, "medicos_json": formulario.medicos_por_especialidad},
    )


@login_required
@require_POST
def cancelar_cita(request, pk):
    cita = get_object_or_404(Cita.objects.select_related("paciente"), pk=pk)
    if not puede_cancelar_cita(request.user, cita):
        raise PermissionDenied("No puede cancelar esta cita.")
    formulario = CancelarCitaForm(request.POST)
    motivo = formulario.cleaned_data.get("motivo") if formulario.is_valid() else ""
    try:
        services.cancelar_cita(cita, usuario=request.user, motivo=motivo, ip=obtener_ip(request))
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "La cita fue cancelada.")
    return redirect("consultas:cita_detalle", pk=cita.pk)


@require_POST
@permiso_requerido("consultas.change_cita")
def confirmar_cita(request, pk):
    cita = get_object_or_404(Cita, pk=pk)
    try:
        services.confirmar_cita(cita, usuario=request.user, ip=obtener_ip(request))
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Cita confirmada.")
    return redirect("consultas:cita_detalle", pk=cita.pk)


@login_required
def registrar_consulta(request, pk):
    cita = get_object_or_404(
        Cita.objects.select_related("paciente", "medico"), pk=pk
    )
    medico = medico_de(request.user)
    if medico is None or cita.medico_id != medico.pk:
        raise PermissionDenied("Solo el médico de la cita puede registrar la consulta.")
    if cita.estado != Cita.Estado.CONFIRMADA:
        messages.warning(request, "La cita debe estar confirmada para registrar la consulta.")
        return redirect("consultas:cita_detalle", pk=cita.pk)
    if Consulta.objects.filter(cita=cita).exists():
        messages.warning(request, "La cita ya tiene una consulta registrada.")
        return redirect("consultas:cita_detalle", pk=cita.pk)

    formulario = ConsultaForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            services.registrar_consulta(
                cita,
                medico=medico,
                diagnostico=formulario.cleaned_data["diagnostico"],
                tratamiento=formulario.cleaned_data["tratamiento"],
                medicamentos=formulario.cleaned_data["medicamentos"],
                proxima_cita=formulario.cleaned_data["proxima_cita"],
                archivos_referencia=formulario.cleaned_data["archivos_referencia"],
                usuario=request.user,
                ip=obtener_ip(request),
            )
        except ValidationError as exc:
            formulario.add_error(None, exc.messages)
        else:
            messages.success(request, "Consulta registrada. La cita quedó completada.")
            return redirect("consultas:historial", pk=cita.paciente_id)
    return render(
        request,
        "consultas/consulta_form.html",
        {"form": formulario, "cita": cita},
    )


@login_required
def historial(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk)
    if not puede_ver_historial(request.user, paciente):
        raise PermissionDenied("No tiene autorización para ver este historial clínico.")
    consultas = (
        Consulta.objects.filter(cita__paciente=paciente)
        .select_related("cita", "cita__medico", "medico", "cita__especialidad")
        .prefetch_related("notas__autor")
        .order_by("-fecha_registro")
    )
    return render(
        request,
        "consultas/historial.html",
        {"paciente": paciente, "consultas": consultas},
    )


@login_required
def agregar_nota(request, pk):
    consulta = get_object_or_404(
        Consulta.objects.select_related("cita", "medico"), pk=pk
    )
    medico = medico_de(request.user)
    if medico is None or consulta.medico_id != medico.pk:
        raise PermissionDenied("Solo el médico responsable puede agregar notas.")
    formulario = NotaClinicaForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            services.agregar_nota(
                consulta, autor=request.user,
                contenido=formulario.cleaned_data["contenido"], ip=obtener_ip(request),
            )
        except ValidationError as exc:
            formulario.add_error(None, exc.messages)
        else:
            messages.success(request, "Nota clínica agregada. La consulta original no fue modificada.")
            return redirect("consultas:historial", pk=consulta.cita.paciente_id)
    return render(
        request,
        "consultas/nota_form.html",
        {"form": formulario, "consulta": consulta},
    )


@permiso_requerido("consultas.view_paciente")
def pacientes(request):
    formulario = BusquedaPacienteForm(request.GET or None)
    consulta = Paciente.objects.annotate(total_citas=Count("citas"))
    if formulario.is_bound and formulario.is_valid() and formulario.cleaned_data.get("q"):
        q = formulario.cleaned_data["q"]
        consulta = consulta.filter(
            Q(dni__icontains=q)
            | Q(nombres__icontains=q)
            | Q(apellidos__icontains=q)
        )
    return render(
        request,
        "consultas/pacientes.html",
        {"form": formulario, "page_obj": _paginar(request, consulta, 15)},
    )


@permiso_requerido("consultas.add_paciente")
def paciente_crear(request):
    formulario = PacienteForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        paciente = formulario.save()
        messages.success(request, "Paciente registrado correctamente.")
        return redirect("consultas:paciente_editar", pk=paciente.pk)
    return render(
        request,
        "consultas/paciente_form.html",
        {"form": formulario, "titulo": "Registrar paciente"},
    )


@permiso_requerido("consultas.change_paciente")
def paciente_editar(request, pk):
    paciente = get_object_or_404(Paciente, pk=pk)
    formulario = PacienteForm(request.POST or None, instance=paciente)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "Datos del paciente actualizados.")
        return redirect("consultas:pacientes")
    return render(
        request,
        "consultas/paciente_form.html",
        {"form": formulario, "titulo": "Editar paciente", "paciente": paciente},
    )


@permiso_requerido("consultas.view_medico")
def medicos(request):
    consulta = Medico.objects.select_related("especialidad").annotate(
        total_consultas=Count("consultas")
    )
    return render(
        request,
        "consultas/medicos.html",
        {"page_obj": _paginar(request, consulta, 15), "medicos": consulta},
    )


@permiso_requerido("consultas.add_medico")
def medico_crear(request):
    formulario = MedicoForm(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        medico = formulario.save()
        messages.success(request, "Médico registrado. Configure sus horarios en el admin.")
        return redirect("consultas:medicos")
    return render(
        request,
        "consultas/medico_form.html",
        {"form": formulario, "titulo": "Registrar médico"},
    )


@permiso_requerido("consultas.change_medico")
def medico_editar(request, pk):
    medico = get_object_or_404(Medico, pk=pk)
    formulario = MedicoForm(request.POST or None, instance=medico)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "Datos del médico actualizados.")
        return redirect("consultas:medicos")
    return render(
        request,
        "consultas/medico_form.html",
        {"form": formulario, "titulo": "Editar médico", "medico": medico},
    )


@permiso_requerido("consultas.generar_reportes")
def reportes(request):
    por_especialidad = Especialidad.objects.annotate(total=Count("citas")).order_by("-total")
    por_estado = Cita.objects.values("estado").annotate(total=Count("id")).order_by("estado")
    top_medicos = (
        Medico.objects.annotate(total_consultas=Count("consultas"))
        .filter(total_consultas__gt=0)
        .order_by("-total_consultas")[:5]
    )
    pacientes_frecuentes = (
        Paciente.objects.annotate(total_citas=Count("citas"))
        .filter(total_citas__gt=0)
        .order_by("-total_citas")[:5]
    )
    return render(
        request,
        "consultas/reportes.html",
        {
            "por_especialidad": por_especialidad,
            "por_estado": por_estado,
            "top_medicos": top_medicos,
            "pacientes_frecuentes": pacientes_frecuentes,
            "total_citas": Cita.objects.count(),
            "total_consultas": Consulta.objects.count(),
            "total_pacientes": Paciente.objects.count(),
            "total_medicos": Medico.objects.count(),
        },
    )


def acceso_denegado(request, exception=None):
    return render(request, "403.html", status=403)
