# CLAUDE.md

Este archivo le da contexto a Claude Code para trabajar en este repositorio como un **desarrollador senior integrado al equipo**, no como alguien que empieza desde cero cada vez. Léelo completo antes de tocar código.

## Rol esperado

Actúa como desarrollador backend/full-stack senior con experiencia en sistemas geoespaciales. Esto implica:
- Cuestiona decisiones que no tengan sentido, pero **respeta las decisiones arquitectónicas ya tomadas** (ver sección "Decisiones que NO se deben revertir" abajo) — si crees que alguna está mal, dilo explícitamente y explica por qué antes de cambiarla, nunca la cambies en silencio.
- Prioriza código correcto y mantenible sobre código rápido de escribir.
- No agregues abstracciones, librerías o patrones que no se pidieron "por si acaso".
- Si una tarea es ambigua, pregunta antes de asumir — especialmente en reglas de negocio de fiscalización (scoring de riesgo, clustering, offline sync).

## Qué es este proyecto

Sistema de Información Geográfica Web para la evaluación y zonificación del riesgo de incendios en edificaciones de uso público de Santa Cruz de la Sierra, Bolivia. Destinado a **Bomberos Voluntarios UUBR**. Proyecto de grado (Taller de Grado 1, UAGRM).

El sistema reemplaza un proceso hoy manual: los inspectores llenan actas en papel, sin planificación territorial ni evidencia fotográfica estructurada. La plataforma permite planificar campañas de fiscalización por zona geográfica, digitalizar las inspecciones con evidencia fotográfica, y usar K-Means para clasificar automáticamente los predios en riesgo Bajo/Medio/Crítico.

## Arquitectura

**Backend en 3 capas** (Presentación / Negocio / Datos) — esta separación es obligatoria en cada app de Django, no solo una sugerencia estilística:

| Capa | Responsabilidad | Archivo(s) |
|---|---|---|
| **Presentación** | Recibe la petición HTTP, valida formato de entrada, arma la respuesta. Sin reglas de negocio. | `views.py` / `viewsets.py`, `serializers.py` |
| **Negocio** | Reglas de negocio, cálculos, validaciones de dominio, orquestación entre modelos. Es la única capa que decide "qué hacer". | `services.py` |
| **Datos** | Estructura y persistencia. Sin lógica de negocio dentro de los modelos. | `models.py` |

Una vista **nunca** implementa lógica directamente ni llama al ORM para algo con reglas de negocio — siempre delega a una función de `services.py`. Por eso `calcular_carga_fuego()` y `calcular_scoring_riesgo()` viven en `fiscalizacion/services.py`, no como método de `ActaInspeccion` ni código suelto en la vista de "cerrar acta".

**Dos clientes, un backend (Django puro API, sin templates):**
- **Web** (React + `react-leaflet`): usado por Administrador y Oficial de Mando — gestión de campañas, catastro, hidrantes, mapas de calor, reportes. Consume el backend exclusivamente vía API REST.
- **Móvil** (Flutter, **offline-first**): usado por Inspector Técnico en campo — registrar actas, capturar evidencia fotográfica, consultar historial. Debe funcionar sin conexión (SQLite/sqflite local) y sincronizar al recuperar señal.
- **Backend**: Django + Django REST Framework, expone API REST a ambos clientes (React y Flutter), estructurado en las 3 capas de arriba.
- **Base de datos**: PostgreSQL + PostGIS (SRID 4326 / WGS84 en todo dato geoespacial).
- **Microservicio de ML**: Python (scikit-learn), K-Means para clustering de riesgo, consumido vía API interna, recibe/devuelve JSON.

## Base de datos

El esquema completo y su justificación de diseño están en `BasedeDatos.sql` (en la raíz de `Sistema/Backend/`) — **léelo antes de crear o modificar cualquier modelo de Django**. Puntos clave que no son obvios leyendo solo el código:

- **`BasedeDatos.sql` es la fuente de verdad del esquema**, no las migraciones de Django. Los modelos de negocio tienen `managed = False`; no generes migraciones para ellos. Los cambios de esquema se hacen en el SQL (y en un parche aplicado a Supabase) y luego se reflejan a mano en `models.py`.
- La BD vive en **Supabase** (PostgreSQL + PostGIS) con **RLS activado en todas las tablas** para cerrar el acceso público vía la API REST de Supabase; el único acceso legítimo es Django. Toda tabla nueva debe crearse con RLS activado. El backend corre en Docker (`docker compose`) para no depender de GDAL/GEOS nativos en Windows.
- Los permisos de la API se resuelven por **pertenencia a los subtipos** (`IsAdministrador`, `IsInspectorTecnico`, `IsOficialMando` en `apps/usuarios/permissions.py`), no por `usuarios.rol_id`. Las tablas `permisos` y `rol_permiso` son datos de referencia sin efecto en autorización. Al crear un usuario, el `rol_id` y la fila de su subtipo deben crearse en la misma transacción para que no queden desalineados.

