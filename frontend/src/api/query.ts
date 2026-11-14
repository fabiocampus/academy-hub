/** Stato del server con React Query: una funzione per lettura, chiavi in un solo posto. */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, dati } from "./client";

export interface FiltriCatalogo {
  titolo: string;
  limite: number;
  offset: number;
}

export const chiavi = {
  profilo: ["profilo"] as const,
  catalogo: (filtri: FiltriCatalogo) => ["catalogo", filtri] as const,
};

export function useProfilo() {
  return useQuery({
    queryKey: chiavi.profilo,
    queryFn: async () => dati(await api.GET("/api/v1/io")),
    staleTime: 5 * 60_000,
  });
}

export function useCatalogo(filtri: FiltriCatalogo) {
  return useQuery({
    queryKey: chiavi.catalogo(filtri),
    queryFn: async ({ signal }) =>
      dati(
        await api.GET("/api/v1/catalogo", {
          params: {
            query: {
              titolo: filtri.titolo.trim() || null,
              limite: filtri.limite,
              offset: filtri.offset,
            },
          },
          signal,
        }),
      ),
    // Cambiando pagina o filtro resta visibile la pagina precedente finché arriva la nuova.
    placeholderData: keepPreviousData,
  });
}
