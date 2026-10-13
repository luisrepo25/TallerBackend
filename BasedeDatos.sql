-- ============================================================
-- Sistema de Informacion Geografica Web para la Evaluacion y
-- Zonificacion del Riesgo de Incendios
-- Script de creacion de base de datos - PostgreSQL + PostGIS
--
-- ESTE ES EL UNICO ARCHIVO DE ESQUEMA. Fuente de verdad de la BD (ver CLAUDE.md).
-- No se crean archivos "parche": todo cambio se agrega aqui.
--
-- Es IDEMPOTENTE: se puede ejecutar completo, cuantas veces haga falta, sobre una BD
-- nueva o sobre la de Supabase (SQL Editor). Lo que ya existe no se toca.
--
-- COMO AGREGAR UN CAMBIO:
--   * Tabla nueva: agregarla en su seccion con CREATE TABLE IF NOT EXISTS (y sus indices
--     con CREATE INDEX IF NOT EXISTS) y anadirla a la lista de RLS de la seccion 9.
--   * Columna nueva en una tabla existente: CREATE TABLE IF NOT EXISTS no la agrega a una
--     tabla que ya existe, asi que ademas va en la seccion 10 (MIGRACIONES) con
--     ALTER TABLE ... ADD COLUMN IF NOT EXISTS, y tambien en el CREATE TABLE original.
--   * Datos de catalogo nuevos: en la seccion 8, con WHERE NOT EXISTS.
--   * Despues: reflejarlo a mano en models.py (managed = False) y anotarlo en el historial.
--
-- HISTORIAL DE CAMBIOS
--   v8    Esquema base (24 tablas) con las correcciones acordadas:
--         - Un usuario tiene UN SOLO rol (rol_id directo, sin usuario_rol)
--         - Subtipos funcionales solapados (administradores/inspectores/oficiales)
--         - Catalogo extensible de tipos de predio (con atributos_extra JSONB)
--         - N:M con atributos propios: predio_hidrante_cobertura, campania_funcionarios
--         - Sin FK directa Predio<->Campania (evita relacion triangulo)
--         - Sincronizacion offline para app movil Flutter (Inspector Tecnico)
--         - Bitacora de auditoria con snapshot del rol al momento de la accion
--         - Calculo de carga de fuego (NB 58005) basado en catalogo de materiales,
--           calculado en el sistema (Django), la BD solo almacena los datos
--   v8.1  Indices idx_actas_inspector, idx_actas_cerrada, idx_cobertura_hidrante.
--   v9    Tabla solicitudes_material: el Inspector solicita materiales nuevos y el
--         Administrador los aprueba (2026-10-10).
--   v10   Tabla distritos: zona de analisis del mapa de calor y de la priorizacion de
--         campanias, RF-18 y RF-19 (2026-10-13).
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- 1. ROLES Y PERMISOS (RBAC)
-- Se persisten como dato de referencia: alimentan la bitacora
-- de auditoria (que rol actuaba el usuario) y el rol unico de
-- cada usuario. La AUTORIZACION en si vive en el sistema.
-- ============================================================

