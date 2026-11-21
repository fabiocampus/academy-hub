import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import userEvent from "@testing-library/user-event";
import { User, UserManager } from "oidc-client-ts";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { impostaAlNonAutenticato, impostaToken } from "../api/client";
import { FLAG_SPENTE } from "../api/flag";
import { useProfilo } from "../api/query";
import { tema, variabiliCss } from "../tema";
import { API, profiloDipendente, server } from "../test/server";
import {
  Accesso,
  CHIAVE_RITORNO,
  PAGINA_PUBBLICA,
  creaGestoreOidc,
  dopoIlLogin,
  percorsoDiRitorno,
} from "./Accesso";
import { navigazione } from "./navigazione";

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
  let sostituisci: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    sostituisci = vi.spyOn(navigazione, "sostituisci").mockImplementation(() => undefined);
  });
  afterEach(() => {
    impostaToken(() => Promise.resolve(undefined));
    impostaAlNonAutenticato(() => undefined);
    window.history.replaceState({}, "", "/");
    window.sessionStorage.clear();
  });

  it("con una sessione valida entra e manda il token del gestore all'API", async () => {
    salvaUtente("token-di-anna", 300);
    const autorizzazioni = registraAutorizzazioni();

    mostraAccesso({ flag: FLAG_SPENTE, identita: "oidc", oidc: OIDC }, <ChiSono />);

    expect(await screen.findByText(profiloDipendente.nome)).toBeInTheDocument();
    expect(autorizzazioni).toEqual(["Bearer token-di-anna"]);
  });

  it("con un token scaduto torna alla pagina pubblica e non lo manda", async () => {
    salvaUtente("token-scaduto", -60);
    const autorizzazioni = registraAutorizzazioni();

    mostraAccesso({ flag: FLAG_SPENTE, identita: "oidc", oidc: OIDC }, <ChiSono />);

    await vi.waitFor(() => {
      expect(sostituisci).toHaveBeenCalledWith(PAGINA_PUBBLICA);
    });
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

    await vi.waitFor(() => {
      expect(sostituisci).toHaveBeenCalledWith(PAGINA_PUBBLICA);
    });
    expect(window.sessionStorage.getItem(`oidc.user:${OIDC.emittente}:${OIDC.client_id}`)).toBe(
      null,
    );
  });

  it("senza sessione va alla pagina pubblica e ricorda la pagina aperta", async () => {
    window.history.replaceState({}, "", "/approvazioni?pagina=2");
    const accedi = vi.spyOn(UserManager.prototype, "signinRedirect").mockResolvedValue();

    mostraAccesso({ flag: FLAG_SPENTE, identita: "oidc", oidc: OIDC });

    await vi.waitFor(() => {
      expect(sostituisci).toHaveBeenCalledWith(PAGINA_PUBBLICA);
    });
    expect(window.sessionStorage.getItem(CHIAVE_RITORNO)).toBe("/approvazioni?pagina=2");
    expect(accedi).not.toHaveBeenCalled();
    expect(screen.queryByText("Area riservata")).not.toBeInTheDocument();
  });

  it("su Databricks entra subito: il login l'ha fatto la piattaforma", () => {
    mostraAccesso({ flag: FLAG_SPENTE, identita: "databricks", oidc: null });

    expect(screen.getByText("Area riservata")).toBeInTheDocument();
    // Nessuna pagina pubblica: il proxy dell'App ha già fatto entrare (US-19).
    expect(sostituisci).not.toHaveBeenCalled();
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

  it("con ?accedi=1 dalla pagina pubblica parte il login verso la pagina ricordata", async () => {
    window.sessionStorage.setItem(CHIAVE_RITORNO, "/approvazioni?pagina=2");
    window.history.replaceState({}, "", "/?accedi=1");
    const accedi = vi.spyOn(UserManager.prototype, "signinRedirect").mockResolvedValue();

    mostraAccesso({ flag: FLAG_SPENTE, identita: "oidc", oidc: OIDC });

    await vi.waitFor(() => {
      expect(accedi).toHaveBeenCalledWith(
        expect.objectContaining({ state: { ritorno: "/approvazioni?pagina=2" } }),
      );
    });
    expect(window.sessionStorage.getItem(CHIAVE_RITORNO)).toBe(null);
    expect(sostituisci).not.toHaveBeenCalled();
    // Tornando indietro da Keycloak non si riparte verso il login.
    expect(window.location.search).toBe("");
  });

  it("con ?accedi=1 un ritorno manomesso verso un altro sito diventa la radice", async () => {
    window.sessionStorage.setItem(CHIAVE_RITORNO, "//esterno.example/trappola");
    window.history.replaceState({}, "", "/?accedi=1");
    const accedi = vi.spyOn(UserManager.prototype, "signinRedirect").mockResolvedValue();

    mostraAccesso({ flag: FLAG_SPENTE, identita: "oidc", oidc: OIDC });

    await vi.waitFor(() => {
      expect(accedi).toHaveBeenCalledWith(expect.objectContaining({ state: { ritorno: "/" } }));
    });
  });

  it("con ?accedi=1 e nessuna pagina ricordata torna alla radice", async () => {
    window.history.replaceState({}, "", "/?accedi=1");
    const accedi = vi.spyOn(UserManager.prototype, "signinRedirect").mockResolvedValue();

    mostraAccesso({ flag: FLAG_SPENTE, identita: "oidc", oidc: OIDC });

    await vi.waitFor(() => {
      expect(accedi).toHaveBeenCalledWith(expect.objectContaining({ state: { ritorno: "/" } }));
    });
  });

  it("se il ritorno da Keycloak fallisce mostra l'errore e fa riprovare", async () => {
    window.history.replaceState({}, "", "/?error=access_denied&state=sconosciuto");
    const accedi = vi.spyOn(UserManager.prototype, "signinRedirect").mockResolvedValue();

    mostraAccesso({ flag: FLAG_SPENTE, identita: "oidc", oidc: OIDC });

    expect(await screen.findByText("Accesso non riuscito")).toBeInTheDocument();
    expect(sostituisci).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Riprova ad accedere" }));
    expect(accedi).toHaveBeenCalledWith(expect.objectContaining({ state: { ritorno: "/" } }));
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
