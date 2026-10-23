// Who is watching: the producer, or a fan with their own settings (docs/experience.md, "The people").
// The ready-made profiles let a judge switch between them mid-match and see the same moment change.
// Settings a viewer changes are kept in this browser; they start from the profile picked.

import { DETAILS, type Detail, type Pace, PACES } from "./described";
import { type Language, LANGUAGES } from "./language";
import { DELAYS } from "./playback";

export type Role = "producer" | "fan";
export type Mode = "casual" | "analyst";

/** The one figure an analyst pins at the top of the panel. */
export const METRICS = {
  pass_difficulty: "Pass difficulty",
  possession: "Possession",
  pass_accuracy: "Pass accuracy",
  distance: "Distance covered",
  shots: "Shots",
} as const;
export type Metric = keyof typeof METRICS;

export interface Settings {
  mode: Mode;
  club: string | null; // club ID: the fan's side
  player: string | null; // player ID: the player in focus, on top of the club
  metric: Metric;
  language: Language; // the cards' language (lib/live/language.ts)
  delay: (typeof DELAYS)[number]; // seconds of match time the fan's stream runs behind live
  calm: boolean; // no motion, nothing flashing
  graphics: boolean; // graphics on the pitch view
  pitch: boolean; // the pitch view itself: moving content a viewer can hide (WCAG 2.2.2)
  described: boolean; // the described feed, read out by the device's screen reader (lib/live/described.ts)
  detail: Detail; // how much it describes
  pace: Pace; // how often it speaks
}

export interface Profile {
  id: "nadia" | "sam" | "priya" | "lucia" | "tom";
  name: string;
  role: Role;
  summary: string;
  settings: Settings;
}

const BASE: Settings = {
  mode: "casual",
  club: null,
  player: null,
  metric: "possession",
  language: "en",
  delay: DELAYS[0],
  calm: false,
  graphics: true,
  pitch: true,
  described: false,
  detail: "standard",
  pace: "normal",
};

// The showcase's clubs and cast (docs/experience.md): Saltmarsh are "sal", Teo Varlan "sal-10".
export const PROFILES: Profile[] = [
  {
    id: "nadia",
    name: "Nadia",
    role: "producer",
    summary: "Runs the graphics: approves, edits or kills each one before it airs.",
    settings: BASE,
  },
  {
    id: "sam",
    name: "Sam",
    role: "fan",
    summary: "Casual fan of Saltmarsh, on a stream 40 seconds behind live.",
    settings: { ...BASE, club: "sal", delay: 40 },
  },
  {
    id: "priya",
    name: "Priya",
    role: "fan",
    summary: "Fantasy manager who owns Varlan. Analyst view, focused on him, pinned to pass difficulty.",
    settings: { ...BASE, mode: "analyst", club: "sal", player: "sal-10", metric: "pass_difficulty" },
  },
  {
    id: "lucia",
    name: "Lucía",
    role: "fan",
    summary: "In Madrid, joining after work: the graphics in Spanish, starting with what she missed.",
    settings: { ...BASE, language: "es", delay: 20 },
  },
  {
    id: "tom",
    name: "Tom",
    role: "fan",
    summary: "Blind fan following on a phone with a screen reader: the described feed at standard detail.",
    settings: { ...BASE, described: true, calm: true, pitch: false, graphics: false },
  },
];

export function profile(id: string | null | undefined): Profile {
  return PROFILES.find((p) => p.id === id) ?? PROFILES[1];
}

const SETTINGS_KEY = "footnote.settings";
const STARTED_KEY = "footnote.started";

// Where storage is blocked (a private window, say) what this browser keeps lasts as long as the page.
const memory = new Map<string, string>();
const listeners = new Set<() => void>();

function readText(key: string): string | null {
  try {
    return localStorage.getItem(key) ?? memory.get(key) ?? null;
  } catch {
    return memory.get(key) ?? null;
  }
}

function read<T>(key: string): T | null {
  const raw = readText(key);
  try {
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown): void {
  const raw = JSON.stringify(value);
  memory.set(key, raw);
  try {
    localStorage.setItem(key, raw);
  } catch {
    // Kept in memory only.
  }
  for (const listener of listeners) listener();
}

/** Calls `listener` whenever saved settings change, here or in another tab. */
export function subscribeSettings(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (e: StorageEvent) => e.key === SETTINGS_KEY && listener();
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** The saved settings of every profile, as stored: unchanged text until something is saved. */
export function savedSettingsText(): string {
  return readText(SETTINGS_KEY) ?? "";
}

/** A profile's settings: what this browser saved for it over the profile's own. */
export function settingsFrom(text: string, p: Profile): Settings {
  let saved: Partial<Settings> | undefined;
  try {
    saved = text ? (JSON.parse(text) as Record<string, Partial<Settings>>)[p.id] : undefined;
  } catch {
    saved = undefined;
  }
  const merged = { ...p.settings, ...saved };
  const valid =
    DELAYS.includes(merged.delay) &&
    merged.metric in METRICS &&
    merged.language in LANGUAGES &&
    merged.detail in DETAILS &&
    merged.pace in PACES;
  return valid ? merged : p.settings;
}

export function saveSettings(p: Profile, settings: Settings): void {
  write(SETTINGS_KEY, { ...read<Record<string, Settings>>(SETTINGS_KEY), [p.id]: settings });
}

export function resetSettings(p: Profile): void {
  const saved = read<Record<string, Settings>>(SETTINGS_KEY) ?? {};
  delete saved[p.id];
  write(SETTINGS_KEY, saved);
}

/** Remember that this browser started a run: only its starter may produce it. */
export function rememberStarted(runId: string): void {
  write(STARTED_KEY, [runId, ...(read<string[]>(STARTED_KEY) ?? []).filter((id) => id !== runId)].slice(0, 20));
}

export function startedHere(runId: string): boolean {
  return (read<string[]>(STARTED_KEY) ?? []).includes(runId);
}
