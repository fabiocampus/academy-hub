# File di esempio delle importazioni

CSV sintetici di presenze e valutazioni nel formato che la pipeline `storico` legge dal volume `<catalogo>.bronze.importazioni` (ADR-0017). Solo email `@academy.example`: nessun dato reale.

| File | Colonne | Che cosa mostra |
| --- | --- | --- |
| `presenze_pulite.csv` | `edizione_id,email,giorno` | tutte righe valide: file accettato |
| `presenze_sporche.csv` | idem | duplicato, giorno futuro e edizione inesistente (bloccanti), persona sconosciuta, giorno fuori dall'edizione, valori non validi: file respinto |
| `valutazioni_pulite.csv` | `edizione_id,email,voto,commento` | voti 1-5, commento facoltativo e con virgole: file accettato |
| `valutazioni_sporche.csv` | idem | voto fuori scala o non numerico, due valutazioni della stessa persona, edizione inesistente (bloccante), persona sconosciuta, un commento che sembra una formula (resta testo): file respinto |

Gli id delle edizioni (101, 102) e le persone sono di esempio: `analisi/tests/test_campioni.py` li classifica con anagrafiche costruite apposta (edizione 101 dal 2 al 6 marzo 2026, 102 il 13 e 14 aprile 2026). Per una prova in collaudo servono id ed email veri di quell'ambiente: si generano file nuovi con lo stesso formato.

Regole del formato:

- UTF-8, prima riga d'intestazione, separatore virgola, testo con virgole fra virgolette doppie, estensione `.csv`.
- Le colonne valgono per posizione: un file con le colonne in un altro ordine finisce in quarantena.
- `giorno` in `AAAA-MM-GG`; `voto` intero da 1 a 5.
- La persona si riconosce dall'email, senza distinguere maiuscole e spazi.
- Un file già caricato non viene riletto: una versione corretta si carica con un nome nuovo.

Caricamento (collaudo, dove tutti gli utenti del workspace possono scrivere nel volume):

```bash
databricks fs cp presenze_pulite.csv dbfs:/Volumes/academy_collaudo/bronze/importazioni/presenze/2026-03-presenze.csv
```

Il job `analisi` della notte (o `databricks bundle run analisi -t collaudo`) li legge, li controlla e, se nessun file nuovo è respinto, aggiorna il gold. Com'è andata si legge in `academy_collaudo.qualita.esiti`; le righe scartate in `qualita.presenze_quarantena` e `qualita.valutazioni_quarantena`.
