import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Schemi } from "../api/client";
import { API, iscrizioneLetta, miaIscrizione, pagina, problema, server } from "../test/server";
import { mostra } from "../test/render";
import { MieIscrizioni } from "./MieIscrizioni";

type Voce = Schemi["VoceMiaIscrizione"];

/** Le mie iscrizioni servite da un elenco che le azioni possono cambiare. */
function conIscrizioni(iniziali: Voce[]): { elenco: Voce[] } {
  const stato = { elenco: iniziali };
  server.use(http.get(`${API}/iscrizioni`, () => HttpResponse.json(pagina(stato.elenco))));
  return stato;
}

describe("Le mie iscrizioni", () => {
  it("mostra corso, date, stato e posizione in lista d'attesa", async () => {
    conIscrizioni([
      miaIscrizione(1, { corso: { id: 1, titolo: "Python di base", durata_ore: 8 } }),
      miaIscrizione(2, {
        corso: { id: 2, titolo: "SQL avanzato", durata_ore: 16 },
        stato: "InAttesa",
        posizione_lista_attesa: 2,
      }),
    ]);

    mostra(<MieIscrizioni />);

    expect(
      screen.getByRole("status", { name: "Caricamento delle iscrizioni" }),
    ).toBeInTheDocument();
    const righe = await screen.findAllByRole("row");
    expect(righe).toHaveLength(3);
    const sql = within(righe[2] as HTMLElement);
    expect(sql.getByText("SQL avanzato")).toBeInTheDocument();
    expect(sql.getByText("In attesa")).toBeInTheDocument();
    expect(sql.getByText("2ª in lista")).toBeInTheDocument();
    expect(within(righe[1] as HTMLElement).getByText("Richiesta")).toBeInTheDocument();
  });

  it("senza iscrizioni rimanda al catalogo", async () => {
    mostra(<MieIscrizioni />);

    expect(
      await screen.findByText("Non hai ancora chiesto iscrizioni: le trovi nel catalogo."),
    ).toBeInTheDocument();
  });

  it("offre l'annullamento solo per le iscrizioni attive", async () => {
    conIscrizioni([
      miaIscrizione(1, { corso: { id: 1, titolo: "Attiva", durata_ore: 8 }, stato: "Confermata" }),
      miaIscrizione(2, { corso: { id: 2, titolo: "Chiusa", durata_ore: 8 }, stato: "Rifiutata" }),
      miaIscrizione(3, { corso: { id: 3, titolo: "Finita", durata_ore: 8 }, stato: "Completata" }),
    ]);

    mostra(<MieIscrizioni />);

    expect(
      await screen.findByRole("button", { name: "Annulla l'iscrizione a Attiva" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Annulla l'iscrizione a/ })).toHaveLength(1);
  });

  it("annulla dopo la conferma e rilegge l'elenco", async () => {
    const stato = conIscrizioni([miaIscrizione(7, { stato: "Confermata" })]);
    const annullate: string[] = [];
    server.use(
      http.post(`${API}/iscrizioni/:id/annullamento`, ({ params }) => {
        annullate.push(String(params.id));
        stato.elenco = [miaIscrizione(7, { stato: "Annullata" })];
        return HttpResponse.json(iscrizioneLetta(7, "Annullata"));
      }),
    );
    mostra(<MieIscrizioni />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Annulla l'iscrizione a Corso 7" }),
    );
    const finestra = await screen.findByRole("dialog", { name: "Annullare l'iscrizione?" });
    expect(within(finestra).getByText(/Il posto passa al primo della lista/)).toBeInTheDocument();
    expect(annullate).toEqual([]);
    await userEvent.click(within(finestra).getByRole("button", { name: "Annulla l'iscrizione" }));

    expect(await screen.findByText("Iscrizione a «Corso 7» annullata.")).toBeInTheDocument();
    expect(annullate).toEqual(["7"]);
    expect(await screen.findByText("Annullata")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Annulla l'iscrizione a/ }),
    ).not.toBeInTheDocument();
  });

  it("tornando indietro non annulla", async () => {
    conIscrizioni([miaIscrizione(7)]);
    mostra(<MieIscrizioni />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Annulla l'iscrizione a Corso 7" }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Indietro" }));

    // Nessun handler POST: una richiesta farebbe fallire il test (onUnhandledFrame).
    expect(
      screen.getByRole("button", { name: "Annulla l'iscrizione a Corso 7" }),
    ).toBeInTheDocument();
  });

  it("mostra il motivo del rifiuto dell'API (scadenza superata)", async () => {
    conIscrizioni([miaIscrizione(7, { stato: "Confermata" })]);
    server.use(
      http.post(`${API}/iscrizioni/:id/annullamento`, () =>
        problema(409, {
          type: "/problemi/scadenza-annullamento-superata",
          title: "Scadenza di annullamento superata",
          detail: "Mancano 2 giorni all'inizio: si annulla solo fino a 4 giorni prima",
        }),
      ),
    );
    mostra(<MieIscrizioni />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Annulla l'iscrizione a Corso 7" }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Annulla l'iscrizione" }));

    expect(await screen.findByText("Scadenza di annullamento superata")).toBeInTheDocument();
    expect(
      screen.getByText("Mancano 2 giorni all'inizio: si annulla solo fino a 4 giorni prima"),
    ).toBeInTheDocument();
  });
});
