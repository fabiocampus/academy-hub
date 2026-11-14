import { createTheme, Modal, Notification } from "@mantine/core";

/** Pulsante di chiusura con un nome per i lettori di schermo (WCAG 2.2, 4.1.2). */
const chiudi = { closeButtonProps: { "aria-label": "Chiudi" } };

export const tema = createTheme({
  primaryColor: "indigo",
  // Testo dei pulsanti pieni scelto per il contrasto (WCAG 2.2, 1.4.3).
  autoContrast: true,
  components: {
    Modal: Modal.extend({ defaultProps: chiudi }),
    Notification: Notification.extend({ defaultProps: chiudi }),
  },
});
