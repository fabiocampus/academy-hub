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

export const profiloResponsabile: Schemi["Profilo"] = {
  ...profiloDipendente,
  persona_id: 2,
  nome: "Bruno Capo",
  email: "bruno@academy.example",
  ruoli: ["dipendente", "responsabile"],
  responsabile_di_team: true,
};

export const profiloAdmin: Schemi["Profilo"] = {
  ...profiloDipendente,
  persona_id: 3,
  nome: "Carla Academy",
  email: "carla@academy.example",
  ruoli: ["admin_academy"],
  responsabile_di_team: false,
};

export function miaIscrizione(
  id: number,
  modifiche: Partial<Schemi["VoceMiaIscrizione"]> = {},
): Schemi["VoceMiaIscrizione"] {
  return {
    id,
    persona_id: profiloDipendente.persona_id,
    edizione_id: id,
    stato: "Richiesta",
    richiesta_il: "2027-01-05T09:30:00Z",
    approvata_il: null,
    aggiornata_il: "2027-01-05T09:30:00Z",
    corso: { id: 100 + id, titolo: `Corso ${id}`, durata_ore: 8 },
    data_inizio: "2027-03-10",
    data_fine: "2027-03-11",
    posizione_lista_attesa: null,
    ...modifiche,
  };
}

export function richiestaDaApprovare(
  iscrizioneId: number,
  modifiche: Partial<Schemi["RichiestaDaApprovare"]> = {},
): Schemi["RichiestaDaApprovare"] {
  return {
    iscrizione_id: iscrizioneId,
    persona: { id: 1, nome: "Anna Dati" },
    edizione_id: iscrizioneId,
    corso: { id: 100 + iscrizioneId, titolo: `Corso ${iscrizioneId}`, durata_ore: 8 },
    data_inizio: "2027-03-10",
    richiesta_il: "2027-01-05T09:30:00Z",
    ...modifiche,
  };
}

/** L'iscrizione come la restituiscono i comandi (richiesta, approvazione, ...). */
export function iscrizioneLetta(
  id: number,
  stato: Schemi["StatoIscrizione"],
): Schemi["IscrizioneLetta"] {
  return {
    id,
    persona_id: profiloDipendente.persona_id,
    edizione_id: id,
    stato,
    richiesta_il: "2027-01-05T09:30:00Z",
    approvata_il: null,
    aggiornata_il: "2027-01-05T09:30:00Z",
  };
}

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

export function corsoLetto(
  id: number,
  modifiche: Partial<Schemi["CorsoLetto"]> = {},
): Schemi["CorsoLetto"] {
  return {
    id,
    titolo: `Corso ${String(id)}`,
    descrizione: "",
    durata_ore: 8,
    archiviato_il: null,
    ...modifiche,
  };
}

export function edizioneLetta(
  id: number,
  modifiche: Partial<Schemi["EdizioneLetta"]> = {},
): Schemi["EdizioneLetta"] {
  return {
    id,
    corso_id: 7,
    data_inizio: "2099-03-10",
    data_fine: "2099-03-11",
    capienza: 10,
    posti_confermati: 0,
    docente_id: null,
    cancellata_il: null,
    ...modifiche,
  };
}

export function voceEdizione(
  id: number,
  modifiche: Partial<Schemi["VoceEdizione"]> = {},
): Schemi["VoceEdizione"] {
  return { ...edizioneLetta(id), lista_attesa: 0, ...modifiche };
}

export function voceIscrizioneEdizione(
  id: number,
  modifiche: Partial<Schemi["VoceIscrizioneEdizione"]> = {},
): Schemi["VoceIscrizioneEdizione"] {
  return {
    ...iscrizioneLetta(id, "Approvata"),
    persona: { id: 1, nome: "Anna Dati" },
    posizione_lista_attesa: null,
    ...modifiche,
  };
}

/** Risposta JSON con l'ETag della versione, come le GET di corso ed edizione. */
export function conEtag<T extends object>(corpo: T, versione: number): HttpResponse<T> {
  return HttpResponse.json(corpo, { headers: { ETag: `"${String(versione)}"` } });
}

export function pagina<T>(
  elementi: T[],
  totale = elementi.length,
): { elementi: T[]; totale: number; limite: number; offset: number } {
  return { elementi, totale, limite: 20, offset: 0 };
}

export function problema(stato: number, modifiche: Partial<Problema> = {}): HttpResponse<Problema> {
  return HttpResponse.json(
    { type: "about:blank", title: "Errore", status: stato, ...modifiche },
    { status: stato, headers: { "Content-Type": "application/problem+json" } },
  );
}

export const handlerPredefiniti = [
  http.get(`${API}/docenti`, () =>
    HttpResponse.json<Schemi["PersonaInBreve"][]>([{ id: 50, nome: "Dora Docente" }]),
  ),
  http.get(`${API}/io`, () => HttpResponse.json(profiloDipendente)),
  http.get(`${API}/catalogo`, () => HttpResponse.json(pagina([voceCatalogo(1)]))),
  http.get(`${API}/iscrizioni`, () => HttpResponse.json(pagina<Schemi["VoceMiaIscrizione"]>([]))),
  http.get(`${API}/richieste-da-approvare`, () =>
    HttpResponse.json(pagina<Schemi["RichiestaDaApprovare"]>([])),
  ),
];

export const server = setupServer(...handlerPredefiniti);
