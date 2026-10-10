-- ============================================================
-- Parche v8.1 sobre BasedeDatos.sql (solo indices; no cambia datos ni columnas)
-- Aplicar en Supabase. Idempotente (IF NOT EXISTS).
-- Los demas ajustes sugeridos (UNIQUE predio+campania, ejecucion_id en actas,
-- columnas de archivo en reportes_generados, entidad_id en bitacora, TIMESTAMPTZ)
-- son decisiones de negocio pendientes y NO se incluyen aqui.
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_actas_inspector ON actas_inspeccion (inspector_id);
CREATE INDEX IF NOT EXISTS idx_actas_cerrada   ON actas_inspeccion (cerrada);
CREATE INDEX IF NOT EXISTS idx_cobertura_hidrante ON predio_hidrante_cobertura (hidrante_id);
