import { Route, Routes } from "react-router";

import { Struttura } from "./componenti/Struttura";
import { Vuoto } from "./componenti/Stati";
import { Catalogo } from "./pagine/Catalogo";

export function App() {
  return (
    <Routes>
      <Route element={<Struttura />}>
        <Route index element={<Catalogo />} />
        <Route path="*" element={<Vuoto>Pagina non trovata.</Vuoto>} />
      </Route>
    </Routes>
  );
}
