/**
 * Gestione Academy (issue #64): letture e azioni su corsi, edizioni e iscrizioni di
 * un'edizione. Le chiavi stanno sotto `gestione`, così dopo ogni azione si rilegge
 * tutto con una sola invalidazione, più gli elenchi del flusso (catalogo, iscrizioni).
 *
 * Le modifiche usano la concorrenza ottimistica: si legge la risorsa con il suo ETag e
 * lo si rimanda in `If-Match`; se nel frattempo è cambiata l'API risponde 412.
 */
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { api, dati, datiConVersione, type Schemi } from "./client";
import { rileggiElenchi, type Pagina } from "./query";

export interface FiltriCorsi extends Pagina {
  titolo: string;
}

export interface FiltriIscrizioni extends Pagina {
  stato: Schemi["StatoIscrizione"] | null;
}

export const chiaviGestione = {
  radice: ["gestione"] as const,
  corsi: (filtri: FiltriCorsi) => ["gestione", "corsi", filtri] as const,
  corso: (id: number) => ["gestione", "corso", id] as const,
  edizioni: (corsoId: number, pagina: Pagina) => ["gestione", "edizioni", corsoId, pagina] as const,
  edizione: (id: number) => ["gestione", "edizione", id] as const,
  iscrizioni: (edizioneId: number, filtri: FiltriIscrizioni) =>
    ["gestione", "iscrizioni", edizioneId, filtri] as const,
  docenti: ["gestione", "docenti"] as const,
};

function rileggiTutto(queryClient: QueryClient): Promise<void> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: chiaviGestione.radice }),
    rileggiElenchi(queryClient),
  ]).then(() => undefined);
}

export function useCorsi(filtri: FiltriCorsi) {
  return useQuery({
    queryKey: chiaviGestione.corsi(filtri),
    queryFn: async ({ signal }) =>
      dati(
        await api.GET("/api/v1/corsi", {
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
    placeholderData: keepPreviousData,
  });
}

/** Il corso con il suo ETag, letto ogni volta che si apre una modifica. */
export function useCorso(id: number) {
  return useQuery({
    queryKey: chiaviGestione.corso(id),
    queryFn: async ({ signal }) =>
      datiConVersione(
        await api.GET("/api/v1/corsi/{corso_id}", { params: { path: { corso_id: id } }, signal }),
      ),
  });
}

export function useEdizioniDelCorso(corsoId: number, pagina: Pagina) {
  return useQuery({
    queryKey: chiaviGestione.edizioni(corsoId, pagina),
    queryFn: async ({ signal }) =>
      dati(
        await api.GET("/api/v1/corsi/{corso_id}/edizioni", {
          params: { path: { corso_id: corsoId }, query: pagina },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/** L'edizione con il suo ETag. */
export function useEdizione(id: number) {
  return useQuery({
    queryKey: chiaviGestione.edizione(id),
    queryFn: async ({ signal }) =>
      datiConVersione(
        await api.GET("/api/v1/edizioni/{edizione_id}", {
          params: { path: { edizione_id: id } },
          signal,
        }),
      ),
  });
}

export function useIscrizioniDellEdizione(edizioneId: number, filtri: FiltriIscrizioni) {
  return useQuery({
    queryKey: chiaviGestione.iscrizioni(edizioneId, filtri),
    queryFn: async ({ signal }) =>
      dati(
        await api.GET("/api/v1/edizioni/{edizione_id}/iscrizioni", {
          params: {
            path: { edizione_id: edizioneId },
            query: { stato: filtri.stato, limite: filtri.limite, offset: filtri.offset },
          },
          signal,
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useDocenti() {
  return useQuery({
    queryKey: chiaviGestione.docenti,
    queryFn: async ({ signal }) => dati(await api.GET("/api/v1/docenti", { signal })),
    staleTime: 5 * 60_000,
  });
}

/** US-01. */
export function useCreaCorso() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (corso: Schemi["NuovoCorso"]) =>
      dati(await api.POST("/api/v1/corsi", { body: corso })),
    onSettled: () => rileggiTutto(queryClient),
  });
}

interface Modifica<T> {
  id: number;
  etag: string;
  modifiche: T;
}

/** US-01, con `If-Match`. */
export function useModificaCorso() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, etag, modifiche }: Modifica<Schemi["ModificaCorso"]>) =>
      dati(
        await api.PATCH("/api/v1/corsi/{corso_id}", {
          params: { path: { corso_id: id }, header: { "if-match": etag } },
          body: modifiche,
        }),
      ),
    onSettled: () => rileggiTutto(queryClient),
  });
}

/** US-01: il corso esce dal catalogo; le edizioni restano. */
export function useArchiviaCorso() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, etag }: { id: number; etag: string }) =>
      dati(
        await api.POST("/api/v1/corsi/{corso_id}/archiviazione", {
          params: { path: { corso_id: id }, header: { "if-match": etag } },
        }),
      ),
    onSettled: () => rileggiTutto(queryClient),
  });
}

/** US-02. */
export function useCreaEdizione() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (edizione: Schemi["NuovaEdizione"]) =>
      dati(await api.POST("/api/v1/edizioni", { body: edizione })),
    onSettled: () => rileggiTutto(queryClient),
  });
}

/** US-02, con `If-Match`. */
export function useModificaEdizione() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, etag, modifiche }: Modifica<Schemi["ModificaEdizione"]>) =>
      dati(
        await api.PATCH("/api/v1/edizioni/{edizione_id}", {
          params: { path: { edizione_id: id }, header: { "if-match": etag } },
          body: modifiche,
        }),
      ),
    onSettled: () => rileggiTutto(queryClient),
  });
}

/** US-18. Comando: niente `If-Match`, lo stato si verifica sotto lock. */
export function useCancellaEdizione() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) =>
      dati(
        await api.POST("/api/v1/edizioni/{edizione_id}/cancellazione", {
          params: { path: { edizione_id: id } },
        }),
      ),
    onSettled: () => rileggiTutto(queryClient),
  });
}

/** US-08: Confermata se c'è posto, altrimenti InAttesa. */
export function useConfermaIscrizione() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (iscrizioneId: number) =>
      dati(
        await api.POST("/api/v1/iscrizioni/{iscrizione_id}/conferma", {
          params: { path: { iscrizione_id: iscrizioneId } },
        }),
      ),
    onSettled: () => rileggiTutto(queryClient),
  });
}
