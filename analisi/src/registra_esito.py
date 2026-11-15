"""Task del job `analisi`: registra_esito (esito della passata in qualita.esiti), ADR-0017.

File eseguito da Databricks (spark_python_task): la sua cartella è in sys.path, quindi
il pacchetto academy_analisi accanto si importa senza installarlo.
"""

from academy_analisi import gate

if __name__ == "__main__":
    # Su serverless lo script gira dentro IPython: ogni SystemExit, anche con 0, fa
    # fallire il task. Si esce solo con un errore.
    codice = gate.main_esito()
    if codice != 0:
        raise SystemExit(codice)
