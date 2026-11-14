/** Intestazione, menu e area principale; il menu dipende dal profilo (ruoli). */
import { AppShell, Burger, Button, Group, NavLink, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { Suspense } from "react";
import { NavLink as Collegamento, Outlet, useLocation } from "react-router";

import { useSessione } from "../accesso/contesto";
import type { Schemi } from "../api/client";
import { useProfilo } from "../api/query";
import { ConfinePagina } from "./ConfinePagina";
import { Caricamento, Errore } from "./Stati";

export interface VoceMenu {
  percorso: string;
  etichetta: string;
}

/**
 * Le voci che il profilo può usare. È solo comodità: le pagine restano raggiungibili
 * dall'indirizzo e l'API rifiuta comunque con 403 le azioni non permesse (matrice in
 * backend/tests/test_autorizzazione.py).
 */
export function vociMenu(profilo: Schemi["Profilo"]): VoceMenu[] {
  const voci: VoceMenu[] = [{ percorso: "/", etichetta: "Catalogo" }];
  if (profilo.ruoli.includes("dipendente")) {
    voci.push({ percorso: "/iscrizioni", etichetta: "Le mie iscrizioni" });
  }
  // Decide il responsabile diretto; per chi non ne ha uno sopra, l'admin Academy (US-07).
  if (profilo.responsabile_di_team || profilo.ruoli.includes("admin_academy")) {
    voci.push({ percorso: "/approvazioni", etichetta: "Approvazioni" });
  }
  if (profilo.ruoli.includes("admin_academy")) {
    voci.push({ percorso: "/gestione", etichetta: "Gestione" });
  }
  return voci;
}

export function Struttura() {
  const profilo = useProfilo();
  const { pathname } = useLocation();
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
              aria-label={aperto ? "Chiudi il menu" : "Apri il menu"}
              aria-expanded={aperto}
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
          vociMenu(profilo.data).map((voce) => (
            <NavLink
              key={voce.percorso}
              component={Collegamento}
              to={voce.percorso}
              end={voce.percorso !== "/gestione"}
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
        {profilo.isSuccess && (
          // Le pagine arrivano in chunk separati (App.tsx): intestazione e menu restano,
          // anche se un chunk non arriva; il confine riparte a ogni cambio di pagina.
          <ConfinePagina key={pathname}>
            <Suspense fallback={<Caricamento etichetta="Caricamento della pagina" />}>
              <Outlet />
            </Suspense>
          </ConfinePagina>
        )}
      </AppShell.Main>
    </AppShell>
  );
}
