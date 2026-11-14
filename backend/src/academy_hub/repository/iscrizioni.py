"""Accesso ai dati di iscrizioni, edizioni ed eventi di audit. Unico posto con le query."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime
from typing import cast

from sqlalchemy import case, func, select, tuple_
from sqlalchemy.orm import Session, aliased

from academy_hub.db.modelli import Corso, Edizione, EventoAudit, Iscrizione, Persona, Team
from academy_hub.dominio.errori import NonTrovato
from academy_hub.dominio.stati import STATI_ATTIVI, STATI_PENDENTI, StatoIscrizione
from academy_hub.repository.persone import antenati


class IscrizioneNonTrovata(NonTrovato):
    def __init__(self, iscrizione_id: int) -> None:
        super().__init__("Iscrizione", iscrizione_id)


# Lock di riga: `FOR NO KEY UPDATE` (key_share=True) serializza chi modifica la riga ma
# non blocca chi inserisce righe che la referenziano con una chiave esterna.
# Ordine dei lock in tutto il codice: prima l'edizione, poi la persona o le iscrizioni
# (ADR-0004, ADR-0006).


def edizione_di(sessione: Session, iscrizione_id: int) -> int:
    """Edizione di un'iscrizione, senza lock: `edizione_id` non cambia mai."""
    edizione_id = sessione.scalar(
        select(Iscrizione.edizione_id).where(Iscrizione.id == iscrizione_id)
    )
    if edizione_id is None:
        raise IscrizioneNonTrovata(iscrizione_id)
    return edizione_id


def iscrizione(sessione: Session, iscrizione_id: int) -> Iscrizione:
    trovata = sessione.get(Iscrizione, iscrizione_id)
    if trovata is None:
        raise IscrizioneNonTrovata(iscrizione_id)
    return trovata