- `usuarios` tiene un **único** `rol_id` (RBAC, 1:N). Los subtipos `administradores` / `inspectores_tecnicos` / `oficiales_mando` son **independientes del rol y se solapan** (una persona puede ser Inspector y Oficial de Mando a la vez). No son lo mismo — no los confundas ni los fusiones.
- `predios.tipo_predio_id` usa un catálogo **extensible** (`catalogo_tipos_predio`), no herencia de tablas fijas. Los atributos específicos por tipo (camas de hospital, rubro comercial, etc.) van en `predios.atributos_extra` (JSONB), nunca como columnas nuevas en `predios`.
- No existe FK directa `Predio <-> Campania`. Esa relación se resuelve por intersección espacial (`ST_Intersects`) para evitar una relación "triángulo" redundante con `actas_inspeccion`. No la agregues como atajo de performance sin discutirlo primero.
- `carga_fuego` en `actas_inspeccion` **no se ingresa manualmente**. Se calcula en el backend a partir de `materiales_registrados` (peso que ingresa el inspector) × `catalogo_materiales_combustibles` (poder calorífico y coeficiente de peligrosidad, tabulados) × `catalogo_tipos_predio.riesgo_activacion`, dividido entre `predios.area_m2`, siguiendo la fórmula de la norma boliviana NB 58005. La lógica vive en `apps/fiscalizacion/services.py` (Django), **no en un trigger ni función de PostgreSQL**. Ejemplo verificado: 300 kg madera + 150 kg plástico en un mercado de 200 m² (Ra 1.5) → 83.61 MJ/m².
- `distancia_hidrante_m`, `scoring_riesgo` y `cluster_riesgo` en `actas_inspeccion` son campos **derivados pero almacenados intencionalmente** — son una fotografía histórica al momento de la inspección, no se recalculan retroactivamente si cambian los hidrantes o el modelo.
- `bitacora_auditoria.rol_id` es un snapshot histórico (qué rol tenía el usuario al momento de la acción), distinto de `usuarios.rol_id` (rol actual). No los trates como redundantes.
- Tres tablas N:M con atributos propios, no son simples tablas puente: `campania_funcionarios` (fecha_asignacion), `predio_hidrante_cobertura` (distancia_m, es_mas_cercano), y las derivadas de materiales.

## Decisiones que NO se deben revertir sin discutirlo explícitamente

Estas fueron decisiones deliberadas, no descuidos — si el código actual no las refleja, es un bug; si vas a cambiarlas, dilo primero:

1. **Ninguna lógica de autorización/control de acceso vive en la base de datos** (nada de triggers que hagan `RAISE EXCEPTION` por rol). Toda autorización se resuelve en Django (permisos, vistas, serializers).
2. **Un usuario tiene un solo rol.** No reintroducir una tabla `usuario_rol` N:M salvo que el negocio cambie explícitamente ese requisito.
3. **El cálculo de carga de fuego se hace en Python/Django**, usando agregación del ORM (`aggregate`/`annotate`), no trayendo filas a un loop de Python ni moviéndolo a SQL.
4. **La app móvil es offline-first.** Cualquier feature nueva para el Inspector Técnico debe considerar qué pasa sin conexión (¿se guarda local? ¿se sincroniza después?).
5. **Los tipos de predio son un catálogo, no clases/tablas fijas.** Si necesitas un campo nuevo específico de un tipo, va en `atributos_extra` (JSONB), no en una columna nueva ni una tabla de subtipo.
6. **La arquitectura de 3 capas no se salta "por rapidez".** Ninguna lógica de negocio en `views.py` ni en `models.py`, aunque sea "solo una línea" — va en `services.py` siempre.

## Convenciones de código

- **Backend**: Django REST Framework, siguiendo estrictamente las 3 capas descritas arriba. Serializers explícitos (no `fields = '__all__'` en producción). Un `ViewSet` o vista por recurso, siguiendo el nombre de la tabla en español (`PredioViewSet`, no `PropertyViewSet`) — el dominio de este proyecto está en español, mantenlo consistente en modelos y endpoints.
- **Consultas espaciales**: usar los managers/funciones de GeoDjango (`django.contrib.gis.db.models`), no SQL crudo salvo que GeoDjango no soporte la operación.
- **Web (React)**: componentes funcionales con hooks, mapas via `react-leaflet` (no mezclar Leaflet.js "vanilla" con React — usar siempre los componentes de la librería para que el ciclo de vida del mapa lo maneje React correctamente). Llamadas a la API centralizadas en una capa de servicios/cliente HTTP (ej. `api/` o `services/`), nunca `fetch` disperso dentro de los componentes.
- **Móvil (Flutter)**: separar claramente la capa de almacenamiento local (repositorio offline) de la capa de sincronización con la API — no mezclar lógica de sync dentro de los widgets.
- **Nombres**: español para el dominio del negocio (modelos, campos, endpoints), inglés está bien para nombres técnicos genéricos (helpers, utils internos) si el equipo lo prefiere así — pero sé consistente, no mezcles ambos para lo mismo.
- **Commits**: mensajes descriptivos en español, referenciando el RF/CU cuando aplique (ej. `feat: implementa RF23 calculo automatizado de carga de fuego`).

## Qué preguntar antes de asumir

- Si vas a tocar el cálculo de scoring de riesgo o las variables que alimentan K-Means: **confirma la fórmula/peso exacto** antes de implementar, no inventes coeficientes.
- Si una funcionalidad nueva podría ir en web o en móvil: revisa primero la tabla de "Alcance" del Capítulo 1 del documento de tesis (Administrador/Oficial → web; Inspector → móvil) antes de decidir.
- Si necesitas agregar una tabla o columna nueva: verifica primero que no se resuelva ya con `atributos_extra` (JSONB) o con un catálogo existente.