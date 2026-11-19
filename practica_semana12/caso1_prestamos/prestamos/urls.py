from django.urls import path

from . import views

app_name = "prestamos"

urlpatterns = [
    path("", views.catalogo, name="catalogo"),
    path("equipos/<int:pk>/", views.equipo_detalle, name="equipo_detalle"),
    path("login/", views.iniciar_sesion, name="login"),
    path("logout/", views.cerrar_sesion, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("mis-prestamos/", views.mis_prestamos, name="mis_prestamos"),
    path("prestamos/", views.lista_prestamos, name="lista_prestamos"),
    path("prestamos/solicitar/", views.solicitar_prestamo, name="solicitar_prestamo"),
    path("prestamos/rapido/", views.prestamo_rapido, name="prestamo_rapido"),
    path("prestamos/<int:pk>/", views.prestamo_detalle, name="prestamo_detalle"),
    path("prestamos/<int:pk>/aprobar/", views.aprobar_prestamo, name="aprobar_prestamo"),
    path("prestamos/<int:pk>/rechazar/", views.rechazar_prestamo, name="rechazar_prestamo"),
    path("devoluciones/", views.devoluciones_pendientes, name="devoluciones_pendientes"),
    path(
        "devoluciones/<int:pk>/registrar/",
        views.registrar_devolucion,
        name="registrar_devolucion",
    ),
    path("reportes/", views.reportes, name="reportes"),
    path("reportes/exportar/", views.exportar_reporte, name="exportar_reporte"),
    path("auditoria/", views.auditoria_lista, name="auditoria"),
    path("gestion/equipos/nuevo/", views.equipo_crear, name="equipo_crear"),
    path("gestion/equipos/<int:pk>/editar/", views.equipo_editar, name="equipo_editar"),
    path("gestion/equipos/<int:pk>/eliminar/", views.equipo_eliminar, name="equipo_eliminar"),
    path("acceso-denegado/", views.acceso_denegado, name="acceso_denegado"),
]
