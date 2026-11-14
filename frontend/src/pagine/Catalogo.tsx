/** US-03: catalogo delle edizioni, filtrabile per titolo e paginato. */
import { Badge, Group, Pagination, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useState } from "react";

import type { Schemi } from "../api/client";
import { useCatalogo } from "../api/query";
import { formattaData } from "../componenti/formato";
import { Caricamento, Errore, Vuoto } from "../componenti/Stati";

export const PER_PAGINA = 20;

const COLORE_STATO: Record<Schemi["StatoIscrizione"], string> = {
  Richiesta: "blue",
  Approvata: "teal",
  InAttesa: "yellow",
  Confermata: "green",
  Rifiutata: "gray",
  Annullata: "gray",
  Completata: "gray",
};

export function Catalogo() {
  const [titolo, setTitolo] = useState("");
  const [cercato] = useDebouncedValue(titolo.trim(), 300);
  const [pagina, setPagina] = useState(1);
  const catalogo = useCatalogo({
    titolo: cercato,
    limite: PER_PAGINA,
    offset: (pagina - 1) * PER_PAGINA,
  });

  return (
    <Stack>
      <Title order={1}>Catalogo</Title>
      <TextInput
        label="Cerca per titolo"
        type="search"
        value={titolo}
        maxLength={200}
        onChange={(evento) => {
          setTitolo(evento.currentTarget.value);
          setPagina(1);
        }}
        maw={360}
      />
      {catalogo.isPending && <Caricamento etichetta="Caricamento del catalogo" />}
      {catalogo.isError && (
        <Errore errore={catalogo.error} riprova={() => void catalogo.refetch()} />
      )}
      {catalogo.isSuccess && catalogo.data.totale === 0 && (
        <Vuoto>
          {cercato ? `Nessuna edizione per «${cercato}».` : "Nessuna edizione in programma."}
        </Vuoto>
      )}
      {catalogo.isSuccess && catalogo.data.totale > 0 && (
        <>
          <Table.ScrollContainer minWidth={640}>
            <Table striped aria-busy={catalogo.isPlaceholderData}>
              <caption className="solo-lettori-schermo">Edizioni in catalogo</caption>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th scope="col">Corso</Table.Th>
                  <Table.Th scope="col">Date</Table.Th>
                  <Table.Th scope="col">Posti</Table.Th>
                  <Table.Th scope="col">In attesa</Table.Th>
                  <Table.Th scope="col">La mia iscrizione</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {catalogo.data.elementi.map((voce) => (
                  <Table.Tr key={voce.edizione_id}>
                    <Table.Td>
                      <Text fw={500}>{voce.corso.titolo}</Text>
                      <Text size="xs" c="dimmed">
                        {voce.corso.durata_ore} ore
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      {formattaData(voce.data_inizio)} – {formattaData(voce.data_fine)}
                    </Table.Td>
                    <Table.Td>
                      {voce.capienza - voce.posti_confermati} liberi su {voce.capienza}
                    </Table.Td>
                    <Table.Td>{voce.lista_attesa}</Table.Td>
                    <Table.Td>
                      {voce.mia_iscrizione === null ? (
                        "—"
                      ) : (
                        <Badge color={COLORE_STATO[voce.mia_iscrizione.stato]} variant="light">
                          {voce.mia_iscrizione.stato}
                        </Badge>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Group justify="space-between">
            <Text size="sm" c="dimmed">
              {catalogo.data.totale} edizioni
            </Text>
            <Pagination
              total={Math.ceil(catalogo.data.totale / PER_PAGINA)}
              value={pagina}
              onChange={setPagina}
              aria-label="Pagine del catalogo"
              getControlProps={(controllo) => ({
                "aria-label": controllo === "previous" ? "Pagina precedente" : "Pagina successiva",
              })}
              getItemProps={(numero) => ({ "aria-label": `Pagina ${numero}` })}
            />
          </Group>
        </>
      )}
    </Stack>
  );
}
