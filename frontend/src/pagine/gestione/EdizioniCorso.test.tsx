import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { Problema, Schemi } from "../../api/client";
import {
  API,
  conEtag,
  corsoLetto,
  edizioneLetta,
  pagina,
  problema,
  server,
  voceEdizione,
} from "../../test/server";
import { mostra } from "../../test/render";
import { EdizioniCorso } from "./EdizioniCorso";

type Voce = Schemi["VoceEdizione"];

function pagina7(): void {
  mostra(
    <Routes>
      <Route path="/gestione/corsi/:corsoId" element={<EdizioniCorso />} />
    </Routes>,
    { percorso: "/gestione/corsi/7" },
  );
}

function conEdizioni(
  iniziali: Voce[],
  corso: Schemi["CorsoLetto"] = corsoLetto(7, { titolo: "SQL" }),
): { elenco: Voce[] } {
  const stato = { elenco: iniziali };
  server.use(
    http.get(`${API}/corsi/7`, () => conEtag(corso, 1)),
    http.get(`${API}/corsi/7/edizioni`, () => HttpResponse.json(pagina(stato.elenco))),
    http.get<{ id: string }, never, Voce | Problema>(`${API}/edizioni/:id`, ({ params }) => {
      const voce = stato.elenco.find((v) => String(v.id) === params.id);
      return voce === undefined ? problema(404) : conEtag(voce, 2);
    }),
  );
  return stato;
}

