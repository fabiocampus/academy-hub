/**
 * Controlli automatici di accessibilità (WCAG 2.2 A e AA, per quanto axe sa verificare)
 * sulle pagine principali di ogni profilo, con dati veri dall'API. axe non sostituisce
 * una prova con tastiera e lettore di schermo: trova le regressioni meccaniche.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { entra, preparaEdizione, type Utente } from "./sessione";

const REGOLE = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function senzaViolazioni(pagina: Page, titolo: string): Promise<void> {
  // La pagina è pronta quando ha il suo titolo e nessun caricamento in corso.
  await expect(pagina.getByRole("heading", { level: 1, name: titolo })).toBeVisible();
  await expect(pagina.locator('[aria-busy="true"]')).toHaveCount(0);
  const esito = await new AxeBuilder({ page: pagina }).withTags(REGOLE).analyze();
  expect(esito.violations, `violazioni axe su «${titolo}»`).toEqual([]);
}

test("pagina pubblica, dove arriva chi non ha una sessione", async ({ page }) => {
  // Senza animazioni d'ingresso axe non misura il contrasto a metà dissolvenza.
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page).toHaveURL(/\/benvenuto\.html$/);
  await senzaViolazioni(page, "Iscrizioni ai corsi dell'Academy aziendale");
});

test("pagine di ogni profilo", async ({ browser, request }) => {
  const { titolo, corsoId, edizioneId } = await preparaEdizione(request);
  const pagine: [Utente, string, string][] = [
    ["dipendente", "/", "Catalogo"],
    ["dipendente", "/iscrizioni", "Le mie iscrizioni"],
    ["responsabile", "/approvazioni", "Approvazioni"],
    ["admin", "/gestione", "Gestione corsi"],
    ["admin", `/gestione/corsi/${corsoId.toString()}`, titolo],
    ["admin", `/gestione/edizioni/${edizioneId.toString()}`, titolo],
  ];
  const sessioni = new Map<Utente, Page>();
  for (const [utente, percorso, intestazione] of pagine) {
    let pagina = sessioni.get(utente);
    if (pagina === undefined) {
      pagina = await entra(browser, utente, percorso);
      sessioni.set(utente, pagina);
    } else {
      await pagina.goto(percorso);
    }
    await senzaViolazioni(pagina, intestazione);
  }
});
