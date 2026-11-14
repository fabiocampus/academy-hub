/**
 * Criterio della fase 7: richiesta → approvazione → conferma da browser, con tre utenti
 * veri di Keycloak (US-04, US-06, US-08).
 */
import { expect, test } from "@playwright/test";

import { entra, preparaEdizione } from "./sessione";

test("richiesta, approvazione del responsabile e conferma dell'admin", async ({
  browser,
  request,
}) => {
  const { titolo, edizioneId } = await preparaEdizione(request);

  // Il dipendente chiede l'iscrizione dal catalogo.
  const dipendente = await entra(browser, "dipendente");
  await dipendente.getByLabel("Cerca per titolo").fill(titolo);
  await dipendente.getByRole("button", { name: new RegExp(`^Iscriviti a ${titolo} `) }).click();
  await expect(dipendente.getByText(`Richiesta inviata per «${titolo}».`)).toBeVisible();
  await dipendente.getByRole("link", { name: "Le mie iscrizioni" }).click();
  const riga = dipendente.getByRole("row").filter({ hasText: titolo });
  await expect(riga).toContainText("Richiesta");

  // La responsabile diretta la approva.
  const responsabile = await entra(browser, "responsabile", "/approvazioni");
  await responsabile
    .getByRole("button", { name: `Approva la richiesta di Dario Dipendente per ${titolo}` })
    .click();
  await expect(responsabile.getByText("Richiesta di Dario Dipendente approvata.")).toBeVisible();

  // L'admin conferma il posto; il percorso diretto prova anche il fallback della SPA.
  const admin = await entra(browser, "admin", `/gestione/edizioni/${edizioneId.toString()}`);
  await admin.getByRole("button", { name: "Conferma l'iscrizione di Dario Dipendente" }).click();
  await expect(admin.getByText("Iscrizione di Dario Dipendente confermata.")).toBeVisible();

  // Il dipendente la vede Confermata.
  await dipendente.reload();
  await expect(riga).toContainText("Confermata");
});
