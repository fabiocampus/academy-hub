/**
 * Aiuti degli end-to-end: login dalla pagina di Keycloak e dati preparati con l'API.
 *
 * Ogni test crea il proprio corso e la propria edizione con un titolo unico, così si
 * può ripetere su un docker compose già usato senza `down -v` e senza dipendere dai
 * dati demo. Gli utenti di prova sono quelli del realm di sviluppo (password = nome).
 */
import {
  expect,
  test,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Page,
} from "@playwright/test";

export type Utente = "dipendente" | "responsabile" | "admin";

const KEYCLOAK = process.env.E2E_KEYCLOAK ?? "http://localhost:8080";
const API = "/api/v1";

// Un contesto del browser per utente; si chiudono tutti alla fine di ogni test.
const aperti: BrowserContext[] = [];
test.afterEach(async () => {
  await Promise.all(aperti.splice(0).map((contesto) => contesto.close()));
});

/** Apre `percorso` in un contesto nuovo (sessione separata) ed entra come `utente`. */
export async function entra(browser: Browser, utente: Utente, percorso = "/"): Promise<Page> {
  const contesto = await browser.newContext();
  aperti.push(contesto);
  const pagina = await contesto.newPage();
  await pagina.goto(percorso);
  await pagina.getByRole("button", { name: "Accedi" }).click();
  await pagina.getByLabel("Username or email").fill(utente);
  await pagina.getByLabel("Password", { exact: true }).fill(utente);
  await pagina.getByRole("button", { name: "Sign In" }).click();
  // Tornati nell'app: il menu c'è solo con la sessione aperta.
  await expect(pagina.getByRole("navigation", { name: "Menu principale" })).toBeVisible();
  return pagina;
}

/** Token del client academy-cli (password grant, solo sviluppo), come scripts/fumo_identita.py. */
async function token(request: APIRequestContext, utente: Utente): Promise<string> {
  const risposta = await request.post(`${KEYCLOAK}/realms/academy/protocol/openid-connect/token`, {
    form: { grant_type: "password", client_id: "academy-cli", username: utente, password: utente },
  });
  expect(risposta.ok()).toBe(true);
  return ((await risposta.json()) as { access_token: string }).access_token;
}

function tra(giorni: number): string {
  const data = new Date();
  data.setDate(data.getDate() + giorni);
  return data.toISOString().slice(0, 10);
}

export interface EdizioneDiProva {
  titolo: string;
  corsoId: number;
  edizioneId: number;
}

/** Un corso nuovo con un'edizione fra un mese, creati dall'admin con l'API. */
export async function preparaEdizione(request: APIRequestContext): Promise<EdizioneDiProva> {
  const intestazioni = { Authorization: `Bearer ${await token(request, "admin")}` };
  const titolo = `E2E ${Date.now().toString(36)}`;
  const corso = await request.post(`${API}/corsi`, {
    headers: intestazioni,
    data: { titolo, descrizione: "Creato dal test end-to-end", durata_ore: 8 },
  });
  expect(corso.status()).toBe(201);
  const corsoId = ((await corso.json()) as { id: number }).id;
  const edizione = await request.post(`${API}/edizioni`, {
    headers: intestazioni,
    data: { corso_id: corsoId, data_inizio: tra(30), data_fine: tra(31), capienza: 5 },
  });
  expect(edizione.status()).toBe(201);
  return { titolo, corsoId, edizioneId: ((await edizione.json()) as { id: number }).id };
}
