from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .horarios import (
    DIAS_SEMANA,
    ESTADOS_CITA_ACTIVOS,
    hora_fin,
    se_solapan,
    validar_horario_general,
    validar_horario_medico,
)
from .validators import (
    sanitizar_texto,
    validar_cmp,
    validar_correo_institucional,
    validar_dni,
    validar_sin_html,
)


class Especialidad(models.Model):
    nombre = models.CharField("nombre", max_length=80, unique=True)
    descripcion = models.TextField("descripción", blank=True, max_length=400)

    class Meta:
        verbose_name = "especialidad"
        verbose_name_plural = "especialidades"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def clean(self):
        self.descripcion = sanitizar_texto(self.descripcion, 400)


class Paciente(models.Model):
    class Tipo(models.TextChoices):
        ESTUDIANTE = "estudiante", "Estudiante"
        DOCENTE = "docente", "Docente"

    dni = models.CharField("DNI", max_length=8, unique=True, validators=[validar_dni])
    nombres = models.CharField("nombres", max_length=100)
    apellidos = models.CharField("apellidos", max_length=100)
    fecha_nacimiento = models.DateField("fecha de nacimiento")
    tipo = models.CharField("tipo", max_length=15, choices=Tipo.choices, default=Tipo.ESTUDIANTE)
    codigo_uncp = models.CharField(
        "código UNCP", max_length=15, blank=True, null=True, unique=True
    )
    email = models.EmailField("correo electrónico")
    alergias = models.TextField("alergias conocidas", blank=True, max_length=500)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paciente",
        verbose_name="usuario relacionado",
    )

    class Meta:
        verbose_name = "paciente"
        verbose_name_plural = "pacientes"
        ordering = ["apellidos", "nombres"]
        permissions = [
            ("ver_historial_clinico", "Puede ver historiales clínicos autorizados"),
            ("agendar_cita", "Puede agendar citas"),
            ("cancelar_cita", "Puede cancelar citas"),
            ("generar_reportes", "Puede generar reportes médicos"),
        ]
        indexes = [models.Index(fields=["dni"]), models.Index(fields=["apellidos", "nombres"])]

    def __str__(self):
        return f"{self.apellidos}, {self.nombres} · DNI {self.dni}"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}".strip()

    @property
    def edad(self):
        if not self.fecha_nacimiento:
            return None
        hoy = timezone.localdate()
        return hoy.year - self.fecha_nacimiento.year - (
            (hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day)
        )

    @property
    def dias_desde_ultima_consulta(self):
        ultima = (
            self.consultas.order_by("-fecha_registro")
            .values_list("fecha_registro", flat=True)
            .first()
        )
        if not ultima:
            return None
        return (timezone.localdate() - timezone.localtime(ultima).date()).days

    def clean(self):
        errores = {}
        self.nombres = sanitizar_texto(self.nombres, 100)
        self.apellidos = sanitizar_texto(self.apellidos, 100)
        self.alergias = sanitizar_texto(self.alergias, 500)
        if self.dni and not self.dni.isdigit():
            errores["dni"] = "El DNI debe contener solo dígitos."
        if self.fecha_nacimiento and self.fecha_nacimiento > timezone.localdate():
            errores["fecha_nacimiento"] = "La fecha de nacimiento no puede ser futura."
        if self.tipo == self.Tipo.ESTUDIANTE and self.email:
            try:
                validar_correo_institucional(self.email)
            except ValidationError as exc:
                errores["email"] = exc.messages
        if errores:
            raise ValidationError(errores)


class Medico(models.Model):
    nombres = models.CharField("nombres", max_length=100)
    apellidos = models.CharField("apellidos", max_length=100)
    cmp = models.CharField("CMP", max_length=5, unique=True, validators=[validar_cmp])
    especialidad = models.ForeignKey(
        Especialidad, on_delete=models.PROTECT, related_name="medicos",
        verbose_name="especialidad",
    )
    consultorio = models.CharField("consultorio", max_length=30)
    activo = models.BooleanField("activo", default=True)
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medico",
        verbose_name="usuario relacionado",
    )

    class Meta:
        verbose_name = "médico"
        verbose_name_plural = "médicos"
        ordering = ["apellidos", "nombres"]

    def __str__(self):
        return f"Dr(a). {self.nombres} {self.apellidos} · CMP {self.cmp}"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}".strip()

    def clean(self):
        self.nombres = sanitizar_texto(self.nombres, 100)
        self.apellidos = sanitizar_texto(self.apellidos, 100)
        self.consultorio = sanitizar_texto(self.consultorio, 30)
        if self.cmp and not self.cmp.isdigit():
            raise ValidationError({"cmp": "El CMP debe contener solo dígitos."})

    def horario_resumen(self):
        return ", ".join(
            f"{DIAS_SEMANA[h.dia_semana][:3]} {h.hora_inicio:%H:%M}-{h.hora_fin:%H:%M}"
            for h in self.horarios.all()
        )


