"""Personalización del Django Admin del caso 1."""
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.html import format_html

from . import services
from .models import ESTADOS_QUE_OCUPAN, Auditoria, Devolucion, Equipo, Laboratorio, Prestamo
from .utils import registrar_auditoria

admin.site.site_header = "UNCP · Administración de Préstamos"
admin.site.site_title = "Préstamos UNCP"


# ---------------------------------------------------------------------------
# Laboratorios
# ---------------------------------------------------------------------------
@admin.register(Laboratorio)
class LaboratorioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "ubicacion", "activo", "total_equipos")
    list_filter = ("activo",)
    search_fields = ("nombre", "codigo", "ubicacion")
    list_editable = ("activo",)

    @admin.display(description="Equipos")
    def total_equipos(self, obj):
        return obj.equipos.count()


# ---------------------------------------------------------------------------
# Equipos
# ---------------------------------------------------------------------------
@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = (
        "codigo_patrimonial", "nombre", "categoria", "laboratorio",
        "estado_coloreado", "stock_total", "disponibles", "mantenimiento",
    )
    list_filter = ("laboratorio", "estado", "categoria")
    search_fields = ("codigo_patrimonial", "nombre", "categoria", "marca")
    readonly_fields = ("fecha_registro", "dias_mantenimiento_admin", "disponibles")
    list_per_page = 25
    actions = ("marcar_en_mantenimiento",)

    fieldsets = (
        ("Identificación", {
            "fields": ("codigo_patrimonial", "nombre", "marca", "modelo", "categoria")
        }),
        ("Ubicación y estado", {"fields": ("laboratorio", "estado", "stock_total")}),
        ("Mantenimiento", {
            "fields": ("fecha_ultimo_mantenimiento", "dias_mantenimiento_admin",
                       "fecha_registro", "disponibles")
        }),
    )

    @admin.display(description="Estado", ordering="estado")
    def estado_coloreado(self, obj):
        colores = {
            Equipo.Estado.OPERATIVO: "#198754",
            Equipo.Estado.MANTENIMIENTO: "#fd7e14",
            Equipo.Estado.BAJA: "#dc3545",
        }
        return format_html(
            '<span style="padding:2px 8px;border-radius:10px;color:#fff;background:{};">{}</span>',
            colores.get(obj.estado, "#6c757d"),
            obj.get_estado_display(),
        )

    @admin.display(description="Disponibles")
    def disponibles(self, obj):
        return obj.cantidad_disponible

    @admin.display(description="Días desde mantenimiento")
    def mantenimiento(self, obj):
        dias = obj.dias_desde_ultimo_mantenimiento
        return "Sin registro" if dias is None else f"{dias} día(s)"

    @admin.display(description="Días desde mantenimiento")
    def dias_mantenimiento_admin(self, obj):
        return self.mantenimiento(obj)

    @admin.action(description="Marcar equipos seleccionados en mantenimiento")
    def marcar_en_mantenimiento(self, request, queryset):
        actualizados = queryset.update(estado=Equipo.Estado.MANTENIMIENTO)
        registrar_auditoria(
            usuario=request.user, accion=Auditoria.Accion.EQUIPO, entidad="Equipo",
            entidad_id=",".join(str(pk) for pk in queryset.values_list("pk", flat=True))[:40],
            descripcion=f"{actualizados} equipo(s) marcados en mantenimiento desde el admin.",
        )
        self.message_user(
            request, f"{actualizados} equipo(s) marcados en mantenimiento.", messages.SUCCESS
        )

    def delete_model(self, request, obj):
        try:
            services.eliminar_equipo(obj, usuario=request.user)
        except ValidationError as exc:
            self.message_user(request, "; ".join(exc.messages), messages.ERROR)

    def delete_queryset(self, request, queryset):
        bloqueados = queryset.filter(prestamos__estado__in=ESTADOS_QUE_OCUPAN).distinct()
        if bloqueados.exists():
            self.message_user(
                request,
                "No se eliminaron equipos con préstamos pendientes, activos o vencidos: "
                + ", ".join(bloqueados.values_list("codigo_patrimonial", flat=True)),
                messages.ERROR,
            )
            return
        codigos = ", ".join(queryset.values_list("codigo_patrimonial", flat=True))
        super().delete_queryset(request, queryset)
        registrar_auditoria(
            usuario=request.user, accion=Auditoria.Accion.EQUIPO, entidad="Equipo",
            descripcion=f"Equipos eliminados desde el admin: {codigos}"[:500],
        )


