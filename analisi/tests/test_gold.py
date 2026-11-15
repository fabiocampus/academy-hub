"""Gold dei report: Completata calcolata, ore per team, tasso di completamento, valutazioni."""

from datetime import UTC, date, datetime

import pytest
from pyspark.errors import AnalysisException
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from academy_analisi.gold import (
    aggiorna,
    correnti,
    da_file_accettati,
    iscrizioni_concluse,
    lettore,
    ore_per_team,
    sql_filtro_team,
    sql_sovrascrivi,
    tasso_completamento,
    valutazione_media,
)
from academy_analisi.storico import versione

OGGI = date(2026, 11, 20)
SOGLIA = 75
# Versioni dello storico: due scatti, prima e dopo il cambio di team di una persona.
PRIMA = versione(datetime(2026, 11, 1, 5, 0, tzinfo=UTC))
DOPO = versione(datetime(2026, 11, 10, 5, 0, tzinfo=UTC))
SCD = "__START_AT BIGINT, __END_AT BIGINT"


def _storico(spark: SparkSession, schema: str, *righe: tuple[object, ...]) -> DataFrame:
    return spark.createDataFrame(list(righe), f"{schema}, {SCD}")


@pytest.fixture
def persone(spark: SparkSession) -> DataFrame:
    # Anna passa dal team 1 al team 2 il 10 novembre; Bruno resta nel team 1.
    return _storico(
        spark,
        "id BIGINT, team_id BIGINT",
        (1, 1, PRIMA, DOPO),
        (1, 2, DOPO, None),
        (2, 1, PRIMA, None),
    )


@pytest.fixture
def edizioni(spark: SparkSession) -> DataFrame:
    schema = "id BIGINT, corso_id BIGINT, data_inizio DATE, data_fine DATE, cancellata_il TIMESTAMP"
    return _storico(
        spark,
        schema,
        # Conclusa prima del cambio di team (4 giornate).
        (10, 100, date(2026, 11, 2), date(2026, 11, 5), None, PRIMA, None),
        # Conclusa dopo (2 giornate).
        (11, 100, date(2026, 11, 16), date(2026, 11, 17), None, PRIMA, None),
        # Non ancora conclusa.
        (12, 101, date(2026, 11, 19), date(2026, 11, 21), None, PRIMA, None),
        # Cancellata.
        (
            13,
            101,
            date(2026, 11, 3),
            date(2026, 11, 4),
            datetime(2026, 11, 1, tzinfo=UTC),
            PRIMA,
            None,
        ),
    )


@pytest.fixture
def iscrizioni(spark: SparkSession) -> DataFrame:
    return _storico(
        spark,
        "id BIGINT, persona_id BIGINT, edizione_id BIGINT, stato STRING",
        (1000, 1, 10, "Confermata", PRIMA, None),
        (1001, 2, 10, "Confermata", PRIMA, None),
        (1002, 1, 11, "Confermata", PRIMA, None),
        (1003, 2, 11, "Annullata", PRIMA, None),
        (1004, 1, 12, "Confermata", PRIMA, None),
        (1005, 2, 13, "Confermata", PRIMA, None),
        # Annullata dopo essere stata Confermata: conta lo stato corrente.
        (1006, 2, 11, "Confermata", PRIMA, DOPO),
    )


def _presenze(spark: SparkSession, *righe: tuple[int, int, date]) -> DataFrame:
    return spark.createDataFrame(list(righe), "persona_id BIGINT, edizione_id BIGINT, giorno DATE")


@pytest.fixture
def presenze(spark: SparkSession) -> DataFrame:
    return _presenze(
        spark,
        # Anna: 3 giornate su 4 (75%, completata), la stessa giornata due volte.
        (1, 10, date(2026, 11, 2)),
        (1, 10, date(2026, 11, 3)),
        (1, 10, date(2026, 11, 3)),
        (1, 10, date(2026, 11, 4)),
        # Bruno: 2 su 4 (50%, no).
        (2, 10, date(2026, 11, 2)),
        (2, 10, date(2026, 11, 3)),
        # Anna: 2 su 2 nell'edizione 11.
        (1, 11, date(2026, 11, 16)),
        (1, 11, date(2026, 11, 17)),
    )


@pytest.fixture
def concluse(
    iscrizioni: DataFrame, edizioni: DataFrame, persone: DataFrame, presenze: DataFrame
) -> DataFrame:
    return iscrizioni_concluse(
        iscrizioni=iscrizioni,
        edizioni=edizioni,
        persone=persone,
        presenze=presenze,
        oggi=F.lit(OGGI),
        soglia=SOGLIA,
    )


def test_correnti_solo_righe_aperte(iscrizioni: DataFrame) -> None:
    ids = sorted(r.id for r in correnti(iscrizioni).collect())

    assert ids == [1000, 1001, 1002, 1003, 1004, 1005]
    assert "__START_AT" not in correnti(iscrizioni).columns


def test_concluse_solo_confermate_di_edizioni_finite_e_non_cancellate(concluse: DataFrame) -> None:
    assert sorted(r.iscrizione_id for r in concluse.collect()) == [1000, 1001, 1002]


