"use client";

import { useEffect, useState } from "react";
import { useTheme } from "@/components/theme-provider";
import { RichTextEditor } from "@/components/RichTextEditor";
import {
  useSettings,
  useUpdateFooterPresets,
  useUpdateHeaderPresets,
  useUpdateSettings,
} from "@/hooks/useSettings";
import type { FooterPreset, HeaderPreset } from "@/lib/api";
import { COLOR_THEMES, THEME_MODES, type ColorTheme, type ThemeMode } from "@/lib/theme";
import { cn } from "@/lib/utils";

const MAX_PRESETS = 5;
// Mirrors the backend's max_logo_size_kb default (src/core/config.py) -- no
// shared-constants mechanism exists between the two stacks today, so this is
// a client-side pre-check for a fast/clear error; the server-side check is
// the real enforcement.
const MAX_LOGO_BYTES = 200 * 1024;

function newHeaderPreset(): HeaderPreset {
  return { id: crypto.randomUUID(), title: "", logo: null, enabled: false };
}

function newFooterPreset(): FooterPreset {
  return { id: crypto.randomUUID(), html: "", enabled: false };
}

// Only one preset (per type) can be "active" at a time -- enabling one
// deactivates its siblings, enforced again server-side (src/settings/service.py).
function toggleEnabled<T extends { id: string; enabled: boolean }>(presets: T[], id: string): T[] {
  const target = presets.find((p) => p.id === id);
  const nextEnabled = target ? !target.enabled : false;
  return presets.map((p) => ({ ...p, enabled: p.id === id ? nextEnabled : false }));
}

