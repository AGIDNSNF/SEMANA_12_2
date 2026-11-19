from datetime import date, time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .reglas import (
    dias_habiles,
    dias_por_anio,
    es_dia_habil,
    horas_extra,
    horas_trabajadas,
    jornada_horas,
    saldo_anual_dias,
    solapan,
)
from .validators import (
    justificacion_minima,
    sanitizar_texto,
    validar_correo_corporativo,
    validar_dni,
    validar_sin_html,
)

ESTADOS_SOLICITUD_ACTIVOS = ("pendiente", "aprobada")
TIPOS_CON_SALDO = ("permiso", "vacaciones")


class Area(models.Model):
    nombre = models.CharField("nombre del área", max_length=100, unique=True)
    codigo = models.CharField("código", max_length=10, unique=True)
    jefe = models.ForeignKey(
        "Empleado", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="areas_dirigidas", verbose_name="jefe de área",
    )

    class Meta:
        verbose_name = "área"
        verbose_name_plural = "áreas"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"

    @property
    def total_empleados(self):
        return self.empleados.filter(activo=True).count()


class Empleado(models.Model):
    dni = models.CharField("DNI", max_length=8, unique=True, validators=[validar_dni])
    nombres = models.CharField("nombres", max_length=100)
    apellidos = models.CharField("apellidos", max_length=100)
    email = models.EmailField("correo corporativo", unique=True)
    cargo = models.CharField("cargo", max_length=100)
    area = models.ForeignKey(
        Area, on_delete=models.PROTECT, related_name="empleados", verbose_name="área"
    )
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="empleado", verbose_name="usuario relacionado",
    )
    fecha_ingreso = models.DateField("fecha de ingreso")
    activo = models.BooleanField("activo", default=True)
    sueldo_basico = models.DecimalField(
        "sueldo básico (referencial)", max_digits=10, decimal_places=2, default=0
    )

    class Meta:
        verbose_name = "empleado"
        verbose_name_plural = "empleados"
        ordering = ["apellidos", "nombres"]
        indexes = [
            models.Index(fields=["dni"]),
            models.Index(fields=["area", "activo"]),
            models.Index(fields=["apellidos", "nombres"]),
        ]
        permissions = [
            ("marcar_asistencia", "Puede registrar su propia asistencia"),
            ("crear_solicitud", "Puede solicitar permisos y vacaciones"),
            ("corregir_asistencia", "Puede corregir registros de asistencia"),
            ("aprobar_solicitud", "Puede aprobar o rechazar solicitudes"),
            ("ver_reportes_asistencia", "Puede generar reportes de asistencia"),
        ]

    def __str__(self):
        return f"{self.apellidos}, {self.nombres} · DNI {self.dni}"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}".strip()

    @property
    def es_jefe(self):
        return self.areas_dirigidas.exists()

    def areas_a_cargo(self):
        return self.areas_dirigidas.all()

    def saldo_disponible(self, anio: int | None = None, excluir_pk=None) -> int:
        anio = anio or timezone.localdate().year
        consulta = self.solicitudes.filter(
            estado=Solicitud.Estado.APROBADA, tipo__in=TIPOS_CON_SALDO,
            fecha_inicio__lte=date(anio, 12, 31), fecha_fin__gte=date(anio, 1, 1),
        )
        if excluir_pk:
            consulta = consulta.exclude(pk=excluir_pk)
        consumidos = sum(solicitud.dias_en_anio(anio) for solicitud in consulta)
        return max(saldo_anual_dias() - consumidos, 0)

    def clean(self):
        errores = {}
        self.nombres = sanitizar_texto(self.nombres, 100)
        self.apellidos = sanitizar_texto(self.apellidos, 100)
        self.cargo = sanitizar_texto(self.cargo, 100)
        if self.dni and not self.dni.isdigit():
            errores["dni"] = "El DNI debe contener solo dígitos."
        if self.email:
            try:
                validar_correo_corporativo(self.email)
            except ValidationError as exc:
                errores["email"] = exc.messages
        if self.fecha_ingreso and self.fecha_ingreso > timezone.localdate():
            errores["fecha_ingreso"] = "La fecha de ingreso no puede ser futura."
        if errores:
            raise ValidationError(errores)

    def get_absolute_url(self):
        return reverse("asistencia:empleado_detalle", args=[self.pk])


