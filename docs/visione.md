# Visione del prodotto

## Problema

L'Academy di un'azienda di medie dimensioni gestisce le iscrizioni ai corsi con email e fogli di calcolo. Ne derivano tre problemi:

- **Nessuna traccia delle decisioni.** Non si sa chi ha approvato un'iscrizione, quando, e perché un posto è andato a una persona invece che a un'altra.
- **Posti assegnati male.** Due conferme quasi simultanee sull'ultimo posto producono un'aula sovraffollata; i posti liberati da un annullamento non vengono riassegnati in modo equo.
- **Report poco affidabili.** Le presenze arrivano in file compilati a mano, con duplicati, persone sconosciute e date sbagliate. I report sulle ore di formazione per team vengono calcolati su questi dati senza alcun controllo.

## Per chi

| Attore | Bisogno principale |
|---|---|
| Dipendente | Trovare un corso, chiedere l'iscrizione e sapere a che punto è la richiesta |
| Responsabile | Decidere rapidamente sulle richieste del proprio team e vedere quanta formazione fa il team |
| Amministratore Academy | Gestire corsi ed edizioni, assegnare i posti in modo equo, caricare le presenze, avere report affidabili |
| Docente (facoltativo) | Caricare le presenze della propria edizione senza passare dall'Academy |

## Che cosa fa il prodotto

1. **Catalogo**: corsi ed edizioni con date, capienza e scadenza per gli annullamenti.
2. **Flusso approvativo**: richiesta del dipendente, approvazione del responsabile diretto, conferma del posto da parte dell'Academy, lista d'attesa.
3. **Audit**: ogni cambio di stato registra chi, quando, da quale stato a quale.
4. **Presenze e valutazioni**: importazione da file con controlli di qualità; valutazione del corso da parte di chi lo ha completato.
5. **Report**: ore di formazione per team, tasso di completamento, valutazione media per corso. Ogni responsabile vede solo il proprio team.

## Perimetro

**Dentro:** le funzioni sopra, un'interfaccia web, un'API documentata, una piattaforma dati con controlli di qualità bloccanti, rilascio automatico in collaudo e produzione.

**Fuori:** notifiche email reali, calendari, integrazione con sistemi HR, multilingua, pagamenti, gestione delle aule fisiche.

## Come capiamo che funziona

- Nessuna edizione supera mai la capienza, nemmeno sotto carico concorrente.
- Ogni iscrizione ha una storia completa nell'audit.
- Un file di presenze con errori gravi non arriva mai nei report, e il motivo del blocco è registrato.
- Un responsabile non vede mai i dati di un altro team.
- Le operazioni principali dell'API rispondono in meno di 500 ms in ambiente locale.

## Vincoli

- Dati personali minimi: nome, email, team.
- Solo dati sintetici, in nessun caso dati reali.
- Stessa build in collaudo e in produzione; cambia solo la configurazione.
- Solo servizi gratuiti (vedi [ADR-0003](adr/0003-github-al-posto-di-azure-devops.md)).

## Ciclo di vita del progetto

Il progetto attraversa le fasi del piano: visione e backlog, repository e CI, ambiente locale, dominio e database, API, sicurezza, frontend, Databricks, infrastruttura come codice, rilascio continuo, parte analitica, osservabilità, documentazione finale. Ogni fase ha un criterio di completamento verificabile.
