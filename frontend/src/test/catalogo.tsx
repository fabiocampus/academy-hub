import { http, HttpResponse } from "msw";

import { useCatalogo } from "../api/query";
import { API, pagina, server } from "./server";

/** Tiene montata la lettura del catalogo, come se la sua pagina fosse aperta in cache. */
export function SpiaCatalogo(): null {
  useCatalogo({ titolo: "", limite: 20, offset: 0 });
  return null;
}

/** Conta le letture del catalogo: dopo un'azione della gestione deve rileggersi. */
export function contaLettureCatalogo(): { letture: number } {
  const conteggio = { letture: 0 };
  server.use(
    http.get(`${API}/catalogo`, () => {
      conteggio.letture += 1;
      return HttpResponse.json(pagina([]));
    }),
  );
  return conteggio;
}
