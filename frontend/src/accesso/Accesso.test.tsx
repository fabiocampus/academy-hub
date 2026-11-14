import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { tema } from "../tema";
import { Accesso, creaGestoreOidc } from "./Accesso";

const OIDC = { emittente: "http://localhost:8080/realms/academy", client_id: "academy-web" };

function mostraAccesso(configurazione: Parameters<typeof Accesso>[0]["configurazione"]) {
  return render(
    <MantineProvider theme={tema}>
      <Accesso configurazione={configurazione}>
        <p>Area riservata</p>
      </Accesso>
    </MantineProvider>,
  );
}

describe("Accesso", () => {
  it("con OIDC e senza sessione chiede di accedere", async () => {
    mostraAccesso({ identita: "oidc", oidc: OIDC });

    expect(await screen.findByRole("button", { name: "Accedi" })).toBeInTheDocument();
    expect(screen.queryByText("Area riservata")).not.toBeInTheDocument();
  });

  it("su Databricks entra subito: il login l'ha fatto la piattaforma", () => {
    mostraAccesso({ identita: "databricks", oidc: null });

    expect(screen.getByText("Area riservata")).toBeInTheDocument();
  });

  it("con l'identità provvisoria del backend non entra", () => {
    mostraAccesso({ identita: "provvisoria", oidc: null });

    expect(screen.getByText("Accesso non configurato")).toBeInTheDocument();
    expect(screen.queryByText("Area riservata")).not.toBeInTheDocument();
  });

  it("il gestore usa authorization code con PKCE e torna all'origine", () => {
    const gestore = creaGestoreOidc(OIDC, "http://localhost:5173");

    expect(gestore.settings.authority).toBe(OIDC.emittente);
    expect(gestore.settings.client_id).toBe("academy-web");
    expect(gestore.settings.response_type).toBe("code");
    expect(gestore.settings.redirect_uri).toBe("http://localhost:5173/");
    expect(gestore.settings.disablePKCE).toBe(false);
  });
});
