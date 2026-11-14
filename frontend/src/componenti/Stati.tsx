/** Stati comuni delle schermate: caricamento, errore, vuoto. */
import { Alert, Button, Center, Loader, Stack, Text } from "@mantine/core";
import type { ReactNode } from "react";

import { ErroreApi } from "../api/client";

export function Caricamento({ etichetta = "Caricamento" }: { etichetta?: string }) {
  return (
    <Center py="xl" role="status" aria-label={etichetta}>
      <Loader />
    </Center>
  );
}

export function messaggio(errore: unknown): { titolo: string; dettaglio?: string } {
  if (errore instanceof ErroreApi) {
    const { title, detail } = errore.problema;
    return detail ? { titolo: title, dettaglio: detail } : { titolo: title };
  }
  return { titolo: "Server non raggiungibile", dettaglio: "Controlla la connessione e riprova." };
}

export function Errore({
  errore,
  riprova,
  azione = "Riprova",
}: {
  errore: unknown;
  riprova?: () => void;
  /** Etichetta del pulsante, es. «Ricarica i dati» dopo un 412. */
  azione?: string;
}) {
  const { titolo, dettaglio } = messaggio(errore);
  return (
    <Alert color="red" title={titolo} role="alert">
      <Stack gap="xs" align="flex-start">
        {dettaglio !== undefined && <Text size="sm">{dettaglio}</Text>}
        {riprova !== undefined && (
          <Button size="xs" variant="light" color="red" onClick={riprova}>
            {azione}
          </Button>
        )}
      </Stack>
    </Alert>
  );
}

export function Vuoto({ children }: { children: ReactNode }) {
  return (
    <Text c="dimmed" ta="center" py="xl">
      {children}
    </Text>
  );
}