# ---------------------------------------------------------------------------
# Préstamos
# ---------------------------------------------------------------------------
class DevolucionInline(admin.StackedInline):
    model = Devolucion
    extra = 0
    can_delete = False
    readonly_fields = ("fecha", "estado_equipo_al_retornar", "observaciones",
                       "asistente_responsable", "fecha_registro")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    list_display = (
        "id", "docente", "equipo", "cantidad", "fecha_prestamo",
        "fecha_prevista_devolucion", "estado_coloreado", "dias_retraso",
        "asistente_responsable",
    )
    list_filter = (
        "estado", "equipo__laboratorio",
        ("fecha_prestamo", admin.DateFieldListFilter),
        ("fecha_prevista_devolucion", admin.DateFieldListFilter),
    )
    search_fields = (
        "docente__username", "docente__first_name", "docente__last_name",
        "equipo__codigo_patrimonial", "equipo__nombre",
    )
    date_hierarchy = "fecha_prestamo"
    readonly_fields = ("fecha_creacion", "fecha_actualizacion", "dias_retraso")
    autocomplete_fields = ("docente", "equipo")
    list_select_related = ("docente", "equipo")
    inlines = (DevolucionInline,)
    actions = ("enviar_recordatorio", "marcar_vencidos", "aprobar_solicitudes")
    list_per_page = 25

    fieldsets = (
        ("Solicitante y equipo", {"fields": ("docente", "equipo", "cantidad")}),
        ("Fechas", {"fields": ("fecha_prestamo", "fecha_prevista_devolucion",
                               "fecha_real_devolucion")}),
        ("Gestión", {"fields": ("estado", "asistente_responsable", "observaciones")}),
        ("Metadatos", {"fields": ("fecha_creacion", "fecha_actualizacion", "dias_retraso")}),
    )

    @admin.display(description="Estado", ordering="estado")
    def estado_coloreado(self, obj):
        return format_html(
            '<span style="padding:2px 8px;border-radius:10px;color:#fff;background:{};">{}</span>',
            {
                "pendiente": "#fd7e14", "activo": "#0d6efd", "devuelto": "#198754",
                "vencido": "#dc3545", "rechazado": "#6c757d",
            }.get(obj.estado, "#6c757d"),
            obj.get_estado_display(),
        )

    @admin.display(description="Días de retraso")
    def dias_retraso(self, obj):
        return obj.dias_retraso

    @admin.action(description="Enviar recordatorio de devolución (correo de consola)")
    def enviar_recordatorio(self, request, queryset):
        pendientes = queryset.filter(
            estado__in=(Prestamo.Estado.ACTIVO, Prestamo.Estado.VENCIDO)
        ).select_related("docente", "equipo")
        enviados = 0
        sin_correo = 0
        for prestamo in pendientes:
            if not prestamo.docente.email:
                sin_correo += 1
                continue
            send_mail(
                subject=f"Recordatorio de devolución · Préstamo #{prestamo.pk}",
                message=(
                    f"Estimado(a) {prestamo.docente.get_full_name() or prestamo.docente.username}:\n\n"
                    f"Le recordamos devolver el equipo {prestamo.equipo.nombre} "
                    f"({prestamo.equipo.codigo_patrimonial}), préstamo #{prestamo.pk}, "
                    f"cuya fecha prevista fue {prestamo.fecha_prevista_devolucion:%d/%m/%Y}.\n\n"
                    "Facultad de Ingeniería de Sistemas · UNCP"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[prestamo.docente.email],
                fail_silently=True,
            )
            enviados += 1
        registrar_auditoria(
            usuario=request.user, accion=Auditoria.Accion.OTRO, entidad="Prestamo",
            descripcion=f"Recordatorios enviados: {enviados}; sin correo: {sin_correo}.",
        )
        self.message_user(
            request,
            f"Recordatorios enviados: {enviados}. Omitidos sin correo: {sin_correo}.",
            messages.SUCCESS,
        )

    @admin.action(description="Marcar préstamos activos como vencidos")
    def marcar_vencidos(self, request, queryset):
        total = services.marcar_vencidos(usuario=request.user)
        self.message_user(request, f"Préstamos marcados como vencidos: {total}.", messages.SUCCESS)

    @admin.action(description="Aprobar solicitudes pendientes seleccionadas")
    def aprobar_solicitudes(self, request, queryset):
        aprobados, errores = 0, []
        for prestamo in queryset.filter(estado=Prestamo.Estado.PENDIENTE):
            try:
                services.aprobar_prestamo(prestamo, asistente=request.user)
                aprobados += 1
            except ValidationError as exc:
                errores.append(f"#{prestamo.pk}: {'; '.join(exc.messages)}")
        if aprobados:
            self.message_user(request, f"Aprobados: {aprobados}.", messages.SUCCESS)
        if errores:
            self.message_user(request, " | ".join(errores), messages.ERROR)


@admin.register(Devolucion)
class DevolucionAdmin(admin.ModelAdmin):
    list_display = ("prestamo", "fecha", "estado_equipo_al_retornar",
                    "asistente_responsable", "fecha_registro")
    list_filter = ("estado_equipo_al_retornar", ("fecha", admin.DateFieldListFilter))
    search_fields = ("prestamo__equipo__codigo_patrimonial",
                     "prestamo__docente__username", "observaciones")
    readonly_fields = ("fecha_registro",)
    list_select_related = ("prestamo", "asistente_responsable")
    date_hierarchy = "fecha"


@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    list_display = ("fecha_hora", "usuario", "accion", "entidad", "entidad_id", "ip")
    list_filter = ("accion", ("fecha_hora", admin.DateFieldListFilter))
    search_fields = ("usuario__username", "descripcion", "entidad", "entidad_id")
    readonly_fields = ("fecha_hora", "usuario", "ip", "accion", "entidad",
                       "entidad_id", "descripcion")
    date_hierarchy = "fecha_hora"
    list_per_page = 30

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
