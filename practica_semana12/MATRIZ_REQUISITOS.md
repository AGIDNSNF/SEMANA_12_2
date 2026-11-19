# Matriz de requisitos y trazabilidad

Correspondencia entre los requisitos de la práctica, su implementación y las pruebas que los
verifican. Todas las pruebas citadas se ejecutaron realmente; ver
[`RESULTADOS_PRUEBAS.md`](RESULTADOS_PRUEBAS.md).

Leyenda de estado:

- **Implementado y probado**: existe código y al menos una prueba automatizada que lo cubre.
- **Implementado**: existe código; la verificación es manual o visual.

---

## 1. Requisitos generales

| ID | Requisito | Implementación | Verificación | Estado |
|---|---|---|---|---|
| RG-01 | Tres sistemas Django independientes | `caso1_prestamos`, `caso2_consultas_medicas`, `caso3_asistencia` | `manage.py check` en cada caso | Implementado y probado |
| RG-02 | Django 5.2 LTS y Python 3.12+ | `requirements.txt`, `config/settings.py` | Ejecución real de pruebas | Implementado y probado |
| RG-03 | SQLite, sin Docker/Redis/Celery/SPA | `DATABASES`, estáticos locales | Inspección de configuración | Implementado |
| RG-04 | Estructura solicitada por caso | `manage.py`, `config/`, app, `templates/`, `static/`, `requirements.txt`, `README.md`, `.gitignore` | Listado del repositorio | Implementado |
| RG-05 | Lógica de negocio real | Modelos con `clean()`, servicios transaccionales, permisos | Pruebas por caso | Implementado y probado |
| RG-06 | Middleware propio | `middleware.py` de cada caso | Pruebas de sesión y auditoría | Implementado y probado |
| RG-07 | Admin personalizado | `admin.py` de cada caso | Clases `AdminTest` y revisión visual | Implementado y probado |
| RG-08 | Datos demo ficticios e idempotentes | `crear_datos_demo.py` | `test_comando_demo_es_idempotente` (caso 1) y ejecución manual | Implementado y probado |
| RG-09 | Pruebas automatizadas | `tests.py` por caso | 158 pruebas OK | Implementado y probado |
| RG-10 | Scripts de instalación y ejecución | `instalar.ps1`, `iniciar_caso*.ps1`, `probar_todo.ps1` | Ejecución manual documentada | Implementado |
| RG-11 | Documentación y evidencias | README por caso, documentos raíz, `evidencias/` | Revisión de archivos | Implementado |
| RG-12 | No declarar pruebas/capturas no realizadas | `RESULTADOS_PRUEBAS.md`, `GUIA_EVIDENCIAS.md` | Revisión editorial | Implementado |

---

## 2. Caso 1 · Préstamos de equipos

| ID | Requisito | Implementación | Prueba / evidencia | Estado |
|---|---|---|---|---|
| C1-01 | Roles Admin/Docente/Asistente/Invitado | Grupos en demo, `permissions.py` | `AccesoYAuditoriaTests` | Implementado y probado |
| C1-02 | Catálogo de laboratorios y equipos | `Laboratorio`, `Equipo`, vistas de catálogo | `Vistas` y catálogo público | Implementado y probado |
| C1-03 | Solicitud de préstamo | `services.crear_prestamo()` | `test_solicitud_valida_crea_pendiente` | Implementado y probado |
| C1-04 | Máximo 3 préstamos activos | `MAX_PRESTAMOS_ACTIVOS`, `clean()`, servicio | `test_mas_de_tres_prestamos_activos` | Implementado y probado |
| C1-05 | Fechas válidas y coherentes | `Prestamo.clean()`, constraint | `test_fechas_invalidas`, `test_fecha_prestamo_pasada` | Implementado y probado |
| C1-06 | Solo equipos operativos | `Equipo.Estado`, `clean()`, servicio | `test_equipo_en_mantenimiento_no_prestable` | Implementado y probado |
| C1-07 | Control de stock | `cantidad_disponible`, `select_for_update()` | `test_stock_insuficiente`, `test_disponibilidad_calculada` | Implementado y probado |
| C1-08 | Aprobación/rechazo | `aprobar_prestamo()`, `rechazar_prestamo()` | Vistas y admin | Implementado y probado |
| C1-09 | Devolución única | `Devolucion` 1:1, servicio | `test_devolucion_duplicada` | Implementado y probado |
| C1-10 | No eliminar equipo con préstamos activos | `services.eliminar_equipo()` | `test_no_eliminar_equipo_con_prestamo_activo` | Implementado y probado |
| C1-11 | Sanitización de textos | `sanitizar_texto()`, `validar_sin_html()` | `test_observaciones_se_sanitizan` | Implementado y probado |
| C1-12 | Operaciones atómicas | `transaction.atomic()` + bloqueo | Revisión de servicios y pruebas de stock | Implementado y probado |
| C1-13 | Sesión de 30 minutos | `SESSION_TIMEOUT`, middleware | `test_timeout_de_sesion_por_inactividad` | Implementado y probado |
| C1-14 | Auditoría de acciones | `Auditoria`, `registrar_auditoria()` | `test_acceso_denegado_se_audita`, `test_login_fallido_se_audita` | Implementado y probado |
| C1-15 | Reportes y exportación | Vista de reportes + CSV | Revisión visual | Implementado |
| C1-16 | Admin con filtros y solo lectura | `admin.py` | `test_admin_marca_equipos_en_mantenimiento` | Implementado y probado |

