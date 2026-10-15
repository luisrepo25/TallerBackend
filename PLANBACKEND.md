# Plan de Backend — Sistema de Riesgo de Incendios (UUBR)

Plan de trabajo del backend (Django + DRF + PostGIS), dividido entre **Luis** y **Roly**. Cada tarea referencia el RF/CU que implementa, para que quede trazable con el documento de tesis. Lee `CLAUDE.md` antes de empezar cualquier fase — ahí están las decisiones de diseño que no se deben revertir.

## Registro de cambios (lo último primero)

### 2026-10-14 — Roly
- **Fase 6 completa a nivel de backend** (RF-20, CU20): generación de reportes ejecutivos y dictámenes técnicos en formatos PDF (`reportlab`) y Excel (`openpyxl`), con almacenamiento de metadatos en `reportes_generados`, registro en `bitacora_auditoria`, control RBAC (`ReportesPermission` para Administrador y Oficial de Mando) y descarga directa vía streaming HTTP con `Content-Disposition`. 9 tests unitarios/integración automatizados pasando con `--keepdb`. Detalle en la sección Fase 6.

### 2026-10-13 — Luis
- **Fase 5 completa a nivel de backend** (RF-17, RF-18, RF-19): microservicio de clustering en `Sistema/MicroservicioML/` (carpeta aparte, será su propio repo), integración en `apps/analitica/` y endpoints `clustering/`, `mapa-calor/`, `distritos/` y `zonas-sugeridas/`. Detalle en la Fase 5.
- **`BasedeDatos.sql` es ahora el ÚNICO archivo de esquema.** Se eliminaron `parche_v8_1.sql`, `parche_v9_solicitudes_material.sql` y `parche_v10_distritos.sql` (siguen en el historial de git). El archivo quedó **idempotente**: se puede ejecutar completo en Supabase sin duplicar nada, y su cabecera explica cómo agregar cambios futuros. Incluye la tabla nueva `distritos` (v10, **ya creada en Supabase**) y los 3 índices del v8.1.
  - Los 3 índices del v8.1 (`idx_actas_inspector`, `idx_actas_cerrada`, `idx_cobertura_hidrante`) no existían en Supabase; se crearon hoy al ejecutar `BasedeDatos.sql` completo (sin duplicar datos de catálogo).
- **Distritos cargados (2026-10-13):** `geo.gob.bo` (GeoBolivia) y Overpass/OSM no respondían, así que se usó la **API pública de la Guía Urbana del GAMSC** con `Sistema/distrito/scriptdistrito.py` (requiere `pip install requests`; hace ~20 GET con pausa de 0.5 s y guarda `distritos_gamsc.geojson`). Trajo 18 elementos: los distritos urbanos 1–12, el 13 (urbano/rural), el 14, el 15 (Montero Hoyos) y el Distrito Industrial, más "Área Urbana" y "limite jurisdiccional", que **no son distritos** y se excluyen. Se verificó: coordenadas en Santa Cruz, sin solapamientos, y el Industrial traía un contorno que se cruza (se reparó con `--reparar`; su área no cambió: 22.1 km²). Se cargó con:
  `python manage.py importar_distritos datos/distritos_gamsc.geojson --excluir "Área Urbana" "limite jurisdiccional" --reparar`
  El archivo está versionado en `Backend/datos/distritos_gamsc.geojson` (102 KB). Cada polígono trae su ordenanza de aprobación en las propiedades originales (p. ej. Ordenanza Municipal 078/2005 - PLOT), que el importador no guarda. Para recargar basta repetir el comando (es idempotente por nombre).
  - Los nombres quedaron tal como los publica el GAMSC ("Distrito Urbano 1", ..., "Distrito Industrial"). Los 16 polígonos suman unos 380 km², mientras que el "límite jurisdiccional" del municipio abarca 1405 km²: buena parte del municipio rural no pertenece a ningún distrito, y un predio ahí cuenta en `inspeccionados_sin_distrito`.
  - Datos reales hoy: 2 predios y 3 actas cerradas. Para tener algo que mostrar y probar, ver los **datos de demostración** (75 predios y 93 actas simuladas) más abajo en este mismo registro.
- **Configuración local:** `Backend/.env` ya tiene `ML_SERVICE_URL`, `ML_API_KEY` y `ML_TIMEOUT_SEGUNDOS`; `MicroservicioML/.env` tiene la misma clave (cada quien genera la suya en su máquina; no se versiona).
  - **Regla nueva:** no crear más archivos `parche_*.sql`; cualquier cambio de esquema va en `BasedeDatos.sql` (ver `CLAUDE.md`).
