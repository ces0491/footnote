"use client";

import { RotateCcw, SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
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
      variant="outline"
      size="sm"
      value={current.id}
      onValueChange={(v) => v && onPick(v as Profile["id"])}
      aria-label="Watch as"
    >
      {PROFILES.map((p) => (
        <ToggleGroupItem key={p.id} value={p.id} className="px-3" title={p.summary}>
          {p.name}
          {/* Darker on the muted background of a selected or hovered item, for 4.5:1 contrast. */}
          <span className="text-muted-foreground group-hover/toggle:text-foreground/70 group-data-[state=on]/toggle:text-foreground/70">
            {p.role === "producer" ? " · producer" : ""}
          </span>
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

function Row({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] items-center gap-3">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}

/** A fan's settings, kept in this browser for the profile they started from. */
export function SettingsDialog({
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
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <SlidersHorizontal /> Settings
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{profile.name}&apos;s settings</DialogTitle>
          <DialogDescription>{profile.summary} Changes stay in this browser.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <Row id="set-mode" label="Mode">
            <NativeSelect id="set-mode" value={settings.mode} onChange={(e) => set("mode", e.target.value as Mode)}>
              <option value="casual">Casual</option>
              <option value="analyst">Analyst</option>
            </NativeSelect>
          </Row>
          <Row id="set-club" label="Your club">
            <NativeSelect id="set-club" value={settings.club ?? ""} onChange={(e) => set("club", e.target.value || null)}>
              <option value="">None</option>
              <option value={match.home.id}>{match.home.name}</option>
              <option value={match.away.id}>{match.away.name}</option>
            </NativeSelect>
          </Row>
          <Row id="set-player" label="Player in focus">
            <NativeSelect id="set-player" value={settings.player ?? ""} onChange={(e) => set("player", e.target.value || null)}>
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
          </Row>
          <Row id="set-language" label="Cards in">
            <NativeSelect
              id="set-language"
              value={settings.language}
              onChange={(e) => set("language", e.target.value as Language)}
              aria-describedby="set-language-note"
            >
              {Object.entries(LANGUAGES).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </NativeSelect>
          </Row>
          <p id="set-language-note" className="-mt-2 pl-39 text-xs text-muted-foreground">
            Translated by Azure AI Translator; code checks every figure and name came through.
          </p>
          <Row id="set-metric" label="Pinned metric">
            <NativeSelect id="set-metric" value={settings.metric} onChange={(e) => set("metric", e.target.value as Metric)}>
              {Object.entries(METRICS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </NativeSelect>
          </Row>
          <Row id="set-delay" label="Stream delay">
            <div className="grid gap-1">
              <NativeSelect
                id="set-delay"
                value={settings.delay}
                onChange={(e) => set("delay", Number(e.target.value) as Settings["delay"])}
                aria-describedby="set-delay-note"
              >
                {DELAYS.map((d) => (
                  <option key={d} value={d}>
                    {d} seconds behind live
                  </option>
                ))}
              </NativeSelect>
              <span id="set-delay-note" className="text-xs text-muted-foreground">
                In match time: a replay at 2× plays it in half the time.
              </span>
            </div>
          </Row>
          <Row id="set-calm" label="Calm mode">
            <div className="flex items-center gap-2">
              <Switch id="set-calm" checked={settings.calm} onCheckedChange={(v) => set("calm", v)} />
              <span className="text-xs text-muted-foreground">No motion or flashing</span>
            </div>
          </Row>
          <Row id="set-pitch" label="The pitch view">
            <div className="flex items-center gap-2">
              <Switch id="set-pitch" checked={settings.pitch} onCheckedChange={(v) => set("pitch", v)} />
              <span className="text-xs text-muted-foreground">Hide it to follow from the panel alone</span>
            </div>
          </Row>
          <Row id="set-graphics" label="Graphics on the pitch">
            <Switch id="set-graphics" checked={settings.graphics} onCheckedChange={(v) => set("graphics", v)} />
          </Row>
          <Row id="set-described" label="Described feed">
            <div className="flex items-center gap-2">
              <Switch id="set-described" checked={settings.described} onCheckedChange={(v) => set("described", v)} />
              <span className="text-xs text-muted-foreground">The match in words, for a screen reader</span>
            </div>
          </Row>
          {settings.described && (
            <>
              <Row id="set-detail" label="Feed detail">
                <NativeSelect id="set-detail" value={settings.detail} onChange={(e) => set("detail", e.target.value as Detail)}>
                  {Object.entries(DETAILS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </NativeSelect>
              </Row>
              <Row id="set-pace" label="Feed pace">
                <NativeSelect id="set-pace" value={settings.pace} onChange={(e) => set("pace", e.target.value as Pace)}>
                  {Object.entries(PACES).map(([value, p]) => (
                    <option key={value} value={value}>
                      {p.label}
                    </option>
                  ))}
                </NativeSelect>
              </Row>
            </>
          )}
        </div>
        <div>
          <Button variant="ghost" size="sm" onClick={onReset}>
            <RotateCcw /> Back to {profile.name}&apos;s own settings
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
