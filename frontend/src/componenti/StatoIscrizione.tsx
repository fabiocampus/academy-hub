import { Badge } from "@mantine/core";

import type { Schemi } from "../api/client";

export type Stato = Schemi["StatoIscrizione"];

const COLORE: Record<Stato, string> = {
  Richiesta: "blu",
  Approvata: "teal",
  InAttesa: "yellow",
  Confermata: "green",
  Rifiutata: "gray",
  Annullata: "gray",
  Completata: "gray",
};

const ETICHETTA: Record<Stato, string> = {
  Richiesta: "Richiesta",
  Approvata: "Approvata",
  InAttesa: "In attesa",
  Confermata: "Confermata",
  Rifiutata: "Rifiutata",
  Annullata: "Annullata",
  Completata: "Completata",
};

/** Gli stati da cui il titolare può annullare (CONTEXT.md, transizioni verso Annullata). */
export const STATI_ANNULLABILI: ReadonlySet<Stato> = new Set([
  "Richiesta",
  "Approvata",
  "InAttesa",
  "Confermata",
]);

export function StatoIscrizione({ stato }: { stato: Stato }) {
  return (
    <Badge color={COLORE[stato]} variant="light">
      {ETICHETTA[stato]}
    </Badge>
  );
}
