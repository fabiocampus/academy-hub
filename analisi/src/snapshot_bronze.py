"""Task del job `analisi`: snapshot di Lakebase in bronze (ADR-0016).

File eseguito da Databricks (spark_python_task): la sua cartella è in sys.path, quindi
il pacchetto academy_analisi accanto si importa senza installarlo.
"""

import sys

from academy_analisi.snapshot import main

if __name__ == "__main__":
    sys.exit(main())
