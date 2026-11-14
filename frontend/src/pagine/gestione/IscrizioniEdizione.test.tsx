import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { Schemi } from "../../api/client";
import {
  API,
  conEtag,
  corsoLetto,
  edizioneLetta,
  iscrizioneLetta,
  pagina,
  problema,
  server,
  voceIscrizioneEdizione,
} from "../../test/server";
import { contaLettureCatalogo, SpiaCatalogo } from "../../test/catalogo";
import { mostra } from "../../test/render";
import { cancello, mostraSmontabile } from "../../test/smontaggio";
import { IscrizioniEdizione } from "./IscrizioniEdizione";

type Voce = Schemi["VoceIscrizioneEdizione"];

function pagina3(): void {
  mostra(
    <Routes>
      <Route path="/gestione/edizioni/:edizioneId" element={<IscrizioniEdizione />} />
    </Routes>,
    { percorso: "/gestione/edizioni/3" },
  );
}

/** Le iscrizioni dell'edizione 3; registra il filtro di stato di ogni lettura. */
function conIscrizioni(iniziali: Voce[]): { elenco: Voce[]; filtri: (string | null)[] } {
  const stato = { elenco: iniziali, filtri: [] as (string | null)[] };
  server.use(
    http.get(`${API}/edizioni/3`, () =>
      conEtag(edizioneLetta(3, { corso_id: 7, capienza: 2, posti_confermati: 1 }), 1),
    ),
    http.get(`${API}/corsi/7`, () => conEtag(corsoLetto(7, { titolo: "SQL" }), 1)),
    http.get(`${API}/edizioni/3/iscrizioni`, ({ request }) => {
      const filtro = new URL(request.url).searchParams.get("stato");
      stato.filtri.push(filtro);
      const elenco = stato.elenco.filter((v) => filtro === null || v.stato === filtro);
      return HttpResponse.json(pagina(elenco));
    }),
  );
  return stato;
}

