import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { lazy } from "react";
import { Link, Route, Routes } from "react-router";
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
  it("se il chunk di una pagina non arriva lo dice e offre di ricaricare", async () => {
    // Dopo un rilascio un chunk vecchio risponde 404 (ADR-0009 §14): senza un confine
    // React smonterebbe tutta l'app e resterebbe una pagina bianca.
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const ricarica = vi.fn();
    vi.stubGlobal("location", { reload: ricarica });
    const Rotta = lazy(() =>
      Promise.reject(new Error("Failed to fetch dynamically imported module")),
    );
    mostra(
      <Routes>
        <Route element={<Struttura />}>
          <Route index element={<Link to="/altra">Altra</Link>} />
          <Route path="rotta" element={<Rotta />} />
          <Route path="altra" element={<p>Altra pagina</p>} />
        </Route>
      </Routes>,
      { percorso: "/rotta" },
    );

    expect(await screen.findByText("Questa pagina non si è caricata")).toBeInTheDocument();
    // Struttura e menu restano.
    expect(screen.getByRole("navigation", { name: "Menu principale" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ricarica l'app" }));
    expect(ricarica).toHaveBeenCalledOnce();
    // Cambiando pagina il confine riparte.
    await userEvent.click(screen.getByRole("link", { name: "Catalogo" }));
    expect(await screen.findByRole("link", { name: "Altra" })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

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

  it("segna la voce della pagina corrente con aria-current (US-20)", async () => {
    mostra(conPagina());

    expect(await screen.findByRole("link", { name: "Catalogo" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Le mie iscrizioni" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("il primo link della pagina porta al contenuto (US-20)", async () => {
    mostra(conPagina());
    await screen.findByText("Contenuto");

    const salta = screen.getByRole("link", { name: "Vai al contenuto" });
    expect(salta).toHaveAttribute("href", "#contenuto");
    expect(screen.getAllByRole("link")[0]).toBe(salta);
    expect(screen.getByRole("main")).toHaveAttribute("id", "contenuto");
  });

  it("il pulsante del menu dice se il menu è aperto e Esc lo chiude (US-20)", async () => {
    mostra(conPagina());
    await screen.findByText("Contenuto");

    const pulsante = screen.getByRole("button", { name: "Apri il menu" });
    expect(pulsante).toHaveAttribute("aria-expanded", "false");
    expect(pulsante).toHaveAttribute("aria-controls", "menu-principale");

    await userEvent.click(pulsante);
    expect(screen.getByRole("button", { name: "Chiudi il menu" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("navigation", { name: "Menu principale" })).toHaveAttribute(
      "data-aperto",
    );

    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Apri il menu" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
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
