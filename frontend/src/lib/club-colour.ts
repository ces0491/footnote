// The colour a club is shown in on the page's dark ground. Graphics such as a possession bar need
// 3:1 contrast with what they sit on (WCAG 1.4.11), and a kit's first colour doesn't always have it:
// Kingsferry's navy all but vanishes here. Then the kit's second colour stands in, if it has colour
// of its own (Kingsferry's amber does; a cream or white would read as nobody's), or failing that the
// first colour lightened until it reads. The pitch view draws the kits as they are.

import type { Club } from "./live/contract";

/** The lightest surface a club's colour sits on: --muted in app/globals.css. */
export const GROUND = "#1e2834";
export const NIGHT = "#0d141e"; // --night
export const CHALK = "#f1f4f7"; // --foreground
const MIN_CONTRAST = 3;

type Rgb = [number, number, number];

function rgb(hex: string): Rgb {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as Rgb;
}

function hex([r, g, b]: Rgb): string {
  return `#${[r, g, b].map((c) => Math.round(c * 255).toString(16).padStart(2, "0")).join("")}`;
}

function luminance(colour: Rgb): number {
  const [r, g, b] = colour.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** The WCAG contrast ratio between two colours, from 1 to 21. */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(rgb(a)), luminance(rgb(b))].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Whether a colour has a hue to it, rather than being a white, grey or black. */
function coloured(hex: string): boolean {
  const c = rgb(hex);
  return Math.max(...c) - Math.min(...c) > 0.15;
}

/** `colour` mixed with white, a twentieth at a time, until it has 3:1 against the ground. */
function lightened(colour: string): string {
  const c = rgb(colour);
  for (let t = 0.05; t < 1; t += 0.05) {
    const mixed = hex(c.map((v) => v + (1 - v) * t) as Rgb);
    if (contrast(mixed, GROUND) >= MIN_CONTRAST) return mixed;
  }
  return CHALK;
}

const shown = new Map<string, string>();

/** The colour `club` is shown in on the page: see the note at the top. */
export function clubColour(club: Club): string {
  const key = club.colours.join();
  let colour = shown.get(key);
  if (colour === undefined) {
    const [first, second] = club.colours;
    if (contrast(first, GROUND) >= MIN_CONTRAST) colour = first;
    else if (contrast(second, GROUND) >= MIN_CONTRAST && coloured(second)) colour = second;
    else colour = lightened(first);
    shown.set(key, colour);
  }
  return colour;
}

/** The page's dark or light ink, whichever reads better on `background`. */
export function inkOn(background: string): string {
  return contrast(NIGHT, background) >= contrast(CHALK, background) ? NIGHT : CHALK;
}
