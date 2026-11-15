# Post-mortem

Uno per incidente, senza colpa: si cercano le condizioni che hanno reso possibile il guasto, non chi l'ha causato. Nome del file `AAAA-MM-GG-<titolo>.md`, scritto entro due giorni dalla chiusura (`docs/runbook.md`, punto 4).

## Modello

```markdown
# <Titolo>

- **Data**: AAAA-MM-GG · **Durata**: dal guasto al ripristino · **Ambiente**: collaudo | produzione
- **Impatto**: chi o che cosa ne ha risentito, quale SLO (docs/slo.md) e quanto budget di errore

## Cronologia
Ora per ora, con i link a run, PR, email (orari in Europe/Rome).

## Rilevamento
Quale avviso è scattato e dopo quanto tempo. Se nessun avviso: perché.

## Causa
La catena di condizioni, fino a quella che nessun controllo ha fermato.

## Ripristino
Che cosa si è fatto, seguendo quale punto del runbook; che cosa nel runbook mancava.

## Che cosa ha funzionato, che cosa no

## Azioni
- [ ] Azione, issue #n
```
