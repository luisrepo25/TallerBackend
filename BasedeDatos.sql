-- ============================================================
-- Sistema de Informacion Geografica Web para la Evaluacion y
-- Zonificacion del Riesgo de Incendios
-- Script de creacion de base de datos - PostgreSQL + PostGIS
-- Version 8 (definitiva y completa)
--
-- Incluye todas las correcciones acordadas:
-- - Un usuario tiene UN SOLO rol (rol_id directo, sin usuario_rol)
-- - Subtipos funcionales solapados (administradores/inspectores/oficiales)
-- - Catalogo extensible de tipos de predio (con atributos_extra JSONB)
-- - N:M con atributos propios: predio_hidrante_cobertura, campania_funcionarios
-- - Sin FK directa Predio<->Campania (evita relacion triangulo)
-- - Sincronizacion offline para app movil Flutter (Inspector Tecnico)
-- - Bitacora de auditoria con snapshot del rol al momento de la accion
-- - Calculo de carga de fuego (NB 58005) basado en catalogo de materiales,
--   calculado en el sistema (Django), la BD solo almacena los datos
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================
-- 1. ROLES Y PERMISOS (RBAC)
-- Se persisten como dato de referencia: alimentan la bitacora
-- de auditoria (que rol actuaba el usuario) y el rol unico de
-- cada usuario. La AUTORIZACION en si vive en el sistema.
-- ============================================================

