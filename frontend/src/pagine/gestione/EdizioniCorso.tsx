/** Gestione Academy (issue #64): le edizioni di un corso, anche passate e cancellate. */
import { Anchor, Badge, Button, Group, Modal, Stack, Table, Text, Title } from "@mantine/core";
import { useState } from "react";
import { Link, useParams } from "react-router";

import type { Schemi } from "../../api/client";
import { useCancellaEdizione, useCorso, useDocenti, useEdizioniDelCorso } from "../../api/gestione";
import { avvisaErrore, avvisaSuccesso } from "../../componenti/avvisi";
import { Conferma } from "../../componenti/Conferma";
import { formattaPeriodo, idDaPercorso, oggiARoma } from "../../componenti/formato";
import { IntestazionePagina } from "../../componenti/IntestazionePagina";
import { Paginazione } from "../../componenti/Paginazione";
import { Caricamento, Errore, Vuoto } from "../../componenti/Stati";
import { ModificaEdizione, NuovaEdizione } from "./FormEdizione";

export const PER_PAGINA = 20;

type Voce = Schemi["VoceEdizione"];

/** Si modifica e si cancella solo un'edizione non cancellata e non ancora iniziata. */
function inProgramma(voce: Voce, oggi: string): boolean {
  return voce.cancellata_il === null && voce.data_inizio > oggi;
}

function StatoEdizione({ voce, oggi }: { voce: Voce; oggi: string }) {
  if (voce.cancellata_il !== null) {
    return (
      <Badge color="gray" variant="light">
        Cancellata
      </Badge>
    );
  }
  if (voce.data_inizio <= oggi) {
    return (
      <Badge color="gray" variant="outline">
        Iniziata
      </Badge>
    );
  }
  return (
    <Badge color="green" variant="light">
      In programma
    </Badge>
  );
}

export function EdizioniCorso() {
  const corsoId = idDaPercorso(useParams().corsoId);
  if (corsoId === null) {
    return (
      <Stack>
        <IntestazionePagina
          titolo="Edizioni del corso"
          ritorno={{ a: "/gestione", etichetta: "Tutti i corsi" }}
        />
        <Vuoto>Pagina non trovata.</Vuoto>
      </Stack>
    );
  }
  return <Edizioni corsoId={corsoId} />;
}

