/**
 * Client HTTP tipizzato, generato dal contratto OpenAPI (`npm run api:genera`).
 *
 * I tipi in `schema.d.ts` vengono da `backend/contratto/openapi.json`: se l'API cambia,
 * la CI fallisce finché il file non è rigenerato.
 */
import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type Schemi = components["schemas"];
export type Problema = Schemi["Problema"];

/** Restituisce l'access token da mandare all'API, se il login è nostro (OIDC). */
export type LeggiToken = () => Promise<string | undefined>;

let leggiToken: LeggiToken = () => Promise.resolve(undefined);

/** Da chiamare prima del primo render; su Databricks il token non serve (lo mette il proxy). */
export function impostaToken(lettore: LeggiToken): void {
  leggiToken = lettore;
}

let alNonAutenticato: () => void = () => undefined;

/**
 * Che cosa fare quando l'API risponde 401 (token scaduto e rinnovo fallito, sessione
 * revocata): con OIDC si torna alla schermata d'accesso invece di riprovare a vuoto.
 */
export function impostaAlNonAutenticato(azione: () => void): void {
  alNonAutenticato = azione;
}

const autenticazione: Middleware = {
  async onRequest({ request }) {
    const token = await leggiToken();
    if (token !== undefined) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401) {
      alNonAutenticato();
    }
    return response;
  },
};

/**
 * Retry di React Query: gli errori del client (401, 403, 404, ...) non passano
 * riprovando; errori del server e di rete sì, al più due volte.
 */
export function riprova(tentativi: number, errore: unknown): boolean {
  if (errore instanceof ErroreApi && errore.stato < 500) {
    return false;
  }
  return tentativi < 2;
}

export const api = createClient<paths>({
  baseUrl: window.location.origin,
  // Legge fetch a ogni chiamata: nei test MSW lo sostituisce dopo l'import del modulo.
  fetch: (richiesta) => globalThis.fetch(richiesta),
});
api.use(autenticazione);

/** Errore dell'API in formato RFC 9457 (ADR-0005). */
export class ErroreApi extends Error {
  readonly problema: Problema;

  constructor(problema: Problema) {
    super(problema.detail ?? problema.title);
    this.name = "ErroreApi";
    this.problema = problema;
  }

  get stato(): number {
    return this.problema.status;
  }
}

function eProblema(corpo: unknown): corpo is Problema {
  return (
    typeof corpo === "object" &&
    corpo !== null &&
    "title" in corpo &&
    "status" in corpo &&
    "type" in corpo
  );
}

/** Il corpo della risposta, o `ErroreApi` se l'API ha risposto con un errore. */
export function dati<T>(esito: { data?: T; error?: unknown; response: Response }): T {
  if (esito.response.ok && esito.data !== undefined) {
    return esito.data;
  }
  if (eProblema(esito.error)) {
    throw new ErroreApi(esito.error);
  }
  throw new ErroreApi({
    type: "about:blank",
    title: esito.response.statusText || "Risposta inattesa dal server",
    status: esito.response.status,
  });
}

/** Errori di validazione per campo (422) da mostrare nel form: `{ motivo: "..." }`. */
export function erroriDeiCampi(errore: unknown): Record<string, string> {
  if (!(errore instanceof ErroreApi)) {
    return {};
  }
  return Object.fromEntries((errore.problema.errori ?? []).map((e) => [e.campo, e.messaggio]));
}
