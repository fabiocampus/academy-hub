/** Navigazione fuori dall'App React, in un oggetto perché i test possano sostituirla (jsdom non naviga). */
export const navigazione = {
  sostituisci(indirizzo: string): void {
    window.location.replace(indirizzo);
  },
};
