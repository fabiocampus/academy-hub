/** US-03: catalogo delle edizioni, filtrabile per titolo e paginato; US-04: richiesta. */
import { Button, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useRef, useState } from "react";

import type { Schemi } from "../api/client";
import { useCatalogo, useProfilo, useRichiediIscrizione } from "../api/query";
import { avvisaErrore, avvisaSuccesso } from "../componenti/avvisi";
import { formattaPeriodo } from "../componenti/formato";
import { Paginazione } from "../componenti/Paginazione";
import { Caricamento, Errore, Vuoto } from "../componenti/Stati";
import { STATI_ANNULLABILI, StatoIscrizione } from "../componenti/StatoIscrizione";

export const PER_PAGINA = 20;

function postiLiberi(n: number): string {
  return n === 1 ? "1 libero" : `${n} liberi`;
}

/**
 * Una chiave d'idempotenza per edizione, tenuta finché la richiesta non riesce: se la
 * risposta si perde e si clicca di nuovo, l'API riconosce la richiesta già fatta.
 */
function useChiaviIdempotenza(): ChiaviIdempotenza {
  const chiavi = useRef(new Map<number, string>());
  return {
    per(edizioneId: number): string {
      let chiave = chiavi.current.get(edizioneId);
      if (chiave === undefined) {
        chiave = crypto.randomUUID();
        chiavi.current.set(edizioneId, chiave);
      }
      return chiave;
    },
    usata(edizioneId: number): void {
      chiavi.current.delete(edizioneId);
    },
  };
}

interface ChiaviIdempotenza {
  per(edizioneId: number): string;
  usata(edizioneId: number): void;
}

/**
 * Ogni riga ha la sua mutazione: due clic su righe diverse hanno ciascuno il proprio
 * esito e il proprio indicatore di attesa.
 */
function PulsanteIscriviti({
  voce,
  chiavi,
}: {
  voce: Schemi["VoceCatalogo"];
  chiavi: ChiaviIdempotenza;
}) {
  const richiesta = useRichiediIscrizione();
  const periodo = formattaPeriodo(voce.data_inizio, voce.data_fine);

  function richiedi(dopoUnaChiusa = false): void {
    richiesta.mutate(
      { edizioneId: voce.edizione_id, chiave: chiavi.per(voce.edizione_id) },
      {
        onSuccess: (iscrizione) => {
          chiavi.usata(voce.edizione_id);
          if (!STATI_ANNULLABILI.has(iscrizione.stato) && !dopoUnaChiusa) {
            // La chiave apparteneva a un'iscrizione già chiusa (annullata altrove):
            // l'API l'ha restituita com'è (ADR-0006). Si riprova con una chiave nuova.
            richiedi(true);
            return;
          }
          avvisaSuccesso(`Richiesta inviata per «${voce.corso.titolo}».`);
        },
        onError: avvisaErrore,
      },
    );
  }

  return (
    <Button
      size="xs"
      variant="light"
      aria-label={`Iscriviti a ${voce.corso.titolo} dal ${periodo}`}
      loading={richiesta.isPending}
      onClick={() => {
        richiedi();
      }}
    >
      Iscriviti
    </Button>
  );
}

export function Catalogo() {
  const [titolo, setTitolo] = useState("");
  const [cercato] = useDebouncedValue(titolo.trim(), 300);
  const [pagina, setPagina] = useState(1);
  const catalogo = useCatalogo({
    titolo: cercato,
    limite: PER_PAGINA,
    offset: (pagina - 1) * PER_PAGINA,
  });
  const profilo = useProfilo();
  // Solo comodità: l'API rifiuta comunque la richiesta a chi non è dipendente (403).
  const puoRichiedere = profilo.data?.ruoli.includes("dipendente") ?? false;
  const chiavi = useChiaviIdempotenza();

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
                    <Table.Td>{formattaPeriodo(voce.data_inizio, voce.data_fine)}</Table.Td>
                    <Table.Td>
                      {postiLiberi(voce.capienza - voce.posti_confermati)} su {voce.capienza}
                    </Table.Td>
                    <Table.Td>{voce.lista_attesa}</Table.Td>
                    <Table.Td>
                      {voce.mia_iscrizione !== null ? (
                        <StatoIscrizione stato={voce.mia_iscrizione.stato} />
                      ) : puoRichiedere ? (
                        <PulsanteIscriviti voce={voce} chiavi={chiavi} />
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
            totale={catalogo.data.totale}
            perPagina={PER_PAGINA}
            pagina={pagina}
            cambia={setPagina}
            di="del catalogo"
            conteggio={`${catalogo.data.totale} edizioni`}
          />
        </>
      )}
    </Stack>
  );
}