export default function SettingsPage() {
  const { mode, colorTheme, setMode, setColorTheme } = useTheme();
  const updateSettings = useUpdateSettings();
  const settingsQuery = useSettings();
  const updateHeaderPresets = useUpdateHeaderPresets();
  const updateFooterPresets = useUpdateFooterPresets();

  // null = "no local edits yet, defer to the query result" -- same
  // local-state-forks-from-query pattern as the presentation builder.
  const [localHeaders, setLocalHeaders] = useState<HeaderPreset[] | null>(null);
  const [localFooters, setLocalFooters] = useState<FooterPreset[] | null>(null);
  const [logoError, setLogoError] = useState<string | null>(null);

  const headers = localHeaders ?? settingsQuery.data?.header_presets ?? [];
  const footers = localFooters ?? settingsQuery.data?.footer_presets ?? [];

  // Debounced autosave for free-text edits (title/logo/rich-text) -- discrete
  // actions (add/remove/toggle-enable) save immediately instead, in their
  // own handlers below, matching the presentation builder's same two-tier
  // instant-vs-debounced convention.
  useEffect(() => {
    if (localHeaders === null) return;
    const timeout = setTimeout(() => updateHeaderPresets.mutate(localHeaders), 800);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localHeaders]);

  useEffect(() => {
    if (localFooters === null) return;
    const timeout = setTimeout(() => updateFooterPresets.mutate(localFooters), 800);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localFooters]);

  function handleModeChange(next: ThemeMode) {
    setMode(next);
    updateSettings.mutate({ theme_mode: next, color_theme: colorTheme });
  }

  function handleColorThemeChange(next: ColorTheme) {
    setColorTheme(next);
    updateSettings.mutate({ theme_mode: mode, color_theme: next });
  }

  function handleAddHeader() {
    if (headers.length >= MAX_PRESETS) return;
    setLocalHeaders([...headers, newHeaderPreset()]);
  }

  function handleRemoveHeader(id: string) {
    const next = headers.filter((p) => p.id !== id);
    setLocalHeaders(next);
    updateHeaderPresets.mutate(next);
  }

  function handleToggleHeaderEnabled(id: string) {
    const next = toggleEnabled(headers, id);
    setLocalHeaders(next);
    updateHeaderPresets.mutate(next);
  }

  function handleHeaderTitleChange(id: string, title: string) {
    setLocalHeaders(headers.map((p) => (p.id === id ? { ...p, title } : p)));
  }

  function handleHeaderLogoChange(id: string, file: File) {
    if (file.size > MAX_LOGO_BYTES) {
      setLogoError(`Logo must be under ${Math.round(MAX_LOGO_BYTES / 1024)}KB`);
      return;
    }
    setLogoError(null);
    const reader = new FileReader();
    reader.onload = () => {
      const logo = reader.result as string;
      // Goes through the same debounced autosave as title edits (below) --
      // a one-time file pick doesn't need to skip the debounce the way
      // add/remove/toggle do, an ~800ms delay here is imperceptible.
      setLocalHeaders(headers.map((p) => (p.id === id ? { ...p, logo } : p)));
    };
    reader.readAsDataURL(file);
  }

  function handleAddFooter() {
    if (footers.length >= MAX_PRESETS) return;
    setLocalFooters([...footers, newFooterPreset()]);
  }

  function handleRemoveFooter(id: string) {
    const next = footers.filter((p) => p.id !== id);
    setLocalFooters(next);
    updateFooterPresets.mutate(next);
  }

  function handleToggleFooterEnabled(id: string) {
    const next = toggleEnabled(footers, id);
    setLocalFooters(next);
    updateFooterPresets.mutate(next);
  }

  function handleFooterHtmlChange(id: string, html: string) {
    setLocalFooters(footers.map((p) => (p.id === id ? { ...p, html } : p)));
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-8 px-4 py-12">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-medium">Appearance</h2>
        <div className="flex gap-2">
          {THEME_MODES.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => handleModeChange(option)}
              className={cn(
                "rounded border px-4 py-2 text-sm capitalize transition-colors",
                mode === option
                  ? "border-accent bg-accent text-accent-foreground"
                  : "border-border text-foreground"
              )}
            >
              {option}
            </button>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-medium">Colour theme</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {COLOR_THEMES.map((theme) => (
            <button
              key={theme.value}
              type="button"
              onClick={() => handleColorThemeChange(theme.value)}
              className={cn(
                "flex items-center gap-2 rounded border px-3 py-2 text-left text-sm transition-colors",
                colorTheme === theme.value
                  ? "border-accent ring-1 ring-accent"
                  : "border-border text-foreground"
              )}
            >
              <span
                className="h-4 w-4 shrink-0 rounded-full border border-border"
                style={{ backgroundColor: theme.swatch }}
              />
              {theme.label}
            </button>
          ))}
        </div>
      </section>

      {updateSettings.isError && (
        <p className="text-sm text-red-600">
          Couldn&apos;t save to your account, but the change still applies on this device.
        </p>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-medium">Header presets</h2>
        <p className="text-xs opacity-60">
          Shown on downloaded PDFs/images and on shared chart links. Enable one to make it active
          — enabling a preset disables any other.
        </p>
        {headers.map((preset) => (
          <div key={preset.id} className="flex flex-col gap-2 rounded border border-border p-3">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={preset.enabled}
                onChange={() => handleToggleHeaderEnabled(preset.id)}
                aria-label="Enable this header"
              />
              <input
                value={preset.title}
                onChange={(e) => handleHeaderTitleChange(preset.id, e.target.value)}
                placeholder="Title"
                className="flex-1 rounded border border-border bg-surface px-2 py-1 text-sm"
              />
              <button
                type="button"
                onClick={() => handleRemoveHeader(preset.id)}
                className="text-xs underline opacity-60 hover:opacity-100"
              >
                Remove
              </button>
            </div>
            <div className="flex items-center gap-3">
              {preset.logo && (
                // A user-uploaded data URL, not a static/remote asset next/image can optimize.
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preset.logo} alt="Logo preview" className="h-10 w-10 rounded object-contain" />
              )}
              <input
                type="file"
                accept="image/*"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleHeaderLogoChange(preset.id, file);
                }}
                className="text-xs"
              />
            </div>
          </div>
        ))}
        {logoError && <p className="text-xs text-red-600">{logoError}</p>}
        <button
          type="button"
          onClick={handleAddHeader}
          disabled={headers.length >= MAX_PRESETS}
          className="self-start rounded border border-dashed border-border px-3 py-1.5 text-sm disabled:opacity-40"
        >
          + Add header ({headers.length}/{MAX_PRESETS})
        </button>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-medium">Footer presets</h2>
        <p className="text-xs opacity-60">
          Shown on downloaded PDFs/images and on shared chart links. Enable one to make it active
          — enabling a preset disables any other.
        </p>
        {footers.map((preset) => (
          <div key={preset.id} className="flex flex-col gap-2 rounded border border-border p-3">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={preset.enabled}
                onChange={() => handleToggleFooterEnabled(preset.id)}
                aria-label="Enable this footer"
              />
              <span className="flex-1 text-xs opacity-60">Footer</span>
              <button
                type="button"
                onClick={() => handleRemoveFooter(preset.id)}
                className="text-xs underline opacity-60 hover:opacity-100"
              >
                Remove
              </button>
            </div>
            <RichTextEditor
              key={preset.id}
              value={preset.html}
              onChange={(html) => handleFooterHtmlChange(preset.id, html)}
              placeholder="Address, contact info…"
            />
          </div>
        ))}
        <button
          type="button"
          onClick={handleAddFooter}
          disabled={footers.length >= MAX_PRESETS}
          className="self-start rounded border border-dashed border-border px-3 py-1.5 text-sm disabled:opacity-40"
        >
          + Add footer ({footers.length}/{MAX_PRESETS})
        </button>
      </section>

      {(updateHeaderPresets.isError || updateFooterPresets.isError) && (
        <p className="text-sm text-red-600">
          Couldn&apos;t save branding:{" "}
          {((updateHeaderPresets.error ?? updateFooterPresets.error) as Error).message}
        </p>
      )}
    </main>
  );
}
