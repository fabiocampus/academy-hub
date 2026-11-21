/**
 * Un solo tema Mantine dai token della pagina pubblica (taste-skill, ADR-0020): palette
 * white-link-blue, font Funnel ospitati dall'App (`public/vetrina/fonts`), raggi soft,
 * pulsanti alti 44 px. Le variabili CSS gemelle per le parti fuori da Mantine sono in
 * `stile.css`.
 */
import {
  Button,
  createTheme,
  darken,
  Modal,
  Notification,
  type CSSVariablesResolver,
  type MantineColorsTuple,
} from "@mantine/core";

/** Pulsante di chiusura con un nome per i lettori di schermo (WCAG 2.2, 4.1.2). */
const chiudi = { closeButtonProps: { "aria-label": "Chiudi" } };

/** Il blu d'azione della pagina pubblica (#1a4be0) all'indice 7, con la sua scala. */
const blu: MantineColorsTuple = [
  "#eef2fd",
  "#dce4fb",
  "#b6c6f6",
  "#8ea6f1",
  "#6585eb",
  "#3f67e6",
  "#2a57e3",
  "#1a4be0",
  "#143cb4",
  "#0f2d87",
];

const TESTO = '"Funnel Sans", system-ui, sans-serif';
const TITOLI = '"Funnel Display", system-ui, sans-serif';

export const tema = createTheme({
  colors: { blu },
  primaryColor: "blu",
  // #1a4be0 su bianco fa 6.9:1: basta per il testo normale (WCAG 2.2, 1.4.3, axe negli e2e).
  primaryShade: { light: 7, dark: 7 },
  // Testo dei pulsanti pieni scelto per il contrasto.
  autoContrast: true,
  black: "#111111",
  white: "#ffffff",
  fontFamily: TESTO,
  fontFamilyMonospace: '"DM Mono", ui-monospace, Consolas, monospace',
  headings: {
    fontFamily: TITOLI,
    fontWeight: "400",
    sizes: {
      h1: { fontSize: "clamp(2rem, 1.4rem + 1.6vw, 2.75rem)", lineHeight: "1.08" },
      h2: { fontSize: "1.75rem", lineHeight: "1.15" },
      h3: { fontSize: "1.25rem", lineHeight: "1.25" },
    },
  },
  defaultRadius: "sm",
  radius: { xs: "4px", sm: "8px", md: "12px", lg: "20px", xl: "24px" },
  components: {
    // I pulsanti della taglia normale sono alti 44 px come quelli della pagina pubblica.
    Button: Button.extend({
      vars: (_tema, proprieta) =>
        proprieta.size === undefined || proprieta.size === "md"
          ? { root: { "--button-height": "44px", "--button-padding-x": "20px" } }
          : { root: {} },
    }),
    Modal: Modal.extend({ defaultProps: chiudi }),
    Notification: Notification.extend({ defaultProps: chiudi }),
  },
});

/**
 * Altre variabili CSS per il contrasto nel tema chiaro: il testo attenuato (#6b6b6b su
 * bianco fa 5.3:1) e il testo delle varianti light, come i badge degli stati (green.9 su
 * green.1 fa 3.8:1; scurito del 30% supera 5:1 per tutti i colori).
 */
export const variabiliCss: CSSVariablesResolver = (theme) => ({
  variables: {},
  light: {
    "--mantine-color-body": "#ffffff",
    "--mantine-color-text": "#111111",
    "--mantine-color-dimmed": "#6b6b6b",
    "--mantine-color-default-border": "color-mix(in oklab, #111111 11%, transparent)",
    ...Object.fromEntries(
      Object.entries(theme.colors).map(([nome, scala]) => [
        `--mantine-color-${nome}-light-color`,
        darken(scala[9], 0.3),
      ]),
    ),
  },
  dark: {},
});