- **Datos de demostración para probar la Fase 5 (`datos/` y `manage.py cargar_datos_demo`):** como la BD real tenía 2 predios y 3 actas, se descargaron de OpenStreetMap **472 predios reales con nombre** de Santa Cruz (hospitales, clínicas, colegios, universidades, mercados, centros comerciales e industrias; `datos/predios_osm_santacruz.geojson`) y 7 hidrantes. `cargar_datos_demo` toma una muestra (15 por tipo), crea los predios y les hace inspecciones **simuladas** pasando por los servicios reales (`registrar_acta` → materiales → infracciones → `cerrar_acta`), así que carga de fuego y scoring son los oficiales. La simulación (`analitica/demo_simulacion.py`) usa un riesgo latente por predio según su tipo, con traslape entre tipos, y ~15 % de predios reciben una reinspección (prueba la reincidencia y el criterio de "última acta"). Todo queda marcado (`atributos_extra.demo`, campaña `[DEMO]…` cerrada, hidrantes `DEMO-OSM-*`, inspector `demo.inspector@uubr.invalid` sin contraseña) y **se borra con `cargar_datos_demo --borrar`**. 11 tests (5 de simulación sin BD y 1 de carga+borrado completo). ⚠️ **Las actas demo son ficticias: no presentarlas como inspecciones reales y borrarlas antes de producción.** Los datos de OpenStreetMap exigen citar "© OpenStreetMap contributors" (ODbL); ver `datos/README.md`.
  - **Ya cargado en Supabase (2026-10-13): 75 predios, 93 actas cerradas simuladas y 7 hidrantes.** Prueba de punta a punta con el microservicio real (dentro de una transacción revertida, así que **`cluster_riesgo` aún no está guardado**: falta que un Administrador ejecute `POST api/analitica/clustering/`): 96 actas (93 demo + 3 reales) → silueta **0.249** (grupos que se traslapan, esperable con datos simulados; no es un defecto del microservicio), clusters Bajo 48 / Medio 25 / Crítico 23 con scoring promedio 25 / 45 / 64 (orden correcto). Los industriales son los más críticos (8 de 15) y los educativos/de salud los menos, como se programó. Mapa de calor: 76 puntos. Zonas sugeridas, primeras: Distrito Industrial (4 críticos, 67 %), Urbano 11, Urbano 1, Urbano 7, Urbano 5. 5 predios de la muestra quedan fuera de todo distrito. **Ojo al interpretar:** la estructura que "descubre" el clustering es la que puso la simulación; sirve para validar el flujo, no para sacar conclusiones sobre el riesgo real.
- **Decisión de negocio:** `cluster_riesgo` ya **no** es una foto histórica: cada ejecución del clustering lo reasigna en todas las actas cerradas. Carga de fuego, scoring y distancia sí siguen siendo fotos. Quedó anotado en `CLAUDE.md` y en el comentario de la columna.
- **Cambio en código de Roly (Fase 4):** `riesgo_extintores()` se extrajo de `calcular_scoring_riesgo` en `fiscalizacion/services.py`. Mismo comportamiento; lo reutiliza analítica. Sus 49 tests siguen pasando.
- **Variables nuevas en `.env`:** `ML_SERVICE_URL` (desde Docker: `http://host.docker.internal:8001`), `ML_API_KEY` (idéntica a la del `.env` del microservicio; la inventa quien configura) y `ML_TIMEOUT_SEGUNDOS`. Ver `.env.example`.
- **Para correr el clustering en local:** levantar primero el microservicio (`docker compose up` dentro de `MicroservicioML/`, puerto 8001) y luego llamar a `POST api/analitica/clustering/` como Administrador.
- **Frontend y móvil:** ver las notas de hoy en `FRONTEND.md` (Fase F6 desbloqueada, rutas en §9) y `MOVIL.md` (§10, nota sobre el cluster).

## Arquitectura: 3 capas

Todo el backend sigue una arquitectura de **3 capas**, y cada app de Django debe respetar esta separación — no mezclar responsabilidades entre capas:

| Capa | Responsabilidad | Dónde vive en cada app |
|---|---|---|
| **Presentación** | Recibe la petición HTTP, valida el formato de entrada, arma la respuesta. No contiene reglas de negocio. | `views.py` / `viewsets.py` + `serializers.py` |
| **Negocio (lógica de aplicación)** | Reglas de negocio, cálculos, validaciones de dominio, orquestación entre modelos. Es la única capa que decide "qué hacer". | `services.py` (uno por app, o carpeta `services/` si crece) |
| **Datos** | Acceso y persistencia. Solo estructura y relaciones, sin lógica de negocio dentro de los modelos (nada de métodos que calculen scoring, por ejemplo). | `models.py` |

**Regla práctica:** una vista **nunca** llama directo al ORM para hacer una operación con lógica (ej. cerrar un acta y calcular su scoring) — la vista llama a una función de `services.py`, y esa función es la que usa los modelos. Esto es exactamente por qué `calcular_carga_fuego()` y `calcular_scoring_riesgo()` van en `fiscalizacion/services.py` y no como método de `ActaInspeccion` ni código suelto dentro de la vista de "cerrar acta" (Fase 4).

Aplica esto en cada fase de abajo: si una tarea dice "endpoint que hace X", el endpoint (presentación) delega a una función de servicio (negocio), que a su vez usa los modelos (datos).

## Cómo está organizado

- **Fases secuenciales**: no hay que terminar el 100% de una fase para empezar la siguiente, pero respeta las dependencias marcadas.
- **Cada tarea tiene un dueño** (Luis / Roly), pensado para minimizar conflictos de merge (cada quien trabaja en modelos/apps distintas la mayor parte del tiempo).
- **Rama por tarea**: `feature/<modulo>-<breve-descripcion>` (ej. `feature/actas-registro`). PR revisado por el otro antes de mergear a `develop`.
- Marca con `[x]` lo que termines y agrega la fecha, para que el otro sepa el avance sin tener que preguntar.

---

## Fase 0 — Setup del proyecto (AMBOS, en conjunto)