def test_completata_dalla_soglia(concluse: DataFrame) -> None:
    righe = {r.iscrizione_id: r for r in concluse.collect()}

    assert (righe[1000].giornate, righe[1000].giorni_presenti, righe[1000].completata) == (
        4,
        3,
        True,
    )
    assert (righe[1001].giorni_presenti, righe[1001].completata) == (2, False)
    assert righe[1002].completata is True


def test_soglia_configurabile(
    iscrizioni: DataFrame, edizioni: DataFrame, persone: DataFrame, presenze: DataFrame
) -> None:
    concluse = iscrizioni_concluse(
        iscrizioni=iscrizioni,
        edizioni=edizioni,
        persone=persone,
        presenze=presenze,
        oggi=F.lit(OGGI),
        soglia=50,
    )

    assert {r.iscrizione_id: r.completata for r in concluse.collect()}[1001] is True


def test_senza_presenze_non_completata(
    spark: SparkSession, iscrizioni: DataFrame, edizioni: DataFrame, persone: DataFrame
) -> None:
    concluse = iscrizioni_concluse(
        iscrizioni=iscrizioni,
        edizioni=edizioni,
        persone=persone,
        presenze=_presenze(spark),
        oggi=F.lit(OGGI),
        soglia=SOGLIA,
    )

    assert all(r.giorni_presenti == 0 and r.completata is False for r in concluse.collect())


def test_team_alla_fine_dell_edizione(concluse: DataFrame) -> None:
    team = {r.iscrizione_id: r.team_id for r in concluse.collect()}

    # Anna era nel team 1 per l'edizione 10, nel team 2 per l'edizione 11.
    assert team[1000] == 1
    assert team[1002] == 2


def test_team_prima_dello_storico(
    spark: SparkSession, iscrizioni: DataFrame, edizioni: DataFrame, presenze: DataFrame
) -> None:
    # Storico iniziato dopo l'edizione: vale la prima versione nota della persona.
    persone = _storico(spark, "id BIGINT, team_id BIGINT", (1, 7, DOPO, None), (2, 8, DOPO, None))

    concluse = iscrizioni_concluse(
        iscrizioni=iscrizioni,
        edizioni=edizioni,
        persone=persone,
        presenze=presenze,
        oggi=F.lit(OGGI),
        soglia=SOGLIA,
    )

    assert {r.iscrizione_id: r.team_id for r in concluse.collect()}[1000] == 7


@pytest.fixture
def corsi(spark: SparkSession) -> DataFrame:
    return spark.createDataFrame(
        [(100, "Python", 8), (101, "SQL", 4)], "id BIGINT, titolo STRING, durata_ore INT"
    )


@pytest.fixture
def team(spark: SparkSession) -> DataFrame:
    return spark.createDataFrame([(1, "Dati"), (2, "Piattaforma")], "id BIGINT, nome STRING")


def test_ore_per_team(concluse: DataFrame, corsi: DataFrame, team: DataFrame) -> None:
    righe = {r.team_id: r for r in ore_per_team(concluse, corsi, team).collect()}

    assert (righe[1].team, righe[1].ore_formazione, righe[1].iscrizioni_completate) == (
        "Dati",
        8,
        1,
    )
    assert (righe[2].team, righe[2].ore_formazione) == ("Piattaforma", 8)


def test_tasso_completamento_per_corso(concluse: DataFrame, corsi: DataFrame) -> None:
    [python] = tasso_completamento(concluse, corsi).collect()

    assert (python.corso_id, python.titolo) == (100, "Python")
    assert (python.concluse, python.completate) == (3, 2)
    assert python.tasso == pytest.approx(0.6667)


def _valutazioni(spark: SparkSession, *righe: tuple[int, int, int, datetime, str]) -> DataFrame:
    return spark.createDataFrame(
        list(righe),
        "persona_id BIGINT, edizione_id BIGINT, voto INT, _caricata_il TIMESTAMP, _file STRING",
    )


def test_valutazione_media_solo_di_chi_ha_completato(
    spark: SparkSession, concluse: DataFrame, corsi: DataFrame
) -> None:
    prima = datetime(2026, 11, 18, tzinfo=UTC)
    dopo = datetime(2026, 11, 19, tzinfo=UTC)
    valutazioni = _valutazioni(
        spark,
        (1, 10, 4, prima, "a.csv"),
        # Seconda valutazione della stessa iscrizione: vale la prima (non modificabile).
        (1, 10, 1, dopo, "b.csv"),
        (1, 11, 5, prima, "a.csv"),
        # Bruno non ha completato l'edizione 10: non conta.
        (2, 10, 1, prima, "a.csv"),
    )

    [python] = valutazione_media(valutazioni, concluse, corsi).collect()

    assert (python.corso_id, python.valutazioni, python.voto_medio) == (100, 2, 4.5)


