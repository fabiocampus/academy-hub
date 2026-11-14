/** Gestione Academy (issue #64): i corsi, archiviati compresi; creazione, modifica, archiviazione. */
import {
  Anchor,
  Badge,
  Button,
  Group,
  Modal,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useState } from "react";
import { Link } from "react-router";

import type { Schemi } from "../../api/client";
import { useArchiviaCorso, useCorsi, useCorso } from "../../api/gestione";
import { avvisaSuccesso } from "../../componenti/avvisi";
import { Conferma } from "../../componenti/Conferma";
import { Paginazione } from "../../componenti/Paginazione";
import { Caricamento, Errore, Vuoto } from "../../componenti/Stati";
import { ErroreForm } from "./ErroreForm";
import { ModificaCorso, NuovoCorso } from "./FormCorso";

export const PER_PAGINA = 20;

type Corso = Schemi["CorsoLetto"];

export function Corsi() {
  const [titolo, setTitolo] = useState("");
  const [cercato] = useDebouncedValue(titolo.trim(), 300);
  const [pagina, setPagina] = useState(1);
  const corsi = useCorsi({
    titolo: cercato,
    limite: PER_PAGINA,
    offset: (pagina - 1) * PER_PAGINA,
  });
  const [nuovo, setNuovo] = useState(false);
  const [daModificare, setDaModificare] = useState<Corso | null>(null);
  const [daArchiviare, setDaArchiviare] = useState<Corso | null>(null);

  return (
    <Stack>
      <Group justify="space-between" align="flex-end">
        <Title order={1}>Gestione corsi</Title>
        <Button
          onClick={() => {
            setNuovo(true);
          }}
        >
          Nuovo corso
        </Button>
      </Group>
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
      {corsi.isPending && <Caricamento etichetta="Caricamento dei corsi" />}
      {corsi.isError && <Errore errore={corsi.error} riprova={() => void corsi.refetch()} />}
      {corsi.isSuccess && corsi.data.totale === 0 && (
        <Vuoto>{cercato ? `Nessun corso per «${cercato}».` : "Nessun corso: creane uno."}</Vuoto>
      )}
      {corsi.isSuccess && corsi.data.totale > 0 && (
        <>
          <Table.ScrollContainer minWidth={640}>
            <Table striped aria-busy={corsi.isPlaceholderData}>
              <caption className="solo-lettori-schermo">Corsi</caption>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th scope="col">Titolo</Table.Th>
                  <Table.Th scope="col">Durata</Table.Th>
                  <Table.Th scope="col">Stato</Table.Th>
                  <Table.Th scope="col">Azioni</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {corsi.data.elementi.map((corso) => (
                  <Table.Tr key={corso.id}>
                    <Table.Td>
                      <Anchor component={Link} to={`/gestione/corsi/${String(corso.id)}`}>
                        {corso.titolo}
                      </Anchor>
                    </Table.Td>
                    <Table.Td>{corso.durata_ore} ore</Table.Td>
                    <Table.Td>
                      {corso.archiviato_il === null ? (
                        <Badge color="green" variant="light">
                          Attivo
                        </Badge>
                      ) : (
                        <Badge color="gray" variant="light">
                          Archiviato
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Group gap="xs" wrap="nowrap">
                        <Button
                          size="xs"
                          variant="light"
                          aria-label={`Modifica ${corso.titolo}`}
                          onClick={() => {
                            setDaModificare(corso);
                          }}
                        >
                          Modifica
                        </Button>
                        {corso.archiviato_il === null && (
                          <Button
                            size="xs"
                            variant="light"
                            color="red"
                            aria-label={`Archivia ${corso.titolo}`}
                            onClick={() => {
                              setDaArchiviare(corso);
                            }}
                          >
                            Archivia
                          </Button>
                        )}
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Paginazione
            totale={corsi.data.totale}
            perPagina={PER_PAGINA}
            pagina={pagina}
            cambia={setPagina}
            di="dei corsi"
            conteggio={corsi.data.totale === 1 ? "1 corso" : `${String(corsi.data.totale)} corsi`}
          />
        </>
      )}
      <Modal
        opened={nuovo}
        onClose={() => {
          setNuovo(false);
        }}
        title="Nuovo corso"
      >
        <NuovoCorso
          chiudi={() => {
            setNuovo(false);
          }}
        />
      </Modal>
      <Modal
        opened={daModificare !== null}
        onClose={() => {
          setDaModificare(null);
        }}
        title="Modifica del corso"
      >
        {daModificare !== null && (
          <ModificaCorso
            id={daModificare.id}
            chiudi={() => {
              setDaModificare(null);
            }}
          />
        )}
      </Modal>
      {daArchiviare !== null && (
        <ConfermaArchiviazione
          corso={daArchiviare}
          chiudi={() => {
            setDaArchiviare(null);
          }}
        />
      )}
    </Stack>
  );
}

/** L'archiviazione vuole l'ETag: lo legge all'apertura, come una modifica. */
function ConfermaArchiviazione({ corso, chiudi }: { corso: Corso; chiudi: () => void }) {
  const letto = useCorso(corso.id);
  const archiviazione = useArchiviaCorso();
  const [errore, setErrore] = useState<unknown>(null);

  function archivia(): void {
    if (letto.data === undefined) {
      return;
    }
    setErrore(null);
    archiviazione.mutate(
      { id: corso.id, etag: letto.data.etag },
      {
        onSuccess: () => {
          avvisaSuccesso(`Corso «${corso.titolo}» archiviato.`);
          chiudi();
        },
        onError: setErrore,
      },
    );
  }

  return (
    <Conferma
      aperta
      titolo="Archiviare il corso?"
      azione="Archivia il corso"
      inCorso={archiviazione.isPending}
      pronta={letto.isSuccess}
      conferma={archivia}
      chiudi={chiudi}
    >
      <ErroreForm errore={errore ?? (letto.isError ? letto.error : null)} />
      <Text>
        «{corso.titolo}» e le sue edizioni escono dal catalogo e non se ne potranno pianificare
        altre. Le edizioni e le iscrizioni già fatte restano.
      </Text>
    </Conferma>
  );
}
