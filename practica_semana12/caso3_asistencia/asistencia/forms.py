"""Formularios del caso 3 con validación de backend."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Area, CorreccionAsistencia, Empleado, RegistroAsistencia, Solicitud
from .permissions import (
    GRUPO_EMPLEADO,
    empleado_de,
    es_administrador,
    es_rrhh,
)
from .validators import sanitizar_texto, validar_correo_corporativo, validar_sin_html

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
        label="Usuario",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Contraseña", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class EmpleadoForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Empleado
        fields = [
            "dni", "nombres", "apellidos", "email", "cargo", "area",
            "fecha_ingreso", "activo", "sueldo_basico",
        ]
        widgets = {"fecha_ingreso": forms.DateInput(attrs={"type": "date"})}

    def clean_dni(self):
        dni = (self.cleaned_data.get("dni") or "").strip()
        if not dni.isdigit() or len(dni) != 8:
            raise ValidationError("El DNI debe tener exactamente 8 dígitos numéricos.")
        if Empleado.objects.filter(dni=dni).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe un empleado con ese DNI.")
        return dni

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        validar_correo_corporativo(email)
        if Empleado.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe un empleado con ese correo corporativo.")
        return email

    def save(self, commit=True):
        empleado = super().save(commit=False)
        if not empleado.usuario_id:
            usuario, creado = Usuario.objects.get_or_create(
                username=f"emp_{empleado.dni}",
                defaults={
                    "email": empleado.email,
                    "first_name": empleado.nombres,
                    "last_name": empleado.apellidos,
                    "is_active": True,
                },
            )
            if creado:
                usuario.set_unusable_password()
                usuario.save()
                grupo, _ = Group.objects.get_or_create(name=GRUPO_EMPLEADO)
                usuario.groups.add(grupo)
            empleado.usuario = usuario
        if commit:
            empleado.save()
            self.save_m2m()
        return empleado


class CorreccionForm(EstiloBootstrapMixin, forms.Form):
    hora_entrada = forms.TimeField(
        label="Hora de entrada corregida",
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    hora_salida = forms.TimeField(
        label="Hora de salida corregida",
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    justificacion = forms.CharField(
        label="Justificación de la corrección", min_length=50,
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "Explique el motivo de la corrección (mínimo 50 caracteres).",
        }),
    )

    def clean_justificacion(self):
        texto = sanitizar_texto(self.cleaned_data.get("justificacion"), 800)
        validar_sin_html(texto)
        if len(texto) < 50:
            raise ValidationError("La justificación debe tener al menos 50 caracteres.")
        return texto

    def clean(self):
        datos = super().clean()
        entrada, salida = datos.get("hora_entrada"), datos.get("hora_salida")
        if entrada and salida and salida <= entrada:
            self.add_error("hora_salida", "La salida debe ser posterior a la entrada.")
        return datos


class SolicitudForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Solicitud
        fields = ["empleado", "tipo", "fecha_inicio", "fecha_fin", "motivo"]
        widgets = {
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}),
            "fecha_fin": forms.DateInput(attrs={"type": "date"}),
            "motivo": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Describa el motivo (mínimo 20 caracteres).",
            }),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        propio = empleado_de(usuario)
        if not (es_rrhh(usuario) or es_administrador(usuario)):
            self.fields.pop("empleado", None)
            if propio is not None:
                self.instance.empleado = propio
        else:
            self.fields["empleado"].queryset = Empleado.objects.filter(
                activo=True
            ).select_related("area")
            self.fields["empleado"].label_from_instance = (
                lambda e: f"{e.apellidos}, {e.nombres} · {e.area.nombre}"
            )
        hoy = timezone.localdate().isoformat()
        self.fields["fecha_inicio"].widget.attrs.setdefault("min", hoy)
        self.fields["fecha_fin"].widget.attrs.setdefault("min", hoy)

    def clean_motivo(self):
        motivo = sanitizar_texto(self.cleaned_data.get("motivo"), 500)
        validar_sin_html(motivo)
        if len(motivo) < 20:
            raise ValidationError("El motivo debe tener al menos 20 caracteres.")
        return motivo


class ResolucionForm(EstiloBootstrapMixin, forms.Form):
    comentario = forms.CharField(
        label="Comentario de revisión", required=False, max_length=300,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean_comentario(self):
        return sanitizar_texto(self.cleaned_data.get("comentario"), 300)


class BusquedaRegistroForm(EstiloBootstrapMixin, forms.Form):
    fecha = forms.DateField(
        label="Fecha", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    area = forms.ModelChoiceField(
        label="Área", required=False, queryset=Area.objects.all(),
        empty_label="Todas las áreas",
    )


class BusquedaSolicitudForm(EstiloBootstrapMixin, forms.Form):
    estado = forms.ChoiceField(
        label="Estado", required=False,
        choices=[("", "Todos los estados")] + list(Solicitud.Estado.choices),
    )
    tipo = forms.ChoiceField(
        label="Tipo", required=False,
        choices=[("", "Todos los tipos")] + list(Solicitud.Tipo.choices),
    )
    area = forms.ModelChoiceField(
        label="Área", required=False, queryset=Area.objects.all(),
        empty_label="Todas las áreas",
    )