def blocca_iscrizione(sessione: Session, iscrizione_id: int) -> Iscrizione:
    """Lock sull'iscrizione, con i valori freschi dal database."""
    trovata = sessione.scalar(
        select(Iscrizione)
        .where(Iscrizione.id == iscrizione_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if trovata is None:
        raise IscrizioneNonTrovata(iscrizione_id)
    return trovata


def blocca_edizione(sessione: Session, edizione_id: int) -> Edizione:
    """Lock sull'edizione: serializza chi tocca `posti_confermati` (R3)."""
    edizione = sessione.scalar(
        select(Edizione)
        .where(Edizione.id == edizione_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if edizione is None:
        raise NonTrovato("Edizione", edizione_id)
    return edizione


def blocca_edizione_in_lettura(sessione: Session, edizione_id: int) -> Edizione:
    """FOR SHARE: le richieste non si bloccano fra loro, ma una conferma o una cancellazione
    dell'edizione aspetta che finiscano (e poi vede le iscrizioni nuove)."""
    edizione = sessione.scalar(
        select(Edizione)
        .where(Edizione.id == edizione_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if edizione is None:
        raise NonTrovato("Edizione", edizione_id)
    return edizione


def blocca_iscrizioni(
    sessione: Session, edizione_id: int, stati: Collection[StatoIscrizione]
) -> list[Iscrizione]:
    """Lock sulle iscrizioni dell'edizione negli stati dati, in ordine di id.

    Da chiamare con l'edizione già bloccata (cancellazione, scadenza). Le richieste nuove
    prendono l'edizione in `FOR SHARE`, quindi l'elenco è completo. Approvazione e rifiuto
    (`_decidi`) bloccano invece solo l'iscrizione: qui il `FOR NO KEY UPDATE` aspetta la
    loro fine e, in READ COMMITTED, ricontrolla il WHERE sulla riga nuova. Una `Approvata`
    resta nell'elenco, una `Rifiutata` ne esce. Niente LIMIT, quindi nessuna riga persa;
    niente deadlock, perché `_decidi` non chiede l'edizione.
    """
    return list(
        sessione.scalars(
            select(Iscrizione)
            .where(Iscrizione.edizione_id == edizione_id, Iscrizione.stato.in_(stati))
            .order_by(Iscrizione.id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
    )


def blocca_prima_in_attesa(sessione: Session, edizione_id: int) -> Iscrizione | None:
    """R4: la prima della lista d'attesa, per approvazione e poi id (`ix_iscrizioni_lista_attesa`).

    Da chiamare con l'edizione già bloccata: ogni cambio di una `InAttesa` blocca prima
    l'edizione, quindi la riga scelta non può cambiare sotto il lock. Niente `SKIP LOCKED`:
    saltare una riga bloccata scavalcherebbe la lista (ADR-0004, punto 4).
    """
    return sessione.scalar(
        select(Iscrizione)
        .where(
            Iscrizione.edizione_id == edizione_id,
            Iscrizione.stato == StatoIscrizione.IN_ATTESA,
        )
        .order_by(Iscrizione.approvata_il, Iscrizione.id)
        .limit(1)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )


def edizioni_iniziate_con_pendenti(sessione: Session, oggi: date) -> list[int]:
    """Edizioni iniziate (entro `oggi`) con iscrizioni ancora pendenti (US-17, D8)."""
    return list(
        sessione.scalars(
            select(Edizione.id)
            .where(
                Edizione.data_inizio <= oggi,
                select(Iscrizione.id)
                .where(
                    Iscrizione.edizione_id == Edizione.id,
                    Iscrizione.stato.in_(STATI_PENDENTI),
                )
                .exists(),
            )
            .order_by(Edizione.id)
        )
    )


def edizioni_con_posti_e_lista(sessione: Session, oggi: date) -> list[int]:
    """Edizioni aperte con posti liberi e lista d'attesa: la promozione inline non le lascia,
    il job le ripara (US-09, ADR-0007)."""
    return list(
        sessione.scalars(
            select(Edizione.id)
            .where(
                Edizione.data_inizio > oggi,
                Edizione.cancellata_il.is_(None),
                Edizione.posti_confermati < Edizione.capienza,
                select(Iscrizione.id)
                .where(
                    Iscrizione.edizione_id == Edizione.id,
                    Iscrizione.stato == StatoIscrizione.IN_ATTESA,
                )
                .exists(),
            )
            .order_by(Edizione.id)
        )
    )


def iscrizione_per_chiave(sessione: Session, persona_id: int, chiave: str) -> Iscrizione | None:
    return sessione.scalar(
        select(Iscrizione).where(
            Iscrizione.persona_id == persona_id, Iscrizione.chiave_idempotenza == chiave
        )
    )


def ha_iscrizione_attiva(sessione: Session, persona_id: int, edizione_id: int) -> bool:
    """R1, usa `uq_iscrizioni_attiva`."""
    return (
        sessione.scalar(
            select(Iscrizione.id).where(
                Iscrizione.persona_id == persona_id,
                Iscrizione.edizione_id == edizione_id,
                Iscrizione.stato.in_(STATI_ATTIVI),
            )
        )
        is not None
    )


def adesso(sessione: Session) -> datetime:
    """Istante della transazione secondo il database: un solo orologio per tutte le repliche."""
    return sessione.execute(select(func.now())).scalar_one()


def aggiungi(sessione: Session, nuova: Iscrizione) -> None:
    sessione.add(nuova)
    sessione.flush()


def registra_evento(
    sessione: Session,
    iscrizione_id: int,
    stato_da: StatoIscrizione | None,
    stato_a: StatoIscrizione,
    autore_id: int | None,
    motivo: str | None = None,
) -> None:
    sessione.add(
        EventoAudit(
            iscrizione_id=iscrizione_id,
            autore_id=autore_id,
            stato_da=stato_da,
            stato_a=stato_a,
            motivo=motivo,
        )
    )


def eventi_audit(sessione: Session, iscrizione_id: int) -> list[EventoAudit]:
    """Storia di un'iscrizione in ordine cronologico (US-11)."""
    return list(
        sessione.scalars(
            select(EventoAudit)
            .where(EventoAudit.iscrizione_id == iscrizione_id)
            .order_by(EventoAudit.avvenuto_il, EventoAudit.id)
        )
    )


@dataclass(frozen=True)
class VoceMiaIscrizione:
    iscrizione: Iscrizione
    edizione: Edizione
    corso: Corso
    posizione_lista_attesa: int | None


def mie_iscrizioni(
    sessione: Session, persona_id: int, limite: int, offset: int
) -> tuple[list[VoceMiaIscrizione], int]:
    """Iscrizioni della persona, dall'ultimo cambio (US-05). Usa `ix_iscrizioni_persona_id`.

    La posizione in lista d'attesa segue R4: ordine di approvazione, `id` come spareggio.
    """
    altra = aliased(Iscrizione)
    davanti = (
        select(func.count())
        .where(
            altra.edizione_id == Iscrizione.edizione_id,
            altra.stato == StatoIscrizione.IN_ATTESA,
            tuple_(altra.approvata_il, altra.id) <= tuple_(Iscrizione.approvata_il, Iscrizione.id),
        )
        .correlate(Iscrizione)
        .scalar_subquery()
    )
    posizione = case((Iscrizione.stato == StatoIscrizione.IN_ATTESA, davanti), else_=None)
    filtro = Iscrizione.persona_id == persona_id

    totale = sessione.scalar(select(func.count()).select_from(Iscrizione).where(filtro))
    righe = sessione.execute(
        select(Iscrizione, Edizione, Corso, posizione)
        .join(Edizione, Edizione.id == Iscrizione.edizione_id)
        .join(Corso, Corso.id == Edizione.corso_id)
        .where(filtro)
        .order_by(Iscrizione.aggiornata_il.desc(), Iscrizione.id.desc())
        .limit(limite)
        .offset(offset)
    ).all()
    voci = [VoceMiaIscrizione(i, e, c, cast("int | None", p)) for i, e, c, p in righe]
    return voci, totale or 0


@dataclass(frozen=True)
class RichiestaDaDecidere:
    iscrizione: Iscrizione
    persona: Persona
    edizione: Edizione
    corso: Corso


def richieste_da_decidere(
    sessione: Session, decisore_id: int, amministratore: bool, limite: int, offset: int
) -> tuple[list[RichiestaDaDecidere], int]:
    """Iscrizioni `Richiesta` su cui `decisore_id` è il responsabile diretto (US-07).

    Stessa regola di `dominio.organigramma.responsabile_diretto`, in SQL: il primo
    responsabile risalendo dal team del richiedente, diverso dal richiedente; se non c'è,
    l'amministrazione (`amministratore=True`). Le proprie richieste non compaiono mai.
    """
    albero = antenati()
    team = aliased(Team)
    responsabile = (
        select(team.responsabile_id)
        .select_from(albero)
        .join(team, team.id == albero.c.antenato_id)
        .where(
            albero.c.team_id == Persona.team_id,
            team.responsabile_id.is_not(None),
            team.responsabile_id != Persona.id,
        )
        .order_by(albero.c.livello)
        .limit(1)
        .correlate(Persona)
        .scalar_subquery()
    )
    decide_io = responsabile == decisore_id
    if amministratore:
        decide_io = decide_io | responsabile.is_(None)
    filtri = [
        Iscrizione.stato == StatoIscrizione.RICHIESTA,
        Persona.id != decisore_id,
        decide_io,
    ]

    totale = sessione.scalar(
        select(func.count())
        .select_from(Iscrizione)
        .join(Persona, Persona.id == Iscrizione.persona_id)
        .where(*filtri)
    )
    righe = sessione.execute(
        select(Iscrizione, Persona, Edizione, Corso)
        .join(Persona, Persona.id == Iscrizione.persona_id)
        .join(Edizione, Edizione.id == Iscrizione.edizione_id)
        .join(Corso, Corso.id == Edizione.corso_id)
        .where(*filtri)
        .order_by(Iscrizione.richiesta_il, Iscrizione.id)
        .limit(limite)
        .offset(offset)
    ).all()
    voci = [RichiestaDaDecidere(i, p, e, c) for i, p, e, c in righe]
    return voci, totale or 0
