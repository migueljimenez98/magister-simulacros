// Notas sobre 10 + escala de color continua rojo→amarillo→verde.
// (percent 0-100 internamente; se muestra /10).

export function nota10(percent: number | null | undefined): string {
  if (percent == null) return "—";
  return (percent / 10).toFixed(1);
}

// Color continuo: 0 → rojo, 5 → amarillo, 10 → verde.
export function notaHsl(percent: number | null | undefined): string {
  if (percent == null) return "rgb(113 113 122)"; // zinc-500
  const p = Math.max(0, Math.min(100, percent));
  const hue = p * 1.2; // 0=rojo, 60=amarillo, 120=verde
  return `hsl(${hue} 75% 55%)`;
}
