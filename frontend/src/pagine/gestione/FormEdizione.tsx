/** US-02: pianificare un'edizione o modificarla (con l'ETag letto all'apertura). */
import { Button, Group, NumberInput, Select, Stack, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useState } from "react";

import type { ConVersione, Schemi } from "../../api/client";
import { useCreaEdizione, useDocenti, useEdizione, useModificaEdizione } from "../../api/gestione";
import { avvisaSuccesso } from "../../componenti/avvisi";
import { formattaPeriodo } from "../../componenti/formato";
import { Caricamento, Errore } from "../../componenti/Stati";
import { campiNonValidi, ErroreForm, statoLettura } from "./ErroreForm";

/** Come `Capienza` nel contratto. */
export const CAPIENZA_MASSIMA = 10_000;

type Edizione = Schemi["EdizioneLetta"];

/** Valore del Select per «Nessun docente». */
const NESSUNO = "";

interface Valori {
  data_inizio: string;
  data_fine: string;
  capienza: number | string;
  /** Id del docente come testo (valore del Select); `""` o `null` = nessuno. */
  docente: string | null;
}

/** `minimo`: in modifica la capienza non scende sotto i posti confermati (R3). */
function validatore(minimo: number) {
  return (valori: Valori): Partial<Record<keyof Valori, string>> => {
    const errori: Partial<Record<keyof Valori, string>> = {};
    if (valori.data_inizio === "") {
      errori.data_inizio = "Scegli la data di inizio.";
    }
    if (valori.data_fine === "") {
      errori.data_fine = "Scegli la data di fine.";
    } else if (valori.data_inizio !== "" && valori.data_fine < valori.data_inizio) {
      errori.data_fine = "La fine non può precedere l'inizio.";
    }
    const capienza = Number(valori.capienza);
    const da = Math.max(1, minimo);
    if (
      valori.capienza === "" ||
      !Number.isInteger(capienza) ||
      capienza < da ||
      capienza > CAPIENZA_MASSIMA
    ) {
      errori.capienza =
        minimo > 0
          ? `Da ${String(da)} (posti già confermati) a ${String(CAPIENZA_MASSIMA)}.`
          : `Un numero intero da 1 a ${String(CAPIENZA_MASSIMA)}.`;
    }
    return errori;
  };
}

/** I nomi dei campi del form per i 422 dell'API (`docente_id` → `docente`). */
function suiCampi(campi: Record<string, string>): Record<string, string> {
  const { docente_id: docente, ...altri } = campi;
  return docente === undefined ? altri : { ...altri, docente };
}

function useFormEdizione(iniziali: Valori, postiConfermati: number) {
  return useForm<Valori>({ initialValues: iniziali, validate: validatore(postiConfermati) });
}

function CampiEdizione({ form }: { form: ReturnType<typeof useFormEdizione> }) {
  const docenti = useDocenti();
  return (
    <>
      <Group grow align="flex-start">
        <TextInput
          type="date"
          label="Inizio"
          required
          data-autofocus
          {...form.getInputProps("data_inizio")}
        />
        <TextInput type="date" label="Fine" required {...form.getInputProps("data_fine")} />
      </Group>
      <NumberInput
        label="Capienza"
        required
        min={1}
        max={CAPIENZA_MASSIMA}
        allowDecimal={false}
        allowNegative={false}
        {...form.getInputProps("capienza")}
      />
      <Select
        label="Docente"
        description={docenti.isError ? "Elenco dei docenti non disponibile" : undefined}
        allowDeselect={false}
        searchable
        nothingFoundMessage="Nessun docente con questo nome"
        // «Nessun docente» è un'opzione vera: si sceglie anche da tastiera.
        data={[
          { value: NESSUNO, label: "Nessun docente" },
          ...(docenti.data ?? []).map((d) => ({ value: String(d.id), label: d.nome })),
        ]}
        {...form.getInputProps("docente")}
      />
    </>
  );
}

function Pulsanti({
  chiudi,
  inCorso,
  azione,
}: {
  chiudi: () => void;
  inCorso: boolean;
  azione: string;
}) {
  return (
    <Group justify="flex-end">
      <Button variant="default" onClick={chiudi}>
        Indietro
      </Button>
      <Button type="submit" loading={inCorso}>
        {azione}
      </Button>
    </Group>
  );
}

function docenteId(docente: string | null): number | null {
  return docente === null || docente === NESSUNO ? null : Number(docente);
}

