import { Group, Pagination, Text } from "@mantine/core";

interface Proprieta {
  totale: number;
  perPagina: number;
  pagina: number;
  cambia: (pagina: number) => void;
  /** Nome dell'elenco per i lettori di schermo, es. «catalogo». */
  di: string;
  /** Testo del conteggio, es. `12 edizioni`. */
  conteggio: string;
}

export function Paginazione({ totale, perPagina, pagina, cambia, di, conteggio }: Proprieta) {
  return (
    <Group justify="space-between">
      <Text size="sm" c="dimmed">
        {conteggio}
      </Text>
      <Pagination
        total={Math.ceil(totale / perPagina)}
        value={pagina}
        onChange={cambia}
        aria-label={`Pagine ${di}`}
        getControlProps={(controllo) => ({
          "aria-label": controllo === "previous" ? "Pagina precedente" : "Pagina successiva",
        })}
        getItemProps={(numero) => ({ "aria-label": `Pagina ${numero}` })}
      />
    </Group>
  );
}
