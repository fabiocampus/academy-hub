/** API finta con MSW: le risposte hanno i tipi del contratto OpenAPI. */
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import type { Problema, Schemi } from "../api/client";

export const API = `${window.location.origin}/api/v1`;

export const profiloDipendente: Schemi["Profilo"] = {
  persona_id: 1,
  nome: "Anna Dati",
  email: "anna@academy.example",
  team_id: 10,
  ruoli: ["dipendente"],
  responsabile_di_team: false,
};

export function voceCatalogo(
  edizioneId: number,
  modifiche: Partial<Schemi["VoceCatalogo"]> = {},
): Schemi["VoceCatalogo"] {
  return {
    edizione_id: edizioneId,
    corso: { id: 100 + edizioneId, titolo: `Corso ${edizioneId}`, durata_ore: 8 },
    data_inizio: "2027-03-10",
    data_fine: "2027-03-11",
    capienza: 10,
    posti_confermati: 4,
    lista_attesa: 0,
    mia_iscrizione: null,
    ...modifiche,
  };
}

export function pagina(
  elementi: Schemi["VoceCatalogo"][],
  totale = elementi.length,
): Schemi["PaginaCatalogo"] {
  return { elementi, totale, limite: 20, offset: 0 };
}

export function problema(stato: number, modifiche: Partial<Problema> = {}): HttpResponse<Problema> {
  return HttpResponse.json(
    { type: "about:blank", title: "Errore", status: stato, ...modifiche },
    { status: stato, headers: { "Content-Type": "application/problem+json" } },
  );
}

export const handlerPredefiniti = [
  http.get(`${API}/io`, () => HttpResponse.json(profiloDipendente)),
  http.get(`${API}/catalogo`, () => HttpResponse.json(pagina([voceCatalogo(1)]))),
];

export const server = setupServer(...handlerPredefiniti);
