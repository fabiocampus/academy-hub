import { Route, Routes } from "react-router";

import { Struttura } from "./componenti/Struttura";
import { Vuoto } from "./componenti/Stati";
import { Approvazioni } from "./pagine/Approvazioni";
import { Catalogo } from "./pagine/Catalogo";
import { Corsi } from "./pagine/gestione/Corsi";
import { EdizioniCorso } from "./pagine/gestione/EdizioniCorso";
import { IscrizioniEdizione } from "./pagine/gestione/IscrizioniEdizione";
import { MieIscrizioni } from "./pagine/MieIscrizioni";

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
