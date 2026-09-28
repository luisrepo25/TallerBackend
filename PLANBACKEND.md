# Plan de Backend — Sistema de Riesgo de Incendios (UUBR)

Plan de trabajo del backend (Django + DRF + PostGIS), dividido entre **Luis** y **Roly**. Cada tarea referencia el RF/CU que implementa, para que quede trazable con el documento de tesis. Lee `CLAUDE.md` antes de empezar cualquier fase — ahí están las decisiones de diseño que no se deben revertir.

## Arquitectura: 3 capas

Todo el backend sigue una arquitectura de **3 capas**, y cada app de Django debe respetar esta separación — no mezclar responsabilidades entre capas:

| Capa | Responsabilidad | Dónde vive en cada app |
|---|---|---|
| **Presentación** | Recibe la petición HTTP, valida el formato de entrada, arma la respuesta. No contiene reglas de negocio. | `views.py` / `viewsets.py` + `serializers.py` |
| **Negocio (lógica de aplicación)** | Reglas de negocio, cálculos, validaciones de dominio, orquestación entre modelos. Es la única capa que decide "qué hacer". | `services.py` (uno por app, o carpeta `services/` si crece) |
| **Datos** | Acceso y persistencia. Solo estructura y relaciones, sin lógica de negocio dentro de los modelos (nada de métodos que calculen scoring, por ejemplo). | `models.py` |

**Regla práctica:** una vista **nunca** llama directo al ORM para hacer una operación con lógica (ej. cerrar un acta y calcular su scoring) — la vista llama a una función de `services.py`, y esa función es la que usa los modelos. Esto es exactamente por qué `calcular_carga_fuego()` y `calcular_scoring_riesgo()` van en `services/calculo_riesgo.py` y no como método de `ActaInspeccion` ni código suelto dentro de la vista de "cerrar acta" (Fase 4).

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
- [ ] Definir convención de serializers/viewsets (ver `CLAUDE.md` — nombres en español, serializers explícitos). *(ya documentada en CLAUDE.md; falta aplicarla en código real al escribir los primeros serializers/viewsets en cada Fase)*
- [x] Configurar linting (`ruff` + `black`) — **2026-09-26**. Config en `pyproject.toml`. Se decidió no usar pre-commit hook (innecesario para el equipo por ahora); correr `ruff check .` y `black .` manualmente o vía CI cuando se configure.
- [x] Correr el script `BasedeDatos.sql` contra Supabase — **hecho por Luis, 2026-09-26** (24 tablas + datos iniciales creados, RLS activado en las 24 tablas para cerrar el acceso público vía la API REST de Supabase, ver `CLAUDE.md`).
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
- [x] Tests: cálculo de distancia con datos conocidos, filtrado de hidrantes inactivos, validación GeoJSON, endpoints y control de permisos — **2026-09-28**. `apps/catastro/tests/test_catastro.py`, 12 tests ejecutados y pasando al 100% en Docker contra Supabase.

---

## Fase 3 — Campañas de Fiscalización — *dueño: Luis*

Referencia: RF-7 a RF-11, CU07 a CU11

- [ ] Modelo `Campania` (`GeometryField(Polygon)`, `creado_por` FK a `Administrador`).
- [ ] Modelo `CampaniaFuncionarios` (N:M con atributo `fecha_asignacion`, `usuario` FK a `InspectorTecnico`).
- [ ] Endpoint crear campaña (solo Administrador) — RF-7.
- [ ] Endpoint para delimitar/actualizar el polígono de zona — RF-8.
- [ ] Endpoint asignar/quitar inspectores a una campaña — RF-9.
- [ ] Endpoint consultar avance: `% = actas cerradas / predios dentro del polígono (ST_Intersects)` — RF-10. **No crear una tabla Predio-Campania directa**, resolver siempre por intersección espacial (ver `CLAUDE.md`, evita relación triángulo).
- [ ] Endpoint cerrar campaña (validar que no queden inspecciones pendientes) — RF-11.
- [ ] Tests: intersección espacial correcta, solo un Administrador puede crear campañas, solo Inspectores pueden ser asignados.

---

## Fase 4 — Fiscalización e Inspecciones — *dueño: Roly*

Referencia: RF-12 a RF-16, RF-22, RF-23, CU12 a CU16, CU21, CU22

Este es el módulo más grande — es el corazón del sistema.