class RegistroAsistencia(models.Model):
    empleado = models.ForeignKey(
        Empleado, on_delete=models.PROTECT, related_name="registros",
        verbose_name="empleado",
    )
    fecha = models.DateField("fecha", default=timezone.localdate)
    hora_entrada = models.TimeField("hora de entrada", null=True, blank=True)
    hora_salida = models.TimeField("hora de salida", null=True, blank=True)
    observacion = models.CharField("observación", max_length=300, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="registros_marcados", verbose_name="registrado por",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        verbose_name = "registro de asistencia"
        verbose_name_plural = "registros de asistencia"
        ordering = ["-fecha", "empleado__apellidos"]
        constraints = [
            models.UniqueConstraint(
                fields=["empleado", "fecha"], name="asistencia_unica_por_dia"
            )
        ]
        indexes = [
            models.Index(fields=["fecha"]),
            models.Index(fields=["empleado", "fecha"]),
        ]

    def __str__(self):
        return f"{self.empleado.nombre_completo} · {self.fecha:%d/%m/%Y}"

    @property
    def esta_abierto(self):
        return bool(self.hora_entrada and not self.hora_salida)

    @property
    def esta_completo(self):
        return bool(self.hora_entrada and self.hora_salida)

    @property
    def total_horas(self):
        return horas_trabajadas(self.hora_entrada, self.hora_salida)

    @property
    def total_extra(self):
        return horas_extra(self.hora_entrada, self.hora_salida)

    @property
    def tiene_extra(self):
        return self.total_extra > 0

    def clean(self):
        errores = {}
        self.observacion = sanitizar_texto(self.observacion, 300)
        if self.fecha and self.fecha > timezone.localdate():
            errores["fecha"] = "No se puede registrar asistencia en una fecha futura."
        if self.hora_salida and not self.hora_entrada:
            errores["hora_entrada"] = "Debe registrar la entrada antes de la salida."
        if self.hora_entrada and self.hora_salida and self.hora_salida <= self.hora_entrada:
            errores["hora_salida"] = "La hora de salida debe ser posterior a la entrada."
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class CorreccionAsistencia(models.Model):
    registro = models.ForeignKey(
        RegistroAsistencia, on_delete=models.PROTECT, related_name="correcciones",
        verbose_name="registro corregido",
    )
    hora_entrada_anterior = models.TimeField("entrada anterior", null=True, blank=True)
    hora_salida_anterior = models.TimeField("salida anterior", null=True, blank=True)
    hora_entrada_nueva = models.TimeField("entrada nueva")
    hora_salida_nueva = models.TimeField("salida nueva")
    justificacion = models.TextField(
        "justificación",
        validators=[MinLengthValidator(justificacion_minima())],
        help_text="Justificación obligatoria de al menos 50 caracteres.",
    )
    corregido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="correcciones_realizadas", verbose_name="corregido por",
    )
    fecha_correccion = models.DateTimeField("fecha de corrección", auto_now_add=True)

    class Meta:
        verbose_name = "corrección de asistencia"
        verbose_name_plural = "correcciones de asistencia"
        ordering = ["-fecha_correccion", "-id"]
        permissions = []

    def __str__(self):
        return f"Corrección #{self.pk} · {self.registro}"

    def clean(self):
        errores = {}
        self.justificacion = sanitizar_texto(self.justificacion, 800)
        try:
            validar_sin_html(self.justificacion)
        except ValidationError as exc:
            errores["justificacion"] = exc.messages
        if len(self.justificacion or "") < justificacion_minima():
            errores["justificacion"] = (
                f"La justificación debe tener al menos {justificacion_minima()} caracteres."
            )
        if self.hora_entrada_nueva and self.hora_salida_nueva:
            if self.hora_salida_nueva <= self.hora_entrada_nueva:
                errores["hora_salida_nueva"] = (
                    "La salida corregida debe ser posterior a la entrada."
                )
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Las correcciones de asistencia son inmutables; registre una nueva corrección."
            )
        self.full_clean()
        return super().save(*args, **kwargs)


