/** Intestazione, menu e area principale; il menu dipende dal profilo (ruoli). */
import { AppShell, Burger, Button, Group, NavLink, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { NavLink as Collegamento, Outlet } from "react-router";

import { useSessione } from "../accesso/contesto";
import { useProfilo } from "../api/query";
import { Caricamento, Errore } from "./Stati";

export interface VoceMenu {
  percorso: string;
  etichetta: string;
}

/**
 * Le voci che il profilo può usare (le schermate per ruolo arrivano con la PR B). È
 * solo comodità: l'API rifiuta comunque con 403 le azioni non permesse (matrice in
 * backend/tests/test_autorizzazione.py).
 */
export function vociMenu(): VoceMenu[] {
  return [{ percorso: "/", etichetta: "Catalogo" }];
}

export function Struttura() {
  const profilo = useProfilo();
  const { esci } = useSessione();
  const [aperto, { toggle, close }] = useDisclosure();

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: "sm", collapsed: { mobile: !aperto } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger
              opened={aperto}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label="Apri il menu"
            />
            <Text fw={700} size="lg">
              Academy Hub
            </Text>
          </Group>
          <Group gap="sm" wrap="nowrap">
            {profilo.data !== undefined && (
              <Text size="sm" visibleFrom="xs">
                {profilo.data.nome}
              </Text>
            )}
            {esci !== undefined && (
              <Button variant="subtle" size="xs" onClick={esci}>
                Esci
              </Button>
            )}
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs" aria-label="Menu principale">
        {profilo.data !== undefined &&
          vociMenu().map((voce) => (
            <NavLink
              key={voce.percorso}
              component={Collegamento}
              to={voce.percorso}
              label={voce.etichetta}
              onClick={close}
            />
          ))}
      </AppShell.Navbar>
      <AppShell.Main>
        {profilo.isPending && <Caricamento etichetta="Caricamento del profilo" />}
        {profilo.isError && (
          <Errore errore={profilo.error} riprova={() => void profilo.refetch()} />
        )}
        {profilo.isSuccess && <Outlet />}
      </AppShell.Main>
    </AppShell>
  );
}
