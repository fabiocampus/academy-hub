/** US-01: creare un corso o modificarlo (con l'ETag letto all'apertura). */
import { Button, Group, NumberInput, Stack, Textarea, TextInput } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useState } from "react";

import type { ConVersione, Schemi } from "../../api/client";
import { useCorso, useCreaCorso, useModificaCorso } from "../../api/gestione";
import { avvisaSuccesso } from "../../componenti/avvisi";
import { Caricamento, Errore } from "../../componenti/Stati";
import { campiNonValidi, ErroreForm } from "./ErroreForm";

/** Come `Titolo` e `OrePositive` nel contratto. */
export const TITOLO_MASSIMO = 200;
export const ORE_MASSIME = 1000;

type Corso = Schemi["CorsoLetto"];

interface Valori {
  titolo: string;
  descrizione: string;
  durata_ore: number | string;
}

function valida(valori: Valori): Partial<Record<keyof Valori, string>> {
  const errori: Partial<Record<keyof Valori, string>> = {};
  if (valori.titolo.trim() === "") {
    errori.titolo = "Scrivi il titolo.";
  }
  const ore = Number(valori.durata_ore);
  if (valori.durata_ore === "" || !Number.isInteger(ore) || ore < 1 || ore > ORE_MASSIME) {
    errori.durata_ore = `Un numero intero di ore, da 1 a ${String(ORE_MASSIME)}.`;
  }
  return errori;
}

function useFormCorso(iniziali: Valori) {
  return useForm<Valori>({ initialValues: iniziali, validate: valida });
}

function CampiCorso({ form }: { form: ReturnType<typeof useFormCorso> }) {
  return (
    <>
      <TextInput
        label="Titolo"
        required
        maxLength={TITOLO_MASSIMO}
        data-autofocus
        {...form.getInputProps("titolo")}
      />
      <Textarea label="Descrizione" autosize minRows={3} {...form.getInputProps("descrizione")} />
      <NumberInput
        label="Durata (ore)"
        required
        min={1}
        max={ORE_MASSIME}
        allowDecimal={false}
        allowNegative={false}
        {...form.getInputProps("durata_ore")}
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

export function NuovoCorso({ chiudi }: { chiudi: () => void }) {
  const creazione = useCreaCorso();
  const [errore, setErrore] = useState<unknown>(null);
  const form = useFormCorso({ titolo: "", descrizione: "", durata_ore: "" });

  const invia = form.onSubmit((valori) => {
    setErrore(null);
    creazione.mutate(
      {
        titolo: valori.titolo.trim(),
        descrizione: valori.descrizione,
        durata_ore: Number(valori.durata_ore),
      },
      {
        onSuccess: (corso) => {
          avvisaSuccesso(`Corso «${corso.titolo}» creato.`);
          chiudi();
        },
        onError: (e) => {
          const campi = campiNonValidi(e);
          if (campi === null) {
            setErrore(e);
          } else {
            form.setErrors(campi);
          }
        },
      },
    );
  });

  return (
    <form onSubmit={invia} noValidate>
      <Stack>
        <ErroreForm errore={errore} />
        <CampiCorso form={form} />
        <Pulsanti chiudi={chiudi} inCorso={creazione.isPending} azione="Crea il corso" />
      </Stack>
    </form>
  );
}

/**
 * Legge il corso (e l'ETag) a ogni apertura. Il form lavora sulla versione letta
 * all'inizio, anche se intanto la query si rilegge: dopo un 412 «Ricarica i dati»
 * rilegge il corso e riparte il form con la versione nuova.
 */
export function ModificaCorso({ id, chiudi }: { id: number; chiudi: () => void }) {
  const corso = useCorso(id);
  const [giro, setGiro] = useState(0);
  if (corso.isPending) {
    return <Caricamento etichetta="Caricamento del corso" />;
  }
  if (corso.isError) {
    return <Errore errore={corso.error} riprova={() => void corso.refetch()} />;
  }
  return (
    <FormModifica
      key={giro}
      corso={corso.data}
      chiudi={chiudi}
      ricarica={() =>
        void corso.refetch().then(() => {
          setGiro((n) => n + 1);
        })
      }
    />
  );
}

function FormModifica({
  corso,
  chiudi,
  ricarica,
}: {
  corso: ConVersione<Corso>;
  chiudi: () => void;
  ricarica: () => void;
}) {
  const modifica = useModificaCorso();
  const [errore, setErrore] = useState<unknown>(null);
  const [letto] = useState(corso);
  const iniziale = letto.dati;
  const form = useFormCorso({
    titolo: iniziale.titolo,
    descrizione: iniziale.descrizione,
    durata_ore: iniziale.durata_ore,
  });

  const invia = form.onSubmit((valori) => {
    // Solo i campi cambiati: il PATCH lascia invariati gli assenti.
    const modifiche: Schemi["ModificaCorso"] = {};
    const titolo = valori.titolo.trim();
    if (titolo !== iniziale.titolo) modifiche.titolo = titolo;
    if (valori.descrizione !== iniziale.descrizione) modifiche.descrizione = valori.descrizione;
    const ore = Number(valori.durata_ore);
    if (ore !== iniziale.durata_ore) modifiche.durata_ore = ore;
    if (Object.keys(modifiche).length === 0) {
      chiudi();
      return;
    }
    setErrore(null);
    modifica.mutate(
      { id: iniziale.id, etag: letto.etag, modifiche },
      {
        onSuccess: (salvato) => {
          avvisaSuccesso(`Corso «${salvato.titolo}» modificato.`);
          chiudi();
        },
        onError: (e) => {
          const campi = campiNonValidi(e);
          if (campi === null) {
            setErrore(e);
          } else {
            form.setErrors(campi);
          }
        },
      },
    );
  });

  return (
    <form onSubmit={invia} noValidate>
      <Stack>
        <ErroreForm errore={errore} ricarica={ricarica} />
        <CampiCorso form={form} />
        <Pulsanti chiudi={chiudi} inCorso={modifica.isPending} azione="Salva" />
      </Stack>
    </form>
  );
}
