/** Finestra che chiede conferma prima di un'azione che non si può disfare. */
import { Button, Group, Modal, Stack } from "@mantine/core";
import type { ReactNode } from "react";

interface Proprieta {
  aperta: boolean;
  titolo: string;
  /** Etichetta del pulsante che esegue, es. «Archivia il corso». */
  azione: string;
  inCorso: boolean;
  /** Disattiva il pulsante, es. finché manca l'ETag da mandare. */
  pronta?: boolean;
  conferma: () => void;
  chiudi: () => void;
  children: ReactNode;
}

export function Conferma({
  aperta,
  titolo,
  azione,
  inCorso,
  pronta = true,
  conferma,
  chiudi,
  children,
}: Proprieta) {
  return (
    <Modal opened={aperta} onClose={chiudi} title={titolo}>
      <Stack>
        {children}
        <Group justify="flex-end">
          <Button variant="default" onClick={chiudi}>
            Indietro
          </Button>
          <Button color="red" loading={inCorso} disabled={!pronta} onClick={conferma}>
            {azione}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
