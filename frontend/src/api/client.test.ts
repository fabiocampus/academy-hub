import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { API, profiloDipendente, server } from "../test/server";
import { api, dati, ErroreApi, impostaToken } from "./client";

describe("client dell'API", () => {
  afterEach(() => {
    impostaToken(() => Promise.resolve(undefined));
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