- [x] Crear repositorio y estructura base del proyecto Django (`apps/` por módulo: `usuarios`, `catastro`, `campanias`, `fiscalizacion`, `analitica`, `reportes`), cada una con el esqueleto de 3 capas (`models.py`, `services.py`, `views.py`/`viewsets.py`, `serializers.py`) desde el inicio — **2026-09-26**. Corre en Docker (`Dockerfile` + `docker-compose.yml`) para no depender de instalar GDAL/GEOS nativos en Windows.
- [x] Configurar `settings.py` con GeoDjango (`django.contrib.gis`) y conexión a PostgreSQL/PostGIS (Supabase) — **2026-09-26**. Verificado con `manage.py check` y `manage.py showmigrations` conectando en vivo a Supabase.
- [x] Configurar variables de entorno (`.env` + `django-environ`): credenciales de BD, `SECRET_KEY` — **2026-09-26**. `.env.example` versionado en git con placeholders; `.env` real (con credenciales reales) queda ignorado, Luis lo comparte por canal privado. Pendiente: credenciales del microservicio ML (aún no existe ese servicio).
- [x] Instalar y configurar Django REST Framework + `djangorestframework-simplejwt` (JWT, ver RF-1) — **2026-09-26**. Endpoints `api/auth/token/` y `api/auth/token/refresh/` wireados en `config/urls.py`. Nota: se usó DRF 3.18.1 en vez de una versión anterior porque 3.16 no es compatible con Django 6.1 (`ImportError: cc_delim_re`).
- [x] Configurar `drf-spectacular` (documentación OpenAPI/Swagger automática) — **2026-09-26**. Disponible en `api/schema/` y `api/docs/`.
- [x] Definir convención de serializers/viewsets (ver `CLAUDE.md` — nombres en español, serializers explícitos). Aplicada en las Fases 1 a 4.
- [x] Configurar linting (`ruff` + `black`) — **2026-09-26**. Config en `pyproject.toml`. Se decidió no usar pre-commit hook (innecesario para el equipo por ahora); correr `ruff check .` y `black .` manualmente o vía CI cuando se configure.
- [x] Correr el script `BasedeDatos.sql` contra Supabase — **hecho por Luis, 2026-09-26** (24 tablas + datos iniciales creados, RLS activado en las 24 tablas para cerrar el acceso público vía la API REST de Supabase, ver sección "Base de datos" de `CLAUDE.md`).
- [x] Correr `manage.py migrate` (tablas internas de Django: auth, admin, sessions, contenttypes) contra Supabase y activar RLS en ellas también — **2026-09-26**.
- [x] Generar los modelos Django con `inspectdb` a partir del schema ya creado en Supabase y limpiarlos — **2026-09-26**. Los 24 modelos ya están escritos a mano y repartidos en el `models.py` de cada app (`managed = False` porque `BasedeDatos.sql` es la fuente de verdad del esquema, no las migraciones de Django), con FKs correctas a subtipos (`Administrador`/`InspectorTecnico`/`OficialMando`), `GeometryField` (Polygon/Point, SRID 4326) en `predios`/`hidrantes`/`campanias`, `JSONField` en `atributos_extra` y `parametros`, `CompositePrimaryKey` en las 3 tablas N:M con atributos propios. Verificado contra Supabase real: `manage.py check` sin errores y queries de conteo/lectura funcionando en las 24 tablas. **Nota para Luis/Roly**: estos modelos son solo la capa de datos (sin métodos ni lógica) — cada Fase agrega sus managers/servicios/serializers/vistas encima, no debería hacer falta tocar `models.py` salvo error de mapeo.

**Bloqueante para todo lo demás.**

---

## Fase 1 — Usuarios, Auth y RBAC — *dueño: Luis*

Referencia: RF-1, RF-2, RF-3, CU01, CU02, CU03