- [ ] Modelo `CatalogoEstadoExtintor`, `CatalogoInfraccion`, `CatalogoMaterialCombustible`.
- [ ] Modelo `ActaInspeccion` (incluir `uuid_local`, `sincronizada`, `fecha_sincronizacion` desde el inicio — los necesita la Fase 7 de sync).
- [ ] Modelo `MaterialRegistrado` (peso por material, entidad débil de `ActaInspeccion`).
- [ ] Modelo `EvidenciaFotografica`, modelo `Infraccion`.
- [ ] Endpoint registrar acta (predio + campaña + inspector) — RF-12.
- [ ] Endpoint subir evidencia fotográfica (guardar en storage — definir con Luis si es S3, Supabase Storage, o filesystem) — RF-13.
- [ ] Endpoint registrar materiales combustibles de una acta — RF-22.
- [ ] **`fiscalizacion/services.py`** (capa de negocio): función `calcular_carga_fuego(acta)` (ya definida en la conversación previa, usar tal cual con `aggregate`/`F()`, no traer filas a Python) — RF-23.
- [ ] En el mismo `services.py`: función `calcular_scoring_riesgo(acta)`, combina carga de fuego + estado extintores + fallas eléctricas + rutas de evacuación + distancia a hidrante en un puntaje — RF-14. **Definir la fórmula/pesos exactos con el resto del equipo antes de implementar** (ver `CLAUDE.md` — no inventar coeficientes).
- [ ] Endpoint (capa de presentación) cerrar acta: **solo llama** a `services.cerrar_acta(acta)`, que internamente encadena `calcular_carga_fuego` → `calcular_scoring_riesgo` → guarda ambos. La vista no calcula nada por sí misma.
- [ ] Endpoint consultar historial de inspecciones por predio/zona — RF-15.
- [ ] Lógica de detección de reincidencia: al registrar una infracción, verificar si ya existe una infracción del mismo `tipo_infraccion` en actas anteriores del mismo predio — RF-16.
- [ ] Tests: cálculo de carga de fuego contra el ejemplo ya verificado (300kg madera + 150kg plástico, mercado 200m² → 83.61 MJ/m²), detección de reincidencia, entidades débiles se borran en cascada al borrar el acta.

---

## Fase 5 — Analítica e Inteligencia Artificial — *dueño: Luis*

Referencia: RF-17 a RF-19, CU17 a CU19

- [ ] Modelo `ClusteringEjecucion`.
- [ ] Microservicio Python separado (o management command de Django, a decidir) que:
  - Trae actas cerradas con sus variables (carga_fuego, fallas_electricas, distancia_hidrante_m, estado_extintores, etc.) vía API interna en JSON.
  - Escala los datos (`StandardScaler`), ejecuta K-Means (k=3), calcula coeficiente de Silueta.
  - Devuelve el cluster asignado por acta.
- [ ] Endpoint que dispare la ejecución (solo Administrador) y guarde el resultado en `ClusteringEjecucion` y en `ActaInspeccion.cluster_riesgo` — RF-17.
- [ ] Endpoint que devuelva los datos agregados por zona para el mapa de calor (frontend React con react-leaflet dibuja la capa) — RF-18.
- [ ] Lógica de priorización: identificar zonas con concentración de riesgo Crítico y sugerirlas como nuevas campañas — RF-19.
- [ ] Tests: el pipeline de clustering corre sobre un dataset de prueba fijo y produce un coeficiente de Silueta reproducible.

---

## Fase 6 — Reportes — *dueño: Roly*

Referencia: RF-20, CU20

- [ ] Modelo `ReporteGenerado`.
- [ ] Generador de reporte ejecutivo en PDF (ej. `WeasyPrint` o `ReportLab`) con resumen de campaña, predios inspeccionados, distribución de riesgo.
- [ ] Generador de reporte en Excel (`openpyxl`) con el detalle tabular.
- [ ] Endpoint que genera y devuelve el archivo (o lo sube a storage y devuelve la URL).
- [ ] Tests: el PDF/Excel se genera sin errores con datos de prueba.

---

## Fase 7 — API de Sincronización Offline (para la app Flutter) — *dueño: Luis*

Referencia: RF-21, CU23 — **este módulo es crítico, no dejarlo para el final**

- [ ] Endpoint `POST /sync/actas/` que reciba un batch de actas (con su `uuid_local`, evidencias en base64 o multipart, materiales) registradas offline.
- [ ] Lógica de deduplicación: si el `uuid_local` ya existe, no duplicar (idempotencia — el celular puede reintentar el envío).
- [ ] Manejo de conflictos: si el predio o campaña referenciada ya no existe o cambió, devolver un error claro por acta (no fallar el batch completo).
- [ ] Al recibir el acta, disparar automáticamente `calcular_carga_fuego` y `calcular_scoring_riesgo`.
- [ ] Marcar `sincronizada = true` y `fecha_sincronizacion` al confirmar.
- [ ] Tests: envío duplicado del mismo `uuid_local` no crea dos actas, batch parcialmente fallido reporta qué actas sí y cuáles no se guardaron.

---

## Fase 8 — Documentación, testing final y despliegue (AMBOS)

- [ ] Revisar que la documentación Swagger (`drf-spectacular`) cubra todos los endpoints con ejemplos.
- [ ] Suite de tests de integración end-to-end de al menos un flujo completo (crear campaña → asignar inspector → registrar acta con materiales → cerrar acta → ejecutar clustering → generar reporte).
- [ ] Configurar despliegue (Railway, Render, u otro — definir con el resto del equipo) apuntando a la BD de Supabase.
- [ ] Variables de entorno de producción separadas de desarrollo.
- [ ] Checklist de seguridad antes de entregar: `DEBUG=False`, `ALLOWED_HOSTS` configurado, CORS restringido al dominio del frontend y la app.

---

## Notas para ambos

- Antes de tocar el módulo del otro, avisen — aunque la división busca minimizar cruces, `ActaInspeccion` (Fase 4) depende de modelos de Fase 1, 2 y 3, así que esas deben ir razonablemente avanzadas primero.
- Cualquier decisión que no esté clara en `CLAUDE.md` ni en este plan (fórmula exacta del scoring, proveedor de storage para fotos, hosting de despliegue) se define en conjunto antes de programarla — no se asume.
- Actualicen este archivo conforme avancen; es más útil que un grupo de WhatsApp para saber en qué está el otro.