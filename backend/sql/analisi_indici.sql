-- Analisi degli indici sulle ricerche frequenti (fasi 4 e 5). Vedi docs/database.md.
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

-- Organigramma (US-07): il team 1 è la radice, i team 2-10 sono suoi figli, i team 11-50
-- dipendono da uno dei team 2-10 e non hanno responsabile, così la ricerca deve risalire.
-- Il responsabile del team t è la persona t + 49, che sta nel team t.
UPDATE team SET team_padre_id = 1 WHERE id BETWEEN 2 AND 10;
UPDATE team SET team_padre_id = 2 + id % 9 WHERE id > 10;
UPDATE team SET responsabile_id = id + 49 WHERE id <= 10;

-- Posti confermati coerenti con le iscrizioni Confermata (R3), come fa l'API.
UPDATE edizioni e SET posti_confermati = c.n
  FROM (SELECT edizione_id, count(*) AS n FROM iscrizioni
        WHERE stato = 'Confermata' GROUP BY edizione_id) c
  WHERE c.edizione_id = e.id;
ANALYZE;

\echo '== Catalogo: edizioni future non cancellate'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  SELECT id, data_inizio FROM edizioni
  WHERE cancellata_il IS NULL AND data_inizio >= DATE '2026-11-14'
  ORDER BY data_inizio LIMIT 20;

-- Da qui in poi le query dell'API e del job sono quelle generate da SQLAlchemy nei
-- repository (catturate dal driver, parametri sostituiti); solo l'elenco delle colonne è
-- abbreviato con `tabella.*`. Se cambia un repository, va aggiornata anche la copia qui.

\echo '== Le mie iscrizioni (US-05, repository.iscrizioni.mie_iscrizioni): conteggio'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  SELECT count(*) FROM iscrizioni WHERE iscrizioni.persona_id = 4242;

\echo '== Le mie iscrizioni (US-05): pagina, con la posizione in lista d''attesa'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  SELECT iscrizioni.*, edizioni.*, corsi.*,
         CASE WHEN iscrizioni.stato = 'InAttesa' THEN
           (SELECT count(*) FROM iscrizioni AS iscrizioni_1
            WHERE iscrizioni_1.edizione_id = iscrizioni.edizione_id
              AND iscrizioni_1.stato = 'InAttesa'
              AND (iscrizioni_1.approvata_il, iscrizioni_1.id)
                  <= (iscrizioni.approvata_il, iscrizioni.id)) END AS posizione
  FROM iscrizioni JOIN edizioni ON edizioni.id = iscrizioni.edizione_id
  JOIN corsi ON corsi.id = edizioni.corso_id
  WHERE iscrizioni.persona_id = 4242
  ORDER BY iscrizioni.aggiornata_il DESC, iscrizioni.id DESC LIMIT 20 OFFSET 0;

-- US-07 (repository.iscrizioni.richieste_da_decidere). Il decisore è la persona 51,
-- responsabile del team 2: decide per i team 2, 18, 27, 36 e 45 (500 persone).
\echo '== Richieste da decidere (US-07): conteggio, responsabile'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  WITH RECURSIVE antenati(team_id, antenato_id, livello) AS
  (SELECT team.id, team.id, 0 FROM team
   UNION ALL
   SELECT antenati.team_id, team_2.team_padre_id, antenati.livello + 1
   FROM antenati JOIN team AS team_2 ON team_2.id = antenati.antenato_id
   WHERE team_2.team_padre_id IS NOT NULL AND antenati.livello < 50),
  responsabile_di AS
  (SELECT DISTINCT ON (persone_1.id) persone_1.id AS persona_id, team_1.responsabile_id
   FROM persone AS persone_1
   JOIN antenati ON antenati.team_id = persone_1.team_id
   JOIN team AS team_1 ON team_1.id = antenati.antenato_id
   WHERE team_1.responsabile_id IS NOT NULL AND team_1.responsabile_id != persone_1.id
   ORDER BY persone_1.id, antenati.livello)
  SELECT count(*) FROM iscrizioni JOIN persone ON persone.id = iscrizioni.persona_id
  LEFT OUTER JOIN responsabile_di ON responsabile_di.persona_id = persone.id
  WHERE iscrizioni.stato = 'Richiesta' AND persone.id != 51
    AND responsabile_di.responsabile_id = 51;