- [x] Modelo `Usuario` (con `rol_id` FK directa — **no crear tabla `usuario_rol`**, ver `CLAUDE.md`) — **2026-09-27**. `apps/usuarios/models.py`, `AbstractBaseUser` custom con `UsuarioManager.create_user`, `USERNAME_FIELD = "email"`.
- [x] Modelos `Administrador`, `InspectorTecnico`, `OficialMando` (subtipos solapados, `usuario` como PK/FK 1:1) — **2026-09-27**.
- [x] Modelos `Rol`, `Permiso`, `RolPermiso` — **2026-09-27**.
- [x] Endpoint de login (JWT) — RF-1 — **2026-09-27**. `api/auth/token/` y `api/auth/token/refresh/` (`TokenObtainPairView`/`TokenRefreshView`, wireados en `config/urls.py`).
- [x] Endpoints CRUD de roles y permisos — RF-2 — **2026-09-27**. `RolViewSet`/`PermisoViewSet`/`UsuarioViewSet` en `apps/usuarios/views.py`, registrados en `apps/usuarios/urls.py` (`api/usuarios/roles/`, `api/usuarios/permisos/`, `api/usuarios/usuarios/`), protegidos con `IsAdministrador`. Los permisos que exige cada acción se resuelven vía estas permission classes, no en BD.
- [x] Middleware o mixin que registre automáticamente en `BitacoraAuditoria` cada acción crítica, guardando el `rol_id` **actual** del usuario al momento de la acción (snapshot histórico) — RF-3 — **2026-09-27**. `apps/usuarios/mixins.py` + `services.registrar_bitacora()`. Pendiente: conectarlo a las acciones críticas reales (crear campaña, cerrar acta, generar/descargar reporte) cuando esas vistas existan (Fases 3, 4, 6).
- [x] Permisos de DRF (`IsAdministrador`, `IsInspectorTecnico`, `IsOficialMando`) como clases reutilizables, basadas en pertenencia a los subtipos, no en el campo `rol` — **2026-09-27**. `apps/usuarios/permissions.py`.
- [x] Endpoint `GET api/usuarios/me/` (usuario autenticado + `subtipos[]`), requerido por el frontend para decidir la UI por rol — **2026-10-09**. `PerfilView`/`PerfilSerializer` + `services.obtener_subtipos()`; 2 tests nuevos.
- [x] Rendimiento y 500 intermitentes con Supabase — **2026-10-09**. Los 500 eran conexiones nuevas a Supabase cerradas de golpe (`server closed the connection unexpectedly`); cada petición abría una (~1.8 s). Ahora: `CONN_MAX_AGE` (`DB_CONN_MAX_AGE`, 300 en dev) + `CONN_HEALTH_CHECKS` + keepalives TCP, `runserver --nothreading` en `docker-compose.yml` (con un hilo por petición no se reutilizan las conexiones), y `JWTAuthenticationConSubtipos` (carga rol y subtipos en la consulta de autenticación: los permisos `hasattr(user, "administrador")` ya no consultan). Vigilado con `assertNumQueries` en 2 tests. **Pendiente:** cada consulta aún cuesta ~0.3 s por la distancia a la región `us-west-2`; opciones: PostGIS local para desarrollo, o mover el proyecto de Supabase a una región más cercana (São Paulo).
- [x] Tests: login válido/inválido, creación de usuario con su subtipo en una sola transacción, bitácora se registra correctamente, permisos de los endpoints CRUD (`IsAdministrador` bloquea a otros subtipos, no autenticado rechazado) — **2026-09-27**. `apps/usuarios/tests/test_usuarios.py`, 9 tests, corren con `docker compose exec web python manage.py test --keepdb` (la BD de test reutiliza la misma Supabase, ver `settings.py`).

---

## Fase 2 — Catastro Geoespacial — *dueño: Roly*

Referencia: RF-4, RF-5, RF-6, CU04, CU05, CU06

- [x] Modelo `CatalogoTipoPredio` (extensible, con `riesgo_activacion`) — **2026-09-28**. En `apps/catastro/models.py`.
- [x] Modelo `Predio` (`GeometryField(Polygon, srid=4326)`, `area_m2`, `atributos_extra` como `JSONField`) — **2026-09-28**. En `apps/catastro/models.py`.
- [x] Modelo `CatalogoTipoAcople`, modelo `Hidrante` (`GeometryField(Point, srid=4326)`) — **2026-09-28**. En `apps/catastro/models.py`.
- [x] Modelo `PredioHidranteCobertura` (N:M con atributos: `distancia_m`, `es_mas_cercano`) — **2026-09-28**. En `apps/catastro/models.py`.
- [x] Endpoint para registrar predio con geometría (recibir GeoJSON desde el frontend React con react-leaflet) — RF-4 — **2026-09-28**. `PredioViewSet` en `apps/catastro/views.py` con `GeometryJSONField` (soporta dict/string GeoJSON Polygon en SRID 4326), integrado con `BitacoraAuditoriaMixin` y validación de permisos `IsCatastroEditorOrReadOnly`.
- [x] Endpoint para registrar hidrante — RF-5 — **2026-09-28**. `HidranteViewSet` en `apps/catastro/views.py` con `GeometryJSONField` (GeoJSON Point en SRID 4326), filtro por `estado_operativo` y registro en bitácora.
- [x] Función/servicio `calcular_cobertura_hidrantes(predio)`: usa `django.contrib.gis.db.models.functions.Distance` para calcular distancia a hidrantes activos y poblar `PredioHidranteCobertura` — RF-6 — **2026-09-28**. `apps/catastro/services.py`, ejecución `@transaction.atomic`, calcula distancias geodésicas sobre la esfera en metros, marca `es_mas_cercano = True` al de menor distancia e ignora hidrantes fuera de servicio.
- [x] Endpoint que devuelva el hidrante más cercano activo a un predio dado (usado luego por Fiscalización) — **2026-09-28**. Acción `@action` `api/catastro/predios/{id}/hidrante-cercano/`, retorna detalle del hidrante activo más cercano y distancia exacta en metros.
- [x] Manejador de excepciones global (`apps/common/exceptions.py`, `EXCEPTION_HANDLER` en settings): un `ProtectedError` al borrar (ej. predio con actas, tipo de predio en uso) responde **409** con `dependientes` en vez de 500 — **2026-10-09**. 2 tests nuevos en `test_catastro.py`. Además, `test_predio_sin_hidrantes_activos_retorna_vacio` ahora desactiva todos los hidrantes: los tests corren sobre la BD real compartida y fallaban en cuanto había un hidrante real activo.
- [x] Tests: cálculo de distancia con datos conocidos, filtrado de hidrantes inactivos, validación GeoJSON, endpoints y control de permisos — **2026-09-28**. `apps/catastro/tests/test_catastro.py`, 12 tests ejecutados y pasando al 100% en Docker contra Supabase.

