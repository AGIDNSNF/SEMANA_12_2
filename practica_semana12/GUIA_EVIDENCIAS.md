# Guía de evidencias verificables

Esta guía indica **cómo reproducir** cada sistema y **qué capturas tomar** para el informe.
Las imágenes deben ser tomadas por los integrantes durante la ejecución real. El repositorio
no incluye capturas simuladas.

---

## 1. Preparación

Desde `practica_semana12`:

```powershell
.\instalar.ps1
```

Luego, en tres terminales distintas:

```powershell
.\iniciar_caso1.ps1
.\iniciar_caso2.ps1
.\iniciar_caso3.ps1
```

También puede ejecutar cada caso manualmente:

```powershell
cd caso1_prestamos
.\.venv\Scripts\Activate.ps1
python manage.py runserver 8001
```

Contraseña de demostración: **`Demo12345!`**.

---

## 2. Convención de archivos

Guardar las capturas en:

```
evidencias/
├── caso1/
├── caso2/
└── caso3/
```

Formato sugerido: `NN_descripcion.png` (por ejemplo `01_login.png`).
Usar resolución legible (mínimo 1280×720), sin recortar el nombre del sistema ni la URL del navegador.
No incluir contraseñas visibles en la imagen.

---

## 3. Caso 1 · Préstamos

### 3.1 Capturas mínimas

| # | Pantalla | Usuario | Qué debe verse |
|---|---|---|---|
| 01 | Catálogo público | `invitado1` o sin sesión | Equipos, laboratorio, stock disponible |
| 02 | Login | — | Formulario y mensaje institucional |
| 03 | Panel del docente | `docente1` | Accesos y resumen |
| 04 | Solicitud de préstamo | `docente1` | Formulario completo con fechas |
| 05 | Préstamo pendiente | `docente1` | Estado `Pendiente` y detalle |
| 06 | Aprobación | `asistente1` | Botón aprobar y estado `Activo` |
| 07 | Devolución | `asistente1` | Formulario y confirmación |
| 08 | Reportes | `admin_uncp` | Métricas y exportación |
| 09 | Auditoría | `admin_uncp` | Eventos con usuario y fecha |
| 10 | Error 403 | `docente1` | Acceso denegado a ruta restringida |

### 3.2 Verificaciones funcionales

1. Intentar solicitar un cuarto préstamo activo con `docente1`: debe rechazarse.
2. Intentar prestar un equipo en mantenimiento: debe rechazarse.
3. Solicitar más unidades que el stock: debe rechazarse.
4. Registrar dos devoluciones del mismo préstamo: la segunda debe rechazarse.
5. Esperar 30 minutos o manipular la sesión para verificar el cierre por inactividad.

### 3.3 Comandos de evidencia

```powershell
cd caso1_prestamos
python manage.py check
python manage.py test prestamos -v 2
```

Guardar la salida de consola como `evidencias/caso1/pruebas_consola.txt`.

---

## 4. Caso 2 · Consultas médicas

### 4.1 Capturas mínimas

| # | Pantalla | Usuario | Qué debe verse |
|---|---|---|---|
| 01 | Login | — | Formulario |
| 02 | Panel del médico | `medico1` | Agenda y citas del día |
| 03 | Agenda | `recepcion1` | Citas por médico y estado |
| 04 | Agendar cita | `recepcion1` | Formulario con fecha/hora |
| 05 | Cita confirmada | `recepcion1` | Estado `Confirmada` |
| 06 | Registro de consulta | `medico1` | Diagnóstico y tratamiento |
| 07 | Consulta registrada | `medico1` | Estado `Completada`, nota clínica |
| 08 | Historial propio | `paciente1` | Consultas del paciente |
| 09 | Historial autorizado | `medico1` | Acceso a paciente con relación |
| 10 | Historial denegado | `medico2` | Error 403 |
| 11 | Reportes | `admin_medico` | Métricas |
| 12 | Admin | `admin_medico` | Listado personalizado |

### 4.2 Verificaciones funcionales