\echo '== Richieste da decidere (US-07): pagina, amministratore (anche chi non ha responsabile)'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  WITH RECURSIVE antenati(team_id, antenato_id, livello) AS
  (SELECT team.id, team.id, 0 FROM team
   UNION ALL
   SELECT antenati.team_id, team_2.team_padre_id, antenati.livello + 1
   FROM antenati JOIN team AS team_2 ON team_2.id = antenati.antenato_id
   WHERE team_2.team_padre_id IS NOT NULL AND antenati.livello < 50),
  responsabile_di AS
  (SELECT DISTINCT ON (persone_1.id) persone_1.id AS persona_id, team_1.responsabile_id
   FROM persone AS persone_1
   JOIN antenati ON antenati.team_id = persone_1.team_id
   JOIN team AS team_1 ON team_1.id = antenati.antenato_id
   WHERE team_1.responsabile_id IS NOT NULL AND team_1.responsabile_id != persone_1.id
   ORDER BY persone_1.id, antenati.livello)
  SELECT iscrizioni.*, persone.*, edizioni.*, corsi.*
  FROM iscrizioni JOIN persone ON persone.id = iscrizioni.persona_id
  LEFT OUTER JOIN responsabile_di ON responsabile_di.persona_id = persone.id
  JOIN edizioni ON edizioni.id = iscrizioni.edizione_id
  JOIN corsi ON corsi.id = edizioni.corso_id
  WHERE iscrizioni.stato = 'Richiesta' AND persone.id != 51
    AND (responsabile_di.responsabile_id = 51 OR responsabile_di.responsabile_id IS NULL)
  ORDER BY iscrizioni.richiesta_il, iscrizioni.id LIMIT 20 OFFSET 0;

\echo '== Richieste da decidere (US-07) PRIMA della riscrittura: sottoquery correlata per persona'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  WITH RECURSIVE antenati(team_id, antenato_id, livello) AS
  (SELECT team.id, team.id, 0 FROM team
   UNION ALL
   SELECT antenati.team_id, team_2.team_padre_id, antenati.livello + 1
   FROM antenati JOIN team AS team_2 ON team_2.id = antenati.antenato_id
   WHERE team_2.team_padre_id IS NOT NULL AND antenati.livello < 50)
  SELECT count(*) FROM iscrizioni JOIN persone ON persone.id = iscrizioni.persona_id
  WHERE iscrizioni.stato = 'Richiesta' AND persone.id != 51
    AND (SELECT team_1.responsabile_id
         FROM antenati JOIN team AS team_1 ON team_1.id = antenati.antenato_id
         WHERE antenati.team_id = persone.team_id AND team_1.responsabile_id IS NOT NULL
           AND team_1.responsabile_id != persone.id
         ORDER BY antenati.livello LIMIT 1) = 51;

\echo '== Job: edizioni iniziate con iscrizioni pendenti (US-17, edizioni_iniziate_con_pendenti)'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  SELECT edizioni.id FROM edizioni
  WHERE edizioni.data_inizio <= DATE '2026-11-14'
    AND EXISTS (SELECT iscrizioni.id FROM iscrizioni
                WHERE iscrizioni.edizione_id = edizioni.id
                  AND iscrizioni.stato IN ('Richiesta', 'Approvata', 'InAttesa'))
  ORDER BY edizioni.id;

\echo '== Job: edizioni aperte con posti liberi e lista d''attesa (US-09, edizioni_con_posti_e_lista)'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
  SELECT edizioni.id FROM edizioni
  WHERE edizioni.data_inizio > DATE '2026-11-14' AND edizioni.cancellata_il IS NULL
    AND edizioni.posti_confermati < edizioni.capienza
    AND EXISTS (SELECT iscrizioni.id FROM iscrizioni
                WHERE iscrizioni.edizione_id = edizioni.id
                  AND iscrizioni.stato = 'InAttesa')
  ORDER BY edizioni.id;

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