---

## Fase 3 — Campañas de Fiscalización — *dueño: Luis*

Referencia: RF-7 a RF-11, CU07 a CU11

- [x] Modelo `Campania` (`GeometryField(Polygon)`, `creado_por` FK a `Administrador`) — **2026-10-03**. Ya existía desde la Fase 0 (`apps/campanias/models.py`); sin cambios.
- [x] Modelo `CampaniaFuncionarios` (N:M con atributo `fecha_asignacion`, `usuario` FK a `InspectorTecnico`) — **2026-10-03**. Ya existía desde la Fase 0 (`CampaniaFuncionario`, `CompositePrimaryKey`).
- [x] Endpoint crear campaña (solo Administrador) — RF-7 — **2026-10-03**. `POST api/campanias/campanias/`. Nace `pendiente`; `creado_por` sale del usuario autenticado y `estado` es de solo lectura. Lectura: Administrador y Oficial ven todas, el Inspector solo las suyas. No existe DELETE: una campaña se cierra, no se borra.
- [x] Endpoint para delimitar/actualizar el polígono de zona — RF-8 — **2026-10-03**. `PUT api/campanias/campanias/{id}/zona/` (también se acepta `geom` en PATCH). Valida Polygon, SRID 4326 y geometría válida; no se edita una campaña cerrada (409).
- [x] Endpoint asignar/quitar inspectores a una campaña — RF-9 — **2026-10-03**. `GET {id}/inspectores/`, `POST {id}/asignar-inspectores/` (idempotente, body `{"usuarios_ids": [...]}`) y `DELETE {id}/inspectores/{usuario_id}/`. La primera asignación pasa la campaña de `pendiente` a `en_curso`. No se quita a un inspector que ya registró actas (409).
- [x] Endpoint consultar avance: `% = actas cerradas / predios dentro del polígono (ST_Intersects)` — RF-10 — **2026-10-03**. `GET {id}/avance/` (Administrador y Oficial). Sin tabla Predio-Campania: `services.predios_en_zona()` es la única definición. Un predio en el borde de dos zonas cuenta en ambas. Sin polígono o sin predios, el porcentaje es 0.
- [x] Endpoint cerrar campaña (validar que no queden inspecciones pendientes) — RF-11 — **2026-10-03**. `POST {id}/cerrar/`. Responde 409 con `predios_pendientes` y `actas_abiertas` si quedan inspecciones pendientes; el Administrador puede enviar `{"forzar": true}` (queda en bitácora como "Cerrar campania (forzado)").
- [x] Cierre automático por vencimiento — **2026-10-03**. `python manage.py cerrar_campanias_vencidas` cierra toda campaña no cerrada con `fecha_fin` anterior a hoy (equivale a cierre forzado; no registra bitácora porque no hay usuario). **Pendiente:** programarlo diariamente en el hosting (cron/scheduler) en la Fase 8.
- [x] Tests — **2026-10-03**. `apps/campanias/tests/test_campanias.py`, 42 tests: intersección espacial, avance, asignación, cierre normal/forzado/automático y permisos.
- [x] `GeometryJSONField` movido a `apps/common/fields.py` (lo comparten catastro y campañas) — **2026-10-03**.

**Nota para Roly (Fase 4):** al registrar un acta hay que rechazar campañas `cerrada` (el modelo no lo impide) y validar que el inspector esté asignado a la campaña (`campania_funcionarios`). El cierre forzado puede dejar actas abiertas.

---

## Fase 4 — Fiscalización e Inspecciones — *dueño: Roly*

Referencia: RF-12 a RF-16, RF-22, RF-23, CU12 a CU16, CU21, CU22

Este es el módulo más grande — es el corazón del sistema.

> **TODO (Roly):** estas tareas están marcadas `[x]` sin fecha; agregar la fecha de cada una. Confirmar también que se aplicó la nota de la Fase 3 (rechazar campañas `cerrada` y validar que el inspector esté asignado en `campania_funcionarios`) y que los pesos del scoring (0.30/0.20/0.20/0.20/0.10) fueron validados con Luis y el docente.

