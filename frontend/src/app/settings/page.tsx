"use client";

import { useRouter } from "next/navigation";
import { useTheme } from "@/components/theme-provider";
import { useUpdateSettings } from "@/hooks/useSettings";
import { COLOR_THEMES, THEME_MODES, type ColorTheme, type ThemeMode } from "@/lib/theme";
import { cn } from "@/lib/utils";

export default function SettingsPage() {
  const router = useRouter();
  const { mode, colorTheme, setMode, setColorTheme } = useTheme();
  const updateSettings = useUpdateSettings();

  function handleModeChange(next: ThemeMode) {
    setMode(next);
    updateSettings.mutate({ theme_mode: next, color_theme: colorTheme });
  }

  function handleColorThemeChange(next: ColorTheme) {
    setColorTheme(next);
    updateSettings.mutate({ theme_mode: mode, color_theme: next });
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-8 px-4 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <button onClick={() => router.push("/dashboard")} className="text-sm underline">
          Back
        </button>
      </div>

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
    </main>
  );
}
