// Pomoćne funkcije za DOM, zajedničke za sve stranice

export const $ = (id) => document.getElementById(id);

// Novi element; tekst ide kroz textContent, pa podaci sa servera ne mogu da ubace HTML
export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}
