import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Problema, Schemi } from "../../api/client";
import { API, conEtag, corsoLetto, pagina, problema, server } from "../../test/server";
import { mostra } from "../../test/render";
import { Corsi } from "./Corsi";

type Corso = Schemi["CorsoLetto"];

/** Elenco dei corsi e lettura del singolo corso (con ETag), sullo stesso stato. */
function conCorsi(iniziali: Corso[], versione = 1): { elenco: Corso[]; versione: number } {
  const stato = { elenco: iniziali, versione };
  server.use(
    http.get(`${API}/corsi`, () => HttpResponse.json(pagina(stato.elenco))),
    http.get<{ id: string }, never, Corso | Problema>(`${API}/corsi/:id`, ({ params }) => {
      const corso = stato.elenco.find((c) => String(c.id) === params.id);
      return corso === undefined ? problema(404) : conEtag(corso, stato.versione);
    }),
  );
  return stato;
}

describe("Gestione corsi", () => {
  it("elenca i corsi, archiviati compresi, con il collegamento alle edizioni", async () => {
    conCorsi([
      corsoLetto(1, { titolo: "Python" }),
      corsoLetto(2, { titolo: "Analisi", archiviato_il: "2027-01-05T09:30:00Z" }),
    ]);

    mostra(<Corsi />);

    const righe = await screen.findAllByRole("row");
    expect(righe).toHaveLength(3);
    const python = within(righe[1] as HTMLElement);
    expect(python.getByRole("link", { name: "Python" })).toHaveAttribute(
      "href",
      "/gestione/corsi/1",
    );
    expect(python.getByText("Attivo")).toBeInTheDocument();
    const analisi = within(righe[2] as HTMLElement);
    expect(analisi.getByText("Archiviato")).toBeInTheDocument();
    expect(analisi.queryByRole("button", { name: /Archivia/ })).not.toBeInTheDocument();
  });

  it("senza corsi lo dice", async () => {
    conCorsi([]);

    mostra(<Corsi />);

    expect(await screen.findByText("Nessun corso: creane uno.")).toBeInTheDocument();
  });

  it("la creazione valida i campi prima di chiamare l'API", async () => {
    conCorsi([]);
    mostra(<Corsi />);

    await userEvent.click(await screen.findByRole("button", { name: "Nuovo corso" }));
    const finestra = await screen.findByRole("dialog", { name: "Nuovo corso" });
    await userEvent.type(within(finestra).getByRole("textbox", { name: /Titolo/ }), "   ");
    await userEvent.click(within(finestra).getByRole("button", { name: "Crea il corso" }));

    // Nessun handler POST: una chiamata farebbe fallire il test.
    expect(await within(finestra).findByText("Scrivi il titolo.")).toBeInTheDocument();
    expect(within(finestra).getByText(/Un numero intero di ore/)).toBeInTheDocument();
  });

  it("crea un corso e lo mostra nell'elenco", async () => {
    const stato = conCorsi([]);
    const corpi: unknown[] = [];
    server.use(
      http.post(`${API}/corsi`, async ({ request }) => {
        const corpo = (await request.json()) as Schemi["NuovoCorso"];
        corpi.push(corpo);
        const creato = corsoLetto(9, corpo);
        stato.elenco = [creato];
        return HttpResponse.json(creato, { status: 201 });
      }),
    );
    mostra(<Corsi />);

    await userEvent.click(await screen.findByRole("button", { name: "Nuovo corso" }));
    const finestra = await screen.findByRole("dialog");
    await userEvent.type(within(finestra).getByRole("textbox", { name: /Titolo/ }), " SQL ");
    await userEvent.type(within(finestra).getByRole("textbox", { name: /Durata/ }), "8");
    await userEvent.click(within(finestra).getByRole("button", { name: "Crea il corso" }));

    expect(await screen.findByText("Corso «SQL» creato.")).toBeInTheDocument();
    expect(corpi).toEqual([{ titolo: "SQL", descrizione: "", durata_ore: 8 }]);
    expect(await screen.findByRole("link", { name: "SQL" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("un 422 dell'API va sul campo", async () => {
    conCorsi([]);
    server.use(
      http.post(`${API}/corsi`, () =>
        problema(422, {
          type: "/problemi/dati-non-validi",
          title: "Dati non validi",
          errori: [{ campo: "titolo", messaggio: "Titolo già usato" }],
        }),
      ),
    );
    mostra(<Corsi />);

    await userEvent.click(await screen.findByRole("button", { name: "Nuovo corso" }));
    const finestra = await screen.findByRole("dialog");
    await userEvent.type(within(finestra).getByRole("textbox", { name: /Titolo/ }), "SQL");
    await userEvent.type(within(finestra).getByRole("textbox", { name: /Durata/ }), "8");
    await userEvent.click(within(finestra).getByRole("button", { name: "Crea il corso" }));

    expect(await within(finestra).findByText("Titolo già usato")).toBeInTheDocument();
  });

  it("la modifica manda l'ETag letto e solo i campi cambiati", async () => {
    conCorsi([corsoLetto(1, { titolo: "Python", descrizione: "Base" })], 3);
    const chiamate: { ifMatch: string | null; corpo: unknown }[] = [];
    server.use(
      http.patch(`${API}/corsi/:id`, async ({ request }) => {
        chiamate.push({ ifMatch: request.headers.get("If-Match"), corpo: await request.json() });
        return HttpResponse.json(corsoLetto(1, { titolo: "Python avanzato" }));
      }),
    );
    mostra(<Corsi />);

    await userEvent.click(await screen.findByRole("button", { name: "Modifica Python" }));
    const finestra = await screen.findByRole("dialog", { name: "Modifica del corso" });
    const titolo = await within(finestra).findByRole("textbox", { name: /Titolo/ });
    await userEvent.type(titolo, " avanzato");
    await userEvent.click(within(finestra).getByRole("button", { name: "Salva" }));

    expect(await screen.findByText("Corso «Python avanzato» modificato.")).toBeInTheDocument();
    expect(chiamate).toEqual([{ ifMatch: '"3"', corpo: { titolo: "Python avanzato" } }]);
  });

  it("con un 412 mostra il problema e «Ricarica i dati» riparte dalla versione nuova", async () => {
    const stato = conCorsi([corsoLetto(1, { titolo: "Python" })], 1);
    const etag: (string | null)[] = [];
    server.use(
      http.patch(`${API}/corsi/:id`, ({ request }) => {
        etag.push(request.headers.get("If-Match"));
        if (etag.length === 1) {
          // Qualcun altro ha modificato il corso dopo la nostra lettura.
          stato.elenco = [corsoLetto(1, { titolo: "Python 3" })];
          stato.versione = 2;
          return problema(412, {
            type: "/problemi/versione-non-corrispondente",
            title: "La risorsa è stata modificata da qualcun altro",
            detail: "Versione attesa 1, attuale 2",
          });
        }
        return HttpResponse.json(corsoLetto(1, { titolo: "Python 3", durata_ore: 12 }));
      }),
    );
    mostra(<Corsi />);

    await userEvent.click(await screen.findByRole("button", { name: "Modifica Python" }));
    const finestra = await screen.findByRole("dialog");
    const durata = await within(finestra).findByRole("textbox", { name: /Durata/ });
    await userEvent.clear(durata);
    await userEvent.type(durata, "12");
    await userEvent.click(within(finestra).getByRole("button", { name: "Salva" }));

    const avviso = await within(finestra).findByRole("alert");
    expect(
      within(avviso).getByText("La risorsa è stata modificata da qualcun altro"),
    ).toBeInTheDocument();
    // Il form resta com'era finché non si ricarica: niente si perde in silenzio.
    expect(within(finestra).getByRole("textbox", { name: /Titolo/ })).toHaveValue("Python");

    await userEvent.click(within(avviso).getByRole("button", { name: "Ricarica i dati" }));
    await waitFor(() => {
      expect(within(finestra).getByRole("textbox", { name: /Titolo/ })).toHaveValue("Python 3");
    });
    expect(within(finestra).queryByRole("alert")).not.toBeInTheDocument();
    const nuovaDurata = within(finestra).getByRole("textbox", { name: /Durata/ });
    await userEvent.clear(nuovaDurata);
    await userEvent.type(nuovaDurata, "12");
    await userEvent.click(within(finestra).getByRole("button", { name: "Salva" }));

    expect(await screen.findByText("Corso «Python 3» modificato.")).toBeInTheDocument();
    expect(etag).toEqual(['"1"', '"2"']);
  });

  it("l'archiviazione chiede conferma e manda l'ETag", async () => {
    const stato = conCorsi([corsoLetto(1, { titolo: "Python" })], 4);
    const etag: (string | null)[] = [];
    server.use(
      http.post(`${API}/corsi/:id/archiviazione`, ({ request }) => {
        etag.push(request.headers.get("If-Match"));
        const archiviato = corsoLetto(1, {
          titolo: "Python",
          archiviato_il: "2027-01-05T09:30:00Z",
        });
        stato.elenco = [archiviato];
        return HttpResponse.json(archiviato);
      }),
    );
    mostra(<Corsi />);

    await userEvent.click(await screen.findByRole("button", { name: "Archivia Python" }));
    const finestra = await screen.findByRole("dialog", { name: "Archiviare il corso?" });
    const conferma = within(finestra).getByRole("button", { name: "Archivia il corso" });
    await waitFor(() => {
      expect(conferma).toBeEnabled();
    });
    await userEvent.click(conferma);

    expect(await screen.findByText("Corso «Python» archiviato.")).toBeInTheDocument();
    expect(etag).toEqual(['"4"']);
    expect(await screen.findByText("Archiviato")).toBeInTheDocument();
  });

  it("anche con il pulsante visibile, l'API può rifiutare: si vede il 403", async () => {
    // La voce «Gestione» è solo comodità: la matrice del backend dice chi può.
    conCorsi([]);
    server.use(
      http.post(`${API}/corsi`, () =>
        problema(403, {
          type: "/problemi/azione-non-consentita",
          title: "Azione non consentita al tuo ruolo",
          detail: "Serve il ruolo admin_academy",
        }),
      ),
    );
    mostra(<Corsi />);

    await userEvent.click(await screen.findByRole("button", { name: "Nuovo corso" }));
    const finestra = await screen.findByRole("dialog");
    await userEvent.type(within(finestra).getByRole("textbox", { name: /Titolo/ }), "SQL");
    await userEvent.type(within(finestra).getByRole("textbox", { name: /Durata/ }), "8");
    await userEvent.click(within(finestra).getByRole("button", { name: "Crea il corso" }));

    const avviso = await within(finestra).findByRole("alert");
    expect(within(avviso).getByText("Serve il ruolo admin_academy")).toBeInTheDocument();
  });

  it("mostra l'errore dell'elenco, con «Riprova»", async () => {
    let chiamate = 0;
    server.use(
      http.get(`${API}/corsi`, () => {
        chiamate += 1;
        return chiamate === 1
          ? problema(500, { title: "Errore interno" })
          : HttpResponse.json(pagina([corsoLetto(1)]));
      }),
    );
    mostra(<Corsi />);

    expect(screen.getByRole("status", { name: "Caricamento dei corsi" })).toBeInTheDocument();
    expect(await screen.findByText("Errore interno")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Riprova" }));

    expect(await screen.findByRole("link", { name: "Corso 1" })).toBeInTheDocument();
  });
});
