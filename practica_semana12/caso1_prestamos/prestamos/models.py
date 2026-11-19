from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q, Sum
from django.urls import reverse
from django.utils import timezone

from .validators import (
    sanitizar_texto,
    validar_codigo_laboratorio,
    validar_codigo_patrimonial,
    validar_sin_html,
)

# Estados que ocupan stock físico del equipo.
ESTADOS_QUE_OCUPAN = ("pendiente", "activo", "vencido")
MAX_PRESTAMOS_ACTIVOS = 3


class Laboratorio(models.Model):
    nombre = models.CharField("nombre", max_length=100, unique=True)
    codigo = models.CharField(
        "código", max_length=20, unique=True, validators=[validar_codigo_laboratorio]
    )
    ubicacion = models.CharField("ubicación", max_length=150)
    descripcion = models.TextField("descripción", blank=True, max_length=500)
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "laboratorio"
        verbose_name_plural = "laboratorios"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"

    def clean(self):
        self.descripcion = sanitizar_texto(self.descripcion, 500)

    @property
    def equipos_operativos(self):
        return self.equipos.filter(estado=Equipo.Estado.OPERATIVO).count()


class Equipo(models.Model):
    class Estado(models.TextChoices):
        OPERATIVO = "operativo", "Operativo"
        MANTENIMIENTO = "mantenimiento", "Mantenimiento"
        BAJA = "baja", "Baja"

    codigo_patrimonial = models.CharField(
        "código patrimonial",
        max_length=30,
        unique=True,
        validators=[validar_codigo_patrimonial],
    )
    nombre = models.CharField("nombre", max_length=120)
    marca = models.CharField("marca", max_length=60)
    modelo = models.CharField("modelo", max_length=60, blank=True)
    categoria = models.CharField("categoría", max_length=60)
    estado = models.CharField(
        "estado", max_length=20, choices=Estado.choices, default=Estado.OPERATIVO
    )
    laboratorio = models.ForeignKey(
        Laboratorio, on_delete=models.PROTECT, related_name="equipos", verbose_name="laboratorio"
    )
    stock_total = models.PositiveIntegerField(
        "stock total", default=1, validators=[MinValueValidator(1)]
    )
    fecha_ultimo_mantenimiento = models.DateField(
        "fecha de último mantenimiento", null=True, blank=True
    )
    fecha_registro = models.DateTimeField("fecha de registro", auto_now_add=True)

    class Meta:
        verbose_name = "equipo"
        verbose_name_plural = "equipos"
        ordering = ["nombre"]
        constraints = [
            models.CheckConstraint(
                condition=Q(stock_total__gte=1), name="equipo_stock_positivo"
            ),
        ]
        indexes = [
            models.Index(fields=["estado", "laboratorio"]),
            models.Index(fields=["categoria"]),
        ]

    def __str__(self):
        return f"{self.codigo_patrimonial} · {self.nombre}"

    def clean(self):
        self.nombre = sanitizar_texto(self.nombre, 120)
        self.marca = sanitizar_texto(self.marca, 60)
        self.modelo = sanitizar_texto(self.modelo, 60)
        self.categoria = sanitizar_texto(self.categoria, 60)
        if self.fecha_ultimo_mantenimiento and self.fecha_ultimo_mantenimiento > timezone.localdate():
            raise ValidationError(
                {"fecha_ultimo_mantenimiento": "El mantenimiento no puede estar en el futuro."}
            )
        if self.stock_total is not None and self.stock_total < 1:
            raise ValidationError({"stock_total": "El stock total debe ser al menos 1."})

    @property
    def dias_desde_ultimo_mantenimiento(self):
        if not self.fecha_ultimo_mantenimiento:
            return None
        return (timezone.localdate() - self.fecha_ultimo_mantenimiento).days

    @property
    def cantidad_prestada(self):
        total = self.prestamos.filter(estado__in=ESTADOS_QUE_OCUPAN).aggregate(
            total=Sum("cantidad")
        )["total"]
        return total or 0

    @property
    def cantidad_disponible(self):
        return max(self.stock_total - self.cantidad_prestada, 0)

    @property
    def estado_visual(self):
        colores = {
            self.Estado.OPERATIVO: ("success", "Operativo"),
            self.Estado.MANTENIMIENTO: ("warning", "Mantenimiento"),
            self.Estado.BAJA: ("danger", "Baja"),
        }
        clase, texto = colores.get(self.estado, ("secondary", self.estado))
        return {"clase": f"bg-{clase}", "texto": texto}

    @property
    def disponible_visual(self):
        if self.estado != self.Estado.OPERATIVO:
            return {"clase": "bg-secondary", "texto": "No prestable"}
        if self.cantidad_disponible <= 0:
            return {"clase": "bg-danger", "texto": "Sin stock"}
        return {"clase": "bg-success", "texto": f"{self.cantidad_disponible} disponible(s)"}

    def get_absolute_url(self):
        return reverse("prestamos:equipo_detalle", args=[self.pk])

    def tiene_prestamos_activos(self):
        return self.prestamos.filter(estado__in=ESTADOS_QUE_OCUPAN).exists()