CREATE TABLE roles (
    id      SERIAL PRIMARY KEY,
    nombre  VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE permisos (
    id          SERIAL PRIMARY KEY,
    nombre      VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT
);

CREATE TABLE rol_permiso (
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

CREATE TABLE usuarios (
    id              SERIAL PRIMARY KEY,
    nombre_completo VARCHAR(150) NOT NULL,
    email           VARCHAR(150) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    rol_id          INTEGER NOT NULL REFERENCES roles(id),
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_usuarios_rol ON usuarios (rol_id);

CREATE TABLE administradores (
    usuario_id      INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    nivel_acceso    VARCHAR(20) NOT NULL DEFAULT 'total'
);

CREATE TABLE inspectores_tecnicos (
    usuario_id                  INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    fecha_certificacion         DATE,
    curso_capacitacion_completo BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE oficiales_mando (
    usuario_id      INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    rango           VARCHAR(50)
);

-- ============================================================
-- 3. CATALOGOS
-- ============================================================

CREATE TABLE catalogo_tipos_predio (
    id                      SERIAL PRIMARY KEY,
    nombre                  VARCHAR(100) NOT NULL UNIQUE,
    categoria_riesgo_base   VARCHAR(20),
    riesgo_activacion       NUMERIC(4,2) NOT NULL DEFAULT 1.0   -- Ra, para calculo de carga de fuego
);

CREATE TABLE catalogo_tipos_acople (
    id      SERIAL PRIMARY KEY,
    nombre  VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE catalogo_estados_extintor (
    id      SERIAL PRIMARY KEY,
    nombre  VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE catalogo_infracciones (
    id                SERIAL PRIMARY KEY,
    nombre            VARCHAR(150) NOT NULL UNIQUE,
    peso_severidad    NUMERIC(4,2) NOT NULL DEFAULT 1.0
);

-- Materiales combustibles: Hi (poder calorifico) y Ci (peligrosidad)
-- tabulados segun NB 58005, para el calculo automatizado de carga de fuego.
CREATE TABLE catalogo_materiales_combustibles (
    id                        SERIAL PRIMARY KEY,
    nombre                    VARCHAR(100) NOT NULL UNIQUE,
    poder_calorifico_mj_kg    NUMERIC(6,2) NOT NULL,   -- Hi
    coeficiente_peligrosidad  NUMERIC(4,2) NOT NULL    -- Ci
);

-- ============================================================
-- 4. CATASTRO E INFRAESTRUCTURA GEOESPACIAL
-- ============================================================

CREATE TABLE predios (
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

CREATE INDEX idx_predios_geom ON predios USING GIST (geom);
CREATE INDEX idx_predios_tipo ON predios (tipo_predio_id);

CREATE TABLE hidrantes (
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

CREATE INDEX idx_hidrantes_geom ON hidrantes USING GIST (geom);

CREATE TABLE predio_hidrante_cobertura (
    predio_id       INTEGER NOT NULL REFERENCES predios(id) ON DELETE CASCADE,
    hidrante_id     INTEGER NOT NULL REFERENCES hidrantes(id) ON DELETE CASCADE,
    distancia_m     NUMERIC(8,2) NOT NULL,
    es_mas_cercano  BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_calculo   TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (predio_id, hidrante_id)
);

-- ============================================================
-- 5. GESTION DE CAMPANIAS DE FISCALIZACION
-- ============================================================

CREATE TABLE campanias (
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

CREATE INDEX idx_campanias_geom ON campanias USING GIST (geom);

CREATE TABLE campania_funcionarios (
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

CREATE TABLE actas_inspeccion (
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
    cluster_riesgo              VARCHAR(20)
                                    CHECK (cluster_riesgo IN ('Bajo', 'Medio', 'Critico')),
    cerrada                     BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_cierre                TIMESTAMP,
    sincronizada                BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_sincronizacion        TIMESTAMP
);

CREATE INDEX idx_actas_predio ON actas_inspeccion (predio_id);
CREATE INDEX idx_actas_campania ON actas_inspeccion (campania_id);

-- Materiales combustibles registrados por el inspector en cada acta.
-- Es la entrada real del calculo de carga_fuego (ejecutado en Django).
CREATE TABLE materiales_registrados (
    id          SERIAL PRIMARY KEY,
    acta_id     INTEGER NOT NULL REFERENCES actas_inspeccion(id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL REFERENCES catalogo_materiales_combustibles(id),
    peso_kg     NUMERIC(8,2) NOT NULL CHECK (peso_kg >= 0)
);

CREATE INDEX idx_materiales_acta ON materiales_registrados (acta_id);

-- Entidades debiles: dependencia en existencia de ActaInspeccion
CREATE TABLE evidencias_fotograficas (
    id                      SERIAL PRIMARY KEY,
    acta_id                 INTEGER NOT NULL REFERENCES actas_inspeccion(id) ON DELETE CASCADE,
    url_imagen              VARCHAR(255) NOT NULL,
    descripcion_infraccion  TEXT,
    fecha_captura           TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE infracciones (
    id                  SERIAL PRIMARY KEY,
    acta_id             INTEGER NOT NULL REFERENCES actas_inspeccion(id) ON DELETE CASCADE,
    tipo_infraccion_id  INTEGER NOT NULL REFERENCES catalogo_infracciones(id),
    descripcion         TEXT,
    es_reincidencia     BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_registro      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_infracciones_acta ON infracciones (acta_id);

-- ============================================================
-- 7. INTELIGENCIA ARTIFICIAL Y REPORTES
-- ============================================================

CREATE TABLE clustering_ejecuciones (
    id                    SERIAL PRIMARY KEY,
    fecha_ejecucion       TIMESTAMP NOT NULL DEFAULT NOW(),
    k_value               INTEGER NOT NULL DEFAULT 3,
    coeficiente_silueta   NUMERIC(4,3),
    ejecutado_por         INTEGER NOT NULL REFERENCES usuarios(id)
);

CREATE TABLE reportes_generados (
    id                  SERIAL PRIMARY KEY,
    tipo                VARCHAR(50) NOT NULL CHECK (tipo IN ('dictamen', 'ejecutivo')),
    formato             VARCHAR(10) NOT NULL CHECK (formato IN ('PDF', 'Excel')),
    generado_por        INTEGER NOT NULL REFERENCES usuarios(id),
    fecha_generacion    TIMESTAMP NOT NULL DEFAULT NOW(),
    parametros          JSONB
);

-- ============================================================
-- 8. AUDITORIA
-- rol_id es un SNAPSHOT historico (que rol tenia el usuario al
-- momento exacto de la accion), independiente de que su rol
-- actual en usuarios.rol_id pueda haber cambiado despues.
-- ============================================================

CREATE TABLE bitacora_auditoria (
    id                  SERIAL PRIMARY KEY,
    usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
    rol_id              INTEGER REFERENCES roles(id),
    accion              VARCHAR(150) NOT NULL,
    entidad_afectada    VARCHAR(100),
    fecha               TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_bitacora_usuario ON bitacora_auditoria (usuario_id);
CREATE INDEX idx_bitacora_rol ON bitacora_auditoria (rol_id);

-- ============================================================
-- DATOS INICIALES
-- ============================================================

INSERT INTO roles (nombre) VALUES ('Administrador'), ('Inspector Tecnico'), ('Oficial de Mando');

INSERT INTO catalogo_tipos_predio (nombre, categoria_riesgo_base, riesgo_activacion) VALUES
    ('Comercial', 'Medio', 1.0),
    ('Salud', 'Alto', 1.5),
    ('Educativo', 'Medio', 1.0),
    ('Industrial', 'Alto', 2.0),
    ('Mercado Distrital', 'Alto', 1.5);

INSERT INTO catalogo_tipos_acople (nombre) VALUES ('Storz'), ('NST'), ('BSP');

INSERT INTO catalogo_estados_extintor (nombre) VALUES ('Vigente'), ('Vencido'), ('No posee');

INSERT INTO catalogo_infracciones (nombre, peso_severidad) VALUES
    ('Extintor vencido', 1.5),
    ('Instalacion electrica precaria', 2.0),
    ('Ruta de evacuacion obstruida', 2.5),
    ('Almacenamiento inadecuado de inflamables', 3.0);

INSERT INTO catalogo_materiales_combustibles (nombre, poder_calorifico_mj_kg, coeficiente_peligrosidad) VALUES
    ('Madera', 18.41, 1.0),
    ('Papel y carton', 16.75, 1.0),
    ('Telas y textiles', 19.00, 1.2),
    ('Plasticos (PVC/PET)', 25.00, 1.5),
    ('Liquidos inflamables', 40.00, 2.0);

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