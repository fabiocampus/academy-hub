/**
 * Stato del server con React Query: una funzione per lettura o azione, chiavi in un
 * solo posto. Dopo ogni azione si rileggono gli elenchi che può aver cambiato, anche
 * se l'azione fallisce (un 409 dice che lo stato era già cambiato).
 */
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { api, dati, riprova } from "./client";

export interface Pagina {
  limite: number;
  offset: number;
}

export interface FiltriCatalogo extends Pagina {
  titolo: string;
}

export const chiavi = {
  profilo: ["profilo"] as const,
  catalogo: (filtri: FiltriCatalogo) => ["catalogo", filtri] as const,
  mieIscrizioni: (pagina: Pagina) => ["iscrizioni", pagina] as const,
  richieste: (pagina: Pagina) => ["richieste", pagina] as const,
};

/** Gli elenchi che un cambio di stato di un'iscrizione può toccare. */
export function rileggiElenchi(queryClient: QueryClient): Promise<void> {
  return Promise.all(
    ["catalogo", "iscrizioni", "richieste"].map((radice) =>
      queryClient.invalidateQueries({ queryKey: [radice] }),
    ),
  ).then(() => undefined);
}

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

export function useMieIscrizioni(pagina: Pagina) {
  return useQuery({
    queryKey: chiavi.mieIscrizioni(pagina),
    queryFn: async ({ signal }) =>
      dati(await api.GET("/api/v1/iscrizioni", { params: { query: pagina }, signal })),
    placeholderData: keepPreviousData,
  });
}

export function useRichiesteDaApprovare(pagina: Pagina) {
  return useQuery({
    queryKey: chiavi.richieste(pagina),
    queryFn: async ({ signal }) =>
      dati(await api.GET("/api/v1/richieste-da-approvare", { params: { query: pagina }, signal })),
    placeholderData: keepPreviousData,
  });
}

export interface RichiestaIscrizione {
  edizioneId: number;
  /** `Idempotency-Key` (ADR-0006): la stessa per i tentativi della stessa richiesta. */
  chiave: string;
}

/**
 * US-04. Unica azione ripetuta da sola dopo un errore di rete o del server: con la
 * stessa chiave l'API restituisce l'iscrizione già creata invece di un doppione.
 */
export function useRichiediIscrizione() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ edizioneId, chiave }: RichiestaIscrizione) =>
      dati(
        await api.POST("/api/v1/iscrizioni", {
          params: { header: { "idempotency-key": chiave } },
          body: { edizione_id: edizioneId },
        }),
      ),
    retry: riprova,
    onSettled: () => rileggiElenchi(queryClient),
  });
}

/** US-10. Comando: lo stato si verifica sul server, niente retry automatico. */
export function useAnnullaIscrizione() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (iscrizioneId: number) =>
      dati(
        await api.POST("/api/v1/iscrizioni/{iscrizione_id}/annullamento", {
          params: { path: { iscrizione_id: iscrizioneId } },
        }),
      ),
    onSettled: () => rileggiElenchi(queryClient),
  });
}

/** US-06. */
export function useApprova() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (iscrizioneId: number) =>
      dati(
        await api.POST("/api/v1/iscrizioni/{iscrizione_id}/approvazione", {
          params: { path: { iscrizione_id: iscrizioneId } },
        }),
      ),
    onSettled: () => rileggiElenchi(queryClient),
  });
}

/** US-06, con il motivo obbligatorio. */
export function useRifiuta() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ iscrizioneId, motivo }: { iscrizioneId: number; motivo: string }) =>
      dati(
        await api.POST("/api/v1/iscrizioni/{iscrizione_id}/rifiuto", {
          params: { path: { iscrizione_id: iscrizioneId } },
          body: { motivo },
        }),
      ),
    onSettled: () => rileggiElenchi(queryClient),
  });
}

/**
 * Evento di calendario di un'iscrizione Confermata (feature flag `calendario`). Si scarica
 * con il client, non con un link: con OIDC serve il Bearer, che un `<a href>` non manda.
 */
export function useScaricaCalendario() {
  return useMutation({
    mutationFn: async (iscrizioneId: number) => {
      const evento = dati(
        await api.GET("/api/v1/iscrizioni/{iscrizione_id}/calendario.ics", {
          params: { path: { iscrizione_id: iscrizioneId } },
          parseAs: "blob",
        }),
      );
      const indirizzo = URL.createObjectURL(evento);
      const link = document.createElement("a");
      link.href = indirizzo;
      link.download = `iscrizione-${String(iscrizioneId)}.ics`;
      link.click();
      // Non subito: alcuni browser leggono il blob dopo il click.
      setTimeout(() => {
        URL.revokeObjectURL(indirizzo);
      }, 10_000);
    },
  });
}
