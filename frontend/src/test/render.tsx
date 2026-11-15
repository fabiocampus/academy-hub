import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";

import { ContestoSessione, type Sessione } from "../accesso/contesto";
import { ContestoFlag, FLAG_SPENTE, type Flag } from "../api/flag";
import { tema, variabiliCss } from "../tema";

interface Opzioni {
  percorso?: string;
  sessione?: Sessione;
  flag?: Flag;
}

/** Il componente con i provider dell'app; nessun retry per vedere subito gli errori. */
export function mostra(elemento: ReactElement, opzioni: Opzioni = {}): RenderResult {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider theme={tema} cssVariablesResolver={variabiliCss}>
      <Notifications />
      <ContestoSessione.Provider value={opzioni.sessione ?? {}}>
        <ContestoFlag.Provider value={opzioni.flag ?? FLAG_SPENTE}>
          <QueryClientProvider client={queryClient}>
            <MemoryRouter initialEntries={[opzioni.percorso ?? "/"]}>{elemento}</MemoryRouter>
          </QueryClientProvider>
        </ContestoFlag.Provider>
      </ContestoSessione.Provider>
    </MantineProvider>,
  );
}