- [x] Modelo `CatalogoEstadoExtintor`, `CatalogoInfraccion`, `CatalogoMaterialCombustible`.
- [x] Modelo `ActaInspeccion` (incluir `uuid_local`, `sincronizada`, `fecha_sincronizacion` desde el inicio — los necesita la Fase 7 de sync).
- [x] Modelo `MaterialRegistrado` (peso por material, entidad débil de `ActaInspeccion`).
- [x] Modelo `EvidenciaFotografica`, modelo `Infraccion`.
- [x] Endpoint registrar acta (predio + campaña + inspector) — RF-12.
- [x] Endpoint subir evidencia fotográfica (guardar en storage — definir con Luis si es S3, Supabase Storage, o filesystem) — RF-13.
- [x] Endpoint registrar materiales combustibles de una acta — RF-22. El inspector solo ingresa tipo de material y peso (kg) desde el móvil; **nadie ingresa la carga de fuego a mano**. Desde la web, Administrador y Oficial de Mando solo **consultan** los materiales y la carga de fuego ya calculada (lectura, sin registro manual en la web).
- [x] **`fiscalizacion/services.py`** (capa de negocio): función `calcular_carga_fuego(acta)` (Σ peso_kg × poder_calorífico × coeficiente_peligrosidad × Ra del tipo de predio ÷ `area_m2`, NB 58005; con `aggregate`/`F()`, no traer filas a Python) — RF-23.
- [x] En el mismo `services.py`: función `calcular_scoring_riesgo(acta)`, combina carga de fuego + estado extintores + fallas eléctricas + rutas de evacuación + distancia a hidrante en un puntaje — RF-14. Constantes y topes centralizados en `fiscalizacion/services.py` (0.30 carga fuego, 0.20 extintores, 0.20 fallas, 0.20 rutas, 0.10 distancia hidrante).
- [x] Endpoint (capa de presentación) cerrar acta: **solo llama** a `services.cerrar_acta(acta)`, que internamente encadena `calcular_carga_fuego` → `calcular_scoring_riesgo` → guarda ambos. La vista no calcula nada por sí misma.
- [x] Endpoint consultar historial de inspecciones por predio/zona — RF-15. El detalle de cada acta debe incluir los materiales registrados y la carga de fuego calculada (lectura para Administrador y Oficial de Mando en la web).
- [x] Lógica de detección de reincidencia: al registrar una infracción, verificar si ya existe una infracción del mismo `tipo_infraccion` en actas anteriores del mismo predio — RF-16.
- [x] Tests: cálculo de carga de fuego contra el ejemplo ya verificado (300kg madera + 150kg plástico, mercado 200m² → 83.61 MJ/m²), detección de reincidencia, entidades débiles se borran en cascada al borrar el acta. (22 tests pasando).

---

## Fase 5 — Analítica e Inteligencia Artificial — *dueño: Luis*

Referencia: RF-17 a RF-19, CU17 a CU19

- [x] Modelo `ClusteringEjecucion` — ya existía desde la Fase 0.
- [x] Microservicio Python separado — **2026-10-13**. Carpeta `Sistema/MicroservicioML/` (FastAPI + scikit-learn, sin estado ni acceso a BD, auth por `X-API-Key`). Recibe las actas por JSON, escala (`StandardScaler`), ejecuta K-Means (k=3), calcula la silueta y devuelve el cluster por acta; los clusters se nombran por scoring promedio (Bajo/Medio/Critico). 14 tests. Contrato en su README.
- [x] Endpoint que dispare la ejecución (solo Administrador) y guarde el resultado — RF-17 — **2026-10-13**. `POST api/analitica/clustering/` (201; 409 si hay pocas actas; 503 si el microservicio no responde) y `GET api/analitica/clustering/` (historial; Administrador y Oficial). `analitica/services.py` arma el payload, llama al ML (`cliente_ml.py`, fuera de la transacción) y guarda `ActaInspeccion.cluster_riesgo` + `ClusteringEjecucion` + bitácora en una sola transacción. 15 tests con el ML simulado. Variables nuevas en `.env`: `ML_SERVICE_URL`, `ML_API_KEY`, `ML_TIMEOUT_SEGUNDOS`.
  - **Nota para Roly:** se extrajo `riesgo_extintores()` de `calcular_scoring_riesgo` en `fiscalizacion/services.py` (mismo comportamiento) para reutilizarla en analítica sin duplicar la regla.
  - **Decidido (Luis, 2026-10-13):** cada ejecución reasigna el cluster de **todas** las actas cerradas (K-Means depende del conjunto completo). Es una excepción a la regla de "fotografía histórica", que ahora aplica solo a carga de fuego, scoring y distancia; quedó documentado en `CLAUDE.md`. Las reinspecciones del mismo predio cuentan como actas separadas.
- [x] Endpoints de datos para el mapa de calor y la capa por distrito — RF-18 — **2026-10-13**. "Zona" = **distrito municipal** (lo pide la tesis). Nueva tabla `distritos` (MultiPolygon 4326, RLS) y modelo `Distrito`; sin FK con predios: el distrito de un predio sale de `ST_Contains` sobre su **centroide** (así un predio que cruza un límite cuenta una sola vez). Toda la lógica en `analitica/zonificacion.py`; "situación actual" = la **última acta cerrada de cada predio**. Solo Administrador y Oficial:
  - `GET api/analitica/mapa-calor/` (`?cluster=`, `?campania_id=`): un punto por predio `{lat, lng, scoring_riesgo, cluster_riesgo, intensidad}`.
  - `GET api/analitica/distritos/`: por distrito, su polígono GeoJSON, predios registrados/inspeccionados, conteo por cluster, `nivel_predominante` (el cluster con más predios; en empate gana el más severo), `% crítico`, scoring promedio, infracciones y reincidencias, más `inspeccionados_sin_distrito`.
  - `python manage.py importar_distritos <archivo.geojson> [--campo-nombre NOMBRE] [--excluir NOMBRE ...] [--reparar]`: carga/actualiza los polígonos (idempotente por nombre, todo o nada, acepta Polygon y MultiPolygon). `--excluir` omite elementos que no son distritos; `--reparar` corrige con GEOS los polígonos inválidos y lo informa (sin él, un polígono inválido se rechaza).
  - **Distritos cargados en Supabase (2026-10-13): 16 polígonos oficiales** de la Guía Urbana del GAMSC (ver el registro de cambios). Ya no están vacíos.
