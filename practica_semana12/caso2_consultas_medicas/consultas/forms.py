"""Formularios del caso 2 con validación en backend y mensajes claros."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    Cita, Consulta, Especialidad, Medico, NotaClinica, Paciente,
)
from .permissions import (
    GRUPO_MEDICO,
    GRUPO_PACIENTE,
    es_administrador,
    paciente_de,
)
from .validators import sanitizar_texto, validar_sin_html

Usuario = get_user_model()


class EstiloBootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")


class LoginForm(EstiloBootstrapMixin, AuthenticationForm):
    username = forms.CharField(
        label="Usuario", widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"})
    )
    password = forms.CharField(
        label="Contraseña", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class PacienteForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Paciente
        fields = [
            "dni", "nombres", "apellidos", "fecha_nacimiento", "tipo",
            "codigo_uncp", "email", "alergias",
        ]
        widgets = {"fecha_nacimiento": forms.DateInput(attrs={"type": "date"})}

    def clean_dni(self):
        dni = (self.cleaned_data.get("dni") or "").strip()
        if not dni.isdigit() or len(dni) != 8:
            raise ValidationError("El DNI debe tener exactamente 8 dígitos numéricos.")
        if Paciente.objects.filter(dni=dni).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe un paciente registrado con ese DNI.")
        return dni

    def clean_codigo_uncp(self):
        codigo = (self.cleaned_data.get("codigo_uncp") or "").strip()
        return codigo or None

    def clean_alergias(self):
        alergias = sanitizar_texto(self.cleaned_data.get("alergias"), 500)
        validar_sin_html(alergias)
        return alergias

    def save(self, commit=True):
        paciente = super().save(commit=False)
        if not paciente.usuario_id:
            usuario, creado = Usuario.objects.get_or_create(
                username=f"pac_{paciente.dni}",
                defaults={
                    "email": paciente.email,
                    "first_name": paciente.nombres,
                    "last_name": paciente.apellidos,
                    "is_active": True,
                },
            )
            if creado:
                usuario.set_unusable_password()
                usuario.save()
                grupo, _ = Group.objects.get_or_create(name=GRUPO_PACIENTE)
                usuario.groups.add(grupo)
            paciente.usuario = usuario
        if commit:
            paciente.save()
            self.save_m2m()
        return paciente


class MedicoForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Medico
        fields = ["nombres", "apellidos", "cmp", "especialidad", "consultorio", "activo"]

    def clean_cmp(self):
        cmp = (self.cleaned_data.get("cmp") or "").strip()
        if not cmp.isdigit() or len(cmp) != 5:
            raise ValidationError("El CMP debe tener exactamente 5 dígitos numéricos.")
        if Medico.objects.filter(cmp=cmp).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe un médico con ese CMP.")
        return cmp

    def save(self, commit=True):
        medico = super().save(commit=False)
        if not medico.usuario_id:
            usuario, creado = Usuario.objects.get_or_create(
                username=f"med_{medico.cmp}",
                defaults={
                    "first_name": medico.nombres,
                    "last_name": medico.apellidos,
                    "is_active": True,
                },
            )
            if creado:
                usuario.set_unusable_password()
                usuario.save()
                grupo, _ = Group.objects.get_or_create(name=GRUPO_MEDICO)
                usuario.groups.add(grupo)
            medico.usuario = usuario
        if commit:
            medico.save()
            self.save_m2m()
        return medico


class CitaForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Cita
        fields = ["paciente", "especialidad", "medico", "fecha", "hora", "motivo"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "hora": forms.TimeInput(attrs={"type": "time"}),
            "motivo": forms.Textarea(attrs={"rows": 3, "placeholder": "Describa el motivo (mínimo 20 caracteres)"}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        pacientes = Paciente.objects.all()
        self.fields["paciente"].queryset = pacientes
        self.fields["paciente"].label_from_instance = lambda p: f"{p.apellidos}, {p.nombres} · DNI {p.dni}"
        medicos = Medico.objects.filter(activo=True).select_related("especialidad").order_by(
            "apellidos", "nombres"
        )
        self.fields["medico"].queryset = medicos
        self.fields["medico"].label_from_instance = (
            lambda m: f"Dr(a). {m.nombres} {m.apellidos} · {m.especialidad.nombre}"
        )
        self.medicos_por_especialidad = {
            str(m.pk): m.especialidad_id for m in medicos
        }
        propio = paciente_de(usuario) if usuario else None
        if propio is not None:
            self.fields.pop("paciente", None)
            self.instance.paciente = propio
        elif usuario and not (
            es_administrador(usuario)
            or usuario.groups.filter(name="Recepcionistas").exists()
        ):
            self.fields.pop("paciente", None)

    def clean_motivo(self):
        motivo = sanitizar_texto(self.cleaned_data.get("motivo"), 500)
        validar_sin_html(motivo)
        if len(motivo) < 20:
            raise ValidationError("El motivo de consulta debe tener al menos 20 caracteres.")
        return motivo

    def clean(self):
        datos = super().clean()
        if self.errors:
            return datos
        paciente = datos.get("paciente") or self.instance.paciente or paciente_de(self.usuario)
        if not paciente:
            self.add_error(None, "No se pudo determinar el paciente de la cita.")
            return datos
        cita = Cita(
            paciente=paciente,
            medico=datos.get("medico"),
            especialidad=datos.get("especialidad"),
            fecha=datos.get("fecha"),
            hora=datos.get("hora"),
            motivo=datos.get("motivo"),
            estado=self.instance.estado if self.instance.pk else Cita.Estado.PENDIENTE,
        )
        if self.instance.pk:
            cita.pk = self.instance.pk
        try:
            cita.full_clean(exclude=["fecha_creacion", "actualizado_en"])
        except ValidationError as exc:
            for campo, mensajes in exc.message_dict.items():
                destino = campo if campo in self.fields else None
                self.add_error(destino, mensajes)
        return datos


class ConsultaForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Consulta
        fields = [
            "diagnostico", "tratamiento", "medicamentos", "proxima_cita",
            "archivos_referencia",
        ]
        widgets = {
            "diagnostico": forms.Textarea(attrs={"rows": 3}),
            "tratamiento": forms.Textarea(attrs={"rows": 3}),
            "medicamentos": forms.Textarea(attrs={"rows": 2}),
            "proxima_cita": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_diagnostico(self):
        valor = sanitizar_texto(self.cleaned_data.get("diagnostico"), 1000)
        validar_sin_html(valor)
        if len(valor) < 5:
            raise ValidationError("El diagnóstico debe tener al menos 5 caracteres.")
        return valor

    def clean_tratamiento(self):
        valor = sanitizar_texto(self.cleaned_data.get("tratamiento"), 1000)
        validar_sin_html(valor)
        if len(valor) < 5:
            raise ValidationError("El tratamiento debe tener al menos 5 caracteres.")
        return valor


class NotaClinicaForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = NotaClinica
        fields = ["contenido"]
        widgets = {"contenido": forms.Textarea(attrs={"rows": 3})}

    def clean_contenido(self):
        contenido = sanitizar_texto(self.cleaned_data.get("contenido"), 1000)
        validar_sin_html(contenido)
        if len(contenido) < 5:
            raise ValidationError("La nota debe tener al menos 5 caracteres.")
        return contenido


class CancelarCitaForm(EstiloBootstrapMixin, forms.Form):
    motivo = forms.CharField(
        label="Motivo de la cancelación", required=False, max_length=200,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean_motivo(self):
        return sanitizar_texto(self.cleaned_data.get("motivo"), 200)


class BusquedaCitaForm(EstiloBootstrapMixin, forms.Form):
    fecha = forms.DateField(
        label="Fecha", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    medico = forms.ModelChoiceField(
        label="Médico", required=False, queryset=Medico.objects.filter(activo=True),
        empty_label="Todos los médicos",
    )
    especialidad = forms.ModelChoiceField(
        label="Especialidad", required=False, queryset=Especialidad.objects.all(),
        empty_label="Todas las especialidades",
    )
    estado = forms.ChoiceField(
        label="Estado", required=False,
        choices=[("", "Todos los estados")] + list(Cita.Estado.choices),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["medico"].queryset = Medico.objects.filter(activo=True).select_related(
            "especialidad"
        )


class BusquedaPacienteForm(EstiloBootstrapMixin, forms.Form):
    q = forms.CharField(
        label="Buscar paciente", required=False, max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "DNI, nombres o apellidos"}),
    )
