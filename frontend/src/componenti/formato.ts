const data = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short", year: "numeric" });

/** `2026-03-10` (data del contratto, senza fuso) → `10 mar 2026`. */
export function formattaData(iso: string): string {
  const [anno, mese, giorno] = iso.split("-").map(Number);
  return data.format(new Date(anno ?? 0, (mese ?? 1) - 1, giorno ?? 1));
}
