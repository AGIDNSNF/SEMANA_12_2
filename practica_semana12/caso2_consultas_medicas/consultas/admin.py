"""Django Admin del caso 2: agenda, estadísticas y acciones controladas."""
from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Max
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from . import services
from .models import (
    AuditoriaMedica, Cita, Consulta, Especialidad, HorarioAtencion, Medico,
    NotaClinica, Paciente,
)
from .horarios import DIAS_SEMANA

admin.site.site_header = "Centro Médico UNCP · Administración"
admin.site.site_title = "Centro Médico UNCP"


@admin.register(Especialidad)
class EspecialidadAdmin(admin.ModelAdmin):
    list_display = ("nombre", "total_medicos", "total_citas")
    search_fields = ("nombre", "descripcion")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _medicos=Count("medicos", distinct=True), _citas=Count("citas", distinct=True)
        )

    @admin.display(description="Médicos")
    def total_medicos(self, obj):
        return obj._medicos

    @admin.display(description="Citas")
    def total_citas(self, obj):
        return obj._citas


@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = (
        "dni", "apellidos", "nombres", "edad_calculada", "tipo", "email",
        "total_citas", "dias_ultima_consulta",
    )
    list_filter = ("tipo",)
    search_fields = ("dni", "nombres", "apellidos", "email", "codigo_uncp")
    readonly_fields = ("edad_calculada",)
    list_select_related = ("usuario",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _citas=Count("citas", distinct=True), _ultima=Max("consultas__fecha_registro")
        )

    @admin.display(description="Edad")
    def edad_calculada(self, obj):
        return f"{obj.edad} años" if obj.edad is not None else "—"

    @admin.display(description="Citas")
    def total_citas(self, obj):
        return obj._citas

    @admin.display(description="Días desde última consulta")
    def dias_ultima_consulta(self, obj):
        if not obj._ultima:
            return "Sin consultas"
        return (timezone.localdate() - timezone.localtime(obj._ultima).date()).days

    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        if obj:
            campos.append("dni")
        return campos


@admin.register(Medico)
class MedicoAdmin(admin.ModelAdmin):
    list_display = ("nombres", "apellidos", "cmp", "especialidad", "consultorio",
                    "total_consultas", "activo")
    list_filter = ("especialidad", "activo")
    search_fields = ("nombres", "apellidos", "cmp", "consultorio")
    list_select_related = ("especialidad",)
    autocomplete_fields = ("usuario",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _consultas=Count("consultas", distinct=True)
        )

    @admin.display(description="Consultas", ordering="_consultas")
    def total_consultas(self, obj):
        return obj._consultas


@admin.register(HorarioAtencion)
class HorarioAtencionAdmin(admin.ModelAdmin):
    list_display = ("medico", "dia_semana", "hora_inicio", "hora_fin")
    list_filter = ("dia_semana", "medico")
    search_fields = ("medico__nombres", "medico__apellidos", "medico__cmp")
    list_select_related = ("medico",)

    @admin.display(description="Día")
    def dia_semana(self, obj):
        return DIAS_SEMANA[obj.dia_semana]


