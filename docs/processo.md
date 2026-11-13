# Processo di lavoro

## Gerarchia del backlog

Il backlog vive in GitHub Issues, con una board in GitHub Projects.

| Livello | Label | Esempio |
|---|---|---|
| Epic | `type:epic` | Iscrizioni e flusso approvativo |
| Feature | `type:feature` | Lista d'attesa |
| User story | `type:story` | Come responsabile voglio approvare una richiesta... |
| Bug | `type:bug` | Il conteggio dei posti ignora gli annullamenti |
| Attività tecnica | `type:chore` | Configurare il ruleset su `main` |

Le storie sono **sub-issue** della feature, le feature sono sub-issue dell'epic.

Colonne della board: `Backlog` → `Ready` → `In corso` → `In revisione` → `Fatto`.

## Definition of Ready

Una storia entra in `Ready` solo se:

- [ ] è scritta come «Come <ruolo> voglio <azione> per <beneficio>»;
- [ ] ha criteri di accettazione in forma *Dato / Quando / Allora*, compresi i casi di errore;
- [ ] cita le regole di business che tocca (R1–R7);
- [ ] non ha domande aperte, oppure le domande sono annotate con la decisione presa;
- [ ] è abbastanza piccola da chiudersi con una sola pull request;
- [ ] gli impatti su schema del database, contratto dell'API e permessi sono indicati, se presenti.

## Definition of Done

Una storia è `Fatto` solo se:

- [ ] ogni criterio di accettazione è coperto da almeno un test automatico, compresi i casi vietati;
- [ ] lint, controllo dei tipi e test sono verdi nella CI;
- [ ] la scansione di sicurezza (dipendenze, SAST, segreti) non segnala problemi nuovi;
- [ ] la pull request è collegata alla issue (`Closes #n`) e la sua descrizione dice che cosa è stato eseguito e con quale esito;
- [ ] il contratto OpenAPI, la documentazione e gli ADR sono aggiornati nella stessa pull request, se toccati;
- [ ] la modifica è stata rilasciata almeno in collaudo (dalla fase 10 in poi).

## Regole di collaborazione

- Branch brevi da `main`, nome `<tipo>/<numero-issue>-<descrizione>`, ad esempio `feat/12-lista-attesa`.
- Messaggi di commit in formato [Conventional Commits](https://www.conventionalcommits.org/).
- Nessun push diretto su `main`: tutto passa da una pull request con CI verde.
- Il repository è pubblico: niente segreti, niente dati reali, nemmeno nei commenti o nelle issue.