export function NuovaEdizione({ corsoId, chiudi }: { corsoId: number; chiudi: () => void }) {
  const creazione = useCreaEdizione();
  const [errore, setErrore] = useState<unknown>(null);
  const form = useFormEdizione(
    { data_inizio: "", data_fine: "", capienza: "", docente: NESSUNO },
    0,
  );

  const invia = form.onSubmit((valori) => {
    setErrore(null);
    creazione.mutate(
      {
        corso_id: corsoId,
        data_inizio: valori.data_inizio,
        data_fine: valori.data_fine,
        capienza: Number(valori.capienza),
        docente_id: docenteId(valori.docente),
      },
      {
        onSuccess: (edizione) => {
          avvisaSuccesso(
            `Edizione ${formattaPeriodo(edizione.data_inizio, edizione.data_fine)} pianificata.`,
          );
          chiudi();
        },
        onError: (e) => {
          const campi = campiNonValidi(e);
          if (campi === null) {
            setErrore(e);
          } else {
            form.setErrors(suiCampi(campi));
          }
        },
      },
    );
  });

  return (
    <form onSubmit={invia} noValidate>
      <Stack>
        <ErroreForm errore={errore} />
        <CampiEdizione form={form} />
        <Pulsanti chiudi={chiudi} inCorso={creazione.isPending} azione="Pianifica" />
      </Stack>
    </form>
  );
}

/** Come `ModificaCorso`: il form lavora sulla versione letta; dopo un 412 si ricarica. */
export function ModificaEdizione({ id, chiudi }: { id: number; chiudi: () => void }) {
  const edizione = useEdizione(id);
  const [giro, setGiro] = useState(0);
  const lettura = statoLettura(edizione);
  if (lettura === "caricamento") {
    return <Caricamento etichetta="Caricamento dell'edizione" />;
  }
  if (lettura === "errore" || edizione.data === undefined) {
    return <Errore errore={edizione.error} riprova={() => void edizione.refetch()} />;
  }
  return (
    <FormModifica
      key={giro}
      edizione={edizione.data}
      chiudi={chiudi}
      ricarica={() =>
        void edizione.refetch().then(() => {
          setGiro((n) => n + 1);
        })
      }
    />
  );
}

function FormModifica({
  edizione,
  chiudi,
  ricarica,
}: {
  edizione: ConVersione<Edizione>;
  chiudi: () => void;
  ricarica: () => void;
}) {
  const modifica = useModificaEdizione();
  const [errore, setErrore] = useState<unknown>(null);
  const [letta] = useState(edizione);
  const iniziale = letta.dati;
  const form = useFormEdizione(
    {
      data_inizio: iniziale.data_inizio,
      data_fine: iniziale.data_fine,
      capienza: iniziale.capienza,
      docente: iniziale.docente_id === null ? NESSUNO : String(iniziale.docente_id),
    },
    iniziale.posti_confermati,
  );

  const invia = form.onSubmit((valori) => {
    // Solo i campi cambiati; `docente_id: null` toglie il docente.
    const modifiche: Schemi["ModificaEdizione"] = {};
    if (valori.data_inizio !== iniziale.data_inizio) modifiche.data_inizio = valori.data_inizio;
    if (valori.data_fine !== iniziale.data_fine) modifiche.data_fine = valori.data_fine;
    const capienza = Number(valori.capienza);
    if (capienza !== iniziale.capienza) modifiche.capienza = capienza;
    const docente = docenteId(valori.docente);
    if (docente !== iniziale.docente_id) modifiche.docente_id = docente;
    if (Object.keys(modifiche).length === 0) {
      chiudi();
      return;
    }
    setErrore(null);
    modifica.mutate(
      { id: iniziale.id, etag: letta.etag, modifiche },
      {
        onSuccess: (salvata) => {
          avvisaSuccesso(
            `Edizione ${formattaPeriodo(salvata.data_inizio, salvata.data_fine)} modificata.`,
          );
          chiudi();
        },
        onError: (e) => {
          const campi = campiNonValidi(e);
          if (campi === null) {
            setErrore(e);
          } else {
            form.setErrors(suiCampi(campi));
          }
        },
      },
    );
  });

  return (
    <form onSubmit={invia} noValidate>
      <Stack>
        <ErroreForm errore={errore} ricarica={ricarica} />
        <CampiEdizione form={form} />
        <Pulsanti chiudi={chiudi} inCorso={modifica.isPending} azione="Salva" />
      </Stack>
    </form>
  );
}
