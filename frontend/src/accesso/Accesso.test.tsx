import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import userEvent from "@testing-library/user-event";
import { User, UserManager } from "oidc-client-ts";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { impostaAlNonAutenticato, impostaToken } from "../api/client";
import { FLAG_SPENTE } from "../api/flag";
import { useProfilo } from "../api/query";
import { tema, variabiliCss } from "../tema";
import { API, profiloDipendente, server } from "../test/server";
import { Accesso, creaGestoreOidc, dopoIlLogin, percorsoDiRitorno } from "./Accesso";

const OIDC = { emittente: "http://localhost:8080/realms/academy", client_id: "academy-web" };

function mostraAccesso(
  configurazione: Parameters<typeof Accesso>[0]["configurazione"],
  figli: ReactNode = <p>Area riservata</p>,
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider theme={tema} cssVariablesResolver={variabiliCss}>
      <QueryClientProvider client={queryClient}>
        <Accesso configurazione={configurazione}>{figli}</Accesso>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

/** Un utente già entrato, come lo salva oidc-client-ts dopo il ritorno da Keycloak. */
function salvaUtente(token: string, scadeTraSecondi: number): void {
  const utente = new User({
    access_token: token,
    token_type: "Bearer",
    profile: { sub: "anna", iss: OIDC.emittente, aud: OIDC.client_id, exp: 0, iat: 0 },
    expires_at: Math.floor(Date.now() / 1000) + scadeTraSecondi,
  });
  window.sessionStorage.setItem(
    `oidc.user:${OIDC.emittente}:${OIDC.client_id}`,
    utente.toStorageString(),
  );
}

function ChiSono() {
  const profilo = useProfilo();
  if (profilo.isError) return <p>Errore del profilo</p>;
  return <p>{profilo.data?.nome ?? "..."}</p>;
}

function registraAutorizzazioni(): string[] {
  const viste: string[] = [];
  server.use(
    http.get(`${API}/io`, ({ request }) => {
      viste.push(request.headers.get("Authorization") ?? "nessuna");
      return HttpResponse.json(profiloDipendente);
    }),
  );
  return viste;
}

describe("Accesso", () => {
  afterEach(() => {
    impostaToken(() => Promise.resolve(undefined));
    impostaAlNonAutenticato(() => undefined);
  });

  it("con una sessione valida entra e manda il token del gestore all'API", async () => {
    salvaUtente("token-di-anna", 300);
    const autorizzazioni = registraAutorizzazioni();

    mostraAccesso({ flag: FLAG_SPENTE, identita: "oidc", oidc: OIDC }, <ChiSono />);

    expect(await screen.findByText(profiloDipendente.nome)).toBeInTheDocument();
    expect(autorizzazioni).toEqual(["Bearer token-di-anna"]);
  });

  it("con un token scaduto chiede di nuovo l'accesso e non lo manda", async () => {
    salvaUtente("token-scaduto", -60);
    const autorizzazioni = registraAutorizzazioni();

    mostraAccesso({ flag: FLAG_SPENTE, identita: "oidc", oidc: OIDC }, <ChiSono />);

    expect(await screen.findByRole("button", { name: "Accedi" })).toBeInTheDocument();
    expect(autorizzazioni).toEqual([]);
  });

  it("se l'API risponde 401 torna alla schermata d'accesso", async () => {
    salvaUtente("token-revocato", 300);
    server.use(
      http.get(`${API}/io`, () =>
        HttpResponse.json(
          { type: "/problemi/non-autenticato", title: "Non autenticato", status: 401 },
          { status: 401 },
        ),
      ),
    );

    mostraAccesso({ flag: FLAG_SPENTE, identita: "oidc", oidc: OIDC }, <ChiSono />);

    expect(await screen.findByRole("button", { name: "Accedi" })).toBeInTheDocument();
    expect(window.sessionStorage.length).toBe(0);
  });

  it("con OIDC e senza sessione chiede di accedere", async () => {
    mostraAccesso({ flag: FLAG_SPENTE, identita: "oidc", oidc: OIDC });

    expect(await screen.findByRole("button", { name: "Accedi" })).toBeInTheDocument();
    expect(screen.queryByText("Area riservata")).not.toBeInTheDocument();
  });

  it("su Databricks entra subito: il login l'ha fatto la piattaforma", () => {
    mostraAccesso({ flag: FLAG_SPENTE, identita: "databricks", oidc: null });

    expect(screen.getByText("Area riservata")).toBeInTheDocument();
  });

  it("con l'identità provvisoria del backend non entra", () => {
    mostraAccesso({ flag: FLAG_SPENTE, identita: "provvisoria", oidc: null });

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

  it("cliccando «Accedi» ricorda la pagina aperta", async () => {
    window.history.replaceState({}, "", "/approvazioni?pagina=2");
    const accedi = vi.spyOn(UserManager.prototype, "signinRedirect").mockResolvedValue();
    mostraAccesso({ flag: FLAG_SPENTE, identita: "oidc", oidc: OIDC });

    await userEvent.click(await screen.findByRole("button", { name: "Accedi" }));

    expect(accedi).toHaveBeenCalledWith(
      expect.objectContaining({ state: { ritorno: "/approvazioni?pagina=2" } }),
    );
    window.history.replaceState({}, "", "/");
  });
});

describe("ritorno dopo il login", () => {
  it.each([
    [{ ritorno: "/iscrizioni" }, "/iscrizioni"],
    [{ ritorno: "/approvazioni?pagina=2#x" }, "/approvazioni?pagina=2#x"],
    [{ ritorno: "//esterno.example/x" }, "/"],
    [{ ritorno: "/\\esterno.example" }, "/"],
    [{ ritorno: "/\t/esterno.example" }, "/"],
    [{ ritorno: "/corsi/../iscrizioni" }, "/iscrizioni"],
    [{ ritorno: "https://esterno.example" }, "/"],
    [{ ritorno: 42 }, "/"],
    [undefined, "/"],
    ["/iscrizioni", "/"],
  ])("da %j torna a %s", (stato, atteso) => {
    expect(percorsoDiRitorno(stato)).toBe(atteso);
  });

  it("toglie code e state dall'indirizzo e porta alla pagina chiesta", () => {
    window.history.replaceState({}, "", "/?code=abc&state=xyz");
    const utente = new User({
      access_token: "t",
      token_type: "Bearer",
      profile: { sub: "anna", iss: OIDC.emittente, aud: OIDC.client_id, exp: 0, iat: 0 },
      userState: { ritorno: "/iscrizioni" },
    });

    dopoIlLogin(utente);

    expect(window.location.pathname + window.location.search).toBe("/iscrizioni");
    window.history.replaceState({}, "", "/");
  });
});
