# ADR-0002 · Un solo workspace Databricks per collaudo e produzione

- **Stato:** accettato
- **Data:** 2026-11-14

## Contesto

La pratica raccomandata è un workspace Databricks per ambiente, così identità, permessi, compute e quote sono isolati. Databricks Free Edition offre **un solo workspace**, senza account console. Collaudo e produzione devono quindi convivere.

## Decisione

Collaudo e produzione vivono nello stesso workspace e sono separati da:

| Elemento | Collaudo | Produzione |
|---|---|---|
| Catalogo Unity Catalog | `academy_collaudo` | `academy_prod` |
| Target del bundle | `collaudo` | `prod` |
| Databricks App | `academy-hub-collaudo` | `academy-hub` |
| Database Lakebase | ramo o database dedicato al collaudo | ramo o database di produzione |
| Secret scope | `academy-collaudo` | `academy-prod` |
| Environment GitHub | `collaudo` | `prod`, con approvazione obbligatoria |

Il codice non contiene nomi di ambiente: legge catalogo, database e scope dalla configurazione del target. Lo sviluppo personale usa il target `dev` del bundle, che aggiunge un prefisso al nome delle risorse.

## Conseguenze

- **Positive:** la promozione fra ambienti cambia solo configurazione, come con workspace separati; il passaggio a più workspace richiede solo nuovi target e nuovi host.
- **Negative:**
  - le quote di compute giornaliere sono condivise: un job pesante in collaudo può fermare la produzione fino al giorno dopo;
  - un amministratore del workspace vede entrambi gli ambienti; la separazione dei permessi sta solo nei grant di Unity Catalog;
  - un errore di configurazione (catalogo sbagliato nel target) scrive in produzione. Mitigazione: test di fumo dopo il rilascio in collaudo che verifica il catalogo in uso, e grant di scrittura su `academy_prod` solo all'identità che rilascia in produzione.
- **Da rivalutare:** se in futuro serve un ambiente con dati realistici o più persone, si passa a workspace separati.

## Alternative considerate

- **Due account Free Edition:** violerebbe lo spirito dell'offerta e complicherebbe identità e CI.
- **Solo produzione, collaudo in locale:** non permetterebbe di provare bundle, App e pipeline prima della produzione.
