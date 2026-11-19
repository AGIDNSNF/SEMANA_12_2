"""Django Admin del caso 3: personal, asistencia y solicitudes."""
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from . import services
from .models import (
    Area,
    AuditoriaAsistencia,
    CorreccionAsistencia,
    Empleado,
    RegistroAsistencia,
    Solicitud,
)
from .permissions import empleado_de

admin.site.site_header = "TecnoAndes · Control de Asistencia"
admin.site.site_title = "TecnoAndes"


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "jefe", "total_empleados")
    search_fields = ("nombre", "codigo", "jefe__nombres", "jefe__apellidos")
    autocomplete_fields = ("jefe",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _empleados=Count("empleados", distinct=True)
        )

    @admin.display(description="Empleados activos")
    def total_empleados(self, obj):
        return obj.empleados.filter(activo=True).count()


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = (
        "dni", "apellidos", "nombres", "area", "cargo", "es_jefe_area",
        "saldo_actual", "activo",
    )
    list_filter = ("area", "activo")
    search_fields = ("dni", "nombres", "apellidos", "email", "cargo")
    list_select_related = ("area", "usuario")
    autocomplete_fields = ("area", "usuario")
    readonly_fields = ("saldo_actual",)
    fieldsets = (
        ("Datos personales", {
            "fields": ("dni", "nombres", "apellidos", "email", "cargo")
        }),
        ("Datos laborales", {
            "fields": ("area", "fecha_ingreso", "activo", "sueldo_basico")
        }),
        ("Acceso al sistema", {"fields": ("usuario", "saldo_actual")}),
    )

    @admin.display(description="Jefe de área", boolean=True)
    def es_jefe_area(self, obj):
        return obj.es_jefe

    @admin.display(description="Saldo disponible")
    def saldo_actual(self, obj):
        if not obj.pk:
            return "—"
        return f"{obj.saldo_disponible()} día(s)"


@admin.register(RegistroAsistencia)
class RegistroAsistenciaAdmin(admin.ModelAdmin):
    list_display = (
        "fecha", "empleado", "area_admin", "hora_entrada", "hora_salida",
        "total_horas", "total_extra", "estado_admin",
    )
    list_filter = ("empleado__area", ("fecha", admin.DateFieldListFilter))
    search_fields = (
        "empleado__dni", "empleado__nombres", "empleado__apellidos",
        "empleado__area__nombre",
    )
    date_hierarchy = "fecha"
    list_select_related = ("empleado", "empleado__area")

    @admin.display(description="Área", ordering="empleado__area__nombre")
    def area_admin(self, obj):
        return obj.empleado.area.nombre

    @admin.display(description="Horas", ordering="hora_salida")
    def total_horas(self, obj):
        return obj.total_horas

    @admin.display(description="Extra")
    def total_extra(self, obj):
        extra = obj.total_extra
        return format_html(
            '<strong style="color:#0f766e;">{}</strong>' if extra > 0 else "{}", extra
        )

    @admin.display(description="Estado")
    def estado_admin(self, obj):
        if obj.esta_completo:
            return "Completo"
        if obj.esta_abierto:
            return "Abierto"
        return "Sin salida" if obj.hora_entrada else "Sin registro"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CorreccionAsistencia)
class CorreccionAsistenciaAdmin(admin.ModelAdmin):
    list_display = (
        "fecha_correccion", "registro", "hora_entrada_anterior",
        "hora_salida_anterior", "hora_entrada_nueva", "hora_salida_nueva",
        "corregido_por",
    )
    list_filter = (("fecha_correccion", admin.DateFieldListFilter), "corregido_por")
    search_fields = (
        "registro__empleado__dni", "registro__empleado__apellidos", "justificacion",
    )
    readonly_fields = (
        "registro", "hora_entrada_anterior", "hora_salida_anterior",
        "hora_entrada_nueva", "hora_salida_nueva", "justificacion",
        "corregido_por", "fecha_correccion",
    )
    list_select_related = ("registro", "registro__empleado", "corregido_por")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Solicitud)
class SolicitudAdmin(admin.ModelAdmin):
    list_display = (
        "id", "empleado", "area_admin", "tipo", "fecha_inicio", "fecha_fin",
        "dias_solicitados", "estado_coloreado", "revisado_por",
    )
    list_filter = ("estado", "tipo", "empleado__area")
    search_fields = (
        "empleado__dni", "empleado__nombres", "empleado__apellidos", "motivo",
    )
    date_hierarchy = "fecha_inicio"
    list_select_related = ("empleado", "empleado__area", "revisado_por")
    actions = ("aprobar_solicitudes", "rechazar_solicitudes")
    change_list_template = "admin/asistencia/solicitud/change_list.html"
    list_per_page = 30

    def get_readonly_fields(self, request, obj=None):
        return tuple(campo.name for campo in Solicitud._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Área", ordering="empleado__area__nombre")
    def area_admin(self, obj):
        return obj.empleado.area.nombre

    @admin.display(description="Días hábiles")
    def dias_solicitados(self, obj):
        return obj.dias_solicitados

    @admin.display(description="Estado", ordering="estado")
    def estado_coloreado(self, obj):
        return format_html(
            '<span style="padding:2px 8px;border-radius:10px;color:#fff;background:{};">{}</span>',
            {
                "pendiente": "#d97706", "aprobada": "#15803d",
                "rechazada": "#b91c1c", "cancelada": "#64748b",
            }.get(obj.estado, "#64748b"),
            obj.get_estado_display(),
        )

    @admin.action(description="Aprobar solicitudes pendientes seleccionadas")
    def aprobar_solicitudes(self, request, queryset):
        aprobadas, errores = 0, []
        for solicitud in queryset.filter(estado=Solicitud.Estado.PENDIENTE):
            try:
                services.resolver_solicitud(
                    solicitud, usuario=request.user, aprobar=True,
                    comentario="Aprobación administrativa",
                )
                aprobadas += 1
            except ValidationError as exc:
                errores.append(f"#{solicitud.pk}: {'; '.join(exc.messages)}")
        if aprobadas:
            self.message_user(request, f"Aprobadas: {aprobadas}.", messages.SUCCESS)
        if errores:
            self.message_user(request, " | ".join(errores), messages.ERROR)

    @admin.action(description="Rechazar solicitudes pendientes seleccionadas")
    def rechazar_solicitudes(self, request, queryset):
        rechazadas, errores = 0, []
        for solicitud in queryset.filter(estado=Solicitud.Estado.PENDIENTE):
            try:
                services.resolver_solicitud(
                    solicitud, usuario=request.user, aprobar=False,
                    comentario="Rechazo administrativo",
                )
                rechazadas += 1
            except ValidationError as exc:
                errores.append(f"#{solicitud.pk}: {'; '.join(exc.messages)}")
        if rechazadas:
            self.message_user(request, f"Rechazadas: {rechazadas}.", messages.SUCCESS)
        if errores:
            self.message_user(request, " | ".join(errores), messages.ERROR)


@admin.register(AuditoriaAsistencia)
class AuditoriaAsistenciaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "usuario", "accion", "empleado", "ip", "detalle")
    list_filter = ("accion", ("fecha", admin.DateFieldListFilter))
    search_fields = ("usuario__username", "empleado__dni", "detalle")
    date_hierarchy = "fecha"
    readonly_fields = ("usuario", "empleado", "accion", "fecha", "ip", "detalle")
    list_select_related = ("usuario", "empleado")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