1. Agendar en domingo: debe rechazarse.
2. Agendar fuera de horario (por ejemplo 19:00): debe rechazarse.
3. Agendar dos citas del mismo médico en la misma franja: debe rechazarse.
4. Agendar dos citas activas del mismo paciente el mismo día: debe rechazarse.
5. Intentar editar una consulta ya registrada: debe rechazarse.
6. Acceder al historial de un paciente sin relación asistencial: debe devolver 403.
7. Verificar que la recepción no vea diagnósticos ni tratamientos.
8. Esperar 20 minutos o manipular la sesión para verificar el cierre.

### 4.3 Comandos de evidencia

```powershell
cd caso2_consultas_medicas
python manage.py check
python manage.py test consultas -v 2
```

Guardar como `evidencias/caso2/pruebas_consola.txt`.

---

## 5. Caso 3 · Asistencia y permisos

### 5.1 Capturas mínimas

| # | Pantalla | Usuario | Qué debe verse |
|---|---|---|---|
| 01 | Login | — | Formulario |
| 02 | Panel del empleado | `empleado1` | Botón de marcación y saldo |
| 03 | Entrada registrada | `empleado1` | Hora de entrada |
| 04 | Salida registrada | `empleado1` | Horas y extra calculados |
| 05 | Mis registros | `empleado1` | Historial |
| 06 | Registros del área | `jefe_ti` | Solo empleados de TI |
| 07 | Corrección RRHH | `rrhh1` | Formulario con justificación |
| 08 | Corrección auditada | `rrhh1` | Registro actualizado y auditoría |
| 09 | Nueva solicitud | `empleado1` | Fechas y saldo |
| 10 | Aprobación | `jefe_ti` | Botón aprobar |
| 11 | Autoaprobación denegada | `jefe_ti` | Error 403 en su propia solicitud |
| 12 | Reportes | `rrhh1` o `contador1` | Horas y extras por área |
| 13 | Admin | `admin_asistencia` | Acción masiva de aprobación |

### 5.2 Verificaciones funcionales

1. Intentar marcar dos entradas el mismo día: debe rechazarse.
2. Intentar marcar salida sin entrada: debe rechazarse.
3. Registrar una jornada de 9.5 horas: debe mostrar 1.5 horas extra.
4. Intentar corregir como jefe o contador: debe devolver 403.
5. Intentar corregir con justificación de menos de 50 caracteres: debe rechazarse.
6. Crear una solicitud que supere el saldo de 30 días: debe rechazarse.
7. Crear una solicitud superpuesta: debe rechazarse.
8. Aprobar la propia solicitud: debe devolver 403.
9. Jefe de TI intentando aprobar solicitud de Operaciones: debe devolver 403.
10. Esperar 45 minutos o manipular la sesión para verificar el cierre.

### 5.3 Comandos de evidencia

```powershell
cd caso3_asistencia
python manage.py check
python manage.py test asistencia -v 2
```

Guardar como `evidencias/caso3/pruebas_consola.txt`.

---

## 6. Evidencias de código y configuración

Además de las capturas de pantalla, se sugiere incluir:

| Evidencia | Archivo o comando |
|---|---|
| Estructura del proyecto | `tree /F` o captura del explorador |
| Migraciones aplicadas | `python manage.py showmigrations` |
| Verificación de migraciones | `python manage.py makemigrations --check --dry-run` |
| Configuración de sesión | captura de `config/settings.py` |
| Middleware propio | captura de `middleware.py` |
| Modelo y reglas | captura de `models.py` / `services.py` |
| Pruebas | salida de `manage.py test` |
| Admin | captura de `/admin/` |

---

## 7. Lista de verificación antes de entregar

- [ ] Los tres casos arrancan en 8001, 8002 y 8003.
- [ ] Los datos demo se generan sin errores.
- [ ] Cada caso tiene capturas de login, panel, operación principal y error 403.
- [ ] Las capturas muestran la URL y no exponen contraseñas.
- [ ] La salida de pruebas coincide con `RESULTADOS_PRUEBAS.md`.
- [ ] El informe final tiene nombres reales de integrantes y docente.
- [ ] No se incluyen capturas de otros proyectos ni resultados inventados.
- [ ] Los archivos `db.sqlite3`, `logs/` y `.venv/` no se entregan como código fuente.

---

## 8. Nota sobre honestidad

Si alguna captura no puede tomarse, debe indicarse expresamente en el informe. Es preferible
una lista de verificación incompleta y honesta que una imagen simulada. Las pruebas y resultados
de este repositorio provienen de ejecuciones reales del entorno descrito.