def test_da_file_accettati(spark: SparkSession) -> None:
    righe = spark.createDataFrame([("a.csv", 1), ("b.csv", 2), ("c.csv", 3)], "_file STRING, n INT")
    verdetti = spark.createDataFrame(
        [("a.csv", "presenze", True), ("b.csv", "presenze", False), ("c.csv", "valutazioni", True)],
        "file STRING, tipo STRING, accettato BOOLEAN",
    )

    # c.csv è un file di valutazioni: non vale per le presenze.
    assert [r.n for r in da_file_accettati(righe, verdetti, "presenze").collect()] == [1]


def test_aggiorna_esclude_i_file_respinti(
    spark: SparkSession, iscrizioni: DataFrame, edizioni: DataFrame, persone: DataFrame
) -> None:
    giorno = "persona_id BIGINT, edizione_id BIGINT, giorno DATE, _file STRING"
    # Anna: 2 giornate dal file buono, la terza solo da quello respinto (2 su 4: no).
    presenze = spark.createDataFrame(
        [
            (1, 10, date(2026, 11, 2), "buono.csv"),
            (1, 10, date(2026, 11, 3), "buono.csv"),
            (1, 10, date(2026, 11, 4), "respinto.csv"),
        ],
        giorno,
    )
    tabelle = {
        "academy_collaudo.silver.iscrizioni": iscrizioni,
        "academy_collaudo.silver.edizioni": edizioni,
        "academy_collaudo.silver.persone": persone,
        "academy_collaudo.silver.corsi": _storico(
            spark, "id BIGINT, titolo STRING, durata_ore INT", (100, "Python", 8, PRIMA, None)
        ),
        "academy_collaudo.silver.team": _storico(
            spark, "id BIGINT, nome STRING", (1, "Dati", PRIMA, None)
        ),
        "academy_collaudo.silver.presenze": presenze,
        "academy_collaudo.silver.valutazioni": _valutazioni(spark),
        "academy_collaudo.qualita.verdetti": spark.createDataFrame(
            [("buono.csv", "presenze", True), ("respinto.csv", "presenze", False)],
            "file STRING, tipo STRING, accettato BOOLEAN",
        ),
    }
    scritte: dict[str, DataFrame] = {}

    def scrivi(righe: DataFrame, nome: str) -> None:
        scritte[nome] = righe

    aggiorna(
        leggi=tabelle.__getitem__,
        scrivi=scrivi,
        silver="academy_collaudo.silver",
        qualita="academy_collaudo.qualita",
        gold="academy_collaudo.gold",
        oggi=F.lit(OGGI),
    )

    assert sorted(scritte) == [
        "academy_collaudo.gold.iscrizioni_concluse",
        "academy_collaudo.gold.ore_per_team",
        "academy_collaudo.gold.tasso_completamento",
        "academy_collaudo.gold.valutazione_media",
    ]
    concluse = {
        r.iscrizione_id: r for r in scritte["academy_collaudo.gold.iscrizioni_concluse"].collect()
    }
    assert (concluse[1000].giorni_presenti, concluse[1000].completata) == (2, False)
    assert scritte["academy_collaudo.gold.ore_per_team"].collect() == []


def test_lettore_senza_verdetti_da_vuoti(spark: SparkSession) -> None:
    # Prima del primo CSV `qualita.verdetti` non esiste: il gold non deve fallire.
    leggi = lettore(spark, "spark_catalog.qualita_assente")

    assert leggi("spark_catalog.qualita_assente.verdetti").collect() == []
    with pytest.raises(AnalysisException):
        _ = leggi("spark_catalog.qualita_assente.altra").schema


def test_soglia_fuori_scala(
    iscrizioni: DataFrame, edizioni: DataFrame, persone: DataFrame, presenze: DataFrame
) -> None:
    with pytest.raises(ValueError, match="Soglia"):
        iscrizioni_concluse(
            iscrizioni=iscrizioni,
            edizioni=edizioni,
            persone=persone,
            presenze=presenze,
            oggi=F.lit(OGGI),
            soglia=0,
        )


def test_filtro_team_legge_silver_e_riconosce_per_email() -> None:
    sql = sql_filtro_team("academy_collaudo.silver", "academy_collaudo.gold")

    assert sql.startswith("CREATE OR REPLACE FUNCTION academy_collaudo.gold.vede_team(")
    assert "academy_collaudo.silver.team t JOIN academy_collaudo.silver.persone p" in sql
    assert "lower(p.email) = lower(current_user())" in sql
    assert "array_contains(p.ruoli, 'admin_academy')" in sql
    with pytest.raises(ValueError):
        sql_filtro_team("silver; DROP", "academy_collaudo.gold")


def test_sovrascrivi_con_filtro_nella_stessa_istruzione() -> None:
    assert sql_sovrascrivi("c.gold.ore_per_team", "_v", "c.gold.vede_team") == (
        "CREATE OR REPLACE TABLE c.gold.ore_per_team "
        "WITH ROW FILTER c.gold.vede_team ON (team_id) AS SELECT * FROM _v"
    )
    assert sql_sovrascrivi("c.gold.tasso_completamento", "_v", None) == (
        "CREATE OR REPLACE TABLE c.gold.tasso_completamento AS SELECT * FROM _v"
    )
