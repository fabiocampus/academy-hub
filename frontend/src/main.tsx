import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "./stile.css";

import { Alert, Center, MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { Accesso } from "./accesso/Accesso";
import { riprova } from "./api/client";
import { leggiConfigurazione } from "./api/configurazione";
import { App } from "./App";
import { messaggio } from "./componenti/Stati";
import { tema } from "./tema";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: riprova },
  },
});

const elemento = document.getElementById("root");
if (elemento === null) {
  throw new Error("Manca #root in index.html");
}
const radice = createRoot(elemento);

function mostra(contenuto: ReactNode): void {
  radice.render(
    <StrictMode>
      <MantineProvider theme={tema}>
        <Notifications />
        {contenuto}
      </MantineProvider>
    </StrictMode>,
  );
}

leggiConfigurazione().then(
  (configurazione) => {
    mostra(
      <Accesso configurazione={configurazione}>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </Accesso>,
    );
  },
  (errore: unknown) => {
    const { titolo, dettaglio } = messaggio(errore);
    mostra(
      <Center h="100vh" p="md">
        <Alert color="red" title={titolo} maw={520}>
          {dettaglio ?? "Impossibile leggere come si accede."}
        </Alert>
      </Center>,
    );
  },
);
