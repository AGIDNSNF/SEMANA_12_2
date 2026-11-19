# Decisiones técnicas

Registro de las decisiones relevantes, su justificación y sus consecuencias. El objetivo es que
otro equipo pueda entender por qué el sistema está construido así y qué alternativas se evaluaron.

---

## 1. Decisiones comunes

### D-01 · Django 5.2 LTS con SQLite

**Decisión:** usar Django 5.2 LTS y SQLite en los tres casos.

**Motivo:** la práctica pide un stack simple, reproducible y sin servicios externos. SQLite no
requiere instalación ni configuración y es suficiente para la demostración académica.

**Consecuencias:**

- Despliegue inmediato en cualquier equipo con Python.
- Bloqueos limitados; se mitigan con `select_for_update()` y transacciones.
- Para producción con concurrencia se recomienda PostgreSQL.

**Alternativas descartadas:** PostgreSQL (más infraestructura), Docker (fuera del alcance),
MySQL (no aporta ventajas para la práctica).

---

### D-02 · Proyectos independientes por caso

**Decisión:** tres proyectos Django separados, cada uno con su propio `manage.py`, base y app.

**Motivo:** los casos son sistemas distintos y se evalúan por separado. La independencia evita
mezclar modelos, permisos y migraciones.

**Consecuencias:**

- Se pueden ejecutar simultáneamente en 8001, 8002 y 8003.
- Algún código se repite (middleware, estilos); se acepta por claridad académica.
- Los scripts de instalación crean un entorno por caso.

**Alternativa descartada:** un solo proyecto con tres apps y un `settings` común. Habría acoplado
las bases de datos y complicado la evaluación individual.

---

### D-03 · Bootstrap local

**Decisión:** almacenar Bootstrap 5.3.3 en `static/vendor/`.

**Motivo:** la demostración debe funcionar sin Internet y sin depender de CDN.

**Consecuencias:**

- Mayor tamaño del repositorio.
- Renderizado consistente en el aula.
- Sin problemas de disponibilidad de CDN.

---

### D-04 · Capa de servicios para reglas críticas

**Decisión:** mover las operaciones críticas a `services.py` y dejar las vistas delgadas.

**Motivo:** las reglas deben aplicarse igual desde la interfaz, el admin y las pruebas. Las vistas
no deben contener lógica de stock, cupos, saldos o aprobaciones.

**Consecuencias:**

- Pruebas más directas y reutilizables.
- Transacciones y bloqueos centralizados.
- Ligeramente más archivos y capas.

**Alternativa descartada:** lógica en vistas o solo en formularios. Se puede saltar desde el admin
o desde una llamada directa al modelo.

---

### D-05 · Autorización por rol y por objeto

**Decisión:** combinar grupos de Django con funciones de permisos por objeto.

**Motivo:** el rol no basta. Un docente solo debe ver sus préstamos; un jefe solo su área; un médico
solo historiales con relación asistencial.

**Consecuencias:**

- Validaciones adicionales en cada vista de detalle.
- Riesgo de olvidar una comprobación si se agrega una vista nueva.
- Se mitiga con funciones centralizadas (`permissions.py`) y pruebas.

---

### D-06 · Middleware de sesión propio

**Decisión:** implementar `ActividadSesionMiddleware` además de `SESSION_COOKIE_AGE`.

**Motivo:** se necesita un cierre explícito por inactividad y un mensaje claro al usuario, con
tiempos distintos por caso (30, 20 y 45 minutos).

**Consecuencias:**

- Control preciso del timeout.
- Una marca `ultima_actividad` en la sesión.
- Pruebas específicas de expiración.

**Alternativa descartada:** confiar solo en la expiración de la cookie. No distingue actividad real
ni permite redirigir con un mensaje institucional.

---

### D-07 · Auditoría en base de datos y archivo

**Decisión:** registrar eventos en un modelo y en `logs/*.log`.

**Motivo:** la base permite consultar y filtrar; el archivo sirve como respaldo operativo.

**Consecuencias:**

- Dos destinos que mantener.
- No se registran contraseñas ni cuerpos completos.
- Crecimiento controlado por paginación y filtros.

---

### D-08 · Datos demo idempotentes

**Decisión:** usar `update_or_create` y borrado selectivo de registros demo.

**Motivo:** el docente puede ejecutar el comando varias veces sin duplicar datos ni romper claves.

**Consecuencias:**

- Demostración repetible.
- Los datos demo se identifican por prefijos o claves estables.
- No se mezclan con datos reales en la práctica.

---