describe("Iscrizioni dell'edizione", () => {
  it("elenca le iscrizioni con stato e posizione in lista d'attesa", async () => {
    conIscrizioni([
      voceIscrizioneEdizione(1, { stato: "Confermata" }),
      voceIscrizioneEdizione(2, {
        stato: "InAttesa",
        persona: { id: 2, nome: "Bruno Rete" },
        posizione_lista_attesa: 1,
      }),
    ]);

    pagina3();

    // Edizione e titolo del corso arrivano da due letture in sequenza.
    expect(await screen.findByText(/1\/2 posti confermati/)).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "SQL" }, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(screen.getByText("2 iscrizioni")).toBeInTheDocument();
    const righe = await screen.findAllByRole("row");
    expect(righe).toHaveLength(3);
    const bruno = within(righe[2] as HTMLElement);
    expect(bruno.getByText("In attesa")).toBeInTheDocument();
    expect(bruno.getByText("1ª in lista")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Conferma/ })).not.toBeInTheDocument();
  });

  it("«Da confermare» chiede all'API solo le Approvate", async () => {
    const stato = conIscrizioni([voceIscrizioneEdizione(1, { stato: "Confermata" })]);
    pagina3();
    await screen.findByText("Confermata");

    await userEvent.click(screen.getByText("Da confermare"));

    expect(
      await screen.findByText("Nessuna iscrizione approvata da confermare."),
    ).toBeInTheDocument();
    expect(stato.filtri).toEqual([null, "Approvata"]);
  });

  it("conferma un'Approvata: Confermata se c'è posto", async () => {
    const stato = conIscrizioni([voceIscrizioneEdizione(4)]);
    server.use(
      http.post(`${API}/iscrizioni/:id/conferma`, ({ params }) => {
        expect(params.id).toBe("4");
        stato.elenco = [voceIscrizioneEdizione(4, { stato: "Confermata" })];
        return HttpResponse.json(iscrizioneLetta(4, "Confermata"));
      }),
    );
    const catalogo = contaLettureCatalogo();
    mostra(
      <>
        <Routes>
          <Route path="/gestione/edizioni/:edizioneId" element={<IscrizioniEdizione />} />
        </Routes>
        <SpiaCatalogo />
      </>,
      { percorso: "/gestione/edizioni/3" },
    );
    await waitFor(() => {
      expect(catalogo.letture).toBe(1);
    });

    await userEvent.click(
      await screen.findByRole("button", { name: "Conferma l'iscrizione di Anna Dati" }),
    );

    expect(await screen.findByText("Iscrizione di Anna Dati confermata.")).toBeInTheDocument();
    expect(await screen.findByText("Confermata")).toBeInTheDocument();
    expect(screen.getByText("1 iscrizione")).toBeInTheDocument();
    // I posti liberi dell'edizione cambiano anche nel catalogo.
    await waitFor(() => {
      expect(catalogo.letture).toBe(2);
    });
  });

  it("l'esito della conferma si vede anche se il pulsante è già sparito", async () => {
    conIscrizioni([voceIscrizioneEdizione(4)]);
    const risposta = cancello();
    server.use(
      http.post(`${API}/iscrizioni/:id/conferma`, async () => {
        await risposta.attendi;
        return HttpResponse.json(iscrizioneLetta(4, "Confermata"));
      }),
    );
    mostraSmontabile(
      <IscrizioniEdizione />,
      "/gestione/edizioni/:edizioneId",
      "/gestione/edizioni/3",
    );

    await userEvent.click(
      await screen.findByRole("button", { name: "Conferma l'iscrizione di Anna Dati" }),
    );
    await userEvent.click(screen.getByRole("link", { name: "Altrove" }));
    risposta.apri();

    expect(await screen.findByText("Iscrizione di Anna Dati confermata.")).toBeInTheDocument();
  });

  it("senza posti l'iscrizione va in lista d'attesa e lo dice", async () => {
    conIscrizioni([voceIscrizioneEdizione(4)]);
    server.use(
      http.post(`${API}/iscrizioni/:id/conferma`, () =>
        HttpResponse.json(iscrizioneLetta(4, "InAttesa")),
      ),
    );
    pagina3();

    await userEvent.click(
      await screen.findByRole("button", { name: "Conferma l'iscrizione di Anna Dati" }),
    );

    expect(
      await screen.findByText("Posti esauriti: Anna Dati è in lista d'attesa."),
    ).toBeInTheDocument();
  });

  it("un 409 sulla conferma si vede con titolo e dettaglio", async () => {
    conIscrizioni([voceIscrizioneEdizione(4)]);
    server.use(
      http.post(`${API}/iscrizioni/:id/conferma`, () =>
        problema(409, { title: "Transizione non consentita", detail: "L'iscrizione è Annullata" }),
      ),
    );
    pagina3();

    await userEvent.click(
      await screen.findByRole("button", { name: "Conferma l'iscrizione di Anna Dati" }),
    );

    const avviso = await screen.findByRole("alert");
    expect(within(avviso).getByText("Transizione non consentita")).toBeInTheDocument();
    expect(within(avviso).getByText("L'iscrizione è Annullata")).toBeInTheDocument();
  });

  it("un'edizione inesistente mostra il 404", async () => {
    server.use(
      http.get(`${API}/edizioni/3`, () => problema(404, { title: "Risorsa inesistente" })),
      http.get(`${API}/edizioni/3/iscrizioni`, () =>
        problema(404, { title: "Risorsa inesistente" }),
      ),
    );
    pagina3();

    expect(await screen.findAllByText("Risorsa inesistente")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Iscrizioni dell'edizione" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Tutti i corsi" })).toHaveAttribute(
      "href",
      "/gestione",
    );
  });

  it("con un id non numerico nell'indirizzo non chiama l'API", async () => {
    mostra(
      <Routes>
        <Route path="/gestione/edizioni/:edizioneId" element={<IscrizioniEdizione />} />
      </Routes>,
      { percorso: "/gestione/edizioni/3x" },
    );

    expect(await screen.findByText("Pagina non trovata.")).toBeInTheDocument();
  });
});
