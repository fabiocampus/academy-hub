/**
 * Come si entra (ADR-0008): con `oidc` il login è nostro (authorization code + PKCE sul
 * client pubblico di Keycloak); con `databricks` lo ha già fatto la piattaforma e il
 * proxy aggiunge l'identità a ogni richiesta, quindi non c'è niente da fare.
 */
import { Alert, Button, Center, Loader, Stack, Text, Title } from "@mantine/core";
import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import { useState, type ReactNode } from "react";
import { AuthProvider, useAuth } from "react-oidc-context";

import { impostaAlNonAutenticato, impostaToken } from "../api/client";
import type { Configurazione } from "../api/configurazione";
import { ContestoSessione } from "./contesto";

type Oidc = NonNullable<Configurazione["oidc"]>;

export function creaGestoreOidc(oidc: Oidc, origine = window.location.origin): UserManager {
  return new UserManager({
    authority: oidc.emittente,
    client_id: oidc.client_id,
    redirect_uri: `${origine}/`,
    post_logout_redirect_uri: `${origine}/`,
    scope: "openid email profile",
    // sessionStorage: il token sparisce con la scheda, non resta sul disco.
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  });
}

/**
 * Il client HTTP prende il token dal gestore; un token scaduto (rinnovo silenzioso
 * fallito, scheda rimasta in background) non si manda. Un 401 toglie l'utente: si
 * torna alla schermata d'accesso.
 */
export function collegaAlClient(gestore: UserManager): void {
  impostaToken(async () => {
    const utente = await gestore.getUser();
    return utente === null || utente.expired === true ? undefined : utente.access_token;
  });
  impostaAlNonAutenticato(() => void gestore.removeUser());
}

/** Toglie `code` e `state` dall'indirizzo dopo il ritorno da Keycloak. */
function dopoIlLogin(): void {
  window.history.replaceState({}, document.title, window.location.pathname);
}

interface Proprieta {
  configurazione: Configurazione;
  children: ReactNode;
}

export function Accesso({ configurazione, children }: Proprieta) {
  switch (configurazione.identita) {
    case "oidc": {
      if (configurazione.oidc === null) {
        return <ErroreConfigurazione dettaglio="Manca l'emittente OIDC." />;
      }
      return <AccessoOidc oidc={configurazione.oidc}>{children}</AccessoOidc>;
    }
    case "databricks":
      return children;
    case "provvisoria":
      return (
        <ErroreConfigurazione dettaglio="Il backend usa l'identità provvisoria X-Persona-Id, che serve solo ai test dell'API. Avvialo con ACADEMY_IDENTITA=oidc." />
      );
  }
}

function AccessoOidc({ oidc, children }: { oidc: Oidc; children: ReactNode }) {
  // Un solo gestore per tutta la vita della pagina: tiene il token e lo rinnova.
  const [gestore] = useState(() => {
    const creato = creaGestoreOidc(oidc);
    collegaAlClient(creato);
    return creato;
  });
  return (
    <AuthProvider userManager={gestore} onSigninCallback={dopoIlLogin}>
      <ConLogin>{children}</ConLogin>
    </AuthProvider>
  );
}

function ConLogin({ children }: { children: ReactNode }) {
  const auth = useAuth();

  if (auth.isLoading || auth.activeNavigator !== undefined) {
    return (
      <Center h="100vh" role="status" aria-label="Accesso in corso">
        <Loader />
      </Center>
    );
  }
  if (!auth.isAuthenticated) {
    return (
      <Center h="100vh">
        <Stack align="center" maw={420} p="md">
          <Title order={1}>Academy Hub</Title>
          <Text>Iscrizioni ai corsi dell&apos;Academy.</Text>
          {auth.error !== undefined && (
            <Alert color="red" title="Accesso non riuscito" w="100%">
              {auth.error.message}
            </Alert>
          )}
          <Button onClick={() => void auth.signinRedirect()}>Accedi</Button>
        </Stack>
      </Center>
    );
  }
  return (
    <ContestoSessione.Provider value={{ esci: () => void auth.signoutRedirect() }}>
      {children}
    </ContestoSessione.Provider>
  );
}

function ErroreConfigurazione({ dettaglio }: { dettaglio: string }) {
  return (
    <Center h="100vh" p="md">
      <Alert color="red" title="Accesso non configurato" maw={520}>
        {dettaglio}
      </Alert>
    </Center>
  );
}
