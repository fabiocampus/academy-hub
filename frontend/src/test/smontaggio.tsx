/**
 * Esiti di un'azione quando il componente che l'ha lanciata non c'è più.
 *
 * React Query chiama i callback passati a `mutate()` solo se il componente è ancora
 * montato. Una riga che cambia dopo l'azione (il pulsante diventa uno stato, la richiesta
 * esce dall'elenco) può smontarsi prima: l'avviso dell'esito andrebbe perso. L'e2e lo
 * ha mostrato a caso; qui lo si rende certo smontando la pagina mentre la risposta aspetta.
 */
import type { RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { Link, Route, Routes } from "react-router";

import { mostra } from "./render";

/** La pagina su `rotta`, con un collegamento «Altrove» fuori: cliccarlo la smonta. */
export function mostraSmontabile(
  elemento: ReactElement,
  rotta = "/",
  percorso = rotta,
): RenderResult {
  return mostra(
    <>
      <Link to="/altrove">Altrove</Link>
      <Routes>
        <Route path={rotta} element={elemento} />
        <Route path="/altrove" element={null} />
      </Routes>
    </>,
    { percorso },
  );
}

/** Una risposta che arriva solo quando il test apre il cancello. */
export function cancello(): { attendi: Promise<void>; apri: () => void } {
  let apri = (): void => undefined;
  const attendi = new Promise<void>((risolvi) => {
    apri = risolvi;
  });
  return { attendi, apri };
}
