import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { API, profiloDipendente, server } from "../test/server";
import { api, dati, ErroreApi, impostaAlNonAutenticato, impostaToken, riprova } from "./client";

describe("client dell'API", () => {
  afterEach(() => {
    impostaToken(() => Promise.resolve(undefined));
    impostaAlNonAutenticato(() => undefined);
  });

  it("un 401 avvisa chi gestisce l'accesso, gli altri errori no", async () => {
    const alNonAutenticato = vi.fn();
    impostaAlNonAutenticato(alNonAutenticato);
    server.use(http.get(`${API}/catalogo`, () => new HttpResponse(null, { status: 403 })));
    await api.GET("/api/v1/catalogo");
    expect(alNonAutenticato).not.toHaveBeenCalled();

    server.use(http.get(`${API}/io`, () => new HttpResponse(null, { status: 401 })));
    await api.GET("/api/v1/io");

    expect(alNonAutenticato).toHaveBeenCalledOnce();
  });

  it("manda l'access token come Bearer", async () => {
    let autorizzazione: string | null = null;
    server.use(
      http.get(`${API}/io`, ({ request }) => {
        autorizzazione = request.headers.get("Authorization");
        return HttpResponse.json(profiloDipendente);
      }),
    );
    impostaToken(() => Promise.resolve("token-di-prova"));

    await api.GET("/api/v1/io");

    expect(autorizzazione).toBe("Bearer token-di-prova");
  });

  it("senza token non manda Authorization (Databricks: lo mette il proxy)", async () => {
    let autorizzazione: string | null = "non letta";
    server.use(
      http.get(`${API}/io`, ({ request }) => {
        autorizzazione = request.headers.get("Authorization");
        return HttpResponse.json(profiloDipendente);
      }),
    );

    await api.GET("/api/v1/io");

    expect(autorizzazione).toBeNull();
  });

  it("trasforma un problema RFC 9457 in ErroreApi", async () => {
    server.use(
      http.get(`${API}/io`, () =>
        HttpResponse.json(
          { type: "/problemi/non-autenticato", title: "Non autenticato", status: 401 },
          { status: 401 },
        ),
      ),
    );

    const errore: unknown = await api
      .GET("/api/v1/io")
      .then(dati)
      .catch((e: unknown) => e);

    expect(errore).toBeInstanceOf(ErroreApi);
    expect((errore as ErroreApi).stato).toBe(401);
    expect((errore as ErroreApi).problema.type).toBe("/problemi/non-autenticato");
  });

  it("un errore senza corpo RFC 9457 diventa comunque ErroreApi", async () => {
    server.use(http.get(`${API}/io`, () => new HttpResponse("Bad gateway", { status: 502 })));

    const esito = await api.GET("/api/v1/io");

    expect(() => dati(esito)).toThrow(ErroreApi);
    expect(() => dati(esito)).toThrow(expect.objectContaining({ stato: 502 }) as Error);
  });
});

describe("riprova", () => {
  const errore = (stato: number) =>
    new ErroreApi({ type: "about:blank", title: "x", status: stato });

  it.each([400, 401, 403, 404, 409, 422])("non riprova un %i", (stato) => {
    expect(riprova(0, errore(stato))).toBe(false);
  });

  it("riprova errori del server e di rete, al più due volte", () => {
    expect(riprova(0, errore(503))).toBe(true);
    expect(riprova(1, new TypeError("Failed to fetch"))).toBe(true);
    expect(riprova(2, errore(500))).toBe(false);
  });
});
