# Issue tracker: GitHub Issues

Issue e backlog vivono in GitHub Issues sul repository `fabiocampus/academy-hub`, con una board in GitHub Projects. Usa la CLI `gh`.

## Convenzioni

- Gerarchia tramite label `type:epic`, `type:feature`, `type:story`, `type:bug`, `type:chore` e **sub-issue** (storia → feature → epic).
- Il titolo di una storia inizia con il suo codice: `US-04 · Chiedere l'iscrizione`.
- Lo stato di triage è una label (vedi `triage-labels.md`).
- Le regole di business toccate sono label `regola:R1` … `regola:R7`.
- Le PR chiudono la issue con `Closes #n` nella descrizione.

## Quando una skill dice «pubblica sul tracker»

`gh issue create --title "..." --body-file <file> --label type:story`, poi collega la sub-issue alla feature con `gh api` (endpoint `repos/{owner}/{repo}/issues/{n}/sub_issues`).

## Quando una skill dice «recupera la issue»

`gh issue view <n> --comments`.

## Attenzione

Il repository è pubblico: nessun segreto, token o dato reale in issue e commenti.
