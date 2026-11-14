import { Alert, Button, Stack, Text } from "@mantine/core";
import { Component, type ReactNode } from "react";

interface Stato {
  errore: boolean;
}

/**
 * Confine d'errore attorno alla pagina (ADR-0009 §16). Il caso tipico è un chunk lazy
 * che non arriva: dopo un rilascio i nomi con l'hash cambiano e il vecchio risponde 404.
 * Senza confine React smonterebbe tutta l'app; così restano menu e intestazione e si
 * offre di ricaricare. La Struttura lo rimonta (key) a ogni cambio di pagina.
 */
export class ConfinePagina extends Component<{ children: ReactNode }, Stato> {
  override state: Stato = { errore: false };

  static getDerivedStateFromError(): Stato {
    return { errore: true };
  }

  override render(): ReactNode {
    if (!this.state.errore) {
      return this.props.children;
    }
    return (
      <Alert color="red" title="Questa pagina non si è caricata" role="alert">
        <Stack gap="xs" align="flex-start">
          <Text size="sm">Forse è uscita una versione nuova dell&apos;app.</Text>
          <Button
            size="xs"
            variant="light"
            color="red"
            onClick={() => {
              window.location.reload();
            }}
          >
            Ricarica l&apos;app
          </Button>
        </Stack>
      </Alert>
    );
  }
}
