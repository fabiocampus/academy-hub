import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import {
  API,
  problema,
  profiloAdmin,
  profiloDipendente,
  profiloResponsabile,
  server,
} from "../test/server";
import { mostra } from "../test/render";
import { Struttura, vociMenu } from "./Struttura";

function conPagina() {
  return (
    <Routes>
      <Route element={<Struttura />}>
        <Route index element={<p>Contenuto</p>} />
      </Route>
    </Routes>
  );
}

describe("Struttura", () => {
  it("mostra la persona collegata, il menu e la pagina", async () => {
    mostra(conPagina());

    expect(await screen.findByText("Contenuto")).toBeInTheDocument();
    expect(screen.getByText("Anna Dati")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Catalogo" })).toHaveAttribute("href", "/");
  });

  it("con il login OIDC offre l'uscita", async () => {
    const esci = vi.fn();
    mostra(conPagina(), { sessione: { esci } });

    await userEvent.click(await screen.findByRole("button", { name: "Esci" }));

    expect(esci).toHaveBeenCalledOnce();
  });

  it("su Databricks non c'è un'uscita nostra", async () => {
    mostra(conPagina());

    await screen.findByText("Contenuto");
    expect(screen.queryByRole("button", { name: "Esci" })).not.toBeInTheDocument();
  });

  it("una persona non registrata vede il motivo e non la pagina", async () => {
    server.use(
      http.get(`${API}/io`, () =>
        problema(403, {
          type: "/problemi/persona-non-registrata",
          title: "Persona non registrata",
          detail: "Nessuna persona con email esterna@academy.example",
        }),
      ),
    );

    mostra(conPagina());

    expect(await screen.findByText("Persona non registrata")).toBeInTheDocument();
    expect(screen.queryByText("Contenuto")).not.toBeInTheDocument();
  });

  it("mostra le voci del menu in base al profilo", async () => {
    server.use(http.get(`${API}/io`, () => HttpResponse.json(profiloResponsabile)));
    mostra(conPagina());

    expect(await screen.findByRole("link", { name: "Le mie iscrizioni" })).toHaveAttribute(
      "href",
      "/iscrizioni",
    );
    expect(screen.getByRole("link", { name: "Approvazioni" })).toHaveAttribute(
      "href",
      "/approvazioni",
    );
  });
});

describe("vociMenu", () => {
  const etichette = (profilo: typeof profiloDipendente) =>
    vociMenu(profilo).map((voce) => voce.etichetta);

  it("al dipendente: catalogo e le sue iscrizioni, non le approvazioni", () => {
    expect(etichette(profiloDipendente)).toEqual(["Catalogo", "Le mie iscrizioni"]);
  });

  it("al responsabile di un team anche le approvazioni", () => {
    expect(etichette(profiloResponsabile)).toEqual([
      "Catalogo",
      "Le mie iscrizioni",
      "Approvazioni",
    ]);
  });

  it("all'admin Academy le approvazioni (decide dal vertice) e la gestione, non le iscrizioni", () => {
    expect(etichette(profiloAdmin)).toEqual(["Catalogo", "Approvazioni", "Gestione"]);
  });
});
