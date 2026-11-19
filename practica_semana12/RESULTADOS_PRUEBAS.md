# Resultados de pruebas

Registro de las ejecuciones reales realizadas el **2026-11-19** en el entorno de desarrollo.

---

## 1. Entorno de ejecución

| Elemento | Valor |
|---|---|
| Sistema operativo | Windows 11 Home Single Language (build 26200) |
| Shell | PowerShell 5.1.26100.9818 |
| Intérprete | Python 3.13.17 |
| Framework | Django 5.2.19 |
| Base de datos de pruebas | SQLite en memoria |
| Base de datos de desarrollo | SQLite (`db.sqlite3`) |
| Zona horaria | `America/Lima` |
| Codificación | UTF-8 (`PYTHONIOENCODING=utf-8`) |

Comandos base:

```powershell
$env:PYTHONIOENCODING="utf-8"
& C:\Users\GABRIEL\Desktop\AGUILAR\S12-2\.venv\Scripts\python.exe manage.py <comando>
```

> En PowerShell, Django escribe parte de su salida en `stderr`; por eso puede aparecer
> `NativeCommandError`. El resultado válido se determina por las líneas `OK`, `Ran N tests`
> y por la ausencia de `FAILED`/`ERROR`.

---

## 2. Verificación de configuración (`check`)

Ejecutado en los tres proyectos:

```powershell
python manage.py check
```

Salida en los tres casos:

```
System check identified no issues (0 silenced).
```

| Caso | Resultado |
|---|---|
| 1 | Sin observaciones |
| 2 | Sin observaciones |
| 3 | Sin observaciones |

---

## 3. Verificación de migraciones

Ejecutado en los tres proyectos:

```powershell
python manage.py makemigrations --check --dry-run
```

Salida en los tres casos:

```
No changes detected
```

Esto confirma que los modelos y las migraciones están sincronizados.

### Migraciones aplicadas

```powershell
python manage.py migrate
```

Cada caso aplicó correctamente su migración inicial `0001_initial` y las migraciones estándar de
Django (`auth`, `admin`, `sessions`, `contenttypes`).

| Caso | Migración de la app | Estado |
|---|---|---|
| 1 | `prestamos.0001_initial` | Aplicada |
| 2 | `consultas.0001_initial` | Aplicada |
| 3 | `asistencia.0001_initial` | Aplicada |

---

## 4. Caso 1 · Préstamos

### Comando

```powershell
cd practica_semana12\caso1_prestamos
python manage.py test prestamos -v 1
```

### Resultado real

```
Ran 32 tests in 16.473s

OK
```

| Métrica | Valor |
|---|---|
| Pruebas ejecutadas | 32 |
| Fallidas | 0 |
| Errores | 0 |
| Resultado | **OK** |

### Cobertura funcional verificada

- Validación de formulario de equipo y código patrimonial.
- Solicitud de préstamo, fechas inválidas y fecha pasada.
- Límite de 3 préstamos activos.
- Equipo en mantenimiento y stock insuficiente.
- Cantidad cero y sanitización de observaciones.
- Devolución válida, devolución duplicada y devolución desde vista.
- Permisos de docente, invitado y acceso a préstamo ajeno.
- Auditoría de acceso denegado y login fallido.
- Login correcto, logout solo por POST.
- Expiración de sesión por inactividad y sesión activa.
- Eliminación de equipo con y sin préstamos.
- Disponibilidad calculada y marcado de vencidos.
- Admin de equipos y búsqueda en catálogo.
- Idempotencia del comando de datos demo.

---

## 5. Caso 2 · Consultas médicas

### Comando

```powershell
cd practica_semana12\caso2_consultas_medicas
python manage.py test consultas -v 1
```

### Resultado real

```
Found 65 test(s).
System check identified no issues (0 silenced).

Ran 65 tests in 19.376s

OK
```

| Métrica | Valor |
|---|---|
| Pruebas ejecutadas | 65 |
| Fallidas | 0 |
| Errores | 0 |
| Resultado | **OK** |

### Cobertura funcional verificada

- Validaciones de DNI, CMP, correo institucional y fecha de nacimiento.
- Horario general, horario del médico, franjas y superposición.
- Reglas de cita: fecha pasada, hora pasada, duplicado paciente/día.
- Ciclo de vida: agendar, confirmar, cancelar y completar.
- Registro de consulta, inmutabilidad y notas clínicas.
- Permisos de historial para paciente, médico, recepción y admin.
- Sesión de 20 minutos.
- Vistas de agendamiento, formularios y admin.
- Auditoría de accesos denegados y operaciones clínicas.

