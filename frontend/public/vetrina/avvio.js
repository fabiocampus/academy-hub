// Le due righe che lo starter della skill scrive inline nella <head>: qui in un file perché la
// CSP dell'App ammette solo script dello stesso sito (script-src 'self', threat model).
// L'entrata dell'hero aspetta motion.js, con 700 ms di margine; i momenti aspettano moments.js.
document.documentElement.classList.add("m-enter", "mo-js");
setTimeout(() => document.documentElement.classList.add("m-enter-done"), 700);
setTimeout(() => document.documentElement.classList.add("mo-safe"), 2500);