- [x] Lógica de priorización de zonas — RF-19 — **2026-10-13**. `GET api/analitica/zonas-sugeridas/?limite=5`: distritos con al menos 1 predio Crítico. Orden: primero los que **no** tienen una campaña activa (pendiente o en curso) tocando su territorio, luego más predios Críticos y mayor % de Críticos. Cada zona trae `campanias_activas[]`. No se inventó ningún umbral: basta 1 predio Crítico y `limite` acota la lista.
- [x] Tests — **2026-10-13**. Silueta reproducible sobre dataset fijo (`MicroservicioML/tests`, 14 tests), clustering en Django con el ML simulado (15) y zonificación/importación/permisos (21) en `analitica/tests/`. Los tests de analítica crean sus datos en una zona despoblada (lon -63.0, lat -20.0), a ≤ 1000 km de los hidrantes: más lejos, `predio_hidrante_cobertura.distancia_m NUMERIC(8,2)` desborda.
- [x] Prueba de integración con el microservicio **real** — **2026-10-13**. Backend (Docker) → `host.docker.internal:8001` → microservicio, con la `ML_API_KEY` compartida: autenticación OK, un lote sintético de 12 actas devolvió 3 clusters correctos con silueta 0.997, y con las 3 actas cerradas reales de hoy respondió el 409 esperado ("al menos 4 actas"). Probado dentro de una transacción revertida: no se escribió ningún cluster en Supabase. **Aún no se ha ejecutado el clustering sobre datos reales** (solo hay 3 actas reales cerradas con scoring; hacen falta 4). Más tarde ese mismo día se cargaron datos de demostración y se repitió la prueba con 96 actas (ver el registro de cambios).

---

## Fase 6 — Reportes — *dueño: Roly*

Referencia: RF-20, CU20

- [x] Modelo `ReporteGenerado` — **2026-10-14**. Mapeado a la tabla existente `reportes_generados` (`managed = False`). Registra metadatos de auditoría: `tipo` (`ejecutivo` o `dictamen`), `formato` (`PDF` o `Excel`), filtros utilizados en JSONB (`campania_id`, `acta_id`, `predio_id`), usuario solicitante (`generado_por`) y fecha/hora UTC. Solo `Administrador` y `Oficial de Mando` tienen acceso (`ReportesPermission`).
- [x] Generador de reporte ejecutivo y dictamen técnico en PDF (`ReportLab`) — **2026-10-14**. Implementado en `apps/reportes/pdf_generator.py`:
  - **Reporte Ejecutivo**: Resumen consolidado de campaña con métricas de inspección, distribución porcentual y conteo por nivel de riesgo / cluster K-Means, promedio de carga de fuego (NB 58005) y scoring, y tabla detallada de predios inspeccionados.
  - **Dictamen Técnico de Prevención contra Incendios**: Ficha técnica formal por predio/acta con datos catastrales, contacto del propietario, evaluación de extintores, rutas de evacuación, instalaciones eléctricas, detalle de materiales combustibles calculados, scoring de riesgo y cluster asignado.
  - Formato institucional UUBR con paleta `#14213D` (azul marino) y `#D7263D` (rojo bomberil), tablas formateadas y paginación dinámica `NumberedCanvas` ("Página X de Y").
- [x] Generador de reportes en Excel (`openpyxl`) con detalle tabular — **2026-10-14**. Implementado en `apps/reportes/excel_generator.py`:
  - **Reporte Ejecutivo (Excel)**: Libro con dos hojas: hoja *"Resumen Ejecutivo"* con KPIs agregados, y hoja *"Inspecciones"* con matriz completa de actas, fechas, direcciones, cargas de fuego, scoring y clusters.
  - **Dictamen Técnico (Excel)**: Hoja técnica estructurada con secciones de datos generales, evaluación de seguridad y desglose analítico de riesgo.
  - Estilos corporativos UUBR, cabeceras con fondo azul y texto blanco en negrita, bordes finos, alineaciones optimizadas y cálculo automático del ancho de columnas.
- [x] Endpoints de generación y consulta histórica — **2026-10-14**:
  - `POST /api/reportes/generar/`: Valida parámetros vía `GenerarReporteInputSerializer`, delega la orquestación a `services.generar_reporte` (que obtiene datos, genera los bytes en memoria con `BytesIO`, registra el reporte en `reportes_generados` y audita en `bitacora_auditoria`), y retorna el archivo descargable como stream binario (`Content-Disposition: attachment; filename=...`, `application/pdf` o `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`).
  - `GET /api/reportes/reportes/`: `ReporteGeneradoViewSet` (ReadOnly) para consultar el historial de reportes generados con ordenamiento cronológico inverso.
- [x] Tests automatizados — **2026-10-14**: Suite en `apps/reportes/tests/test_reportes.py` con 9 tests pasando (`--keepdb`): generación de reporte ejecutivo en PDF y Excel, dictamen técnico en PDF y Excel, validación de inputs erróneos, control de permisos RBAC para inspector (prohibido) vs administrador (permitido), y consulta del historial.

---

## Fase 7 — API de Sincronización Offline (para la app Flutter) — *dueño: Luis*

Referencia: RF-21, CU23 — **este módulo es crítico, no dejarlo para el final**

