/** Gestione Academy (issue #64): chi è iscritto a un'edizione; conferma delle Approvate (US-08). */
import { Anchor, Button, SegmentedControl, Stack, Table, Text, Title } from "@mantine/core";
import { useState } from "react";
import { Link, useParams } from "react-router";

import type { Schemi } from "../../api/client";
import {
  useConfermaIscrizione,
  useCorso,
  useEdizione,
  useIscrizioniDellEdizione,
} from "../../api/gestione";
import { avvisaErrore, avvisaSuccesso } from "../../componenti/avvisi";
import { formattaIstante, formattaPeriodo, idDaPercorso } from "../../componenti/formato";
import { Paginazione } from "../../componenti/Paginazione";
import { Caricamento, Errore, Vuoto } from "../../componenti/Stati";
import { StatoIscrizione } from "../../componenti/StatoIscrizione";

export const PER_PAGINA = 20;

type Voce = Schemi["VoceIscrizioneEdizione"];
type Filtro = "tutte" | "da-confermare";

export function IscrizioniEdizione() {
  const edizioneId = idDaPercorso(useParams().edizioneId);
  if (edizioneId === null) {
    return <PaginaNonTrovata />;
  }
  return <Iscrizioni edizioneId={edizioneId} />;
}

function PaginaNonTrovata() {
  return (
    <Stack>
      <Anchor component={Link} to="/gestione" size="sm">
        ← Tutti i corsi
      </Anchor>
      <Title order={1}>Iscrizioni dell&apos;edizione</Title>
      <Vuoto>Pagina non trovata.</Vuoto>
    </Stack>
  );
}

function Iscrizioni({ edizioneId }: { edizioneId: number }) {
  const edizione = useEdizione(edizioneId);
  const [filtro, setFiltro] = useState<Filtro>("tutte");
  const [pagina, setPagina] = useState(1);
  const iscrizioni = useIscrizioniDellEdizione(edizioneId, {
    stato: filtro === "da-confermare" ? "Approvata" : null,
    limite: PER_PAGINA,
    offset: (pagina - 1) * PER_PAGINA,
  });

  return (
    <Stack>
      {!edizione.isSuccess && (
        <>
          <Anchor component={Link} to="/gestione" size="sm">
            ← Tutti i corsi
          </Anchor>
          <Title order={1}>Iscrizioni dell&apos;edizione</Title>
        </>
      )}
      {edizione.isPending && <Caricamento etichetta="Caricamento dell'edizione" />}
      {edizione.isError && (
        <Errore errore={edizione.error} riprova={() => void edizione.refetch()} />
      )}
      {edizione.isSuccess && <Intestazione edizione={edizione.data.dati} />}
      <SegmentedControl
        aria-label="Quali iscrizioni"
        value={filtro}
        onChange={(valore) => {
          setFiltro(valore);
          setPagina(1);
        }}
        data={[
          { value: "tutte", label: "Tutte" },
          { value: "da-confermare", label: "Da confermare" },
        ]}
        maw={360}
      />
      {iscrizioni.isPending && <Caricamento etichetta="Caricamento delle iscrizioni" />}
      {iscrizioni.isError && (
        <Errore errore={iscrizioni.error} riprova={() => void iscrizioni.refetch()} />
      )}
      {iscrizioni.isSuccess && iscrizioni.data.totale === 0 && (
        <Vuoto>
          {filtro === "da-confermare"
            ? "Nessuna iscrizione approvata da confermare."
            : "Nessuna iscrizione a questa edizione."}
        </Vuoto>
      )}
      {iscrizioni.isSuccess && iscrizioni.data.totale > 0 && (
        <>
          <Table.ScrollContainer minWidth={640}>
            <Table striped aria-busy={iscrizioni.isPlaceholderData}>
              <caption className="solo-lettori-schermo">Iscrizioni dell&apos;edizione</caption>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th scope="col">Persona</Table.Th>
                  <Table.Th scope="col">Stato</Table.Th>
                  <Table.Th scope="col">Chiesta il</Table.Th>
                  <Table.Th scope="col">Azione</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {iscrizioni.data.elementi.map((voce) => (
                  <Table.Tr key={voce.id}>
                    <Table.Td>{voce.persona.nome}</Table.Td>
                    <Table.Td>
                      <StatoIscrizione stato={voce.stato} />
                      {voce.posizione_lista_attesa !== null && (
                        <Text size="xs" c="dimmed">
                          {voce.posizione_lista_attesa}ª in lista
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>{formattaIstante(voce.richiesta_il)}</Table.Td>
                    <Table.Td>
                      {voce.stato === "Approvata" && <PulsanteConferma voce={voce} />}
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
            conteggio={
              iscrizioni.data.totale === 1
                ? "1 iscrizione"
                : `${String(iscrizioni.data.totale)} iscrizioni`
            }
          />
        </>
      )}
    </Stack>
  );
}

function Intestazione({ edizione }: { edizione: Schemi["EdizioneLetta"] }) {
  const corso = useCorso(edizione.corso_id);
  const titolo = corso.data?.dati.titolo ?? "Edizione";
  return (
    <>
      <Anchor component={Link} to={`/gestione/corsi/${String(edizione.corso_id)}`} size="sm">
        ← Edizioni del corso
      </Anchor>
      <Stack gap={0}>
        <Title order={1}>{titolo}</Title>
        <Text c="dimmed" size="sm">
          {formattaPeriodo(edizione.data_inizio, edizione.data_fine)} · {edizione.posti_confermati}/
          {edizione.capienza} posti confermati
          {edizione.cancellata_il !== null && " · edizione cancellata"}
        </Text>
      </Stack>
    </>
  );
}

/** Ogni riga ha la sua mutazione, come nelle approvazioni. */
function PulsanteConferma({ voce }: { voce: Voce }) {
  const conferma = useConfermaIscrizione();
  return (
    <Button
      size="xs"
      variant="light"
      aria-label={`Conferma l'iscrizione di ${voce.persona.nome}`}
      loading={conferma.isPending}
      onClick={() => {
        // mutateAsync, non mutate: il pulsante sparisce quando l'elenco si rilegge e i
        // callback di mutate() non arrivano a un componente smontato (test/smontaggio.tsx).
        conferma.mutateAsync(voce.id).then((iscrizione) => {
          avvisaSuccesso(
            iscrizione.stato === "Confermata"
              ? `Iscrizione di ${voce.persona.nome} confermata.`
              : `Posti esauriti: ${voce.persona.nome} è in lista d'attesa.`,
          );
        }, avvisaErrore);
      }}
    >
      Conferma
    </Button>
  );
}