class HorarioAtencion(models.Model):
    class Dia(models.IntegerChoices):
        LUNES = 0, "Lunes"
        MARTES = 1, "Martes"
        MIERCOLES = 2, "Miércoles"
        JUEVES = 3, "Jueves"
        VIERNES = 4, "Viernes"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    medico = models.ForeignKey(
        Medico, on_delete=models.CASCADE, related_name="horarios", verbose_name="médico"
    )
    dia_semana = models.IntegerField("día de la semana", choices=Dia.choices)
    hora_inicio = models.TimeField("hora de inicio")
    hora_fin = models.TimeField("hora de fin")

    class Meta:
        verbose_name = "horario de atención"
        verbose_name_plural = "horarios de atención"
        ordering = ["medico", "dia_semana", "hora_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["medico", "dia_semana", "hora_inicio"],
                name="horario_unico_por_medico_dia",
            )
        ]

    def __str__(self):
        return f"{self.medico.nombre_completo} · {DIAS_SEMANA[self.dia_semana]} {self.hora_inicio:%H:%M}-{self.hora_fin:%H:%M}"

    def clean(self):
        errores = {}
        if self.dia_semana == self.Dia.DOMINGO:
            errores["dia_semana"] = "El Centro Médico no atiende los domingos."
        if self.hora_inicio and self.hora_fin and self.hora_inicio >= self.hora_fin:
            errores["hora_fin"] = "La hora de fin debe ser posterior a la hora de inicio."
        if not errores and self.hora_inicio and self.hora_fin:
            valido, mensaje = validar_horario_general(
                _fecha_de_dia(self.dia_semana), self.hora_inicio, duracion=0
            )
            fin_permitido = _fin_general(self.dia_semana)
            if not valido:
                errores["hora_inicio"] = mensaje
            elif self.hora_fin > fin_permitido:
                errores["hora_fin"] = (
                    f"El horario debe cerrar a más tardar a las {fin_permitido:%H:%M}."
                )
        if not errores and self.medico_id:
            otros = HorarioAtencion.objects.filter(
                medico_id=self.medico_id, dia_semana=self.dia_semana
            ).exclude(pk=self.pk)
            for otro in otros:
                if se_solapan(self.hora_inicio, self.hora_fin, otro.hora_inicio, otro.hora_fin):
                    errores["hora_inicio"] = "El horario se superpone con otro del mismo médico."
                    break
        if errores:
            raise ValidationError(errores)


def _fecha_de_dia(dia_semana: int):
    """Fecha de referencia (semana del 2024-01-01, lunes) para validar horarios."""
    from datetime import date, timedelta

    return date(2024, 1, 1) + timedelta(days=dia_semana)


def _fin_general(dia_semana: int):
    from .horarios import HORARIO_GENERAL

    rango = HORARIO_GENERAL.get(dia_semana)
    return rango[1] if rango else None


