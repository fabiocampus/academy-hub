/**
 * Errori di un form della gestione: i 422 vanno sui campi, il resto resta in cima al
 * form senza chiuderlo (non si perde quel che si è scritto). Con un 412 la risorsa è
 * cambiata dopo la lettura: si ricaricano i dati e si rifà la modifica.
 */
import { ErroreApi, erroriDeiCampi } from "../../api/client";
import { Errore } from "../../componenti/Stati";

/** I messaggi per campo del 422, se ce ne sono; altrimenti `null`. */
export function campiNonValidi(errore: unknown): Record<string, string> | null {
  const campi = erroriDeiCampi(errore);
  return Object.keys(campi).length > 0 ? campi : null;
}

export function versioneSuperata(errore: unknown): boolean {
  return errore instanceof ErroreApi && errore.stato === 412;
}

/**
 * Stato della lettura con ETag che apre una modifica. «pronta» solo dopo una lettura
 * fatta da questa apertura: una copia rimasta in cache porterebbe un ETag vecchio.
 * Con i dati già letti, un errore di una rilettura in background (per esempio dopo un
 * 412) non toglie il form: i valori scritti restano.
 */
export function statoLettura(lettura: {
  data: unknown;
  isError: boolean;
  isFetchedAfterMount: boolean;
}): "caricamento" | "errore" | "pronta" {
  if (!lettura.isFetchedAfterMount) {
    return "caricamento";
  }
  if (lettura.data === undefined) {
    return lettura.isError ? "errore" : "caricamento";
  }
  return "pronta";
}

export function ErroreForm({ errore, ricarica }: { errore: unknown; ricarica?: () => void }) {
  if (errore === null) {
    return null;
  }
  if (versioneSuperata(errore) && ricarica !== undefined) {
    return <Errore errore={errore} riprova={ricarica} azione="Ricarica i dati" />;
  }
  return <Errore errore={errore} />;
}