### D-09 · Documentación honesta

**Decisión:** documentar solo pruebas ejecutadas y no incluir capturas simuladas.

**Motivo:** la integridad académica exige distinguir entre lo verificado y lo pendiente.

**Consecuencias:**

- `RESULTADOS_PRUEBAS.md` refleja ejecuciones reales.
- `GUIA_EVIDENCIAS.md` explica cómo tomar las capturas.
- El informe final se completa con nombres reales.

---

## 2. Decisiones del caso 1

### D1-01 · Estados que ocupan stock

**Decisión:** `pendiente`, `activo` y `vencido` reservan stock.

**Motivo:** una solicitud pendiente ya compromete una unidad; si no se reservara, dos docentes
podrían solicitar el último equipo y ambas solicitudes parecerían viables.

**Consecuencias:**

- El stock disponible es conservador.
- Al rechazar o devolver se libera.
- El cálculo se hace con `Sum` sobre préstamos que ocupan stock.

---

### D1-02 · Préstamo directo del asistente

**Decisión:** el asistente puede crear un préstamo `activo` sin pasar por `pendiente`.

**Motivo:** en ventanilla el equipo se entrega en el momento; forzar una aprobación posterior
duplicaría trabajo.

**Consecuencias:**

- Dos flujos: solicitud docente y ventanilla.
- Ambos usan el mismo servicio y las mismas validaciones.
- Se audita como aprobación.

---

### D1-03 · Devolución 1:1 y transacción

**Decisión:** `Devolucion` tiene relación uno a uno con `Prestamo` y se registra en transacción.

**Motivo:** evitar devoluciones duplicadas y mantener consistente el estado del equipo.

**Consecuencias:**

- Restricción a nivel de base de datos.
- El préstamo pasa a `devuelto` y se actualiza el equipo.
- La segunda devolución se rechaza con mensaje claro.

---

### D1-04 · Eliminación protegida

**Decisión:** no eliminar equipos con préstamos pendientes, activos o vencidos.

**Motivo:** preservar la trazabilidad y evitar préstamos huérfanos.

**Consecuencias:**

- Se debe devolver o rechazar antes de eliminar.
- El admin y la vista muestran el motivo.
- Los préstamos usan `PROTECT`.

---

## 3. Decisiones del caso 2

### D2-01 · Franja configurable de 30 minutos

**Decisión:** `CITA_DURACION_MINUTOS` con valor por defecto 30.

**Motivo:** el enunciado pide franjas de 30 minutos, pero la duración puede necesitar ajustes.

**Consecuencias:**

- Una sola constante afecta validaciones y cálculo de hora fin.
- Se puede cambiar por variable de entorno.
- Las pruebas usan el valor por defecto.

---

### D2-02 · Restricciones condicionales en base de datos

**Decisión:** usar `UniqueConstraint` con condición sobre citas activas.

**Motivo:** impedir duplicados incluso ante errores de aplicación o concurrencia.

**Consecuencias:**

- Una cita cancelada libera la franja.
- La base y el modelo validan lo mismo.
- Requiere mantener `ESTADOS_CITA_ACTIVOS` coherente.

---

### D2-03 · Consulta inmutable y notas clínicas

**Decisión:** bloquear la edición de `Consulta` y permitir ampliar con `NotaClinica`.

**Motivo:** el historial clínico debe ser íntegro y auditable; la información nueva se agrega sin
alterar lo registrado.

**Consecuencias:**

- No hay edición de diagnósticos ni tratamientos.
- Las correcciones se hacen con notas fechadas y autor.
- El admin muestra las consultas en solo lectura.

---

### D2-04 · Historial con relación asistencial

**Decisión:** un médico solo ve el historial si tiene `ver_historial_clinico` y una cita
confirmada/completada o una consulta previa con el paciente.

**Motivo:** proteger datos sensibles y evitar acceso indiscriminado.

**Consecuencias:**

- La recepción nunca ve datos clínicos.
- El admin sí puede acceder para supervisión.
- Cada acceso se audita.

**Alternativa descartada:** permitir a cualquier médico ver cualquier historial. Viola el principio
de necesidad de conocer.

---

### D2-05 · Separación recepción / clínica

**Decisión:** la recepción gestiona pacientes y citas, pero no consultas ni historiales.

**Motivo:** el personal administrativo no necesita información clínica para agendar.

**Consecuencias:**

- Plantillas y permisos diferenciados.
- Vistas de historial devuelven 403 a recepción.
- Se reduce el riesgo de fuga de datos.

---