class Prestamo(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ACTIVO = "activo", "Activo"
        DEVUELTO = "devuelto", "Devuelto"
        VENCIDO = "vencido", "Vencido"
        RECHAZADO = "rechazado", "Rechazado"

    docente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="prestamos_solicitados",
        verbose_name="docente",
    )
    equipo = models.ForeignKey(
        Equipo, on_delete=models.PROTECT, related_name="prestamos", verbose_name="equipo"
    )
    cantidad = models.PositiveIntegerField(
        "cantidad", default=1, validators=[MinValueValidator(1)]
    )
    fecha_prestamo = models.DateField("fecha de préstamo", default=timezone.localdate)
    fecha_prevista_devolucion = models.DateField("fecha prevista de devolución")
    fecha_real_devolucion = models.DateField("fecha real de devolución", null=True, blank=True)
    estado = models.CharField(
        "estado", max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )
    observaciones = models.TextField("observaciones", blank=True, max_length=500)
    asistente_responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prestamos_gestionados",
        verbose_name="asistente responsable",
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "préstamo"
        verbose_name_plural = "préstamos"
        ordering = ["-fecha_prestamo", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(cantidad__gt=0), name="prestamo_cantidad_positiva"
            ),
            models.CheckConstraint(
                condition=Q(fecha_prevista_devolucion__gt=F("fecha_prestamo")),
                name="prestamo_fechas_coherentes",
            ),
        ]
        indexes = [
            models.Index(fields=["estado", "fecha_prevista_devolucion"]),
            models.Index(fields=["docente", "estado"]),
        ]
        permissions = [
            ("ver_reportes", "Puede ver reportes de préstamos"),
            ("gestionar_equipos", "Puede gestionar el catálogo de equipos"),
            ("registrar_prestamo", "Puede registrar préstamos en ventanilla"),
        ]

    def __str__(self):
        return f"Préstamo #{self.pk} · {self.equipo} · {self.docente}"

    # ------------------------------------------------------------------
    # Validaciones de negocio (se ejecutan también desde services.py)
    # ------------------------------------------------------------------
    def clean(self):
        errores = {}
        self.observaciones = sanitizar_texto(self.observaciones, 500)
        try:
            validar_sin_html(self.observaciones)
        except ValidationError as exc:
            errores["observaciones"] = exc.messages

        if self.fecha_prestamo and self.fecha_prevista_devolucion:
            if self.fecha_prevista_devolucion <= self.fecha_prestamo:
                errores["fecha_prevista_devolucion"] = (
                    "La fecha prevista de devolución debe ser posterior a la fecha de préstamo."
                )

        if self.cantidad is not None and self.cantidad <= 0:
            errores["cantidad"] = "La cantidad debe ser mayor que cero."

        if self.equipo_id and self.estado in ESTADOS_QUE_OCUPAN:
            if self.equipo.estado != Equipo.Estado.OPERATIVO:
                errores["equipo"] = "Solo se pueden prestar equipos en estado Operativo."
            disponible = self.equipo.cantidad_disponible
            if self.pk:
                actual = Prestamo.objects.filter(pk=self.pk).values_list(
                    "cantidad", flat=True
                ).first()
                if actual and self.estado in ESTADOS_QUE_OCUPAN:
                    disponible += actual
            if self.cantidad and self.cantidad > disponible:
                errores["cantidad"] = (
                    f"Stock insuficiente: se solicitan {self.cantidad} y solo hay "
                    f"{disponible} disponible(s)."
                )

        if self.docente_id and self.estado in ESTADOS_QUE_OCUPAN:
            consulta = Prestamo.objects.filter(
                docente_id=self.docente_id, estado__in=ESTADOS_QUE_OCUPAN
            )
            if self.pk:
                consulta = consulta.exclude(pk=self.pk)
            if consulta.count() >= MAX_PRESTAMOS_ACTIVOS:
                errores["docente"] = (
                    f"El docente ya tiene {MAX_PRESTAMOS_ACTIVOS} préstamos activos. "
                    "Debe devolver uno antes de solicitar otro."
                )

        if errores:
            raise ValidationError(errores)

    # ------------------------------------------------------------------
    @property
    def dias_retraso(self):
        if self.estado == self.Estado.DEVUELTO:
            referencia = self.fecha_real_devolucion
        else:
            referencia = timezone.localdate()
        if not referencia or not self.fecha_prevista_devolucion:
            return 0
        return max((referencia - self.fecha_prevista_devolucion).days, 0)

    @property
    def esta_vencido(self):
        return (
            self.estado in (self.Estado.ACTIVO, self.Estado.VENCIDO)
            and self.fecha_prevista_devolucion < timezone.localdate()
        )

    @property
    def puede_devolverse(self):
        return self.estado in (self.Estado.ACTIVO, self.Estado.VENCIDO) and not hasattr(
            self, "devolucion"
        )

    @property
    def estado_visual(self):
        colores = {
            self.Estado.PENDIENTE: "warning",
            self.Estado.ACTIVO: "primary",
            self.Estado.DEVUELTO: "success",
            self.Estado.VENCIDO: "danger",
            self.Estado.RECHAZADO: "secondary",
        }
        return f"bg-{colores.get(self.estado, 'secondary')}"

    def get_absolute_url(self):
        return reverse("prestamos:prestamo_detalle", args=[self.pk])


