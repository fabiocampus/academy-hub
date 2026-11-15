/** US-05, US-10: le mie iscrizioni, con annullamento confermato da una finestra. */
import { Button, Group, Modal, Stack, Table, Text, Title } from "@mantine/core";
import { useState } from "react";

import type { Schemi } from "../api/client";
import { useFlag } from "../api/flag";
import { useAnnullaIscrizione, useMieIscrizioni, useScaricaCalendario } from "../api/query";
import { avvisaErrore, avvisaSuccesso } from "../componenti/avvisi";
import { formattaPeriodo } from "../componenti/formato";
import { Paginazione } from "../componenti/Paginazione";
import { Caricamento, Errore, Vuoto } from "../componenti/Stati";
import { STATI_ANNULLABILI, StatoIscrizione } from "../componenti/StatoIscrizione";

export const PER_PAGINA = 20;

type Voce = Schemi["VoceMiaIscrizione"];

export function MieIscrizioni() {
  const [pagina, setPagina] = useState(1);
  const iscrizioni = useMieIscrizioni({ limite: PER_PAGINA, offset: (pagina - 1) * PER_PAGINA });
  const annullamento = useAnnullaIscrizione();
  const [daAnnullare, setDaAnnullare] = useState<Voce | null>(null);
  const flag = useFlag();
  const calendario = useScaricaCalendario();

  function annulla(voce: Voce): void {
    annullamento.mutate(voce.id, {
      onSuccess: () => {
        avvisaSuccesso(`Iscrizione a «${voce.corso.titolo}» annullata.`);
      },
      onError: avvisaErrore,
      onSettled: () => {
        setDaAnnullare(null);
      },
    });
  }

  return (
    <Stack>
      <Title order={1}>Le mie iscrizioni</Title>
      {iscrizioni.isPending && <Caricamento etichetta="Caricamento delle iscrizioni" />}
      {iscrizioni.isError && (
        <Errore errore={iscrizioni.error} riprova={() => void iscrizioni.refetch()} />
      )}
      {iscrizioni.isSuccess && iscrizioni.data.totale === 0 && (
        <Vuoto>Non hai ancora chiesto iscrizioni: le trovi nel catalogo.</Vuoto>
      )}
      {iscrizioni.isSuccess && iscrizioni.data.totale > 0 && (
        <>
          <Table.ScrollContainer minWidth={560}>
            <Table striped aria-busy={iscrizioni.isPlaceholderData}>
              <caption className="solo-lettori-schermo">Le mie iscrizioni</caption>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th scope="col">Corso</Table.Th>
                  <Table.Th scope="col">Date</Table.Th>
                  <Table.Th scope="col">Stato</Table.Th>
                  <Table.Th scope="col">Azioni</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {iscrizioni.data.elementi.map((voce) => (
                  <Table.Tr key={voce.id}>
                    <Table.Td>
                      <Text fw={500}>{voce.corso.titolo}</Text>
                    </Table.Td>
                    <Table.Td>{formattaPeriodo(voce.data_inizio, voce.data_fine)}</Table.Td>
                    <Table.Td>
                      <Group gap="xs">
                        <StatoIscrizione stato={voce.stato} />
                        {voce.posizione_lista_attesa !== null && (
                          <Text size="sm">{voce.posizione_lista_attesa}ª in lista</Text>
                        )}
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      {STATI_ANNULLABILI.has(voce.stato) ||
                      (flag.calendario && voce.stato === "Confermata") ? (
                        <Group gap="xs" wrap="nowrap">
                          {flag.calendario && voce.stato === "Confermata" && (
                            <Button
                              size="xs"
                              variant="light"
                              aria-label={`Aggiungi al calendario ${voce.corso.titolo}`}
                              loading={calendario.isPending && calendario.variables === voce.id}
                              onClick={() => {
                                calendario.mutate(voce.id, { onError: avvisaErrore });
                              }}
                            >
                              Calendario
                            </Button>
                          )}
                          {STATI_ANNULLABILI.has(voce.stato) && (
                            <Button
                              size="xs"
                              variant="light"
                              color="red"
                              aria-label={`Annulla l'iscrizione a ${voce.corso.titolo}`}
                              onClick={() => {
                                setDaAnnullare(voce);
                              }}
                            >
                              Annulla
                            </Button>
                          )}
                        </Group>
                      ) : (
                        "—"
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Paginazione
            totale={iscrizioni.data.totale}
            perPagina={PER_PAGINA}
            pagina={pagina}
            cambia={setPagina}
            di="delle iscrizioni"
            conteggio={`${iscrizioni.data.totale} iscrizioni`}
          />
        </>
      )}
      <Modal
        opened={daAnnullare !== null}
        onClose={() => {
          setDaAnnullare(null);
        }}
        title="Annullare l'iscrizione?"
      >
        {daAnnullare !== null && (
          <Stack>
            <Text>
              Annulli l&apos;iscrizione a «{daAnnullare.corso.titolo}» (
              {formattaPeriodo(daAnnullare.data_inizio, daAnnullare.data_fine)}).
              {daAnnullare.stato === "Confermata" &&
                " Il posto passa al primo della lista d'attesa."}
            </Text>
            <Group justify="flex-end">
              <Button
                variant="default"
                onClick={() => {
                  setDaAnnullare(null);
                }}
              >
                Indietro
              </Button>
              <Button
                color="red"
                loading={annullamento.isPending}
                onClick={() => {
                  annulla(daAnnullare);
                }}
              >
                Annulla l&apos;iscrizione
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  );
}
