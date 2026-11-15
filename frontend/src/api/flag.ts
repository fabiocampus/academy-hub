/**
 * Feature flag dell'ambiente (ADR-0014), lette da `GET /api/v1/configurazione` prima del
 * primo render. Il frontend nasconde le funzioni spente; l'API risponde comunque 404.
 */
import { createContext, useContext } from "react";

import type { Schemi } from "./client";

export type Flag = Schemi["FlagFunzioni"];

/** Senza configurazione nessuna funzione nuova: spenta è il valore sicuro. */
export const FLAG_SPENTE: Flag = { calendario: false };

export const ContestoFlag = createContext<Flag>(FLAG_SPENTE);

export function useFlag(): Flag {
  return useContext(ContestoFlag);
}
