# ADR-0020 · Interfaccia con la taste-skill e pagina pubblica statica

- **Stato:** accettato
- **Data:** 2026-11-21

## Contesto

Feature #118 (US-19..US-24). Il frontend usava Mantine con il tema predefinito: funzionava ma aveva l'aspetto di un modello. Per ridisegnarlo si è usata la [taste-skill](https://github.com/Leonxlnx/taste-skill) (2.5.1, MIT), una skill per agenti che sceglie un sistema (palette, font, raggi, struttura delle sezioni) e lo verifica in un browser con un gate (`gate.mjs`: consistenza, layout, testi, prestazioni). La skill è pensata per siti di presentazione in HTML/CSS, non per un'applicazione React con tabelle e form. L'App inoltre ha una CSP stretta (`script-src 'self'`, `font-src 'self'`) e non deve caricare nulla da domini esterni.

## Decisione

1. **Pagina pubblica statica** `frontend/public/benvenuto.html`, costruita in pieno con la skill e passata dal suo gate. È la pagina d'arrivo di chi non ha una sessione: con il login OIDC `Accesso.tsx` salva l'indirizzo chiesto in `sessionStorage` e va a `/benvenuto.html`; il pulsante «Accedi con l'account aziendale» porta a `/?accedi=1`, che avvia il login e poi torna all'indirizzo salvato. Su Databricks (proxy dell'App) la pagina non serve e non si vede.
2. **Kit della skill copiato in `frontend/public/vetrina/`** (CSS, JS dei frammenti e del momento animato, licenza MIT accanto) e **font ospitati dall'App** in `public/vetrina/fonts/` (Funnel Display, Funnel Sans, DM Mono, OFL). Gli script inline dello starter sono in `vetrina/avvio.js` per rispettare la CSP. Il kit non passa da ESLint né da Prettier: è codice di terzi, verificato dal gate.
3. **Pagine interne ancora in Mantine**, con un solo tema (`src/tema.ts`) generato dai token scelti per la pagina pubblica: palette bianco e blu (#1a4be0), font Funnel, raggi soft, pulsanti alti 44 px; le parti fuori da Mantine (testata fissa, menu, intestazioni di pagina) usano le variabili gemelle in `src/stile.css`. Restano le tabelle, le etichette e i nomi accessibili su cui contano Vitest, Playwright e axe.
4. **Ogni `.html` della build esce con le intestazioni di `index.html`** (CSP e `no-cache`, `backend/src/academy_hub/frontend.py`); i file di `vetrina/` sono statici come gli altri asset.
5. Lo stato del gate (`frontend/.taste-skill/`: screenshot, profilo del browser) resta fuori da git, tranne `waivers.json`, i falsi positivi accettati con il loro motivo (oggi `button-styles`: le date del frammento calendario non sono pulsanti). Per ritoccare la pagina pubblica si rilancia il gate (`gate.mjs --start public/benvenuto.html --root public ...`, poi `gate.mjs public/benvenuto.html`) fino a `GATE: PASS`; un falso positivo nuovo va in `waivers.json` con il motivo e si committa.

## Alternative scartate

- **Tutta l'App in HTML statico con il kit**: si sarebbero riscritti stato, form, paginazione e test senza guadagno; il gate non sa verificare una SPA dietro login.
- **Sostituire Mantine con un altro sistema di componenti**: lavoro grande, nessun vantaggio per l'accessibilità già verificata da axe.
- **Font da Google Fonts**: richiede di aprire la CSP verso un dominio esterno.

## Conseguenze

- Due fonti per gli stessi token (CSS della pagina pubblica e `tema.ts`/`stile.css`): un cambio di palette o di font va fatto in entrambe.
- Il test axe degli end-to-end copre anche `/benvenuto.html` (con le animazioni ridotte, così il contrasto non si misura a metà dissolvenza).
- Un aggiornamento della skill non arriva da solo: il kit è una copia fissata alla versione 2.5.1.
