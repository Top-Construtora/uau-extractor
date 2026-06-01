-- Schema de destino dos dados extraídos da API UAU.
-- Tabelas fato_*/dim_* concretas serão criadas na próxima fase (ver sql/migrations/).

CREATE SCHEMA IF NOT EXISTS uau;

-- Exemplo (comentado) do padrão de tabela fato com PK de auditoria, espelhando a
-- convenção do schema sienge (dt_ref + hash_linha):
--
-- CREATE TABLE IF NOT EXISTS uau.fato_exemplo (
--     dt_ref      date NOT NULL,
--     hash_linha  text NOT NULL,
--     empresa     text NOT NULL,
--     -- ... colunas do relatório ...
--     PRIMARY KEY (dt_ref, hash_linha)
-- );
