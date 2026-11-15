# ADR-0017 · Importazioni, controlli di qualità e gold dei report

- **Stato:** accettato
- **Data:** 2026-11-15

## Contesto

Fase 11, PR B1 (issue #103, parte di #91). Presenze e valutazioni non nascono nell'App: l'Academy le raccoglie su fogli (firme, questionari) e le carica come file. Da qui, insieme allo storico di silver (ADR-0016), si calcolano i report: ore di formazione per team, tasso di completamento, valutazione media. Un file compilato a mano ha errori: righe doppie, email sbagliate, giorni che non esistono, edizioni sbagliate. Alcuni errori sono di una riga, altri dicono che l'intero file non è quello giusto.

Vincoli: Free Edition (solo serverless), pipeline `storico` e job `analisi` già nel bundle con l'identità di `academy-rilascio` (ADR-0016), grant in Terraform (ADR-0012), nessuna scrittura della parte analitica su Lakebase (ADR-0016 §8), repository pubblico.

## Decisione

1. **File CSV in un volume.** `<catalogo>.bronze.importazioni` (volume gestito, Terraform `infra/databricks/qualita.tf`), una cartella per tipo: `presenze/` (`edizione_id,email,giorno`) e `valutazioni/` (`edizione_id,email,voto,commento`). La persona si riconosce dall'**email** (chi compila un foglio non conosce gli id), confrontata senza maiuscole e spazi. UTF-8, intestazione obbligatoria, colonne **per posizione**: un'intestazione diversa non ferma la lettura, le righe finiscono in quarantena. Esempi e regole del formato in `data/samples/`. Un `LEGGIMI.txt` per cartella la fa esistere (un volume non ha cartelle vuote) ed è ignorato, perché si leggono solo `*.csv`. In collaudo tutti gli utenti del workspace possono caricare (`READ_VOLUME`, `WRITE_VOLUME`, più `USE_SCHEMA` su `bronze` per arrivarci); in produzione solo il proprietario del catalogo.
2. **Auto Loader nella pipeline `storico`** (`analisi/src/pipeline_importazioni.py`, seconda libreria): streaming table `bronze.presenze_importate` e `bronze.valutazioni_importate`, tutto come testo, con il file di origine (`_file`, da `_metadata.file_path`) e l'istante (`_caricata_il`, da `_metadata.file_modification_time`: stabile anche dopo un full refresh). Ogni file si legge una volta: una versione corretta si carica con un nome nuovo. La radice del volume arriva dalla `configuration` della pipeline (`academy.importazioni`).
3. **Classificazione in viste materializzate** della stessa pipeline, con le anagrafiche correnti dello storico (`silver.persone`, `silver.edizioni`): ogni riga riceve un `motivo` (il primo che vale, nell'ordine sotto) e `bloccante`. Le valide vanno in `silver.presenze` / `silver.valutazioni` con i tipi del dominio, le scartate così come sono arrivate in `qualita.presenze_quarantena` / `qualita.valutazioni_quarantena`, e lo stato di ogni file (righe, scartate, bloccanti, accettato, motivo) in `qualita.file_importati`. La logica è in `academy_analisi/qualita.py`, funzioni su `DataFrame` testate con Spark locale; la pipeline dichiara soltanto.

   | Ordine | Motivo | Bloccante | Regola |
   | --- | --- | --- | --- |
   | 1 | `valore_non_valido` | no | edizione non intera, giorno non `AAAA-MM-GG`, voto non intero, email vuota |
   | 2 | `edizione_inesistente` | **sì** | nessuna edizione con quell'id: probabilmente il file di un'altra edizione |
   | 3 | `giorno_futuro` | **sì** | presenza dopo oggi (UTC): un foglio compilato in anticipo |
   | 4 | `persona_sconosciuta` | no | nessuna persona con quell'email |
   | 5 | `giorno_fuori_edizione` | no | presenza prima dell'inizio o dopo la fine dell'edizione |
   | 6 | `voto_fuori_scala` | no | voto fuori da 1-5 |
   | 7 | `duplicato` | no | presenze: la seconda riga valida dello stesso file per persona, edizione e giorno (la prima resta); valutazioni: tutte quelle della stessa persona ed edizione nello stesso file (non si sa quale valga) |

   Un file è **respinto** se ha almeno una riga bloccante o se le righe scartate sono più del 10%; altrimenti è accettato e le sue righe scartate restano in quarantena.
4. **Gate con verdetto fissato.** Il job `analisi` dopo `snapshot` e `storico` ha tre task: `controlli` → `gold` → `registra_esito`. `controlli` (`academy_analisi/gate.py`) confronta `qualita.file_importati` con `qualita.verdetti` e scrive il **verdetto** di ogni file nuovo (per file e tipo, con la run che l'ha dato); se un file nuovo è respinto, dopo aver scritto tutti i verdetti fallisce, e `gold` non parte. Il verdetto non cambia più: un giorno futuro che diventa passato, o una persona aggiunta dopo, non riaprono un file. Così un file respinto blocca solo la passata in cui arriva, e resta fuori dal gold per sempre: si corregge caricandone uno nuovo.
5. **Gold riscritto per intero** a ogni passata riuscita del gate (`academy_analisi/gold.py`, `overwrite` con lo schema): `iscrizioni_concluse`, `ore_per_team`, `tasso_completamento`, `valutazione_media`. Le tabelle sono piccole, e così non restano righe di file respinti o di dati poi corretti. Presenze e valutazioni vengono **solo dai file accettati**. Il gold sintetico della fase 8 (`iscrizioni_per_corso`) resta finché l'API dei report non passa al gold vero (PR B2).
6. **`Completata` si calcola solo nel gold** (ADR-0016 §8): un'iscrizione `Confermata` di un'edizione conclusa (`data_fine` prima di oggi, UTC) e non cancellata è completata se i giorni con una presenza sono almeno la soglia (75%, intera, parametro `--soglia`) delle **giornate di calendario** dell'edizione, dal primo all'ultimo giorno compresi: l'App non conosce i giorni festivi né il calendario delle lezioni. Un giorno ripetuto in due file conta una volta. Il team di una persona è quello che aveva alla fine dell'edizione, letto dallo storico SCD 2; se lo storico comincia dopo, vale la prima versione nota.
7. **Valutazione media** per corso: solo le valutazioni di iscrizioni completate, la prima caricata per iscrizione (una valutazione non si modifica, CONTEXT.md).
8. **Esito di ogni passata** in `qualita.esiti`: `registra_esito` gira sempre (`run_if: ALL_DONE`), riceve lo stato dei due task dai riferimenti dinamici del job (`{{tasks.controlli.result_state}}`, `{{tasks.gold.result_state}}`) e scrive `aggiornato` (gold riuscito), `bloccato` (con i file respinti in quella run e il loro motivo) o `errore` (con gli stati dei task).
9. **Grant** (Terraform): schema `qualita` nuovo con `USE_SCHEMA`, `CREATE_TABLE`, `CREATE_MATERIALIZED_VIEW` ad `academy-rilascio`; su `gold` `USE_SCHEMA`, `CREATE_TABLE`; `READ_VOLUME` sul volume. Gli utenti leggono ancora solo gold (D20). L'apply va fatto prima del rilascio che porta pipeline e task nuovi.
10. **Un file è solo un dato** (D21): letto come testo, convertito con `try_cast`/`try_to_date`, mai eseguito né interpretato; un commento che sembra una formula resta testo.

## Alternative scartate

- **Expectations di Lakeflow** (`expect_or_drop`, `expect_or_fail`): scartano o fermano per riga, non sanno dire "respingi il file se più del 10% è sbagliato", non tengono le righe scartate con il motivo, e `expect_or_fail` ferma l'intera pipeline (anche lo storico) per un file. Le regole come funzioni su `DataFrame` si provano in locale.
- **Persona per id nel file**: chi compila non lo conosce; l'email è già la chiave d'identità (ADR-0008).
- **Verdetto ricalcolato a ogni passata**: un file respinto per un giorno futuro passerebbe da solo qualche giorno dopo, senza che nessuno lo guardi; un file accettato potrebbe diventare respinto e sparire dal gold.
- **Gold incrementale (`MERGE`)**: più codice e più casi (righe da togliere), per tabelle di poche righe.
- **Gate dentro la pipeline**: una pipeline fallita ferma anche lo storico; nel job il gate ferma solo il gold e l'esito si registra comunque.
- **Giornate lavorative**: servirebbe un calendario delle lezioni che l'App non ha.

## Conseguenze

- Il gold si aggiorna solo se nessun file nuovo è respinto: un file sbagliato ferma i report di quella notte per tutti, anche con altri file buoni nella stessa passata (i loro verdetti sono già scritti: alla passata dopo entrano).
- `silver.presenze` e `silver.valutazioni` contengono le righe valide di tutti i file, anche dei respinti: è il gold a filtrare per verdetto. Una riga di un file accettato può cambiare classificazione dopo (persona aggiunta, edizione cancellata): il verdetto del file resta, le righe seguono le anagrafiche di oggi.
- Un CSV caricato in prod da chi non dovrebbe falserebbe i report: per questo in prod carica solo il proprietario del catalogo. In collaudo chiunque nel workspace (Free Edition: uno solo).
- Le email dei file arrivano in bronze e in quarantena: come per lo storico, solo `academy-rilascio` legge quegli schemi (D20).
- Né il rilascio né il fumo provano ancora il job, e un esito `bloccato` o `errore` non manda notifiche: arrivano nella PR B2 con l'API dei report sul gold.
- Le prove di lettura dei file con Spark (`analisi/tests/test_importazioni.py`) girano solo su Linux e macOS (in CI): su Windows Spark legge file solo con le librerie native di Hadoop.
