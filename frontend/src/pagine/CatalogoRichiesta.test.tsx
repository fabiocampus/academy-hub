/** US-04 dal catalogo: richiesta d'iscrizione idempotente (ADR-0006). */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Schemi } from "../api/client";
import {
  API,
  iscrizioneLetta,
  pagina,
  problema,
  profiloAdmin,
  server,
  voceCatalogo,
} from "../test/server";
import { mostra } from "../test/render";
import { Catalogo } from "./Catalogo";

const ISCRIVITI = "Iscriviti a Corso 1 dal 10 mar 2027 – 11 mar 2027";

function conCatalogo(iniziale: Schemi["VoceCatalogo"][]): { elenco: Schemi["VoceCatalogo"][] } {
  const stato = { elenco: iniziale };
  server.use(http.get(`${API}/catalogo`, () => HttpResponse.json(pagina(stato.elenco))));
  return stato;
}

describe("Richiesta d'iscrizione dal catalogo", () => {
  it("manda la richiesta con una chiave d'idempotenza e mostra il nuovo stato", async () => {
    const stato = conCatalogo([voceCatalogo(1)]);
    const chiavi: (string | null)[] = [];
    const corpi: unknown[] = [];
    server.use(
      http.post(`${API}/iscrizioni`, async ({ request }) => {
        chiavi.push(request.headers.get("Idempotency-Key"));
        corpi.push(await request.json());
        stato.elenco = [voceCatalogo(1, { mia_iscrizione: { stato: "Richiesta" } })];
        return HttpResponse.json(iscrizioneLetta(1, "Richiesta"), { status: 201 });
      }),
    );
    mostra(<Catalogo />);

    await userEvent.click(await screen.findByRole("button", { name: ISCRIVITI }));

    expect(await screen.findByText("Richiesta inviata per «Corso 1».")).toBeInTheDocument();
    expect(corpi).toEqual([{ edizione_id: 1 }]);
    expect(chiavi[0]).toMatch(/^[0-9a-f-]{36}$/);
    const riga = (await screen.findAllByRole("row"))[1] as HTMLElement;
    expect(await within(riga).findByText("Richiesta")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: ISCRIVITI })).not.toBeInTheDocument();
  });

  it("dopo un errore del server riprova con la stessa chiave: niente doppioni", async () => {
    const stato = conCatalogo([voceCatalogo(1)]);
    const chiavi: (string | null)[] = [];
    server.use(
      http.post(`${API}/iscrizioni`, ({ request }) => {
        chiavi.push(request.headers.get("Idempotency-Key"));
        if (chiavi.length === 1) {
          return problema(503, { title: "Servizio non disponibile" });
        }
        stato.elenco = [voceCatalogo(1, { mia_iscrizione: { stato: "Richiesta" } })];
        return HttpResponse.json(iscrizioneLetta(1, "Richiesta"), { status: 201 });
      }),
    );
    mostra(<Catalogo />);

    await userEvent.click(await screen.findByRole("button", { name: ISCRIVITI }));

    expect(
      await screen.findByText("Richiesta inviata per «Corso 1».", {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(chiavi).toHaveLength(2);
    expect(chiavi[1]).toBe(chiavi[0]);
  });

  it("un rifiuto dell'API (409) si vede e il pulsante resta", async () => {
    conCatalogo([voceCatalogo(1)]);
    server.use(
      http.post(`${API}/iscrizioni`, () =>
        problema(409, {
          type: "/problemi/edizione-iniziata",
          title: "Edizione già iniziata",
          detail: "L'edizione 1 è già iniziata",
        }),
      ),
    );
    mostra(<Catalogo />);

    await userEvent.click(await screen.findByRole("button", { name: ISCRIVITI }));

    const avviso = await screen.findByRole("alert");
    expect(within(avviso).getByText("Edizione già iniziata")).toBeInTheDocument();
    expect(within(avviso).getByText("L'edizione 1 è già iniziata")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: ISCRIVITI })).toBeInTheDocument();
  });

  it("chi non ha il ruolo dipendente non vede il pulsante", async () => {
    server.use(http.get(`${API}/io`, () => HttpResponse.json(profiloAdmin)));
    mostra(<Catalogo />);

    expect(await screen.findByText("Corso 1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Iscriviti/ })).not.toBeInTheDocument();
  });
});