function Edizioni({ corsoId }: { corsoId: number }) {
  const corso = useCorso(corsoId);
  const [pagina, setPagina] = useState(1);
  const edizioni = useEdizioniDelCorso(corsoId, {
    limite: PER_PAGINA,
    offset: (pagina - 1) * PER_PAGINA,
  });
  const docenti = useDocenti();
  const nomi = new Map((docenti.data ?? []).map((d) => [d.id, d.nome]));
  const oggi = oggiARoma();
  const [nuova, setNuova] = useState(false);
  const [daModificare, setDaModificare] = useState<Voce | null>(null);
  const [daCancellare, setDaCancellare] = useState<Voce | null>(null);
  const archiviato = corso.data !== undefined && corso.data.dati.archiviato_il !== null;

  return (
    <Stack>
      {!corso.isSuccess && (
        <IntestazionePagina
          titolo="Edizioni del corso"
          ritorno={{ a: "/gestione", etichetta: "Tutti i corsi" }}
        />
      )}
      {corso.isPending && <Caricamento etichetta="Caricamento del corso" />}
      {corso.isError && <Errore errore={corso.error} riprova={() => void corso.refetch()} />}
      {corso.isSuccess && (
        <>
          <IntestazionePagina
            titolo={corso.data.dati.titolo}
            descrizione={
              <>
                {corso.data.dati.durata_ore} ore{archiviato && " · corso archiviato"}
              </>
            }
            ritorno={{ a: "/gestione", etichetta: "Tutti i corsi" }}
            azione={
              !archiviato && (
                <Button
                  onClick={() => {
                    setNuova(true);
                  }}
                >
                  Nuova edizione
                </Button>
              )
            }
          />
          <Title order={2} size="h3">
            Edizioni
          </Title>
          {edizioni.isPending && <Caricamento etichetta="Caricamento delle edizioni" />}
          {edizioni.isError && (
            <Errore errore={edizioni.error} riprova={() => void edizioni.refetch()} />
          )}
          {edizioni.isSuccess && edizioni.data.totale === 0 && (
            <Vuoto>Nessuna edizione di questo corso.</Vuoto>
          )}
          {edizioni.isSuccess && edizioni.data.totale > 0 && (
            <>
              <Table.ScrollContainer minWidth={760}>
                <Table striped aria-busy={edizioni.isPlaceholderData}>
                  <caption className="solo-lettori-schermo">Edizioni del corso</caption>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th scope="col">Date</Table.Th>
                      <Table.Th scope="col">Posti</Table.Th>
                      <Table.Th scope="col">Lista d&apos;attesa</Table.Th>
                      <Table.Th scope="col">Docente</Table.Th>
                      <Table.Th scope="col">Stato</Table.Th>
                      <Table.Th scope="col">Azioni</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {edizioni.data.elementi.map((voce) => {
                      const periodo = formattaPeriodo(voce.data_inizio, voce.data_fine);
                      return (
                        <Table.Tr key={voce.id}>
                          <Table.Td>
                            <Anchor
                              component={Link}
                              to={`/gestione/edizioni/${String(voce.id)}`}
                              aria-label={`Iscrizioni dell'edizione ${periodo}`}
                            >
                              {periodo}
                            </Anchor>
                          </Table.Td>
                          <Table.Td>
                            {voce.posti_confermati}/{voce.capienza} confermati
                          </Table.Td>
                          <Table.Td>{voce.lista_attesa}</Table.Td>
                          <Table.Td>
                            {voce.docente_id === null
                              ? "—"
                              : (nomi.get(voce.docente_id) ?? `Persona ${String(voce.docente_id)}`)}
                          </Table.Td>
                          <Table.Td>
                            <StatoEdizione voce={voce} oggi={oggi} />
                          </Table.Td>
                          <Table.Td>
                            {inProgramma(voce, oggi) && (
                              <Group gap="xs" wrap="nowrap">
                                <Button
                                  size="xs"
                                  variant="light"
                                  aria-label={`Modifica l'edizione ${periodo}`}
                                  onClick={() => {
                                    setDaModificare(voce);
                                  }}
                                >
                                  Modifica
                                </Button>
                                <Button
                                  size="xs"
                                  variant="light"
                                  color="red"
                                  aria-label={`Cancella l'edizione ${periodo}`}
                                  onClick={() => {
                                    setDaCancellare(voce);
                                  }}
                                >
                                  Cancella
                                </Button>
                              </Group>
                            )}
                          </Table.Td>
                        </Table.Tr>
                      );
                    })}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
              <Paginazione
                totale={edizioni.data.totale}
                perPagina={PER_PAGINA}
                pagina={pagina}
                cambia={setPagina}
                di="delle edizioni"
                conteggio={
                  edizioni.data.totale === 1
                    ? "1 edizione"
                    : `${String(edizioni.data.totale)} edizioni`
                }
              />
            </>
          )}
        </>
      )}
      <Modal
        opened={nuova}
        onClose={() => {
          setNuova(false);
        }}
        title="Nuova edizione"
      >
        <NuovaEdizione
          corsoId={corsoId}
          chiudi={() => {
            setNuova(false);
          }}
        />
      </Modal>
      <Modal
        opened={daModificare !== null}
        onClose={() => {
          setDaModificare(null);
        }}
        title="Modifica dell'edizione"
      >
        {daModificare !== null && (
          <ModificaEdizione
            id={daModificare.id}
            chiudi={() => {
              setDaModificare(null);
            }}
          />
        )}
      </Modal>
      {daCancellare !== null && (
        <ConfermaCancellazione
          voce={daCancellare}
          chiudi={() => {
            setDaCancellare(null);
          }}
        />
      )}
    </Stack>
  );
}

/** US-18: le iscrizioni attive diventano Annullata; non si torna indietro. */
function ConfermaCancellazione({ voce, chiudi }: { voce: Voce; chiudi: () => void }) {
  const cancellazione = useCancellaEdizione();
  const periodo = formattaPeriodo(voce.data_inizio, voce.data_fine);

  return (
    <Conferma
      aperta
      titolo="Cancellare l'edizione?"
      azione="Cancella l'edizione"
      inCorso={cancellazione.isPending}
      conferma={() => {
        cancellazione.mutate(voce.id, {
          onSuccess: () => {
            avvisaSuccesso(`Edizione ${periodo} cancellata.`);
          },
          onError: avvisaErrore,
          onSettled: chiudi,
        });
      }}
      chiudi={chiudi}
    >
      <Text>
        {`L'edizione ${periodo} esce dal catalogo. Tutte le sue iscrizioni attive diventano
        Annullata: ${String(voce.posti_confermati)} confermate, ${String(voce.lista_attesa)}
        in lista d'attesa, più le richieste e le approvate. Non si torna indietro.`}
      </Text>
    </Conferma>
  );
}