## 4. Decisiones del caso 3

### D3-01 · Horas calculadas, no almacenadas

**Decisión:** calcular `total_horas` y `total_extra` en propiedades.

**Motivo:** si se almacenaran, una corrección podría dejar valores inconsistentes.

**Consecuencias:**

- Siempre coinciden con las horas registradas.
- Los reportes agregan en memoria o por propiedad.
- No se puede ordenar por hora calculada en SQL sin anotación adicional.

**Alternativa descartada:** campos persistidos actualizados en cada guardado. Más riesgo de deriva.

---

### D3-02 · Correcciones inmutables y auditadas

**Decisión:** `CorreccionAsistencia` no se puede modificar después de creada.

**Motivo:** la corrección es una evidencia; alterarla destruiría la trazabilidad.

**Consecuencias:**

- Una nueva corrección crea un registro nuevo.
- Se conservan horas anteriores y nuevas.
- Solo RRHH puede corregir.

---

### D3-03 · Saldo anual compartido

**Decisión:** permisos y vacaciones consumen el mismo saldo de 30 días hábiles.

**Motivo:** el enunciado pide un saldo anual de 30 días para permisos y vacaciones.

**Consecuencias:**

- Una solicitud aprobada descuenta el saldo.
- Las pendientes no descuentan.
- Se valida por año calendario si la solicitud cruza de año.

---

### D3-04 · Aprobación por jefe del área o RRHH, sin autoaprobación

**Decisión:** comparar el empleado solicitante con el usuario que resuelve.

**Motivo:** evitar conflictos de interés, incluso si el jefe o RRHH solicitan.

**Consecuencias:**

- El superusuario también queda bloqueado para su propia solicitud.
- Se requiere otra persona con autoridad.
- La vista y el servicio validan lo mismo.

---

### D3-05 · Alcance por área en consultas

**Decisión:** centralizar los querysets visibles en `permissions.py`.

**Motivo:** evitar filtraciones y duplicar lógica en cada vista.

**Consecuencias:**

- Jefe ve su área; empleado solo lo propio; RRHH/Contador ven todo.
- Las vistas de detalle reutilizan las mismas funciones.
- Las pruebas cubren los límites.

---

### D3-06 · Parámetro `ahora` inyectable

**Decisión:** los servicios de marcación aceptan `ahora` para pruebas.

**Motivo:** permitir pruebas deterministas sin depender de la hora real.

**Consecuencias:**

- Pruebas estables a cualquier hora.
- La vista usa la hora del servidor por defecto.
- No afecta la seguridad.

---

## 5. Decisiones sobre scripts y reproducibilidad

### D5-01 · Entornos virtuales por caso

**Decisión:** `instalar.ps1` crea `.venv` dentro de cada caso.

**Motivo:** aislar dependencias y permitir ejecutar los tres sistemas en paralelo.

**Consecuencias:**

- Tres entornos y tres instalaciones de Django.
- Mayor uso de disco.
- Menor riesgo de conflictos.

**Alternativa descartada:** un solo entorno compartido. Funciona en desarrollo, pero acopla los
casos y complica la entrega individual.

---

### D5-02 · Scripts PowerShell

**Decisión:** usar `.ps1` porque el entorno de la práctica es Windows.

**Motivo:** automatizar instalación, ejecución y pruebas sin pasos manuales.

**Consecuencias:**

- Requiere política de ejecución de PowerShell.
- Los comandos también se documentan para ejecución manual.
- Se puede adaptar a Bash si fuera necesario.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Concurrencia en SQLite | Transacciones y `select_for_update()`; PostgreSQL en producción. |
| Fuga de datos clínicos | Permisos por rol y relación; pruebas de 403. |
| Correcciones sin sustento | Justificación mínima y auditoría inmutable. |
| Autoaprobación | Validación explícita en servicio y vista. |
| Sesión olvidada abierta | Middleware de inactividad por caso. |
| Datos demo duplicados | Comando idempotente. |
| Capturas inventadas | Guía de evidencias y documentación honesta. |
| Cambios de modelo sin migración | `makemigrations --check --dry-run` en cada entrega. |

---

## 7. Decisiones pendientes / trabajo futuro

- Agregar API REST si se requiere integración externa.
- Integrar correo real y notificaciones.
- Añadir exportación PDF de reportes.
- Incorporar pruebas de carga y cobertura medida.
- Evaluar PostgreSQL para producción.
- Agregar recuperación de contraseña.
- Añadir firma digital o adjuntos reales en el caso clínico, con las debidas protecciones.
