from django.urls import path

from . import views

app_name = "consultas"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("login/", views.iniciar_sesion, name="login"),
    path("logout/", views.cerrar_sesion, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("agenda/", views.agenda, name="agenda"),
    path("citas/nueva/", views.agendar_cita, name="agendar_cita"),
    path("citas/<int:pk>/", views.cita_detalle, name="cita_detalle"),
    path("citas/<int:pk>/cancelar/", views.cancelar_cita, name="cancelar_cita"),
    path("citas/<int:pk>/confirmar/", views.confirmar_cita, name="confirmar_cita"),
    path("citas/<int:pk>/consulta/", views.registrar_consulta, name="registrar_consulta"),
    path("historial/<int:pk>/", views.historial, name="historial"),
    path("consultas/<int:pk>/nota/", views.agregar_nota, name="agregar_nota"),
    path("pacientes/", views.pacientes, name="pacientes"),
    path("pacientes/nuevo/", views.paciente_crear, name="paciente_crear"),
    path("pacientes/<int:pk>/editar/", views.paciente_editar, name="paciente_editar"),
    path("medicos/", views.medicos, name="medicos"),
    path("medicos/nuevo/", views.medico_crear, name="medico_crear"),
    path("medicos/<int:pk>/editar/", views.medico_editar, name="medico_editar"),
    path("reportes/", views.reportes, name="reportes"),
    path("acceso-denegado/", views.acceso_denegado, name="acceso_denegado"),
]