---

## 3. Caso 2 · Consultas médicas

| ID | Requisito | Implementación | Prueba / evidencia | Estado |
|---|---|---|---|---|
| C2-01 | Roles Admin/Médico/Recepcionista/Paciente | Grupos y `permissions.py` | `PermisosHistorialTest`, `VistasAgendamientoTest` | Implementado y probado |
| C2-02 | DNI de 8 dígitos | `validar_dni`, `Paciente.clean()` | `ValidacionesModeloTest` | Implementado y probado |
| C2-03 | CMP de 5 dígitos | `validar_cmp`, `Medico.clean()` | `ValidacionesModeloTest` | Implementado y probado |
| C2-04 | Fecha de nacimiento no futura | `Paciente.clean()` | `ValidacionesModeloTest` | Implementado y probado |
| C2-05 | Correo `@uncp.edu.pe` para estudiantes | `validar_correo_institucional()` | `ValidacionesModeloTest` | Implementado y probado |
| C2-06 | Motivo ≥ 20 caracteres | `MinLengthValidator`, `Cita.clean()` | `CitaReglasTest` | Implementado y probado |
| C2-07 | Horario L-V 08–18, Sáb 08–13 | `horarios.HORARIO_GENERAL` | `HorarioTest` | Implementado y probado |
| C2-08 | Franjas de 30 minutos configurables | `CITA_DURACION_MINUTOS`, `hora_fin()` | `HorarioTest` | Implementado y probado |
| C2-09 | Sin superposición de médico | `Cita.clean()`, constraint | `CitaReglasTest` | Implementado y probado |
| C2-10 | Sin cita duplicada paciente/día | `Cita.clean()`, constraint | `CitaReglasTest` | Implementado y probado |
| C2-11 | Ciclo de cita y confirmación | `services.confirmar_cita()` | `VistasAgendamientoTest` | Implementado y probado |
| C2-12 | Consulta inmutable | `Consulta.save()` | `ConsultaTest` | Implementado y probado |
| C2-13 | Notas clínicas posteriores | `NotaClinica`, `agregar_nota()` | `ConsultaTest` | Implementado y probado |
| C2-14 | Historial propio y autorizado | `puede_ver_historial()` | `PermisosHistorialTest` | Implementado y probado |
| C2-15 | Recepción sin datos clínicos | Permisos y vistas | `PermisosHistorialTest` | Implementado y probado |
| C2-16 | Sesión de 20 minutos | `SESSION_TIMEOUT`, middleware | `SesionTest` | Implementado y probado |
| C2-17 | Auditoría médica | `AuditoriaMedica`, middleware | `PermisosHistorialTest`, `SesionTest` | Implementado y probado |
| C2-18 | Diagrama Mermaid de roles | README y documentación técnica | Revisión del documento | Implementado |

---

## 4. Caso 3 · Asistencia y permisos

