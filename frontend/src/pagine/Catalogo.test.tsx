import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { API, pagina, problema, server, voceCatalogo } from "../test/server";
import { mostra } from "../test/render";
import { Catalogo, PER_PAGINA } from "./Catalogo";

describe("Catalogo", () => {
  it("mostra le edizioni con posti liberi e la mia iscrizione", async () => {
    server.use(
      http.get(`${API}/catalogo`, () =>
        HttpResponse.json(
          pagina([
            voceCatalogo(1, { corso: { id: 1, titolo: "Python di base", durata_ore: 8 } }),
            voceCatalogo(2, {
              corso: { id: 2, titolo: "SQL avanzato", durata_ore: 16 },
              capienza: 5,
              posti_confermati: 4,
              lista_attesa: 2,
              mia_iscrizione: { stato: "InAttesa" },
            }),
          ]),
        ),
      ),
    );

    mostra(<Catalogo />);

    expect(screen.getByRole("status", { name: "Caricamento del catalogo" })).toBeInTheDocument();
    const righe = await screen.findAllByRole("row");
    expect(righe).toHaveLength(3); // intestazione + 2 edizioni
    const sql = within(righe[2] as HTMLElement);
    expect(sql.getByText("SQL avanzato")).toBeInTheDocument();
    expect(sql.getByText("1 libero su 5")).toBeInTheDocument();
    expect(sql.getByText("In attesa")).toBeInTheDocument();
    expect(
      within(righe[1] as HTMLElement).getByText("10 mar 2027 – 11 mar 2027"),
    ).toBeInTheDocument();
  });

  it("dice quando il catalogo è vuoto", async () => {
    server.use(http.get(`${API}/catalogo`, () => HttpResponse.json(pagina([]))));

    mostra(<Catalogo />);

    expect(await screen.findByText("Nessuna edizione in programma.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("mostra l'errore RFC 9457 e riprova", async () => {
    let chiamate = 0;
    server.use(
      http.get(`${API}/catalogo`, () => {
        chiamate += 1;
        return chiamate === 1
          ? problema(503, { title: "Servizio non disponibile", detail: "Riprova tra poco" })
          : HttpResponse.json(pagina([voceCatalogo(1)]));
      }),
    );

    mostra(<Catalogo />);

    const avviso = await screen.findByRole("alert");
    expect(within(avviso).getByText("Servizio non disponibile")).toBeInTheDocument();
    expect(within(avviso).getByText("Riprova tra poco")).toBeInTheDocument();

    await userEvent.click(within(avviso).getByRole("button", { name: "Riprova" }));

    expect(await screen.findByText("Corso 1")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("filtra per titolo e torna alla prima pagina", async () => {
    const richieste: URLSearchParams[] = [];
    server.use(
      http.get(`${API}/catalogo`, ({ request }) => {
        const parametri = new URL(request.url).searchParams;
        richieste.push(parametri);
        const titolo = parametri.get("titolo");
        return HttpResponse.json(
          titolo === null
            ? pagina([voceCatalogo(1)], PER_PAGINA * 3)
            : pagina([voceCatalogo(9, { corso: { id: 9, titolo: "Python", durata_ore: 4 } })]),
        );
      }),
    );
    const utente = userEvent.setup();
    mostra(<Catalogo />);

    await utente.click(await screen.findByRole("button", { name: "Pagina 2" }));
    await waitFor(() => {
      expect(richieste.at(-1)?.get("offset")).toBe(String(PER_PAGINA));
    });

    await utente.type(screen.getByLabelText("Cerca per titolo"), "  Python ");

    expect(await screen.findByText("Python")).toBeInTheDocument();
    const ultima = richieste.at(-1);
    expect(ultima?.get("titolo")).toBe("Python");
    expect(ultima?.get("offset")).toBe("0");
  });

  it("dice quando la ricerca non trova niente", async () => {
    server.use(
      http.get(`${API}/catalogo`, ({ request }) =>
        HttpResponse.json(
          new URL(request.url).searchParams.has("titolo") ? pagina([]) : pagina([voceCatalogo(1)]),
        ),
      ),
    );
    mostra(<Catalogo />);
    await screen.findByText("Corso 1");

    await userEvent.type(screen.getByLabelText("Cerca per titolo"), "Cobol");

    expect(await screen.findByText("Nessuna edizione per «Cobol».")).toBeInTheDocument();
  });
});
