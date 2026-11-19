"""Formularios del caso 1 con validaciones específicas y mensajes claros."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import MAX_PRESTAMOS_ACTIVOS, Devolucion, Equipo, Laboratorio, Prestamo
from .permissions import GRUPO_DOCENTE
from .validators import sanitizar_texto, validar_sin_html

Usuario = get_user_model()


class EstiloBootstrapMixin:
    """Aplica clases de Bootstrap a todos los widgets del formulario."""

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
        label="Usuario institucional",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class EquipoForm(EstiloBootstrapMixin, forms.ModelForm):
    class Meta:
        model = Equipo
        fields = [
            "codigo_patrimonial", "nombre", "marca", "modelo", "categoria",
            "estado", "laboratorio", "stock_total", "fecha_ultimo_mantenimiento",
        ]
        widgets = {
            "fecha_ultimo_mantenimiento": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_codigo_patrimonial(self):
        codigo = (self.cleaned_data.get("codigo_patrimonial") or "").strip().upper()
        if Equipo.objects.filter(codigo_patrimonial=codigo).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ya existe un equipo con ese código patrimonial.")
        return codigo

    def clean_nombre(self):
        nombre = sanitizar_texto(self.cleaned_data.get("nombre"), 120)
        validar_sin_html(nombre)
        return nombre

    def clean(self):
        datos = super().clean()
        stock = datos.get("stock_total")
        if self.instance.pk and stock is not None:
            prestado = self.instance.cantidad_prestada
            if stock < prestado:
                self.add_error(
                    "stock_total",
                    f"No puede reducir el stock a {stock}: hay {prestado} unidad(es) "
                    "comprometidas en préstamos.",
                )
        if datos.get("estado") == Equipo.Estado.BAJA and self.instance.pk:
            if self.instance.tiene_prestamos_activos():
                self.add_error(
                    "estado", "No puede dar de baja un equipo con préstamos activos."
                )
        return datos


class PrestamoSolicitudForm(EstiloBootstrapMixin, forms.Form):
    """Formulario clásico (forms.Form) de solicitud de préstamo."""

    equipo = forms.ModelChoiceField(
        queryset=Equipo.objects.none(),
        label="Equipo",
        empty_label="Seleccione un equipo operativo",
    )
    cantidad = forms.IntegerField(label="Cantidad", min_value=1, initial=1)
    fecha_prestamo = forms.DateField(
        label="Fecha de préstamo", widget=forms.DateInput(attrs={"type": "date"})
    )
    fecha_prevista_devolucion = forms.DateField(
        label="Fecha prevista de devolución",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Motivo o detalles del uso"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["equipo"].queryset = (
            Equipo.objects.filter(
                estado=Equipo.Estado.OPERATIVO, laboratorio__activo=True
            )
            .select_related("laboratorio")
            .order_by("nombre")
        )
        if not self.is_bound and not self.initial.get("fecha_prestamo"):
            self.fields["fecha_prestamo"].initial = timezone.localdate()

    def clean_cantidad(self):
        cantidad = self.cleaned_data.get("cantidad")
        if cantidad is None or cantidad <= 0:
            raise ValidationError("La cantidad debe ser mayor que cero.")
        return cantidad

    def clean_observaciones(self):
        observaciones = sanitizar_texto(self.cleaned_data.get("observaciones"), 500)
        validar_sin_html(observaciones)
        return observaciones

    def clean(self):
        datos = super().clean()
        equipo = datos.get("equipo")
        cantidad = datos.get("cantidad")
        inicio = datos.get("fecha_prestamo")
        prevista = datos.get("fecha_prevista_devolucion")

        if inicio and inicio < timezone.localdate():
            self.add_error("fecha_prestamo", "La fecha de préstamo no puede estar en el pasado.")
        if inicio and prevista and prevista <= inicio:
            self.add_error(
                "fecha_prevista_devolucion",
                "La fecha prevista de devolución debe ser posterior a la fecha de préstamo.",
            )
        if equipo and cantidad:
            if equipo.estado != Equipo.Estado.OPERATIVO:
                self.add_error("equipo", "Solo se pueden prestar equipos operativos.")
            elif cantidad > equipo.cantidad_disponible:
                self.add_error(
                    "cantidad",
                    f"Stock insuficiente: hay {equipo.cantidad_disponible} unidad(es) "
                    f"disponible(s) de {equipo.nombre}.",
                )
        return datos


class PrestamoRapidoForm(PrestamoSolicitudForm):
    """Registro directo en ventanilla (Asistente/Administrador)."""

    docente = forms.ModelChoiceField(
        queryset=Usuario.objects.none(),
        label="Docente solicitante",
        empty_label="Seleccione al docente",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["docente"].queryset = (
            Usuario.objects.filter(groups__name=GRUPO_DOCENTE, is_active=True)
            .distinct()
            .order_by("last_name", "first_name")
        )

    def clean(self):
        datos = super().clean()
        docente = datos.get("docente")
        if docente:
            activos = Prestamo.objects.filter(
                docente=docente, estado__in=("pendiente", "activo", "vencido")
            ).count()
            if activos >= MAX_PRESTAMOS_ACTIVOS:
                self.add_error(
                    "docente",
                    f"El docente ya tiene {MAX_PRESTAMOS_ACTIVOS} préstamos activos.",
                )
        return datos


class DevolucionForm(EstiloBootstrapMixin, forms.Form):
    """Formulario clásico de devolución (sin exponer timestamps)."""

    estado_equipo = forms.ChoiceField(
        label="Estado del equipo al retornar",
        choices=Devolucion.EstadoEquipo.choices,
        initial=Devolucion.EstadoEquipo.OPERATIVO,
    )
    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_observaciones(self):
        observaciones = sanitizar_texto(self.cleaned_data.get("observaciones"), 500)
        validar_sin_html(observaciones)
        return observaciones


class BusquedaEquipoForm(EstiloBootstrapMixin, forms.Form):
    q = forms.CharField(
        label="Buscar", required=False, max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Código, nombre o categoría"}),
    )
    laboratorio = forms.ModelChoiceField(
        label="Laboratorio", required=False, queryset=Laboratorio.objects.filter(activo=True),
        empty_label="Todos los laboratorios",
    )
    estado = forms.ChoiceField(
        label="Estado", required=False,
        choices=[("", "Todos los estados")] + list(Equipo.Estado.choices),
    )
    categoria = forms.CharField(
        label="Categoría", required=False, max_length=60,
        widget=forms.TextInput(attrs={"placeholder": "Ej. Cómputo"}),
    )


class FiltroPrestamoForm(EstiloBootstrapMixin, forms.Form):
    estado = forms.ChoiceField(
        label="Estado", required=False,
        choices=[("", "Todos los estados")] + list(Prestamo.Estado.choices),
    )
    desde = forms.DateField(
        label="Desde", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    hasta = forms.DateField(
        label="Hasta", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )


class RechazoForm(EstiloBootstrapMixin, forms.Form):
    motivo = forms.CharField(
        label="Motivo del rechazo", max_length=300,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean_motivo(self):
        motivo = sanitizar_texto(self.cleaned_data.get("motivo"), 300)
        validar_sin_html(motivo)
        if len(motivo) < 10:
            raise ValidationError("El motivo debe tener al menos 10 caracteres.")
        return motivo
