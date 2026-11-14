import { createContext, useContext } from "react";

export interface Sessione {
  /** Presente solo se il login è nostro (OIDC); su Databricks si esce dalla piattaforma. */
  esci?: () => void;
}

export const ContestoSessione = createContext<Sessione>({});

export function useSessione(): Sessione {
  return useContext(ContestoSessione);
}
