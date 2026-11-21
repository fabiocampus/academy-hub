/** L'intestazione di ogni pagina dell'App: ritorno, titolo (h1), una riga attenuata, l'azione. */
import { Anchor, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";
import { Link } from "react-router";

interface Proprieta {
  titolo: ReactNode;
  descrizione?: ReactNode;
  ritorno?: { a: string; etichetta: string };
  azione?: ReactNode;
}

export function IntestazionePagina({ titolo, descrizione, ritorno, azione }: Proprieta) {
  return (
    <header className="intestazione-pagina">
      <div className="intestazione-pagina__testo">
        {ritorno !== undefined && (
          <Anchor
            component={Link}
            to={ritorno.a}
            size="sm"
            className="intestazione-pagina__ritorno"
          >
            ← {ritorno.etichetta}
          </Anchor>
        )}
        <Title order={1}>{titolo}</Title>
        {descrizione !== undefined && <Text c="dimmed">{descrizione}</Text>}
      </div>
      {azione}
    </header>
  );
}
