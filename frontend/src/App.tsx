import { lazy } from "react";
import { Route, Routes } from "react-router";

import { Struttura } from "./componenti/Struttura";
import { Vuoto } from "./componenti/Stati";

// Una pagina per chunk, scaricata alla prima visita (ADR-0009 §16): chi non gestisce i
// corsi non scarica mai le pagine di gestione.
const Catalogo = lazy(() => import("./pagine/Catalogo").then((m) => ({ default: m.Catalogo })));
const MieIscrizioni = lazy(() =>
  import("./pagine/MieIscrizioni").then((m) => ({ default: m.MieIscrizioni })),
);
const Approvazioni = lazy(() =>
  import("./pagine/Approvazioni").then((m) => ({ default: m.Approvazioni })),
);
const Corsi = lazy(() => import("./pagine/gestione/Corsi").then((m) => ({ default: m.Corsi })));
const EdizioniCorso = lazy(() =>
  import("./pagine/gestione/EdizioniCorso").then((m) => ({ default: m.EdizioniCorso })),
);
const IscrizioniEdizione = lazy(() =>
  import("./pagine/gestione/IscrizioniEdizione").then((m) => ({ default: m.IscrizioniEdizione })),
);

export function App() {
  return (
    <Routes>
      <Route element={<Struttura />}>
        <Route index element={<Catalogo />} />
        <Route path="iscrizioni" element={<MieIscrizioni />} />
        <Route path="approvazioni" element={<Approvazioni />} />
        <Route path="gestione" element={<Corsi />} />
        <Route path="gestione/corsi/:corsoId" element={<EdizioniCorso />} />
        <Route path="gestione/edizioni/:edizioneId" element={<IscrizioniEdizione />} />
        <Route path="*" element={<Vuoto>Pagina non trovata.</Vuoto>} />
      </Route>
    </Routes>
  );
}