CREATE TABLE IF NOT EXISTS roles (
    id      SERIAL PRIMARY KEY,
    nombre  VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS permisos (
    id          SERIAL PRIMARY KEY,
    nombre      VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT
);

CREATE TABLE IF NOT EXISTS rol_permiso (
    rol_id      INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permiso_id  INTEGER NOT NULL REFERENCES permisos(id) ON DELETE CASCADE,
    PRIMARY KEY (rol_id, permiso_id)
);

-- ============================================================
-- 2. USUARIOS (SUPERTIPO) Y SUBTIPOS SOLAPADOS
-- rol_id: relacion 1:N directa (un usuario, un solo rol).
-- Los subtipos de abajo son independientes del rol y SI pueden
-- solaparse (reflejan capacidades operativas, no el rol de RBAC).
-- ============================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id              SERIAL PRIMARY KEY,
    nombre_completo VARCHAR(150) NOT NULL,
    email           VARCHAR(150) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    rol_id          INTEGER NOT NULL REFERENCES roles(id),
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usuarios_rol ON usuarios (rol_id);

CREATE TABLE IF NOT EXISTS administradores (
    usuario_id      INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    nivel_acceso    VARCHAR(20) NOT NULL DEFAULT 'total'
);

CREATE TABLE IF NOT EXISTS inspectores_tecnicos (
    usuario_id                  INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    fecha_certificacion         DATE,
    curso_capacitacion_completo BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS oficiales_mando (
    usuario_id      INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    rango           VARCHAR(50)
);

-- ============================================================
-- 3. CATALOGOS
-- ============================================================

CREATE TABLE IF NOT EXISTS catalogo_tipos_predio (
    id                      SERIAL PRIMARY KEY,
    nombre                  VARCHAR(100) NOT NULL UNIQUE,
    categoria_riesgo_base   VARCHAR(20),
    riesgo_activacion       NUMERIC(4,2) NOT NULL DEFAULT 1.0   -- Ra, para calculo de carga de fuego
);

CREATE TABLE IF NOT EXISTS catalogo_tipos_acople (
    id      SERIAL PRIMARY KEY,
    nombre  VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS catalogo_estados_extintor (
    id      SERIAL PRIMARY KEY,
    nombre  VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS catalogo_infracciones (
    id                SERIAL PRIMARY KEY,
    nombre            VARCHAR(150) NOT NULL UNIQUE,
    peso_severidad    NUMERIC(4,2) NOT NULL DEFAULT 1.0
);

-- Materiales combustibles: Hi (poder calorifico) y Ci (peligrosidad)
-- tabulados segun NB 58005, para el calculo automatizado de carga de fuego.
CREATE TABLE IF NOT EXISTS catalogo_materiales_combustibles (
    id                        SERIAL PRIMARY KEY,
    nombre                    VARCHAR(100) NOT NULL UNIQUE,
    poder_calorifico_mj_kg    NUMERIC(6,2) NOT NULL,   -- Hi
    coeficiente_peligrosidad  NUMERIC(4,2) NOT NULL    -- Ci
);

-- ============================================================
-- 4. CATASTRO E INFRAESTRUCTURA GEOESPACIAL
-- ============================================================

CREATE TABLE IF NOT EXISTS predios (
    id                  SERIAL PRIMARY KEY,
    nombre              VARCHAR(150) NOT NULL,
    direccion           VARCHAR(255),
    tipo_predio_id      INTEGER NOT NULL REFERENCES catalogo_tipos_predio(id),
    aforo               INTEGER,
    area_m2             NUMERIC(8,2),          -- necesaria para el calculo de carga de fuego
    atributos_extra     JSONB,
    geom                GEOMETRY(Polygon, 4326) NOT NULL,
    fecha_registro      TIMESTAMP NOT NULL DEFAULT NOW(),
    registrado_por      INTEGER NOT NULL REFERENCES usuarios(id)
);

CREATE INDEX IF NOT EXISTS idx_predios_geom ON predios USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_predios_tipo ON predios (tipo_predio_id);

CREATE TABLE IF NOT EXISTS hidrantes (
    id                SERIAL PRIMARY KEY,
    codigo            VARCHAR(50) UNIQUE,
    estado_operativo  VARCHAR(20) NOT NULL DEFAULT 'activo'
                        CHECK (estado_operativo IN ('activo', 'fuera_de_servicio')),
    presion_nominal   NUMERIC(6,2),
    tipo_acople_id    INTEGER NOT NULL REFERENCES catalogo_tipos_acople(id),
    geom              GEOMETRY(Point, 4326) NOT NULL,
    fecha_registro    TIMESTAMP NOT NULL DEFAULT NOW(),
    registrado_por    INTEGER NOT NULL REFERENCES usuarios(id)
);

CREATE INDEX IF NOT EXISTS idx_hidrantes_geom ON hidrantes USING GIST (geom);

-- Distritos municipales: zona de analisis del mapa de calor (RF-18) y de la priorizacion
-- de nuevas campanias (RF-19). Sin FK con predios: el distrito de un predio se obtiene por
-- ST_Intersects de su centroide (igual que Predio<->Campania). Los poligonos se cargan con
-- `python manage.py importar_distritos <archivo.geojson>`. (v10)
CREATE TABLE IF NOT EXISTS distritos (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL UNIQUE,
    geom            GEOMETRY(MultiPolygon, 4326) NOT NULL,   -- un distrito puede ser multiparte
    fecha_registro  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_distritos_geom ON distritos USING GIST (geom);

CREATE TABLE IF NOT EXISTS predio_hidrante_cobertura (
    predio_id       INTEGER NOT NULL REFERENCES predios(id) ON DELETE CASCADE,
    hidrante_id     INTEGER NOT NULL REFERENCES hidrantes(id) ON DELETE CASCADE,
    distancia_m     NUMERIC(8,2) NOT NULL,
    es_mas_cercano  BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_calculo   TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (predio_id, hidrante_id)
);

CREATE INDEX IF NOT EXISTS idx_cobertura_hidrante ON predio_hidrante_cobertura (hidrante_id);  -- v8.1

-- ============================================================
-- 5. GESTION DE CAMPANIAS DE FISCALIZACION
-- ============================================================

CREATE TABLE IF NOT EXISTS campanias (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL,
    fecha_inicio    DATE NOT NULL,
    fecha_fin       DATE NOT NULL,
    estado          VARCHAR(20) NOT NULL DEFAULT 'pendiente'
                        CHECK (estado IN ('pendiente', 'en_curso', 'cerrada')),
    geom            GEOMETRY(Polygon, 4326),
    creado_por      INTEGER NOT NULL REFERENCES administradores(usuario_id),
    fecha_creacion  TIMESTAMP NOT NULL DEFAULT NOW(),
    CHECK (fecha_fin >= fecha_inicio)
);

CREATE INDEX IF NOT EXISTS idx_campanias_geom ON campanias USING GIST (geom);

CREATE TABLE IF NOT EXISTS campania_funcionarios (
    campania_id      INTEGER NOT NULL REFERENCES campanias(id) ON DELETE CASCADE,
    usuario_id       INTEGER NOT NULL REFERENCES inspectores_tecnicos(usuario_id),
    fecha_asignacion TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (campania_id, usuario_id)
);

-- ============================================================
-- 6. FISCALIZACION E INSPECCIONES TECNICAS
-- Sin FK directa Predio<->Campania (se resuelve por ST_Intersects,
-- evita relacion triangulo). Incluye campos de sincronizacion
-- offline (app movil Flutter).
-- ============================================================

CREATE TABLE IF NOT EXISTS actas_inspeccion (
    id                          SERIAL PRIMARY KEY,
    uuid_local                  UUID UNIQUE,
    predio_id                   INTEGER NOT NULL REFERENCES predios(id),
    campania_id                 INTEGER NOT NULL REFERENCES campanias(id),
    inspector_id                INTEGER NOT NULL REFERENCES inspectores_tecnicos(usuario_id),
    fecha_inspeccion            TIMESTAMP NOT NULL DEFAULT NOW(),
    carga_fuego                 NUMERIC(8,2),   -- calculada por el sistema (ver catalogo_materiales_combustibles)
    estado_extintores_id        INTEGER NOT NULL REFERENCES catalogo_estados_extintor(id),
    fallas_electricas           BOOLEAN NOT NULL DEFAULT FALSE,
    rutas_evacuacion_despejadas BOOLEAN NOT NULL DEFAULT TRUE,
    distancia_hidrante_m        NUMERIC(8,2),
    scoring_riesgo              NUMERIC(6,2),
    -- cluster vigente: lo reasigna TODA ejecucion del clustering (no es foto historica, ver CLAUDE.md)
    cluster_riesgo              VARCHAR(20)
                                    CHECK (cluster_riesgo IN ('Bajo', 'Medio', 'Critico')),
    cerrada                     BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_cierre                TIMESTAMP,
    sincronizada                BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_sincronizacion        TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_actas_predio ON actas_inspeccion (predio_id);
CREATE INDEX IF NOT EXISTS idx_actas_campania ON actas_inspeccion (campania_id);
CREATE INDEX IF NOT EXISTS idx_actas_inspector ON actas_inspeccion (inspector_id);  -- v8.1
CREATE INDEX IF NOT EXISTS idx_actas_cerrada ON actas_inspeccion (cerrada);         -- v8.1

-- Materiales combustibles registrados por el inspector en cada acta.
-- Es la entrada real del calculo de carga_fuego (ejecutado en Django).
CREATE TABLE IF NOT EXISTS materiales_registrados (
    id          SERIAL PRIMARY KEY,
    acta_id     INTEGER NOT NULL REFERENCES actas_inspeccion(id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL REFERENCES catalogo_materiales_combustibles(id),
    peso_kg     NUMERIC(8,2) NOT NULL CHECK (peso_kg >= 0)
);

CREATE INDEX IF NOT EXISTS idx_materiales_acta ON materiales_registrados (acta_id);

-- Solicitud de un material combustible que no esta en el catalogo. El Inspector no
-- crea materiales (Hi y Ci son datos tabulados de la NB 58005): los solicita y el
-- Administrador los aprueba (creando el material con sus Hi y Ci) o los rechaza.
-- Mientras esta pendiente NO cuenta en la carga de fuego. (v9)
CREATE TABLE IF NOT EXISTS solicitudes_material (
    id                SERIAL PRIMARY KEY,
    uuid_local        UUID UNIQUE,                 -- idempotencia: el celular puede reenviar
    nombre            VARCHAR(100) NOT NULL,
    descripcion       TEXT,
    peso_kg_estimado  NUMERIC(8,2) CHECK (peso_kg_estimado >= 0),
    solicitante_id    INTEGER NOT NULL REFERENCES inspectores_tecnicos(usuario_id),
    estado            VARCHAR(20) NOT NULL DEFAULT 'pendiente'
                        CHECK (estado IN ('pendiente', 'aprobada', 'rechazada')),
    material_id       INTEGER REFERENCES catalogo_materiales_combustibles(id),  -- si fue aprobada
    resuelta_por      INTEGER REFERENCES administradores(usuario_id),
    motivo_rechazo    TEXT,
    fecha_solicitud   TIMESTAMP NOT NULL DEFAULT NOW(),
    fecha_resolucion  TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_solicitudes_material_estado ON solicitudes_material (estado);
CREATE INDEX IF NOT EXISTS idx_solicitudes_material_solicitante ON solicitudes_material (solicitante_id);

-- Entidades debiles: dependencia en existencia de ActaInspeccion
CREATE TABLE IF NOT EXISTS evidencias_fotograficas (
    id                      SERIAL PRIMARY KEY,
    acta_id                 INTEGER NOT NULL REFERENCES actas_inspeccion(id) ON DELETE CASCADE,
    url_imagen              VARCHAR(255) NOT NULL,
    descripcion_infraccion  TEXT,
    fecha_captura           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS infracciones (
    id                  SERIAL PRIMARY KEY,
    acta_id             INTEGER NOT NULL REFERENCES actas_inspeccion(id) ON DELETE CASCADE,
    tipo_infraccion_id  INTEGER NOT NULL REFERENCES catalogo_infracciones(id),
    descripcion         TEXT,
    es_reincidencia     BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_registro      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_infracciones_acta ON infracciones (acta_id);

-- ============================================================
-- 7. INTELIGENCIA ARTIFICIAL Y REPORTES
-- ============================================================

CREATE TABLE IF NOT EXISTS clustering_ejecuciones (
    id                    SERIAL PRIMARY KEY,
    fecha_ejecucion       TIMESTAMP NOT NULL DEFAULT NOW(),
    k_value               INTEGER NOT NULL DEFAULT 3,
    coeficiente_silueta   NUMERIC(4,3),
    ejecutado_por         INTEGER NOT NULL REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS reportes_generados (
    id                  SERIAL PRIMARY KEY,
    tipo                VARCHAR(50) NOT NULL CHECK (tipo IN ('dictamen', 'ejecutivo')),
    formato             VARCHAR(10) NOT NULL CHECK (formato IN ('PDF', 'Excel')),
    generado_por        INTEGER NOT NULL REFERENCES usuarios(id),
    fecha_generacion    TIMESTAMP NOT NULL DEFAULT NOW(),
    parametros          JSONB
);

-- AUDITORIA
-- rol_id es un SNAPSHOT historico (que rol tenia el usuario al
-- momento exacto de la accion), independiente de que su rol
-- actual en usuarios.rol_id pueda haber cambiado despues.

CREATE TABLE IF NOT EXISTS bitacora_auditoria (
    id                  SERIAL PRIMARY KEY,
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    rol_id              INTEGER REFERENCES roles(id),
    accion              VARCHAR(150) NOT NULL,
    entidad_afectada    VARCHAR(100),
    fecha               TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bitacora_usuario ON bitacora_auditoria (usuario_id);
CREATE INDEX IF NOT EXISTS idx_bitacora_rol ON bitacora_auditoria (rol_id);

-- ============================================================
-- 8. DATOS INICIALES (catalogos)
-- Cada fila se inserta solo si no existe (por nombre): re-ejecutar el archivo no duplica
-- ni consume ids de las secuencias.
-- ============================================================

INSERT INTO roles (nombre)
SELECT v.nombre
FROM (VALUES ('Administrador'), ('Inspector Tecnico'), ('Oficial de Mando')) AS v(nombre)
WHERE NOT EXISTS (SELECT 1 FROM roles t WHERE t.nombre = v.nombre);

INSERT INTO catalogo_tipos_predio (nombre, categoria_riesgo_base, riesgo_activacion)
SELECT v.nombre, v.categoria_riesgo_base, v.riesgo_activacion
FROM (VALUES
    ('Comercial', 'Medio', 1.0),
    ('Salud', 'Alto', 1.5),
    ('Educativo', 'Medio', 1.0),
    ('Industrial', 'Alto', 2.0),
    ('Mercado Distrital', 'Alto', 1.5)
) AS v(nombre, categoria_riesgo_base, riesgo_activacion)
WHERE NOT EXISTS (SELECT 1 FROM catalogo_tipos_predio t WHERE t.nombre = v.nombre);

INSERT INTO catalogo_tipos_acople (nombre)
SELECT v.nombre
FROM (VALUES ('Storz'), ('NST'), ('BSP')) AS v(nombre)
WHERE NOT EXISTS (SELECT 1 FROM catalogo_tipos_acople t WHERE t.nombre = v.nombre);

INSERT INTO catalogo_estados_extintor (nombre)
SELECT v.nombre
FROM (VALUES ('Vigente'), ('Vencido'), ('No posee')) AS v(nombre)
WHERE NOT EXISTS (SELECT 1 FROM catalogo_estados_extintor t WHERE t.nombre = v.nombre);

INSERT INTO catalogo_infracciones (nombre, peso_severidad)
SELECT v.nombre, v.peso_severidad
FROM (VALUES
    ('Extintor vencido', 1.5),
    ('Instalacion electrica precaria', 2.0),
    ('Ruta de evacuacion obstruida', 2.5),
    ('Almacenamiento inadecuado de inflamables', 3.0)
) AS v(nombre, peso_severidad)
WHERE NOT EXISTS (SELECT 1 FROM catalogo_infracciones t WHERE t.nombre = v.nombre);

INSERT INTO catalogo_materiales_combustibles (nombre, poder_calorifico_mj_kg, coeficiente_peligrosidad)
SELECT v.nombre, v.poder_calorifico_mj_kg, v.coeficiente_peligrosidad
FROM (VALUES
    ('Madera', 18.41, 1.0),
    ('Papel y carton', 16.75, 1.0),
    ('Telas y textiles', 19.00, 1.2),
    ('Plasticos (PVC/PET)', 25.00, 1.5),
    ('Liquidos inflamables', 40.00, 2.0)
) AS v(nombre, poder_calorifico_mj_kg, coeficiente_peligrosidad)
WHERE NOT EXISTS (SELECT 1 FROM catalogo_materiales_combustibles t WHERE t.nombre = v.nombre);

-- ============================================================
-- 9. SEGURIDAD: RLS EN TODAS LAS TABLAS
-- Cierra el acceso publico via la API REST de Supabase: el unico acceso legitimo es
-- Django (conexion directa, que no pasa por RLS). Toda tabla nueva va en esta lista.
-- ALTER TABLE ... ENABLE ROW LEVEL SECURITY es idempotente.
-- ============================================================

ALTER TABLE roles                           ENABLE ROW LEVEL SECURITY;
ALTER TABLE permisos                        ENABLE ROW LEVEL SECURITY;
ALTER TABLE rol_permiso                     ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuarios                        ENABLE ROW LEVEL SECURITY;
ALTER TABLE administradores                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE inspectores_tecnicos            ENABLE ROW LEVEL SECURITY;
ALTER TABLE oficiales_mando                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalogo_tipos_predio           ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalogo_tipos_acople           ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalogo_estados_extintor       ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalogo_infracciones           ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalogo_materiales_combustibles ENABLE ROW LEVEL SECURITY;
ALTER TABLE predios                         ENABLE ROW LEVEL SECURITY;
ALTER TABLE hidrantes                       ENABLE ROW LEVEL SECURITY;
ALTER TABLE distritos                       ENABLE ROW LEVEL SECURITY;
ALTER TABLE predio_hidrante_cobertura       ENABLE ROW LEVEL SECURITY;
ALTER TABLE campanias                       ENABLE ROW LEVEL SECURITY;
ALTER TABLE campania_funcionarios           ENABLE ROW LEVEL SECURITY;
ALTER TABLE actas_inspeccion                ENABLE ROW LEVEL SECURITY;
ALTER TABLE materiales_registrados          ENABLE ROW LEVEL SECURITY;
ALTER TABLE solicitudes_material            ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidencias_fotograficas         ENABLE ROW LEVEL SECURITY;
ALTER TABLE infracciones                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE clustering_ejecuciones          ENABLE ROW LEVEL SECURITY;
ALTER TABLE reportes_generados              ENABLE ROW LEVEL SECURITY;
ALTER TABLE bitacora_auditoria              ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- 10. MIGRACIONES
-- Cambios sobre tablas que ya existen en Supabase (columnas nuevas, restricciones).
-- Siempre idempotentes. Hoy no hay ninguno pendiente. Ejemplo:
--   ALTER TABLE predios ADD COLUMN IF NOT EXISTS zona VARCHAR(50);
-- ============================================================

-- ============================================================
-- EJEMPLOS DE USO
-- ============================================================

-- Crear un usuario con su rol y luego su subtipo (misma transaccion):
-- INSERT INTO usuarios (nombre_completo, email, password_hash, rol_id)
-- VALUES ('Carlos Mamani Rojas', 'cmamani@uubr.org.bo', '...', (SELECT id FROM roles WHERE nombre = 'Inspector Tecnico'))
-- RETURNING id;
-- INSERT INTO inspectores_tecnicos (usuario_id, fecha_certificacion, curso_capacitacion_completo)
-- VALUES (<id_retornado>, '2025-03-10', true);

-- Materiales registrados por el inspector para una acta (el calculo
-- final de carga_fuego se hace en Django, no aqui):
-- INSERT INTO materiales_registrados (acta_id, material_id, peso_kg) VALUES
--     (1, 1, 300),  -- 300 kg de madera
--     (1, 4, 150);  -- 150 kg de plasticos

-- Distancia entre un predio y el hidrante activo mas cercano:
-- SELECT h.id, ST_Distance(p.geom::geography, h.geom::geography) AS distancia_m
-- FROM predios p, hidrantes h
-- WHERE p.id = 1 AND h.estado_operativo = 'activo'
-- ORDER BY distancia_m ASC LIMIT 1;

-- Historial de auditoria con el rol que tenia el usuario en cada momento:
-- SELECT b.fecha, b.accion, r.nombre AS rol_al_momento
-- FROM bitacora_auditoria b
-- LEFT JOIN roles r ON r.id = b.rol_id
-- WHERE b.usuario_id = 3
-- ORDER BY b.fecha DESC;
