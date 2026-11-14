/** Esito delle azioni (richiedi, annulla, approva, ...) come notifiche. */
import { notifications } from "@mantine/notifications";

import { messaggio } from "./Stati";

/** Annunciato con garbo (`status`): non interrompe il lettore di schermo. */
export function avvisaSuccesso(testo: string): void {
  notifications.show({ color: "green", message: testo, role: "status" });
}

/** Il problema RFC 9457 dell'API con titolo e dettaglio; resta finché non si chiude. */
export function avvisaErrore(errore: unknown): void {
  const { titolo, dettaglio } = messaggio(errore);
  notifications.show({
    color: "red",
    title: titolo,
    message: dettaglio ?? "",
    autoClose: false,
    role: "alert",
  });
}
