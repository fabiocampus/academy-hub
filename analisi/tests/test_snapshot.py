"""Snapshot in bronze: colonne esplicite, istante dello scatto, nomi validati."""

from datetime import UTC, datetime

import pytest
from pyspark.sql import DataFrame, SparkSession

from academy_analisi.snapshot import COLONNA_SNAPSHOT, main, nome_tabella, scatta, snapshot
from academy_analisi.tabelle import TABELLE, Tabella

ISTANTE = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)


def test_solo_le_colonne_dichiarate_piu_l_istante(spark: SparkSession) -> None:
    team = Tabella("team", ("id", "nome"))
    sorgente = spark.createDataFrame(
        [(1, "Academy", "segreto")], "id INT, nome STRING, colonna_nuova STRING"
    )

    risultato = snapshot(sorgente, team, ISTANTE)

    assert risultato.columns == ["id", "nome", COLONNA_SNAPSHOT]
    riga = risultato.collect()[0]
    assert riga["nome"] == "Academy"
    # collect() restituisce un datetime naive nel fuso del processo Python.
    assert riga[COLONNA_SNAPSHOT].astimezone(UTC) == ISTANTE


def test_tabelle_dello_storico() -> None:
    assert [t.nome for t in TABELLE] == ["team", "persone", "corsi", "edizioni", "iscrizioni"]
    for t in TABELLE:
        assert t.chiave == ("id",)
        assert set(t.chiave) <= set(t.colonne)


def test_campi_tecnici_esclusi() -> None:
    colonne = {c for t in TABELLE for c in t.colonne}
    # La chiave d'idempotenza è del client; versione serve solo alla concorrenza ottimistica.
    assert "chiave_idempotenza" not in colonne
    assert "versione" not in colonne


@pytest.mark.parametrize(
    ("schema", "tabella", "atteso"),
    [
        ("academy_collaudo.bronze", "team", "academy_collaudo.bronze.team"),
        ("academy_prod_oltp.academy", "persone", "academy_prod_oltp.academy.persone"),
    ],
)
def test_nome_tabella(schema: str, tabella: str, atteso: str) -> None:
    assert nome_tabella(schema, tabella) == atteso


@pytest.mark.parametrize("schema", ["bronze", "a.b.c", "a.b; DROP", "A.b", "a.`b`"])
def test_nome_tabella_rifiuta_schema_non_valido(schema: str) -> None:
    with pytest.raises(ValueError, match=r"catalogo\.schema"):
        nome_tabella(schema, "team")


def test_scatta_aggiunge_ogni_tabella_con_lo_stesso_istante(spark: SparkSession) -> None:
    sorgenti = {
        "academy_collaudo_oltp.academy_collaudo.team": spark.createDataFrame(
            [(1, "Academy", None, 2)], "id INT, nome STRING, team_padre_id INT, responsabile_id INT"
        ),
    }
    scritte: dict[str, list[DataFrame]] = {}
    team = next(t for t in TABELLE if t.nome == "team")

    contate = scatta(
        leggi=sorgenti.__getitem__,
        scrivi=lambda df, nome: scritte.setdefault(nome, []).append(df),
        tabelle=(team,),
        sorgente="academy_collaudo_oltp.academy_collaudo",
        destinazione="academy_collaudo.bronze",
        istante=ISTANTE,
    )

    assert contate == {"team": 1}
    (scritta,) = scritte["academy_collaudo.bronze.team"]
    assert scritta.columns == [*team.colonne, COLONNA_SNAPSHOT]


def test_main_rifiuta_nomi_non_validi_prima_di_spark() -> None:
    with pytest.raises(ValueError, match=r"catalogo\.schema"):
        main(["--sorgente", "academy_collaudo_oltp.academy_collaudo", "--destinazione", "x"])
