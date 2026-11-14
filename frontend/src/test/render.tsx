import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";

import { ContestoSessione, type Sessione } from "../accesso/contesto";
import { tema, variabiliCss } from "../tema";

interface Opzioni {
  percorso?: string;
  sessione?: Sessione;
}

/** Il componente con i provider dell'app; nessun retry per vedere subito gli errori. */
export function mostra(elemento: ReactElement, opzioni: Opzioni = {}): RenderResult {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider theme={tema} cssVariablesResolver={variabiliCss}>
      <Notifications />
      <ContestoSessione.Provider value={opzioni.sessione ?? {}}>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[opzioni.percorso ?? "/"]}>{elemento}</MemoryRouter>
        </QueryClientProvider>
      </ContestoSessione.Provider>
    </MantineProvider>,
  );
}
