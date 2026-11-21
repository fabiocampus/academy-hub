/**
 * Come si entra (ADR-0008): con `oidc` il login è nostro (authorization code + PKCE sul
 * client pubblico di Keycloak); con `databricks` lo ha già fatto la piattaforma e il
 * proxy aggiunge l'identità a ogni richiesta, quindi non c'è niente da fare.
 *
 * Con `oidc` chi arriva senza sessione va alla pagina pubblica statica
 * (`public/benvenuto.html`, ADR-0020); il suo «Accedi» torna qui con `?accedi=1`, che
 * fa partire il login verso la pagina aperta all'inizio.
 */
import { Alert, Button, Center, Loader, Stack, Text, Title } from "@mantine/core";
import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";
import { useEffect, useState, type ReactNode } from "react";
import { AuthProvider, useAuth } from "react-oidc-context";

import { impostaAlNonAutenticato, impostaToken } from "../api/client";
import type { Configurazione } from "../api/configurazione";
import { ContestoSessione } from "./contesto";
import { navigazione } from "./navigazione";

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

/** La pagina pubblica per chi non ha una sessione (servita come file statico). */
export const PAGINA_PUBBLICA = "/benvenuto.html";
/** Dove la pagina aperta senza sessione aspetta il login (sessionStorage, solo un percorso). */
export const CHIAVE_RITORNO = "academy.ritorno";
/** Il parametro con cui la pagina pubblica chiede di far partire il login. */
const PARAMETRO_ACCEDI = "accedi";

/** Dove tornare dopo il login: la pagina aperta quando si è arrivati senza sessione. */
interface StatoLogin {
  ritorno: string;
}

export function statoLogin(posizione: Pick<Location, "pathname" | "search" | "hash">): StatoLogin {
  return { ritorno: posizione.pathname + posizione.search + posizione.hash };
}

/**
 * Il percorso salvato nello `state` del login, solo se resta sulla stessa origine: un
 * indirizzo assoluto o `//host` porterebbe fuori (open redirect). Altrimenti la radice.
 */
export function percorsoDiRitorno(stato: unknown, origine = window.location.origin): string {
  if (typeof stato !== "object" || stato === null || !("ritorno" in stato)) {
    return "/";
  }
  const { ritorno } = stato;
  if (typeof ritorno !== "string" || !ritorno.startsWith("/")) {
    return "/";
  }
  // Normalizzato come lo farebbe il browser (`/<tab>/host` diventa `//host`): conta l'origine.
  try {
    const indirizzo = new URL(ritorno, origine);
    return indirizzo.origin === origine
      ? indirizzo.pathname + indirizzo.search + indirizzo.hash
      : "/";
  } catch {
    return "/";
  }
}

/**
 * Toglie `code` e `state` dall'indirizzo dopo il ritorno da Keycloak e riporta alla
 * pagina chiesta. Gira prima che il router venga montato, che quindi legge già questa.
 */
export function dopoIlLogin(utente: User | undefined): void {
  window.history.replaceState({}, document.title, percorsoDiRitorno(utente?.state));
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

/** Il ritorno salvato prima di andare alla pagina pubblica, letto una volta sola. */
function prendiRitorno(): StatoLogin {
  const salvato = window.sessionStorage.getItem(CHIAVE_RITORNO);
  window.sessionStorage.removeItem(CHIAVE_RITORNO);
  // Ripassa dal controllo dell'origine: sessionStorage è scrivibile da qualunque script.
  return { ritorno: percorsoDiRitorno({ ritorno: salvato }) };
}

function ConLogin({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const inAttesa = auth.isLoading || auth.activeNavigator !== undefined;
  const senzaSessione = !inAttesa && !auth.isAuthenticated && auth.error === undefined;
  // react-oidc-context dà funzioni già legate e stabili: destrutturarla tiene l'effetto fermo.
  // eslint-disable-next-line @typescript-eslint/unbound-method
  const { signinRedirect } = auth;

  useEffect(() => {
    if (!senzaSessione) {
      return;
    }
    if (new URLSearchParams(window.location.search).get(PARAMETRO_ACCEDI) === "1") {
      void signinRedirect({ state: prendiRitorno() });
      return;
    }
    window.sessionStorage.setItem(CHIAVE_RITORNO, statoLogin(window.location).ritorno);
    navigazione.sostituisci(PAGINA_PUBBLICA);
  }, [senzaSessione, signinRedirect]);

  if (inAttesa || senzaSessione) {
    return (
      <Center h="100vh" role="status" aria-label="Accesso in corso">
        <Loader />
      </Center>
    );
  }
  if (!auth.isAuthenticated) {
    return (
      <Center h="100vh">
        <Stack align="flex-start" maw={480} p="md" gap="md">
          <Title order={1}>Accesso non riuscito</Title>
          <Text c="dimmed">
            Il login con l&apos;account aziendale non è andato a buon fine. Riprova; se succede
            ancora, scrivi all&apos;amministratore Academy.
          </Text>
          <Alert color="red" w="100%">
            {auth.error?.message}
          </Alert>
          <Button onClick={() => void auth.signinRedirect({ state: { ritorno: "/" } })}>
            Riprova ad accedere
          </Button>
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