---

## 6. Caso 3 · Asistencia y permisos

### Comando

```powershell
cd practica_semana12\caso3_asistencia
python manage.py test asistencia -v 1
```

### Resultado real

```
Found 61 test(s).
System check identified no issues (0 silenced).

Ran 61 tests in 25.526s

OK
```

| Métrica | Valor |
|---|---|
| Pruebas ejecutadas | 61 |
| Fallidas | 0 |
| Errores | 0 |
| Resultado | **OK** |

### Cobertura funcional verificada

- DNI de 8 dígitos, correo corporativo y fecha de ingreso.
- Jornada de 8 horas, horas extra y validación de salida.
- Marcación de entrada/salida, doble entrada y salida sin entrada.
- Corrección exclusiva de RRHH, justificación mínima e inmutabilidad.
- Reglas de solicitud: motivo, fechas, día hábil, superposición y saldo.
- Saldo anual de 30 días y descuento por aprobación.
- Aprobación por jefe/RRHH, denegación entre áreas y autoaprobación.
- Alcance por área en registros, empleados y solicitudes.
- Sesión de 45 minutos.
- Admin: changelist y acción masiva de aprobación.

---

## 7. Resumen consolidado

| Caso | `check` | `makemigrations --check` | Pruebas | Resultado |
|---|---|---|---|---|
| 1 · Préstamos | OK | Sin cambios | 32 | **OK** |
| 2 · Consultas | OK | Sin cambios | 65 | **OK** |
| 3 · Asistencia | OK | Sin cambios | 61 | **OK** |
| **Total** | — | — | **158** | **OK** |

### 7.1 Ejecución mediante `probar_todo.ps1`

El script se ejecutó el **2026-11-19 a las 11:26** con PowerShell 5.1:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\probar_todo.ps1
```

Resumen impreso por el script:

```
Caso                       Check Migraciones Migrate Test Estado
----                       ----- ----------- ------- ---- ------
Caso 1 - Prestamos         OK    OK          OK      OK   OK
Caso 2 - Consultas medicas OK    OK          OK      OK   OK
Caso 3 - Asistencia        OK    OK          OK      OK   OK

Todas las verificaciones finalizaron correctamente.
```

Las tres pruebas se ejecutaron con el intérprete de cada entorno virtual del caso
(`casoN_*\.venv\Scripts\python.exe`), creado por `instalar.ps1`.

### 7.2 Verificación de servidores

Se inició cada caso con su script correspondiente y se solicitó la raíz con
`Invoke-WebRequest`:

| Caso | URL | Respuesta | Tamaño |
|---|---|---|---|
| 1 | `http://127.0.0.1:8001/` | HTTP 200 | 3764 bytes |
| 2 | `http://127.0.0.1:8002/` | HTTP 200 | 3694 bytes |
| 3 | `http://127.0.0.1:8003/` | HTTP 200 | 3602 bytes |

Los servidores se detuvieron inmediatamente después de la comprobación.

---

## 8. Datos de demostración generados

### Caso 1

```
Laboratorios: 5
Equipos:      10
Usuarios:     6
Préstamos:    15
Devoluciones: 7
```

### Caso 2

```
Especialidades: 5
Médicos:        8
Pacientes:      15
Citas:          30
Consultas:      10
Usuarios:       25
```

### Caso 3

```
Áreas:        4
Empleados:    12
Registros:    75
Correcciones: 1
Solicitudes:  4
Usuarios:     13
```

> Los conteos corresponden a la ejecución del 2026-11-19. El comando es idempotente, por lo que
> volver a ejecutarlo no duplica registros.

---

## 9. Pruebas no realizadas o pendientes de evidencia

| Actividad | Estado |
|---|---|
| Capturas de pantalla | Pendientes de toma manual por los integrantes. |
| Prueba en navegadores adicionales | No realizada. |
| Prueba de carga/concurrencia | No realizada. |
| Despliegue en servidor público | No realizado. |
| Cobertura de código medida con herramienta | No medida. |

Estas actividades no se declaran como completadas. La guía para producirlas está en
[`GUIA_EVIDENCIAS.md`](GUIA_EVIDENCIAS.md).

---

## 10. Reproducción

Para repetir todo desde cero:

```powershell
cd practica_semana12
.\instalar.ps1
.\probar_todo.ps1
```

El script `probar_todo.ps1` ejecuta `check`, `makemigrations --check --dry-run`, `migrate` y
`test` en cada caso, y muestra un resumen final.