- [x] Endpoint `POST /api/fiscalizacion/sync/actas/` — **2026-10-09**. Recibe un lote (máx. 50) de actas **completas** (`uuid_local`, predio, campaña, extintores, fallas, rutas, `fecha_inspeccion` del dispositivo, materiales, infracciones, evidencias por URL) y responde 200 con el resultado **por acta**. Solo Inspector Técnico. Código: `sincronizacion.py` (negocio), `sync_serializers.py`, `sync_views.py`.
- [x] Deduplicación: si el `uuid_local` ya existe devuelve `ya_sincronizada` con lo guardado (también si dos peticiones chocan en la carrera: se captura el `IntegrityError`). Un `uuid_local` de otro inspector se rechaza (`uuid_en_uso`) sin revelar nada del acta ajena — **2026-10-09**.
- [x] Manejo de conflictos por acta, sin frenar el lote: `rechazada` con `codigo` (`conflicto` = campaña cerrada; `validacion` = predio/campaña/catálogo inexistente, predio fuera de la zona, inspector no asignado, fecha futura; `datos_invalidos` = formato) o `error_temporal` (falla inesperada del servidor: la app reintenta) — **2026-10-09**. Cada acta va en su propia transacción: un error a mitad no deja nada a medias.
- [x] Al recibirla se llama a `cerrar_acta` (que calcula carga de fuego y scoring) y la respuesta los devuelve, junto con la reincidencia de cada infracción — **2026-10-09**.
- [x] `sincronizada = true` y `fecha_sincronizacion`; la `fecha_inspeccion` del dispositivo se respeta (se escribe con `update`, porque `auto_now_add` la pisaría; se rechaza si está más de 5 min en el futuro) — **2026-10-09** (brecha G3).
- [x] Tests: `tests/test_sync.py`, 14 tests (acta completa, fecha del dispositivo, fecha futura, reintento idempotente, lote parcial, acta mal formada, campaña cerrada offline, predio fuera de zona, inspector no asignado, atomicidad, reincidencia, uuid ajeno, permisos, tamaño de lote) — **2026-10-09**.
- [x] **Zona horaria (brecha G8)** — **2026-10-09**. Las columnas `timestamp without time zone` guardan UTC, pero Django las devolvía como fechas **sin zona**: la API enviaba `2026-10-10T00:56:06` y web/móvil las mostraban 4 h corridas. Nuevo campo `UtcDateTimeField` (`apps/common/model_fields.py`) usado en todos los modelos: marca UTC al leer, y la API responde ISO 8601 con zona (`2026-10-09T20:56:06-04:00`).
- [x] **Subida de fotos** a Cloudinary (brecha G2) — **2026-10-10**. `POST /api/fiscalizacion/evidencias/subir/` (multipart, campo `imagen`; solo Inspector; JPG/PNG/WEBP, máx. 10 MB) valida la foto (`services.subir_imagen_evidencia`), la sube con firma desde el servidor (`apps/common/cloudinary_storage.py`, sin SDK) y devuelve `url_imagen`. No depende de un acta: la app sube cada foto y luego envía las URLs dentro del acta. Sin tope de fotos por acta. Verificado de punta a punta con la app móvil real (actas 138 y 139).
- [x] **Solicitud de material nuevo** — **2026-10-10**. El Inspector no crea materiales (Hi y Ci son datos tabulados de la NB 58005): los solicita en `POST /api/fiscalizacion/solicitudes-material/` (idempotente por `uuid_local`) y el Administrador los aprueba dando Hi y Ci (`.../{id}/aprobar/`, crea el material en el catálogo) o los rechaza con motivo (`.../{id}/rechazar/`). Mientras estén pendientes no cuentan en la carga de fuego. Requiere la tabla `solicitudes_material` (con RLS; v9 de `BasedeDatos.sql`, aplicada en Supabase 2026-10-10). Tests: `tests/test_solicitudes_evidencias.py`. **Pendiente:** pantalla en la web para que el Administrador las apruebe (hoy solo por la API).

---

## Fase 8 — Documentación, testing final y despliegue (AMBOS)

- [ ] Revisar que la documentación Swagger (`drf-spectacular`) cubra todos los endpoints con ejemplos.
- [ ] Suite de tests de integración end-to-end de al menos un flujo completo (crear campaña → asignar inspector → registrar acta con materiales → cerrar acta → ejecutar clustering → generar reporte).
- [ ] Configurar despliegue (Railway, Render, u otro — definir con el resto del equipo) apuntando a la BD de Supabase. Ahora son **dos servicios** a desplegar: el backend Django y el microservicio de clustering (`MicroservicioML`, que solo debe ser accesible desde el backend, con su `ML_API_KEY`).
- [ ] Variables de entorno de producción separadas de desarrollo.
- [ ] Checklist de seguridad antes de entregar: `DEBUG=False`, `ALLOWED_HOSTS` configurado, CORS restringido al dominio del frontend y la app.

---

## Notas para ambos

- Antes de tocar el módulo del otro, avisen — aunque la división busca minimizar cruces, `ActaInspeccion` (Fase 4) depende de modelos de Fase 1, 2 y 3, así que esas deben ir razonablemente avanzadas primero.
- Cualquier decisión que no esté clara en `CLAUDE.md` ni en este plan (fórmula exacta del scoring, proveedor de storage para fotos, hosting de despliegue) se define en conjunto antes de programarla — no se asume.
- Actualicen este archivo conforme avancen; es más útil que un grupo de WhatsApp para saber en qué está el otro.
