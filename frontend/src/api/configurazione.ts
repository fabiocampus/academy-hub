import { api, dati, type Schemi } from "./client";

export type Configurazione = Schemi["ConfigurazioneClient"];

/** Pubblica: si legge prima del login per sapere come accedere. */
export async function leggiConfigurazione(): Promise<Configurazione> {
  return dati(await api.GET("/api/v1/configurazione"));
}
