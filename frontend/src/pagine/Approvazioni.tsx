/**
 * US-06, US-07: le richieste che spettano a me (responsabile diretto, o admin Academy per
 * chi non ha un responsabile sopra), da approvare o rifiutare con un motivo.
 */
import { Button, Group, Modal, Stack, Table, Text, Textarea, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useState } from "react";

import { erroriDeiCampi, type Schemi } from "../api/client";
import { useApprova, useRichiesteDaApprovare, useRifiuta } from "../api/query";
import { avvisaErrore, avvisaSuccesso } from "../componenti/avvisi";
import { formattaData, formattaIstante } from "../componenti/formato";
import { Paginazione } from "../componenti/Paginazione";
import { Caricamento, Errore, Vuoto } from "../componenti/Stati";

export const PER_PAGINA = 20;
/** Come `Motivo` nel contratto: da 1 a 1000 caratteri, spazi esclusi. */
export const MOTIVO_MASSIMO = 1000;

type Richiesta = Schemi["RichiestaDaApprovare"];

export function Approvazioni() {
  const [pagina, setPagina] = useState(1);
  const richieste = useRichiesteDaApprovare({
    limite: PER_PAGINA,
    offset: (pagina - 1) * PER_PAGINA,
  });
  const approvazione = useApprova();
  const [daRifiutare, setDaRifiutare] = useState<Richiesta | null>(null);

  function approva(richiesta: Richiesta): void {
    approvazione.mutate(richiesta.iscrizione_id, {
      onSuccess: () => {
        avvisaSuccesso(`Richiesta di ${richiesta.persona.nome} approvata.`);
      },
      onError: avvisaErrore,
    });
  }

  return (
    <Stack>
      <Title order={1}>Approvazioni</Title>
      {richieste.isPending && <Caricamento etichetta="Caricamento delle richieste" />}
      {richieste.isError && (
        <Errore errore={richieste.error} riprova={() => void richieste.refetch()} />
      )}
      {richieste.isSuccess && richieste.data.totale === 0 && (
        <Vuoto>Nessuna richiesta da decidere.</Vuoto>
      )}
      {richieste.isSuccess && richieste.data.totale > 0 && (
        <>
          <Table.ScrollContainer minWidth={640}>
            <Table striped aria-busy={richieste.isPlaceholderData}>
              <caption className="solo-lettori-schermo">Richieste da decidere</caption>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th scope="col">Persona</Table.Th>
                  <Table.Th scope="col">Corso</Table.Th>
                  <Table.Th scope="col">Inizio</Table.Th>
                  <Table.Th scope="col">Chiesta il</Table.Th>
                  <Table.Th scope="col">Decisione</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {richieste.data.elementi.map((richiesta) => (
                  <Table.Tr key={richiesta.iscrizione_id}>
                    <Table.Td>{richiesta.persona.nome}</Table.Td>
                    <Table.Td>{richiesta.corso.titolo}</Table.Td>
                    <Table.Td>{formattaData(richiesta.data_inizio)}</Table.Td>
                    <Table.Td>{formattaIstante(richiesta.richiesta_il)}</Table.Td>
                    <Table.Td>
                      <Group gap="xs" wrap="nowrap">
                        <Button
                          size="xs"
                          variant="light"
                          aria-label={`Approva la richiesta di ${richiesta.persona.nome} per ${richiesta.corso.titolo}`}
                          loading={
                            approvazione.isPending &&
                            approvazione.variables === richiesta.iscrizione_id
                          }
                          onClick={() => {
                            approva(richiesta);
                          }}
                        >
                          Approva
                        </Button>
                        <Button
                          size="xs"
                          variant="light"
                          color="red"
                          aria-label={`Rifiuta la richiesta di ${richiesta.persona.nome} per ${richiesta.corso.titolo}`}
                          onClick={() => {
                            setDaRifiutare(richiesta);
                          }}
                        >
                          Rifiuta
                        </Button>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Paginazione
            totale={richieste.data.totale}
            perPagina={PER_PAGINA}
            pagina={pagina}
            cambia={setPagina}
            di="delle richieste"
            conteggio={`${richieste.data.totale} richieste`}
          />
        </>
      )}
      <Modal
        opened={daRifiutare !== null}
        onClose={() => {
          setDaRifiutare(null);
        }}
        title="Rifiutare la richiesta?"
      >
        {daRifiutare !== null && (
          <FormRifiuto
            richiesta={daRifiutare}
            chiudi={() => {
              setDaRifiutare(null);
            }}
          />
        )}
      </Modal>
    </Stack>
  );
}

function validaMotivo(motivo: string): string | null {
  const testo = motivo.trim();
  if (testo === "") {
    return "Scrivi il motivo: lo legge chi ha chiesto l'iscrizione.";
  }
  if (testo.length > MOTIVO_MASSIMO) {
    return `Al massimo ${MOTIVO_MASSIMO} caratteri.`;
  }
  return null;
}

function FormRifiuto({ richiesta, chiudi }: { richiesta: Richiesta; chiudi: () => void }) {
  const rifiuto = useRifiuta();
  const form = useForm({
    initialValues: { motivo: "" },
    validate: { motivo: validaMotivo },
  });

  const invia = form.onSubmit(({ motivo }) => {
    rifiuto.mutate(
      { iscrizioneId: richiesta.iscrizione_id, motivo: motivo.trim() },
      {
        onSuccess: () => {
          avvisaSuccesso(`Richiesta di ${richiesta.persona.nome} rifiutata.`);
          chiudi();
        },
        onError: (errore) => {
          // Un 422 sul motivo resta nel form; gli altri errori chiudono la finestra.
          const campi = erroriDeiCampi(errore);
          if (campi.motivo !== undefined) {
            form.setFieldError("motivo", campi.motivo);
            return;
          }
          avvisaErrore(errore);
          chiudi();
        },
      },
    );
  });

  return (
    <form onSubmit={invia} noValidate>
      <Stack>
        <Text>
          {richiesta.persona.nome} ha chiesto «{richiesta.corso.titolo}» (inizio{" "}
          {formattaData(richiesta.data_inizio)}).
        </Text>
        <Textarea
          label="Motivo"
          required
          autosize
          minRows={3}
          maxLength={MOTIVO_MASSIMO}
          data-autofocus
          {...form.getInputProps("motivo")}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={chiudi}>
            Indietro
          </Button>
          <Button type="submit" color="red" loading={rifiuto.isPending}>
            Rifiuta
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