@admin.register(Cita)
class CitaAdmin(admin.ModelAdmin):
    list_display = (
        "id", "paciente", "medico", "especialidad", "fecha", "hora",
        "estado_coloreado", "fecha_creacion",
    )
    list_filter = (
        "estado", "especialidad", "medico",
        ("fecha", admin.DateFieldListFilter),
    )
    search_fields = (
        "paciente__dni", "paciente__nombres", "paciente__apellidos",
        "medico__nombres", "medico__apellidos", "motivo",
    )
    date_hierarchy = "fecha"
    list_select_related = ("paciente", "medico", "especialidad")
    readonly_fields = ("fecha_creacion", "actualizado_en")
    autocomplete_fields = ("paciente", "medico")
    actions = ("confirmar_citas", "completar_citas", "cancelar_citas")
    list_per_page = 30
    change_list_template = "admin/consultas/cita/change_list.html"

    @admin.display(description="Estado", ordering="estado")
    def estado_coloreado(self, obj):
        return format_html(
            '<span style="padding:2px 8px;border-radius:10px;color:#fff;background:{};">{}</span>',
            {
                "pendiente": "#fd7e14", "confirmada": "#0d6efd",
                "completada": "#198754", "cancelada": "#6c757d",
            }.get(obj.estado, "#6c757d"),
            obj.get_estado_display(),
        )

    # ------------------------------------------------------------------
    # Vistas personalizadas del admin
    # ------------------------------------------------------------------
    def get_urls(self):
        urls = [
            path(
                "agenda/", self.admin_site.admin_view(self.agenda_view),
                name="consultas_cita_agenda",
            ),
            path(
                "reportes/", self.admin_site.admin_view(self.reportes_view),
                name="consultas_cita_reportes",
            ),
        ]
        return urls + super().get_urls()

    def agenda_view(self, request):
        fecha_str = request.GET.get("fecha")
        from django.utils.dateparse import parse_date

        fecha = parse_date(fecha_str) if fecha_str else timezone.localdate()
        citas = (
            Cita.objects.filter(fecha=fecha)
            .select_related("paciente", "medico", "especialidad")
            .order_by("medico__apellidos", "hora")
        )
        contexto = {
            **self.admin_site.each_context(request),
            "title": "Agenda diaria por médico",
            "citas": citas,
            "fecha": fecha,
        }
        return render(request, "admin/consultas/agenda_diaria.html", contexto)

    def reportes_view(self, request):
        contexto = {
            **self.admin_site.each_context(request),
            "title": "Estadísticas del Centro Médico",
            "por_especialidad": Especialidad.objects.annotate(total=Count("citas")).order_by("-total"),
            "top_medicos": Medico.objects.annotate(total=Count("consultas"))
            .filter(total__gt=0).order_by("-total")[:5],
            "pacientes_frecuentes": Paciente.objects.annotate(total=Count("citas"))
            .filter(total__gt=0).order_by("-total")[:5],
            "por_estado": Cita.objects.values("estado").annotate(total=Count("id")),
            "total_citas": Cita.objects.count(),
            "total_consultas": Consulta.objects.count(),
        }
        return render(request, "admin/consultas/reportes.html", contexto)

    # ------------------------------------------------------------------
    # Acciones masivas: reutilizan servicios y respetan el flujo
    # ------------------------------------------------------------------
    @admin.action(description="Confirmar citas pendientes seleccionadas")
    def confirmar_citas(self, request, queryset):
        confirmadas, errores = 0, []
        for cita in queryset.filter(estado=Cita.Estado.PENDIENTE):
            try:
                services.confirmar_cita(cita, usuario=request.user)
                confirmadas += 1
            except ValidationError as exc:
                errores.append(f"#{cita.pk}: {'; '.join(exc.messages)}")
        if confirmadas:
            self.message_user(request, f"Citas confirmadas: {confirmadas}.", messages.SUCCESS)
        if errores:
            self.message_user(request, " | ".join(errores), messages.ERROR)

    @admin.action(description="Marcar como completadas (solo con consulta registrada)")
    def completar_citas(self, request, queryset):
        completadas, errores = 0, []
        for cita in queryset:
            try:
                services.marcar_completada(cita, usuario=request.user)
                completadas += 1
            except ValidationError as exc:
                errores.append(f"#{cita.pk}: {'; '.join(exc.messages)}")
        if completadas:
            self.message_user(request, f"Citas completadas: {completadas}.", messages.SUCCESS)
        if errores:
            self.message_user(
                request,
                "No se crean consultas ficticias. " + " | ".join(errores),
                messages.ERROR,
            )

    @admin.action(description="Cancelar citas seleccionadas")
    def cancelar_citas(self, request, queryset):
        canceladas, errores = 0, []
        for cita in queryset:
            try:
                services.cancelar_cita(cita, usuario=request.user, motivo="Cancelación administrativa")
                canceladas += 1
            except ValidationError as exc:
                errores.append(f"#{cita.pk}: {'; '.join(exc.messages)}")
        if canceladas:
            self.message_user(request, f"Citas canceladas: {canceladas}.", messages.SUCCESS)
        if errores:
            self.message_user(request, " | ".join(errores), messages.ERROR)


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    list_display = ("id", "paciente_admin", "medico", "fecha_registro", "proxima_cita")
    list_filter = ("medico", "medico__especialidad", ("fecha_registro", admin.DateFieldListFilter))
    search_fields = ("cita__paciente__dni", "cita__paciente__apellidos", "diagnostico")
    readonly_fields = (
        "cita", "medico", "diagnostico", "tratamiento", "medicamentos",
        "proxima_cita", "archivos_referencia", "fecha_registro",
    )
    list_select_related = ("cita__paciente", "medico")

    @admin.display(description="Paciente")
    def paciente_admin(self, obj):
        return obj.cita.paciente.nombre_completo

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.has_perm("consultas.ver_historial_clinico")


@admin.register(NotaClinica)
class NotaClinicaAdmin(admin.ModelAdmin):
    list_display = ("consulta", "autor", "fecha")
    list_filter = (("fecha", admin.DateFieldListFilter),)
    search_fields = ("consulta__cita__paciente__dni", "contenido")
    readonly_fields = ("fecha",)
    list_select_related = ("consulta", "autor")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditoriaMedica)
class AuditoriaMedicaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario", "accion", "paciente", "ip", "recurso")
    list_filter = ("accion", ("fecha", admin.DateFieldListFilter))
    search_fields = ("usuario__username", "paciente__dni", "recurso")
    readonly_fields = ("fecha", "usuario", "accion", "paciente", "ip", "recurso")
    date_hierarchy = "fecha"
    list_select_related = ("usuario", "paciente")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
