import { createTheme } from "@mantine/core";

export const tema = createTheme({
  primaryColor: "indigo",
  // Testo dei pulsanti pieni scelto per il contrasto (WCAG 2.2, 1.4.3).
  autoContrast: true,
});
