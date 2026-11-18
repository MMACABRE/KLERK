// Printable documents: the print button is hidden without JavaScript and opens the browser's print dialog.
document.querySelectorAll('button[data-print]').forEach((button) => {
  button.hidden = false;
  button.addEventListener('click', () => window.print());
});