| ID | Requisito | Implementación | Prueba / evidencia | Estado |
|---|---|---|---|---|
| C3-01 | Roles RRHH/Jefe/Empleado/Contador | Grupos y `permissions.py` | `VistasAsistenciaTest` | Implementado y probado |
| C3-02 | DNI de 8 dígitos único | `validar_dni`, campo único | `ModeloAsistenciaTest` | Implementado y probado |
| C3-03 | Correo `@tecnoandes.pe` | `validar_correo_corporativo()` | `test_correo_debe_ser_corporativo`, vista de empleado | Implementado y probado |
| C3-04 | Marcación de entrada/salida | `services.marcar_entrada/salida()` | `MarcacionServiceTest` | Implementado y probado |
| C3-05 | Horas extra sobre 8 horas | `reglas.horas_extra()` | `test_horas_extra_cuando_supera_la_jornada` | Implementado y probado |
| C3-06 | Correcciones solo RRHH | `puede_corregir()`, servicio | `test_solo_rrhh_puede_corregir` | Implementado y probado |
| C3-07 | Justificación ≥ 50 caracteres | Validador, modelo, servicio | `test_justificacion_menor_a_cincuenta...` | Implementado y probado |
| C3-08 | Correcciones inmutables | `CorreccionAsistencia.save()` | `test_correccion_es_inmutable` | Implementado y probado |
| C3-09 | Permisos y vacaciones | `Solicitud`, `crear_solicitud()` | `SolicitudReglasTest` | Implementado y probado |
| C3-10 | Saldo anual de 30 días | `saldo_disponible()`, `dias_por_anio()` | `test_saldo_anual_de_treinta_dias` | Implementado y probado |
| C3-11 | Aprobación por jefe/RRHH | `puede_resolver_solicitud()` | `AprobacionSolicitudTest` | Implementado y probado |
| C3-12 | Sin autoaprobación | Comparación con empleado solicitante | `test_nadie_puede_aprobar_su_propia_solicitud` | Implementado y probado |
| C3-13 | Sin superposición de solicitudes | `Solicitud.clean()` | `test_no_permite_solicitudes_superpuestas` | Implementado y probado |
| C3-14 | Alcance por área | `*_visibles()` en permisos | `test_jefe_solo_ve_registros_de_su_area` | Implementado y probado |
| C3-15 | Sesión de 45 minutos | `SESSION_TIMEOUT`, middleware | `SesionTest` | Implementado y probado |
| C3-16 | Auditoría de asistencia | `AuditoriaAsistencia`, middleware | `MarcacionServiceTest`, `AdminTest` | Implementado y probado |
| C3-17 | Admin con acciones de aprobación | `admin.py` | `test_accion_admin_aprueba_solicitud` | Implementado y probado |

---

## 5. Requisitos no funcionales

| ID | Requisito | Implementación | Verificación | Estado |
|---|---|---|---|---|
| RNF-01 | Seguridad de sesiones | Cookies HttpOnly, SameSite, expiración | Configuración y pruebas | Implementado y probado |
| RNF-02 | Protección CSRF/XSS/clickjacking | Middleware Django, sanitización, `X-Frame-Options` | Configuración y pruebas de sanitización | Implementado y probado |
| RNF-03 | Auditoría de accesos denegados | Middleware de auditoría | Pruebas de 403 y auditoría | Implementado y probado |
| RNF-04 | Operación sin Internet | Bootstrap local, SQLite, correo consola | Ejecución local | Implementado |
| RNF-05 | Idempotencia de datos demo | `update_or_create`, borrado selectivo | `test_comando_demo_es_idempotente` | Implementado y probado |
| RNF-06 | Rendimiento razonable | Índices, `select_related`, paginación | Revisión de código | Implementado |
| RNF-07 | Mantenibilidad | Servicios, reglas centralizadas, documentación | Revisión de código | Implementado |
| RNF-08 | Portabilidad | `requirements.txt`, scripts PowerShell | Instalación documentada | Implementado |

---

## 6. Resumen de cumplimiento

| Caso | Requisitos funcionales | Requisitos no funcionales | Pruebas |
|---|---|---|---|
| 1 | 16/16 | 8/8 | 32 OK |
| 2 | 18/18 | 8/8 | 65 OK |
| 3 | 17/17 | 8/8 | 61 OK |

> La columna “Implementado” sin “probado” indica que la verificación es visual o manual y no
> cuenta con una prueba automatizada específica. No se declaran capturas ni métricas no producidas.