class Devolucion(models.Model):
    class EstadoEquipo(models.TextChoices):
        OPERATIVO = "operativo", "Operativo"
        MANTENIMIENTO = "mantenimiento", "Mantenimiento"
        BAJA = "baja", "Baja"

    prestamo = models.OneToOneField(
        Prestamo, on_delete=models.PROTECT, related_name="devolucion", verbose_name="préstamo"
    )
    fecha = models.DateField("fecha", default=timezone.localdate)
    estado_equipo_al_retornar = models.CharField(
        "estado del equipo al retornar",
        max_length=20,
        choices=EstadoEquipo.choices,
        default=EstadoEquipo.OPERATIVO,
    )
    observaciones = models.TextField("observaciones", blank=True, max_length=500)
    asistente_responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="devoluciones_registradas",
        verbose_name="asistente responsable",
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "devolución"
        verbose_name_plural = "devoluciones"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Devolución del préstamo #{self.prestamo_id}"

    def clean(self):
        errores = {}
        self.observaciones = sanitizar_texto(self.observaciones, 500)
        if self.prestamo_id and self.prestamo.fecha_real_devolucion:
            errores["prestamo"] = "Este préstamo ya tiene una devolución registrada."
        if self.prestamo_id and self.prestamo.estado == Prestamo.Estado.RECHAZADO:
            errores["prestamo"] = "No se puede devolver un préstamo rechazado."
        if self.fecha and self.fecha > timezone.localdate():
            errores["fecha"] = "La fecha de devolución no puede ser futura."
        if errores:
            raise ValidationError(errores)


class Auditoria(models.Model):
    class Accion(models.TextChoices):
        LOGIN = "login", "Inicio de sesión"
        LOGOUT = "logout", "Cierre de sesión"
        LOGIN_FALLIDO = "login_fallido", "Intento de acceso fallido"
        SOLICITUD = "solicitud", "Solicitud de préstamo"
        APROBACION = "aprobacion", "Aprobación de préstamo"
        RECHAZO = "rechazo", "Rechazo de préstamo"
        DEVOLUCION = "devolucion", "Registro de devolución"
        EQUIPO = "equipo", "Gestión de equipo"
        ACCESO_DENEGADO = "acceso_denegado", "Acceso no autorizado"
        OTRO = "otro", "Otra acción"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auditorias",
        verbose_name="usuario",
    )
    fecha_hora = models.DateTimeField("fecha y hora", auto_now_add=True)
    ip = models.GenericIPAddressField("dirección IP", default="127.0.0.1")
    accion = models.CharField("acción", max_length=30, choices=Accion.choices)
    entidad = models.CharField("entidad afectada", max_length=60, blank=True)
    entidad_id = models.CharField("identificador del registro", max_length=40, blank=True)
    descripcion = models.CharField("descripción", max_length=500, blank=True)

    class Meta:
        verbose_name = "auditoría"
        verbose_name_plural = "auditorías"
        ordering = ["-fecha_hora", "-id"]
        indexes = [models.Index(fields=["accion", "fecha_hora"])]

    def __str__(self):
        return f"{self.get_accion_display()} · {self.usuario or 'anónimo'} · {self.fecha_hora:%d/%m/%Y %H:%M}"
