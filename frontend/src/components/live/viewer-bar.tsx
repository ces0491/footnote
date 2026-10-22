"use client";

import { RotateCcw, SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";

import { PersonaBadge } from "@/components/persona";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { MatchMeta } from "@/lib/live/contract";
import { type Detail, DETAILS, type Pace, PACES } from "@/lib/live/described";
import { type Language, LANGUAGES } from "@/lib/live/language";
import { DELAYS } from "@/lib/live/playback";
import { METRICS, type Metric, type Mode, PROFILES, type Profile, type Settings } from "@/lib/live/profiles";

/** Who is watching: switch between the ready-made viewers mid-match. */
export function ProfileSwitch({ current, onPick }: { current: Profile; onPick: (id: Profile["id"]) => void }) {
  return (
    <ToggleGroup
      type="single"
      value={current.id}
      onValueChange={(v) => v && onPick(v as Profile["id"])}
      aria-label="Watch as"
      // As wide as its place and no wider: on a phone the five scroll sideways rather than push the page wide.
      className="-mx-1 flex w-full min-w-0 gap-1.5 overflow-x-auto px-1 py-1 scrollbar-none"
    >
      {PROFILES.map((p) => (
        <ToggleGroupItem
          key={p.id}
          value={p.id}
          title={p.summary}
          className="group/who h-9 shrink-0 gap-2 rounded-full border border-border pr-3.5 pl-1 data-[state=on]:border-foreground data-[state=on]:bg-foreground data-[state=on]:text-background"
        >
          <PersonaBadge
            id={p.id}
            className="size-7 bg-transparent ring-0 group-data-[state=on]/who:bg-background/10"
          />
          {p.name}
          {p.role === "producer" && (
            <span className="hidden text-muted-foreground group-data-[state=on]/who:text-background/70 sm:inline">producer</span>
          )}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

/** A labelled set of settings. */
function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-5 border-b px-6 py-6 last:border-0">
      <h3 className="text-xs font-semibold text-muted-foreground">{title}</h3>
      {children}
    </section>
  );
}

/** A choice among a few options, all in view: a row of buttons that act as radio buttons. */
function Choice<T extends string>({
  id,
  label,
  value,
  options,
  onChange,
  note,
}: {
  id: string;
  label: string;
  value: T;
  options: [T, string][];
  onChange: (value: T) => void;
  note?: string;
}) {
  return (
    <div className="space-y-2">
      <div id={id} className="text-sm font-medium">
        {label}
      </div>
      <ToggleGroup
        type="single"
        variant="outline"
        spacing={0}
        value={value}
        onValueChange={(v) => v && onChange(v as T)}
        aria-labelledby={id}
        aria-describedby={note ? `${id}-note` : undefined}
        className="flex w-full"
      >
        {options.map(([v, text]) => (
          <ToggleGroupItem
            key={v}
            value={v}
            className="h-9 flex-1 px-2 data-[state=on]:border-foreground data-[state=on]:bg-foreground data-[state=on]:text-background"
          >
            {text}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      {note && (
        <p id={`${id}-note`} className="text-xs text-muted-foreground">
          {note}
        </p>
      )}
    </div>
  );
}

/** A setting that is on or off, with what it does beside it. */
function Toggle({ id, label, note, checked, onChange }: { id: string; label: string; note?: string; checked: boolean; onChange: (on: boolean) => void }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="space-y-1">
        <Label htmlFor={id}>{label}</Label>
        {note && (
          <p id={`${id}-note`} className="text-xs text-muted-foreground">
            {note}
          </p>
        )}
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} aria-describedby={note ? `${id}-note` : undefined} />
    </div>
  );
}

/** A fan's settings, kept in this browser for the profile they started from. Changes show at once. */
export function SettingsSheet({
  profile,
  settings,
  match,
  onChange,
  onReset,
}: {
  profile: Profile;
  settings: Settings;
  match: MatchMeta;
  onChange: (settings: Settings) => void;
  onReset: () => void;
}) {
  const set = <K extends keyof Settings>(key: K, value: Settings[K]) => onChange({ ...settings, [key]: value });
  const squads = match.lineups.map((lineup) => ({
    club: lineup.club_id === match.home.id ? match.home : match.away,
    players: [...lineup.starters, ...lineup.bench].sort((a, b) => a.shirt - b.shirt),
  }));
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="h-9 rounded-full px-3.5">
          <SlidersHorizontal /> Settings
        </Button>
      </SheetTrigger>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>{profile.name}&apos;s settings</SheetTitle>
          <SheetDescription>
            {profile.summary} Changes stay in this browser.
          </SheetDescription>
        </SheetHeader>
        <Group title="How you follow it">
          <Choice<Mode>
            id="set-mode"
            label="Mode"
            value={settings.mode}
            options={[
              ["casual", "Casual"],
              ["analyst", "Analyst"],
            ]}
            onChange={(v) => set("mode", v)}
          />
          <Choice
            id="set-club"
            label="Your club"
            value={settings.club ?? "none"}
            options={[
              ["none", "None"],
              [match.home.id, match.home.short_name],
              [match.away.id, match.away.short_name],
            ]}
            onChange={(v) => set("club", v === "none" ? null : v)}
          />
          <div className="space-y-2">
            <Label htmlFor="set-player">Player in focus</Label>
            <NativeSelect id="set-player" value={settings.player ?? ""} onChange={(e) => set("player", e.target.value || null)} className="h-9">
              <option value="">None</option>
              {squads.map(({ club, players }) => (
                <optgroup key={club.id} label={club.name}>
                  {players.map((p) => (
                    <option key={p.player_id} value={p.player_id}>
                      {p.shirt} {p.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </NativeSelect>
          </div>
          <div className="space-y-2">
            <Label htmlFor="set-metric">Pinned metric</Label>
            <NativeSelect id="set-metric" value={settings.metric} onChange={(e) => set("metric", e.target.value as Metric)} className="h-9">
              {Object.entries(METRICS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </NativeSelect>
          </div>
        </Group>
        <Group title="Language and delay">
          <Choice<Language>
            id="set-language"
            label="Cards in"
            value={settings.language}
            options={Object.entries(LANGUAGES) as [Language, string][]}
            onChange={(v) => set("language", v)}
            note="Translated by Azure AI Translator; code checks every figure and name came through."
          />
          <Choice
            id="set-delay"
            label="Stream delay, seconds behind live"
            value={String(settings.delay)}
            options={DELAYS.map((d) => [String(d), `${d} s`])}
            onChange={(v) => set("delay", Number(v) as Settings["delay"])}
            note="In match time: a replay at 2× plays it in half the time."
          />
        </Group>
        <Group title="Display and access">
          <Toggle id="set-calm" label="Calm mode" note="No motion or flashing" checked={settings.calm} onChange={(v) => set("calm", v)} />
          <Toggle
            id="set-pitch"
            label="The pitch view"
            note="Hide it to follow from the panel alone"
            checked={settings.pitch}
            onChange={(v) => set("pitch", v)}
          />
          <Toggle id="set-graphics" label="Graphics on the pitch" checked={settings.graphics} onChange={(v) => set("graphics", v)} />
          <Toggle
            id="set-described"
            label="Described feed"
            note="The match in words, for a screen reader"
            checked={settings.described}
            onChange={(v) => set("described", v)}
          />
          {settings.described && (
            <>
              <Choice<Detail>
                id="set-detail"
                label="Feed detail"
                value={settings.detail}
                options={Object.entries(DETAILS) as [Detail, string][]}
                onChange={(v) => set("detail", v)}
              />
              <Choice<Pace>
                id="set-pace"
                label="Feed pace"
                value={settings.pace}
                options={(Object.entries(PACES) as [Pace, (typeof PACES)[Pace]][]).map(([v, p]) => [v, p.label])}
                onChange={(v) => set("pace", v)}
              />
            </>
          )}
        </Group>
        <div className="mt-auto border-t px-6 py-4">
          <Button variant="ghost" size="sm" onClick={onReset}>
            <RotateCcw /> Back to {profile.name}&apos;s own settings
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
