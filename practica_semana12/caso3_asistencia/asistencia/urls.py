from django.urls import path

from . import views

app_name = "asistencia"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("login/", views.iniciar_sesion, name="login"),
    path("logout/", views.cerrar_sesion, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("asistencia/marcar/", views.marcar_asistencia, name="marcar_asistencia"),
    path("asistencia/mis-registros/", views.mis_registros, name="mis_registros"),
    path("asistencia/registros/", views.registros, name="registros"),
    path("asistencia/<int:pk>/corregir/", views.corregir_registro, name="corregir_registro"),
    path("solicitudes/", views.solicitudes, name="solicitudes"),
    path("solicitudes/nueva/", views.solicitud_crear, name="solicitud_crear"),
    path("solicitudes/<int:pk>/", views.solicitud_detalle, name="solicitud_detalle"),
    path("solicitudes/<int:pk>/resolver/", views.resolver_solicitud, name="resolver_solicitud"),
    path("solicitudes/<int:pk>/cancelar/", views.cancelar_solicitud, name="cancelar_solicitud"),
    path("empleados/", views.empleados, name="empleados"),
    path("empleados/nuevo/", views.empleado_crear, name="empleado_crear"),
    path("empleados/<int:pk>/", views.empleado_detalle, name="empleado_detalle"),
    path("empleados/<int:pk>/editar/", views.empleado_editar, name="empleado_editar"),
    path("reportes/", views.reportes, name="reportes"),
    path("acceso-denegado/", views.acceso_denegado, name="acceso_denegado"),
]
