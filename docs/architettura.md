# Architettura

Diagrammi [C4](https://c4model.com/) in Mermaid: contesto, contenitori, componenti del backend, e il percorso dal commit alla produzione. Le scelte sono negli [ADR](adr/); i termini in [`CONTEXT.md`](../CONTEXT.md).

## 1. Contesto

Chi usa il sistema e con che cosa parla.

```mermaid
flowchart LR
    dip["Dipendente, dirigente, docente<br/>chiede l'iscrizione"]
    resp["Responsabile<br/>decide le richieste del team"]
    adm["Amministratore Academy<br/>corsi, edizioni, posti, presenze"]
    hub["Academy Hub<br/>iscrizioni, approvazioni,<br/>report controllati"]
    idp["Identità<br/>Keycloak in locale,<br/>Databricks in cloud"]
    file["File CSV<br/>presenze e valutazioni"]
    gh["GitHub<br/>codice, CI, rilascio"]

    dip --> hub
    resp --> hub
    adm --> hub
    adm -- carica --> file
    file --> hub
    hub -- verifica l'identità --> idp
    gh -- rilascia --> hub
```

## 2. Contenitori

Un'App su Databricks Apps (backend FastAPI che serve anche il frontend), un database transazionale su Lakebase, la parte analitica in Unity Catalog. In locale gli stessi contenitori girano in docker compose, con Keycloak al posto del proxy di Databricks e PostgreSQL al posto di Lakebase.

```mermaid
flowchart TB
    browser["Frontend<br/>React, Vite, Mantine<br/>+ pagina pubblica statica<br/><i>frontend/</i>"]
    subgraph app["Databricks App (o backend di compose)"]
        api["Backend<br/>FastAPI, SQLAlchemy<br/><i>backend/</i>"]
    end
    db[("Database transazionale<br/>Lakebase / PostgreSQL 17<br/>schema academy")]
    idp["Proxy Databricks Apps<br/>X-Forwarded-Email (solo cloud)"]
    kc["Keycloak<br/>OIDC con PKCE (solo locale)"]
    subgraph uc["Unity Catalog: academy_{env}"]
        oltp[("academy_{env}_oltp<br/>Lakebase registrato")]
        bronze[("bronze<br/>snapshot, volume importazioni")]
        silver[("silver<br/>SCD 2, presenze, valutazioni")]
        qual[("qualita<br/>quarantena, verdetti, esiti")]
        gold[("gold<br/>report, row filter per team")]
    end
    job["Job analisi<br/>snapshot → pipeline storico →<br/>controlli → gold → registra_esito<br/><i>analisi/</i>"]
    wh["SQL warehouse<br/>Statement Execution API"]
    alert["Alert SQL<br/>academy-qualita-{env}"]

    browser -- "HTTPS /api/v1, JSON" --> idp --> api
    browser -. "locale: login, poi Bearer" .-> kc
    api -. "locale: JWKS" .-> kc
    api -- "SQL, token OAuth come password" --> db
    api -- "report con il token dell'utente (OBO)" --> wh --> gold
    db -.-> oltp
    job -- legge --> oltp
    job --> bronze --> silver
    job --> qual
    job -- "solo se nessun file respinto" --> gold
    alert -- legge --> qual
```

- Frontend: l'App React per chi ha una sessione; chi non ce l'ha (login OIDC) arriva a `/benvenuto.html`, una pagina statica costruita con la taste-skill (ADR-0020).
- Identità: ADR-0008. App e Lakebase: ADR-0010. Report con l'identità dell'utente: ADR-0011, ADR-0018.
- Parte analitica: ADR-0016 (storico), ADR-0017 (importazioni, qualità, gold).
- Ambienti: `collaudo` e `prod`, ognuno con la sua App, il suo branch di Lakebase e il suo catalogo.

## 3. Componenti del backend

```mermaid
flowchart LR
    subgraph api["api/"]
        rotte["rotte/<br/>catalogo, corsi, edizioni,<br/>iscrizioni, profilo, report"]
        dip["dipendenze<br/>transazione, attore, If-Match"]
        ident["identita.py<br/>oidc · databricks · provvisoria"]
        err["errori.py<br/>RFC 9457"]
    end
    serv["servizi/<br/>regole e autorizzazione"]
    dom["dominio/<br/>stati, transizioni, ruoli,<br/>errori, calendario"]
    repo["repository/<br/>query e lock"]
    db["db/<br/>modelli, migrazioni,<br/>motore"]
    report["report.py<br/>LettoreReport"]
    job["job.py<br/>scadenze, promozione"]
    oss["osservabilita.py<br/>log JSON, X-Request-Id"]
    fe["frontend.py<br/>build statica"]

    rotte --> dip --> ident
    rotte --> serv --> repo --> db
    serv --> dom
    rotte --> report
    rotte --> err
    job --> serv
```

Regole: niente logica nelle rotte, niente SQL fuori dai repository, un solo punto per ogni cambio di stato dell'iscrizione con audit (R6), ogni posto liberato passa da `promuovi_dalla_lista` (R4), lock prima sull'edizione poi sulle iscrizioni (ADR-0004).

## 4. Dal commit alla produzione

```mermaid
flowchart LR
    pr["Pull request<br/>Closes #n"] --> ci["CI: check obbligatori del ruleset<br/>lint, tipi, test, analisi, frontend,<br/>immagine+Trivy, compose, e2e,<br/>CodeQL, dipendenze (pip-audit),<br/>gitleaks, issue-collegata"]
    ci --> main["main<br/>(squash)"]
    main --> build["build/app<br/>un artifact"]
    build --> coll["collaudo<br/>bundle deploy + fumo"]
    coll --> appr{"approvazione<br/>environment prod"}
    appr --> prod["prod<br/>bundle deploy + fumo"]
    prod -. "rollback.yml<br/>artifact di una run precedente" .-> prod
    infra["infra/<br/>Terraform: GitHub, UC, grant"] -. "plan nella PR,<br/>apply approvato" .-> main
```

Rilascio: ADR-0013. Rollback e DORA: ADR-0015. Infrastruttura: ADR-0012. Feature flag: ADR-0014.
