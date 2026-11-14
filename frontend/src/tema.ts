import { createTheme, darken, type CSSVariablesResolver, Modal, Notification } from "@mantine/core";

/** Pulsante di chiusura con un nome per i lettori di schermo (WCAG 2.2, 4.1.2). */
const chiudi = { closeButtonProps: { "aria-label": "Chiudi" } };

export const tema = createTheme({
  primaryColor: "indigo",
  // I colori predefiniti di Mantine non bastano per il contrasto 4.5:1 del testo
  // normale (WCAG 2.2, 1.4.3), lo ha trovato axe negli e2e: indigo.6 su bianco fa
  // 4.3:1, indigo.8 fa 5.7:1 (anche come testo dei collegamenti e dei pulsanti light).
  primaryShade: { light: 8, dark: 8 },
  // Testo dei pulsanti pieni scelto per il contrasto.
  autoContrast: true,
  components: {
    Modal: Modal.extend({ defaultProps: chiudi }),
    Notification: Notification.extend({ defaultProps: chiudi }),
  },
});

/**
 * Altre variabili CSS per il contrasto nel tema chiaro: il testo attenuato (gray.6 su
 * bianco fa 3.3:1, gray.7 fa 7.8:1) e il testo delle varianti light, come i badge
 * degli stati (green.9 su green.1 fa 3.8:1; scurito del 30% supera 5:1 per tutti i colori).
 */
export const variabiliCss: CSSVariablesResolver = (theme) => ({
  variables: {},
  light: {
    "--mantine-color-dimmed": theme.colors.gray[7],
    ...Object.fromEntries(
      Object.entries(theme.colors).map(([nome, scala]) => [
        `--mantine-color-${nome}-light-color`,
        darken(scala[9], 0.3),
      ]),
    ),
  },
  dark: {},
});