class Cita(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CONFIRMADA = "confirmada", "Confirmada"
        COMPLETADA = "completada", "Completada"
        CANCELADA = "cancelada", "Cancelada"

    paciente = models.ForeignKey(
        Paciente, on_delete=models.PROTECT, related_name="citas", verbose_name="paciente"
    )
    medico = models.ForeignKey(
        Medico, on_delete=models.PROTECT, related_name="citas", verbose_name="médico"
    )
    especialidad = models.ForeignKey(
        Especialidad, on_delete=models.PROTECT, related_name="citas",
        verbose_name="especialidad",
    )
    fecha = models.DateField("fecha")
    hora = models.TimeField("hora")
    motivo = models.TextField(
        "motivo de consulta", max_length=500, validators=[MinLengthValidator(20)]
    )
    estado = models.CharField(
        "estado", max_length=15, choices=Estado.choices, default=Estado.PENDIENTE
    )
    fecha_creacion = models.DateTimeField("fecha de creación", auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cita"
        verbose_name_plural = "citas"
        ordering = ["fecha", "hora"]
        indexes = [
            models.Index(fields=["medico", "fecha"]),
            models.Index(fields=["paciente", "fecha"]),
            models.Index(fields=["estado"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["medico", "fecha", "hora"],
                condition=models.Q(estado__in=ESTADOS_CITA_ACTIVOS),
                name="cita_unica_medico_franja_activa",
            ),
            models.UniqueConstraint(
                fields=["paciente", "fecha"],
                condition=models.Q(estado__in=ESTADOS_CITA_ACTIVOS),
                name="cita_unica_paciente_dia_activa",
            ),
        ]

    def __str__(self):
        return f"Cita {self.fecha:%d/%m/%Y} {self.hora:%H:%M} · {self.paciente}"

    @property
    def hora_fin(self):
        return hora_fin(self.hora)

    @property
    def estado_visual(self):
        return {
            self.Estado.PENDIENTE: "warning",
            self.Estado.CONFIRMADA: "primary",
            self.Estado.COMPLETADA: "success",
            self.Estado.CANCELADA: "secondary",
        }.get(self.estado, "secondary")

    @property
    def es_activa(self):
        return self.estado in ESTADOS_CITA_ACTIVOS

    def get_absolute_url(self):
        return reverse("consultas:cita_detalle", args=[self.pk])

    def clean(self):
        errores = {}
        self.motivo = sanitizar_texto(self.motivo, 500)
        try:
            validar_sin_html(self.motivo)
        except ValidationError as exc:
            errores["motivo"] = exc.messages
        if len(self.motivo or "") < 20:
            errores["motivo"] = "El motivo debe tener al menos 20 caracteres."

        if self.medico_id and self.especialidad_id and self.medico.especialidad_id != self.especialidad_id:
            errores["especialidad"] = (
                "La especialidad debe coincidir con la del médico seleccionado."
            )

        if self.estado in ESTADOS_CITA_ACTIVOS and self.fecha and self.hora:
            hoy = timezone.localdate()
            if self.fecha < hoy:
                errores["fecha"] = "No se pueden agendar citas en fechas pasadas."
            elif self.fecha == hoy and self.hora <= timezone.localtime().time():
                errores["hora"] = "La hora seleccionada ya pasó. Elija un horario posterior."

            valido, mensaje = validar_horario_general(self.fecha, self.hora)
            if not valido:
                errores["hora"] = mensaje
            elif self.medico_id:
                valido_medico, mensaje_medico = validar_horario_medico(
                    self.medico, self.fecha, self.hora
                )
                if not valido_medico:
                    errores["hora"] = mensaje_medico

            # Un paciente no puede tener dos citas activas el mismo día.
            if self.paciente_id and "fecha" not in errores:
                duplicadas = Cita.objects.filter(
                    paciente_id=self.paciente_id,
                    fecha=self.fecha,
                    estado__in=ESTADOS_CITA_ACTIVOS,
                ).exclude(pk=self.pk)
                if duplicadas.exists():
                    errores["fecha"] = "El paciente ya tiene una cita activa ese día."

            # Un médico no puede tener citas superpuestas.
            if self.medico_id and "hora" not in errores:
                inicio = self.hora
                fin = self.hora_fin
                candidatas = Cita.objects.filter(
                    medico_id=self.medico_id,
                    fecha=self.fecha,
                    estado__in=ESTADOS_CITA_ACTIVOS,
                ).exclude(pk=self.pk)
                for candidata in candidatas:
                    if se_solapan(inicio, fin, candidata.hora, candidata.hora_fin):
                        errores["hora"] = (
                            f"El médico ya tiene una cita de {candidata.hora:%H:%M} a "
                            f"{candidata.hora_fin:%H:%M}."
                        )
                        break

        if errores:
            raise ValidationError(errores)


class Consulta(models.Model):
    cita = models.OneToOneField(
        Cita, on_delete=models.PROTECT, related_name="consulta", verbose_name="cita"
    )
    diagnostico = models.TextField("diagnóstico", max_length=1000)
    tratamiento = models.TextField("tratamiento", max_length=1000)
    medicamentos = models.TextField("medicamentos recetados", blank=True, max_length=800)
    proxima_cita = models.DateField("próxima cita de control", null=True, blank=True)
    archivos_referencia = models.CharField(
        "referencias de archivos (simuladas)", max_length=300, blank=True,
        help_text="Rutas o nombres de archivo simulados; el sistema no almacena archivos clínicos.",
    )
    fecha_registro = models.DateTimeField("fecha de registro", auto_now_add=True)
    medico = models.ForeignKey(
        Medico, on_delete=models.PROTECT, related_name="consultas", verbose_name="médico responsable"
    )

    class Meta:
        verbose_name = "consulta"
        verbose_name_plural = "consultas"
        ordering = ["-fecha_registro"]
        permissions = []

    def __str__(self):
        return f"Consulta de {self.cita.paciente.nombre_completo} ({self.fecha_registro:%d/%m/%Y})"

    def clean(self):
        errores = {}
        self.diagnostico = sanitizar_texto(self.diagnostico, 1000)
        self.tratamiento = sanitizar_texto(self.tratamiento, 1000)
        self.medicamentos = sanitizar_texto(self.medicamentos, 800)
        if not self.diagnostico:
            errores["diagnostico"] = "El diagnóstico es obligatorio."
        if not self.tratamiento:
            errores["tratamiento"] = "El tratamiento es obligatorio."
        if self.cita_id:
            if self.medico_id and self.cita.medico_id != self.medico_id:
                errores["medico"] = "El médico responsable debe ser el de la cita."
            if self.cita.estado not in (Cita.Estado.CONFIRMADA, Cita.Estado.COMPLETADA):
                errores["cita"] = "Solo se puede registrar consulta de una cita confirmada."
            if Consulta.objects.filter(cita_id=self.cita_id).exclude(pk=self.pk).exists():
                errores["cita"] = "Esta cita ya tiene una consulta registrada."
        if self.proxima_cita and self.proxima_cita < timezone.localdate():
            errores["proxima_cita"] = "La próxima cita no puede estar en el pasado."
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Las consultas médicas registradas no pueden modificarse. "
                "Agregue una nota clínica para ampliar la información."
            )
        return super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("consultas:historial", args=[self.cita.paciente_id])


class NotaClinica(models.Model):
    consulta = models.ForeignKey(
        Consulta, on_delete=models.CASCADE, related_name="notas", verbose_name="consulta"
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="notas_clinicas",
        verbose_name="autor",
    )
    contenido = models.TextField("contenido", max_length=1000)
    fecha = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "nota clínica"
        verbose_name_plural = "notas clínicas"
        ordering = ["-fecha"]

    def __str__(self):
        return f"Nota de {self.autor} · {self.fecha:%d/%m/%Y %H:%M}"

    def clean(self):
        self.contenido = sanitizar_texto(self.contenido, 1000)
        if len(self.contenido or "") < 5:
            raise ValidationError({"contenido": "La nota debe tener al menos 5 caracteres."})


class AuditoriaMedica(models.Model):
    class Accion(models.TextChoices):
        VER_HISTORIAL = "ver_historial", "Acceso a historial"
        VER_AGENDA = "ver_agenda", "Consulta de agenda"
        CREAR_CONSULTA = "crear_consulta", "Registro de consulta"
        CREAR_NOTA = "crear_nota", "Registro de nota clínica"
        AGENDAR = "agendar", "Agendamiento de cita"
        CANCELAR = "cancelar", "Cancelación de cita"
        CONFIRMAR = "confirmar", "Confirmación de cita"
        ACCESO_DENEGADO = "acceso_denegado", "Acceso denegado"
        LOGIN = "login", "Inicio de sesión"
        LOGOUT = "logout", "Cierre de sesión"
        OTRO = "otro", "Otra acción"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="auditorias_medicas", verbose_name="usuario",
    )
    paciente = models.ForeignKey(
        Paciente, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="auditorias", verbose_name="paciente",
    )
    accion = models.CharField("acción", max_length=25, choices=Accion.choices)
    fecha = models.DateTimeField("fecha", auto_now_add=True)
    ip = models.GenericIPAddressField("dirección IP", default="127.0.0.1")
    recurso = models.CharField("recurso consultado", max_length=200, blank=True)

    class Meta:
        verbose_name = "auditoría médica"
        verbose_name_plural = "auditorías médicas"
        ordering = ["-fecha", "-id"]
        indexes = [models.Index(fields=["accion", "fecha"])]

    def __str__(self):
        return f"{self.get_accion_display()} · {self.usuario or 'anónimo'} · {self.fecha:%d/%m/%Y %H:%M}"
