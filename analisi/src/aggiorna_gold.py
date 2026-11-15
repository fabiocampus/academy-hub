"""Task del job `analisi`: gold (report da silver e importazioni accettate), ADR-0017.

File eseguito da Databricks (spark_python_task): la sua cartella è in sys.path, quindi
il pacchetto academy_analisi accanto si importa senza installarlo.
"""

from academy_analisi import gold

if __name__ == "__main__":
    # Su serverless lo script gira dentro IPython: ogni SystemExit, anche con 0, fa
    # fallire il task. Si esce solo con un errore.
    codice = gold.main()
    if codice != 0:
        raise SystemExit(codice)
