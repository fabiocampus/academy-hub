-- Analisi degli indici sulle ricerche frequenti (fase 4). Vedi docs/database.md.
-- SOLO sul PostgreSQL locale di docker compose: CANCELLA tutti i dati.
--   docker compose exec -T db psql -U academy -d academy -q < backend/sql/analisi_indici.sql

-- Il trigger R6 vieta di svuotare l'audit: lo spegne solo questa transazione (superutente).
BEGIN;
SET LOCAL session_replication_role = replica;
TRUNCATE team, persone, corsi, edizioni, iscrizioni, eventi_audit RESTART IDENTITY CASCADE;
COMMIT;

-- Dati sintetici: 50 team, 5 000 persone, 1 000 edizioni (10% cancellate),
-- 50 000 iscrizioni (ogni persona su 10 edizioni, stati misti), ~93 000 eventi di audit.
INSERT INTO team (nome) SELECT 'Team ' || g FROM generate_series(1, 50) g;
INSERT INTO persone (nome, email, team_id)
  SELECT 'Persona ' || g, 'persona' || g || '@esempio.test', 1 + g % 50
  FROM generate_series(1, 5000) g;
INSERT INTO corsi (titolo, durata_ore) SELECT 'Corso ' || g, 8 FROM generate_series(1, 100) g;
INSERT INTO edizioni (corso_id, data_inizio, data_fine, capienza, cancellata_il)
  SELECT 1 + g % 100, DATE '2026-01-01' + g, DATE '2026-01-02' + g, 20,
         CASE WHEN g % 10 = 0 THEN now() END
  FROM generate_series(1, 1000) g;
INSERT INTO iscrizioni (persona_id, edizione_id, stato, approvata_il)
  SELECT p, 1 + (p * 7 + k * 101) % 1000,
         (ARRAY['Richiesta', 'Approvata', 'InAttesa', 'Confermata',
                'Annullata', 'Completata', 'Rifiutata'])[1 + (p + k) % 7],
         CASE WHEN (p + k) % 7 IN (1, 2, 3, 5) THEN now() - (p || ' minutes')::interval END
  FROM generate_series(1, 5000) p, generate_series(0, 9) k;
INSERT INTO eventi_audit (iscrizione_id, stato_da, stato_a)
  SELECT id, NULL, 'Richiesta' FROM iscrizioni;
INSERT INTO eventi_audit (iscrizione_id, stato_da, stato_a)
  SELECT id, 'Richiesta', stato FROM iscrizioni WHERE stato <> 'Richiesta';
ANALYZE;

\echo '== Catalogo: edizioni future non cancellate'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  SELECT id, data_inizio FROM edizioni
  WHERE cancellata_il IS NULL AND data_inizio >= DATE '2026-11-14'
  ORDER BY data_inizio LIMIT 20;

\echo '== Le mie iscrizioni'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  SELECT id, edizione_id, stato FROM iscrizioni WHERE persona_id = 4242;

\echo '== Primo in lista d''attesa (R4)'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  SELECT id FROM iscrizioni WHERE edizione_id = 500 AND stato = 'InAttesa'
  ORDER BY approvata_il, id LIMIT 1 FOR NO KEY UPDATE;

\echo '== Audit di un''iscrizione'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  SELECT * FROM eventi_audit WHERE iscrizione_id = 1234 ORDER BY avvenuto_il, id;

\echo '== Primo in lista d''attesa SENZA gli indici su edizione_id (rollback alla fine)'
BEGIN;
DROP INDEX ix_iscrizioni_lista_attesa;
DROP INDEX ix_iscrizioni_edizione_stato;
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  SELECT id FROM iscrizioni WHERE edizione_id = 500 AND stato = 'InAttesa'
  ORDER BY approvata_il, id LIMIT 1 FOR NO KEY UPDATE;
ROLLBACK;
