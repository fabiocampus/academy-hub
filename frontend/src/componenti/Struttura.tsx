/** Intestazione fissa, menu e area principale; il menu dipende dal profilo (ruoli). */
import { Burger, Button } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { Suspense, useEffect } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";

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

/** Il marchio della pagina pubblica (un anello), nel colore d'azione. */
function Marchio() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        fillRule="evenodd"
        d="M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20zm0 5.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9z"
      />
    </svg>
  );
}

export function Struttura() {
  const profilo = useProfilo();
  const { pathname } = useLocation();
  const { esci } = useSessione();
  const [aperto, { toggle, close }] = useDisclosure();

  // Il pannello a tutto schermo del telefono si chiude con Esc.
  useEffect(() => {
    if (!aperto) return;
    const suEsc = (evento: KeyboardEvent) => {
      if (evento.key === "Escape") close();
    };
    document.addEventListener("keydown", suEsc);
    return () => {
      document.removeEventListener("keydown", suEsc);
    };
  }, [aperto, close]);

  return (
    <>
      <a className="salta" href="#contenuto">
        Vai al contenuto
      </a>
      <header className="testata">
        <div className="testata__barra">
          <Link className="marchio" to="/" onClick={close}>
            <Marchio />
            Academy Hub
          </Link>
          <nav
            id="menu-principale"
            className="menu"
            aria-label="Menu principale"
            data-aperto={aperto || undefined}
          >
            {profilo.data !== undefined &&
              vociMenu(profilo.data).map((voce) => (
                <NavLink
                  key={voce.percorso}
                  className="menu__voce"
                  to={voce.percorso}
                  end={voce.percorso !== "/gestione"}
                  onClick={close}
                >
                  {voce.etichetta}
                </NavLink>
              ))}
          </nav>
          <div className="testata__destra">
            {profilo.data !== undefined && (
              <span className="testata__persona">{profilo.data.nome}</span>
            )}
            {esci !== undefined && (
              <Button variant="default" size="sm" onClick={esci}>
                Esci
              </Button>
            )}
            <Burger
              className="testata__menu"
              opened={aperto}
              onClick={toggle}
              size="sm"
              aria-label={aperto ? "Chiudi il menu" : "Apri il menu"}
              aria-expanded={aperto}
              aria-controls="menu-principale"
            />
          </div>
        </div>
      </header>
      <main id="contenuto" className="contenuto" tabIndex={-1}>
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
      </main>
    </>
  );
}
