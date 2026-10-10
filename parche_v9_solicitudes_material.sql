-- ============================================================
-- Parche v9: solicitudes de material combustible nuevo
-- El Inspector Tecnico no crea materiales (Hi y Ci son datos tabulados de la
-- NB 58005): los solicita, y el Administrador los da de alta en el catalogo
-- con los valores de la norma. Aplicar en Supabase. Idempotente.
-- ============================================================

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

-- RLS activado como en el resto de tablas: el unico acceso legitimo es Django
ALTER TABLE solicitudes_material ENABLE ROW LEVEL SECURITY;
