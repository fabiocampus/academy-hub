import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Schemi } from "../api/client";
import {
  API,
  iscrizioneLetta,
  pagina,
  problema,
  richiestaDaApprovare,
  server,
} from "../test/server";
import { mostra } from "../test/render";
import { cancello, mostraSmontabile } from "../test/smontaggio";
import { Approvazioni, MOTIVO_MASSIMO } from "./Approvazioni";

type Richiesta = Schemi["RichiestaDaApprovare"];

function conRichieste(iniziali: Richiesta[]): { elenco: Richiesta[] } {
  const stato = { elenco: iniziali };
  server.use(
    http.get(`${API}/richieste-da-approvare`, () => HttpResponse.json(pagina(stato.elenco))),
  );
  return stato;
}

const RIFIUTA = "Rifiuta la richiesta di Anna Dati per Corso 4";
const APPROVA = "Approva la richiesta di Anna Dati per Corso 4";

describe("Approvazioni", () => {
  it("elenca le richieste da decidere", async () => {
    conRichieste([
      richiestaDaApprovare(4),
      richiestaDaApprovare(5, { persona: { id: 9, nome: "Dario Rete" } }),
    ]);

    mostra(<Approvazioni />);

    const righe = await screen.findAllByRole("row");
    expect(righe).toHaveLength(3);
    const dario = within(righe[2] as HTMLElement);
    expect(dario.getByText("Dario Rete")).toBeInTheDocument();
    expect(dario.getByText("Corso 5")).toBeInTheDocument();
    expect(dario.getByText("10 mar 2027")).toBeInTheDocument();
    // 09:30 UTC di gennaio = 10:30 a Roma.
    expect(dario.getByText(/5 gen 2027.*10:30/)).toBeInTheDocument();
  });

  it("senza richieste lo dice", async () => {
    mostra(<Approvazioni />);

    expect(await screen.findByText("Nessuna richiesta da decidere.")).toBeInTheDocument();
  });

  it("approva e toglie la richiesta dall'elenco", async () => {
    const stato = conRichieste([richiestaDaApprovare(4)]);
    server.use(
      http.post(`${API}/iscrizioni/:id/approvazione`, ({ params }) => {
        expect(params.id).toBe("4");
        stato.elenco = [];
        return HttpResponse.json(iscrizioneLetta(4, "Approvata"));
      }),
    );
    mostra(<Approvazioni />);

    await userEvent.click(await screen.findByRole("button", { name: APPROVA }));

    expect(await screen.findByText("Richiesta di Anna Dati approvata.")).toBeInTheDocument();
    expect(await screen.findByText("Nessuna richiesta da decidere.")).toBeInTheDocument();
  });

  it("l'esito dell'approvazione si vede anche se la riga è già sparita", async () => {
    conRichieste([richiestaDaApprovare(4)]);
    const risposta = cancello();
    server.use(
      http.post(`${API}/iscrizioni/:id/approvazione`, async () => {
        await risposta.attendi;
        return HttpResponse.json(iscrizioneLetta(4, "Approvata"));
      }),
    );
    mostraSmontabile(<Approvazioni />);

    await userEvent.click(await screen.findByRole("button", { name: APPROVA }));
    await userEvent.click(screen.getByRole("link", { name: "Altrove" }));
    risposta.apri();

    expect(await screen.findByText("Richiesta di Anna Dati approvata.")).toBeInTheDocument();
  });

  it("anche con il pulsante visibile, l'API può rifiutare l'azione: si vede il 403", async () => {
    // Il menu è solo comodità: chi decide lo verifica il server (R2, matrice di
    // autorizzazione del backend). Qui la persona non è più il responsabile diretto.
    conRichieste([richiestaDaApprovare(4)]);
    server.use(
      http.post(`${API}/iscrizioni/:id/approvazione`, () =>
        problema(403, {
          type: "/problemi/azione-non-consentita",
          title: "Azione non consentita al tuo ruolo",
          detail: "Decide il responsabile diretto della persona",
        }),
      ),
    );
    mostra(<Approvazioni />);

    await userEvent.click(await screen.findByRole("button", { name: APPROVA }));

    const avviso = await screen.findByRole("alert");
    expect(within(avviso).getByText("Azione non consentita al tuo ruolo")).toBeInTheDocument();
    expect(
      within(avviso).getByText("Decide il responsabile diretto della persona"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/approvata\.$/)).not.toBeInTheDocument();
  });

  it("il rifiuto chiede un motivo prima di chiamare l'API", async () => {
    conRichieste([richiestaDaApprovare(4)]);
    mostra(<Approvazioni />);

    await userEvent.click(await screen.findByRole("button", { name: RIFIUTA }));
    const finestra = await screen.findByRole("dialog", { name: "Rifiutare la richiesta?" });
    await userEvent.type(within(finestra).getByRole("textbox", { name: /Motivo/ }), "   ");
    await userEvent.click(within(finestra).getByRole("button", { name: "Rifiuta" }));

    // Nessun handler POST: una chiamata farebbe fallire il test.
    expect(
      await within(finestra).findByText("Scrivi il motivo: lo legge chi ha chiesto l'iscrizione."),
    ).toBeInTheDocument();
    expect(within(finestra).getByRole("textbox", { name: /Motivo/ })).toHaveAttribute(
      "maxlength",
      String(MOTIVO_MASSIMO),
    );
  });

  it("rifiuta con il motivo senza spazi ai lati", async () => {
    const stato = conRichieste([richiestaDaApprovare(4)]);
    const motivi: unknown[] = [];
    server.use(
      http.post(`${API}/iscrizioni/:id/rifiuto`, async ({ request }) => {
        motivi.push(await request.json());
        stato.elenco = [];
        return HttpResponse.json(iscrizioneLetta(4, "Rifiutata"));
      }),
    );
    mostra(<Approvazioni />);

    await userEvent.click(await screen.findByRole("button", { name: RIFIUTA }));
    const finestra = await screen.findByRole("dialog");
    await userEvent.type(
      within(finestra).getByRole("textbox", { name: /Motivo/ }),
      "  Budget esaurito ",
    );
    await userEvent.click(within(finestra).getByRole("button", { name: "Rifiuta" }));

    expect(await screen.findByText("Richiesta di Anna Dati rifiutata.")).toBeInTheDocument();
    expect(motivi).toEqual([{ motivo: "Budget esaurito" }]);
    expect(await screen.findByText("Nessuna richiesta da decidere.")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("un 422 sul motivo resta nel form", async () => {
    conRichieste([richiestaDaApprovare(4)]);
    server.use(
      http.post(`${API}/iscrizioni/:id/rifiuto`, () =>
        problema(422, {
          type: "/problemi/dati-non-validi",
          title: "Dati non validi",
          errori: [{ campo: "motivo", messaggio: "String should have at most 1000 characters" }],
        }),
      ),
    );
    mostra(<Approvazioni />);

    await userEvent.click(await screen.findByRole("button", { name: RIFIUTA }));
    const finestra = await screen.findByRole("dialog");
    await userEvent.type(within(finestra).getByRole("textbox", { name: /Motivo/ }), "Troppo lungo");
    await userEvent.click(within(finestra).getByRole("button", { name: "Rifiuta" }));

    expect(
      await within(finestra).findByText("String should have at most 1000 characters"),
    ).toBeInTheDocument();
  });

  it("mostra il caricamento e poi l'errore dell'elenco, con «Riprova»", async () => {
    let chiamate = 0;
    server.use(
      http.get(`${API}/richieste-da-approvare`, () => {
        chiamate += 1;
        return chiamate === 1
          ? problema(500, { title: "Errore interno" })
          : HttpResponse.json(pagina([richiestaDaApprovare(4)]));
      }),
    );
    mostra(<Approvazioni />);

    expect(screen.getByRole("status", { name: "Caricamento delle richieste" })).toBeInTheDocument();
    expect(await screen.findByText("Errore interno")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Riprova" }));

    expect(await screen.findByRole("button", { name: APPROVA })).toBeInTheDocument();
  });

  it("due approvazioni di fila hanno ciascuna il proprio esito", async () => {
    conRichieste([richiestaDaApprovare(4), richiestaDaApprovare(5)]);
    server.use(
      http.post(`${API}/iscrizioni/:id/approvazione`, ({ params }) =>
        params.id === "4"
          ? problema(409, { title: "Conflitto con lo stato attuale", detail: "Già decisa" })
          : HttpResponse.json(iscrizioneLetta(5, "Approvata")),
      ),
    );
    mostra(<Approvazioni />);

    await userEvent.click(await screen.findByRole("button", { name: APPROVA }));
    await userEvent.click(
      screen.getByRole("button", { name: "Approva la richiesta di Anna Dati per Corso 5" }),
    );

    expect(await screen.findByText("Già decisa")).toBeInTheDocument();
    expect(await screen.findByText("Richiesta di Anna Dati approvata.")).toBeInTheDocument();
  });

  it("finestra e notifiche si chiudono con un pulsante che ha un nome", async () => {
    conRichieste([richiestaDaApprovare(4)]);
    mostra(<Approvazioni />);

    await userEvent.click(await screen.findByRole("button", { name: RIFIUTA }));
    const finestra = await screen.findByRole("dialog");
    await userEvent.click(within(finestra).getByRole("button", { name: "Chiudi" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});
