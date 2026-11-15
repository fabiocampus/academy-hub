"""Task del job `analisi`: snapshot di Lakebase in bronze (ADR-0016).

File eseguito da Databricks (spark_python_task): la sua cartella è in sys.path, quindi
il pacchetto academy_analisi accanto si importa senza installarlo.
"""

from academy_analisi import snapshot

if __name__ == "__main__":
    # Su serverless lo script gira dentro IPython: ogni SystemExit, anche con 0, fa
    # fallire il task. Si esce solo con un errore.
    codice = snapshot.main()
    if codice != 0:
        raise SystemExit(codice)