class Solicitud(models.Model):
    class Tipo(models.TextChoices):
        PERMISO = "permiso", "Permiso"
        VACACIONES = "vacaciones", "Vacaciones"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        APROBADA = "aprobada", "Aprobada"
        RECHAZADA = "rechazada", "Rechazada"
        CANCELADA = "cancelada", "Cancelada"

    empleado = models.ForeignKey(
        Empleado, on_delete=models.PROTECT, related_name="solicitudes",
        verbose_name="empleado",
    )
    tipo = models.CharField("tipo", max_length=15, choices=Tipo.choices)
    fecha_inicio = models.DateField("fecha de inicio")
    fecha_fin = models.DateField("fecha de fin")
    motivo = models.TextField("motivo", max_length=500)
    estado = models.CharField(
        "estado", max_length=15, choices=Estado.choices, default=Estado.PENDIENTE
    )
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="solicitudes_revisadas", verbose_name="revisado por",
    )
    fecha_revision = models.DateTimeField("fecha de revisión", null=True, blank=True)
    comentario_revision = models.CharField("comentario de revisión", max_length=300, blank=True)
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    class Meta:
        verbose_name = "solicitud"
        verbose_name_plural = "solicitudes"
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["empleado", "estado"]),
            models.Index(fields=["fecha_inicio", "fecha_fin"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(fecha_fin__gte=models.F("fecha_inicio")),
                name="solicitud_fechas_coherentes",
            )
        ]
        permissions = []

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.empleado.nombre_completo} · {self.fecha_inicio:%d/%m/%Y}"

    @property
    def dias_solicitados(self):
        return dias_habiles(self.fecha_inicio, self.fecha_fin)

    @property
    def dias_calendario(self):
        if not self.fecha_inicio or not self.fecha_fin:
            return 0
        return (self.fecha_fin - self.fecha_inicio).days + 1

    @property
    def es_pendiente(self):
        return self.estado == self.Estado.PENDIENTE

    @property
    def es_activa(self):
        return self.estado in ESTADOS_SOLICITUD_ACTIVOS

    @property
    def estado_visual(self):
        return {
            self.Estado.PENDIENTE: "warning",
            self.Estado.APROBADA: "success",
            self.Estado.RECHAZADA: "danger",
            self.Estado.CANCELADA: "secondary",
        }.get(self.estado, "secondary")

    def dias_en_anio(self, anio):
        return dias_por_anio(self.fecha_inicio, self.fecha_fin).get(anio, 0)

    def clean(self):
        errores = {}
        self.motivo = sanitizar_texto(self.motivo, 500)
        self.comentario_revision = sanitizar_texto(self.comentario_revision, 300)
        try:
            validar_sin_html(self.motivo)
        except ValidationError as exc:
            errores["motivo"] = exc.messages
        if len(self.motivo or "") < 20:
            errores["motivo"] = "El motivo debe tener al menos 20 caracteres."
        if self.fecha_inicio and self.fecha_fin:
            if self.fecha_fin < self.fecha_inicio:
                errores["fecha_fin"] = "La fecha de fin no puede ser anterior al inicio."
            elif self.fecha_inicio < timezone.localdate() and self.estado == self.Estado.PENDIENTE:
                errores["fecha_inicio"] = "La solicitud no puede iniciar en una fecha pasada."
            elif not es_dia_habil(self.fecha_inicio):
                errores["fecha_inicio"] = "La solicitud debe iniciar en un día hábil (lunes a viernes)."
        if self.empleado_id and self.fecha_inicio and self.fecha_fin:
            duplicadas = Solicitud.objects.filter(
                empleado_id=self.empleado_id,
                estado__in=ESTADOS_SOLICITUD_ACTIVOS,
                fecha_inicio__lte=self.fecha_fin,
                fecha_fin__gte=self.fecha_inicio,
            ).exclude(pk=self.pk)
            if duplicadas.exists():
                errores["fecha_inicio"] = "Ya existe una solicitud activa que se superpone con estas fechas."
        if (
            self.empleado_id and self.fecha_inicio and self.fecha_fin
            and self.tipo in TIPOS_CON_SALDO and not errores.get("fecha_fin")
        ):
            for anio, dias in dias_por_anio(self.fecha_inicio, self.fecha_fin).items():
                disponible = self.empleado.saldo_disponible(anio, excluir_pk=self.pk)
                if dias > disponible:
                    errores["fecha_fin"] = (
                        f"Saldo insuficiente para {anio}: solicita {dias} día(s) hábil(es) "
                        f"y dispone de {disponible}. El saldo anual es de "
                        f"{saldo_anual_dias()} días entre permisos y vacaciones."
                    )
                    break
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("asistencia:solicitud_detalle", args=[self.pk])


class AuditoriaAsistencia(models.Model):
    class Accion(models.TextChoices):
        MARCACION = "marcacion", "Marcación de asistencia"
        CORRECCION = "correccion", "Corrección de asistencia"
        SOLICITUD = "solicitud", "Registro de solicitud"
        APROBACION = "aprobacion", "Aprobación de solicitud"
        RECHAZO = "rechazo", "Rechazo de solicitud"
        CANCELACION = "cancelacion", "Cancelación de solicitud"
        ACCESO_DENEGADO = "acceso_denegado", "Acceso denegado"
        LOGIN = "login", "Inicio de sesión"
        LOGOUT = "logout", "Cierre de sesión"
        OTRO = "otro", "Otra acción"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="auditorias_asistencia", verbose_name="usuario",
    )
    empleado = models.ForeignKey(
        Empleado, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="auditorias", verbose_name="empleado",
    )
    accion = models.CharField("acción", max_length=25, choices=Accion.choices)
    fecha = models.DateTimeField("fecha", auto_now_add=True)
    ip = models.GenericIPAddressField("dirección IP", default="127.0.0.1")
    detalle = models.CharField("detalle", max_length=200, blank=True)

    class Meta:
        verbose_name = "auditoría de asistencia"
        verbose_name_plural = "auditorías de asistencia"
        ordering = ["-fecha", "-id"]
        indexes = [models.Index(fields=["accion", "fecha"])]

    def __str__(self):
        return f"{self.get_accion_display()} · {self.usuario or 'anónimo'} · {self.fecha:%d/%m/%Y %H:%M}"
