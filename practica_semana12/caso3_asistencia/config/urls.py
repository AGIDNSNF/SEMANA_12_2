from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "TecnoAndes · Control de Asistencia"
admin.site.site_title = "TecnoAndes"
admin.site.index_title = "Gestión de personal, asistencia y permisos"

handler403 = "asistencia.views.acceso_denegado"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("asistencia.urls")),
]
