const data = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short", year: "numeric" });
const istante = new Intl.DateTimeFormat("it-IT", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Rome",
});

/** `2026-03-10` (data del contratto, senza fuso) → `10 mar 2026`. */
export function formattaData(iso: string): string {
  const [anno, mese, giorno] = iso.split("-").map(Number);
  return data.format(new Date(anno ?? 0, (mese ?? 1) - 1, giorno ?? 1));
}

/** Istante del contratto (con fuso) → data e ora di Roma, come le regole del dominio. */
export function formattaIstante(iso: string): string {
  return istante.format(new Date(iso));
}

/** Le due date di un'edizione: `10 mar 2027 – 11 mar 2027`. */
export function formattaPeriodo(inizio: string, fine: string): string {
  return `${formattaData(inizio)} – ${formattaData(fine)}`;
}

const giornoIso = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome" });

/** Oggi a Roma come `2027-03-10`, il calendario del dominio: confrontabile con le date ISO. */
export function oggiARoma(adesso: Date = new Date()): string {
  return giornoIso.format(adesso);
}

/** Un id dall'indirizzo (`/gestione/corsi/7`): intero positivo, altrimenti `null`. */
export function idDaPercorso(valore: string | undefined): number | null {
  if (valore === undefined || !/^[1-9]\d*$/.test(valore)) {
    return null;
  }
  const id = Number(valore);
  return Number.isSafeInteger(id) ? id : null;
}