describe("Edizioni del corso", () => {
  it("elenca le edizioni con posti, lista d'attesa, docente e stato", async () => {
    conEdizioni([
      voceEdizione(1, { posti_confermati: 3, lista_attesa: 2, docente_id: 50 }),
      voceEdizione(2, { cancellata_il: "2027-01-05T09:30:00Z" }),
      voceEdizione(3, { data_inizio: "2020-01-10", data_fine: "2020-01-11" }),
    ]);

    pagina7();

    expect(await screen.findByRole("heading", { name: "SQL" })).toBeInTheDocument();
    const righe = await screen.findAllByRole("row");
    expect(righe).toHaveLength(4);
    const prima = within(righe[1] as HTMLElement);
    expect(prima.getByText("3/10 confermati")).toBeInTheDocument();
    expect(prima.getByText("2")).toBeInTheDocument();
    expect(await prima.findByText("Dora Docente")).toBeInTheDocument();
    expect(prima.getByText("In programma")).toBeInTheDocument();
    expect(prima.getByRole("link", { name: /Iscrizioni dell'edizione/ })).toHaveAttribute(
      "href",
      "/gestione/edizioni/1",
    );
    const cancellata = within(righe[2] as HTMLElement);
    expect(cancellata.getByText("Cancellata")).toBeInTheDocument();
    expect(cancellata.queryByRole("button")).not.toBeInTheDocument();
    const passata = within(righe[3] as HTMLElement);
    expect(passata.getByText("Iniziata")).toBeInTheDocument();
    expect(passata.queryByRole("button")).not.toBeInTheDocument();
  });

  it("senza edizioni lo dice; un corso archiviato non ne accetta di nuove", async () => {
    conEdizioni([], corsoLetto(7, { titolo: "SQL", archiviato_il: "2027-01-05T09:30:00Z" }));

    pagina7();

    expect(await screen.findByText("Nessuna edizione di questo corso.")).toBeInTheDocument();
    expect(screen.getByText(/corso archiviato/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nuova edizione" })).not.toBeInTheDocument();
  });

  it("la pianificazione controlla le date prima di chiamare l'API", async () => {
    conEdizioni([]);
    pagina7();

    await userEvent.click(await screen.findByRole("button", { name: "Nuova edizione" }));
    const finestra = await screen.findByRole("dialog", { name: "Nuova edizione" });
    await userEvent.type(within(finestra).getByLabelText(/Inizio/), "2099-03-10");
    await userEvent.type(within(finestra).getByLabelText(/Fine/), "2099-03-09");
    await userEvent.type(within(finestra).getByRole("textbox", { name: /Capienza/ }), "12");
    await userEvent.click(within(finestra).getByRole("button", { name: "Pianifica" }));

    expect(
      await within(finestra).findByText("La fine non può precedere l'inizio."),
    ).toBeInTheDocument();
  });

  it("pianifica un'edizione con il docente scelto", async () => {
    const stato = conEdizioni([]);
    const corpi: unknown[] = [];
    server.use(
      http.post(`${API}/edizioni`, async ({ request }) => {
        const corpo = (await request.json()) as Schemi["NuovaEdizione"];
        corpi.push(corpo);
        stato.elenco = [voceEdizione(5, { ...corpo })];
        return HttpResponse.json(edizioneLetta(5, { ...corpo }), { status: 201 });
      }),
    );
    pagina7();

    await userEvent.click(await screen.findByRole("button", { name: "Nuova edizione" }));
    const finestra = await screen.findByRole("dialog");
    await userEvent.type(within(finestra).getByLabelText(/Inizio/), "2099-03-10");
    await userEvent.type(within(finestra).getByLabelText(/Fine/), "2099-03-11");
    await userEvent.type(within(finestra).getByRole("textbox", { name: /Capienza/ }), "12");
    await userEvent.click(within(finestra).getByLabelText("Docente"));
    // In jsdom la tendina resta `display: none` (transizione di Mantine): l'opzione c'è.
    await userEvent.click(
      await screen.findByRole("option", { name: "Dora Docente", hidden: true }),
    );
    await userEvent.click(within(finestra).getByRole("button", { name: "Pianifica" }));

    expect(await screen.findByText(/^Edizione .* pianificata\.$/)).toBeInTheDocument();
    expect(corpi).toEqual([
      {
        corso_id: 7,
        data_inizio: "2099-03-10",
        data_fine: "2099-03-11",
        capienza: 12,
        docente_id: 50,
      },
    ]);
    expect(await screen.findByText("0/12 confermati")).toBeInTheDocument();
  });

  it("in modifica la capienza non scende sotto i posti confermati", async () => {
    conEdizioni([voceEdizione(1, { posti_confermati: 6 })]);
    pagina7();

    await userEvent.click(await screen.findByRole("button", { name: /Modifica l'edizione/ }));
    const finestra = await screen.findByRole("dialog", { name: "Modifica dell'edizione" });
    const capienza = await within(finestra).findByRole("textbox", { name: /Capienza/ });
    await userEvent.clear(capienza);
    await userEvent.type(capienza, "5");
    await userEvent.click(within(finestra).getByRole("button", { name: "Salva" }));

    expect(
      await within(finestra).findByText("Da 6 (posti già confermati) a 10000."),
    ).toBeInTheDocument();
  });

  it("la modifica manda l'ETag e toglie il docente con null", async () => {
    conEdizioni([voceEdizione(1, { docente_id: 50 })]);
    const chiamate: { ifMatch: string | null; corpo: unknown }[] = [];
    server.use(
      http.patch(`${API}/edizioni/:id`, async ({ request }) => {
        chiamate.push({ ifMatch: request.headers.get("If-Match"), corpo: await request.json() });
        return HttpResponse.json(edizioneLetta(1));
      }),
    );
    pagina7();

    await userEvent.click(await screen.findByRole("button", { name: /Modifica l'edizione/ }));
    const finestra = await screen.findByRole("dialog");
    const docente = await within(finestra).findByLabelText("Docente");
    await waitFor(() => {
      expect(docente).toHaveValue("Dora Docente");
    });
    await userEvent.click(docente);
    await userEvent.click(
      await screen.findByRole("option", { name: "Nessun docente", hidden: true }),
    );
    await userEvent.click(within(finestra).getByRole("button", { name: "Salva" }));

    expect(await screen.findByText(/^Edizione .* modificata\.$/)).toBeInTheDocument();
    expect(chiamate).toEqual([{ ifMatch: '"2"', corpo: { docente_id: null } }]);
  });

  it("la cancellazione chiede conferma; un 409 si vede con il dettaglio", async () => {
    conEdizioni([voceEdizione(1)]);
    server.use(
      http.post(`${API}/edizioni/:id/cancellazione`, () =>
        problema(409, {
          type: "/problemi/edizione-iniziata",
          title: "Edizione già iniziata",
          detail: "L'edizione 1 è già iniziata",
        }),
      ),
    );
    pagina7();

    await userEvent.click(await screen.findByRole("button", { name: /Cancella l'edizione/ }));
    const finestra = await screen.findByRole("dialog", { name: "Cancellare l'edizione?" });
    expect(within(finestra).getByText(/diventano\s+Annullata/)).toBeInTheDocument();
    await userEvent.click(within(finestra).getByRole("button", { name: "Cancella l'edizione" }));

    expect(await screen.findByText("L'edizione 1 è già iniziata")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("cancella l'edizione e aggiorna l'elenco", async () => {
    const stato = conEdizioni([voceEdizione(1)]);
    server.use(
      http.post(`${API}/edizioni/:id/cancellazione`, ({ params }) => {
        expect(params.id).toBe("1");
        stato.elenco = [voceEdizione(1, { cancellata_il: "2027-01-05T09:30:00Z" })];
        return HttpResponse.json(edizioneLetta(1, { cancellata_il: "2027-01-05T09:30:00Z" }));
      }),
    );
    pagina7();

    await userEvent.click(await screen.findByRole("button", { name: /Cancella l'edizione/ }));
    const finestra = await screen.findByRole("dialog");
    await userEvent.click(within(finestra).getByRole("button", { name: "Cancella l'edizione" }));

    expect(await screen.findByText(/^Edizione .* cancellata\.$/)).toBeInTheDocument();
    expect(await screen.findByText("Cancellata")).toBeInTheDocument();
  });
});
