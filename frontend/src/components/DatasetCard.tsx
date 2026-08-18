"use client";

import { useState } from "react";
import Link from "next/link";
import type { DatasetInfo } from "@/lib/api";
import { IconButton, TrashIcon } from "@/components/IconButton";
import { cn } from "@/lib/utils";

const DESCRIPTION_MAX_LENGTH = 200;

function NameEditor({
  name,
  onSave,
  disabled,
}: {
  name: string;
  onSave: (name: string) => void;
  disabled: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);

  function commit() {
    setEditing(false);
    const trimmed = value.trim();
    if (trimmed && trimmed !== name) onSave(trimmed);
    else setValue(name);
  }

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        title="Click to rename"
        className="w-full break-words text-left text-base font-semibold underline decoration-dotted underline-offset-2"
      >
        {name}
      </button>
    );
  }

  return (
    <input
      autoFocus
      value={value}
      disabled={disabled}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
        }
        if (e.key === "Escape") {
          setValue(name);
          setEditing(false);
        }
      }}
      className="w-full rounded border border-border bg-surface px-1 py-0.5 text-base font-semibold"
    />
  );
}

interface EditableTextBlockProps {
  label: string;
  value: string;
  onSave: (value: string) => void;
  disabled: boolean;
  placeholder: string;
  maxLength?: number;
  clampLines: number;
  rows: number;
  /** Typographic treatment for the non-editing display text -- each field
   * (description vs. notes) reads as a visually distinct "kind" of content
   * even though both share this same click-to-edit control. */
  displayClassName: string;
}

/** Shared click-to-edit affordance for both `description` and `notes` --
 * differ in maxLength/character counter (description caps at 200 chars to
 * fit a card; notes is uncapped, for a longer writeup also editable in full
 * on the Column Types page) and in `displayClassName`. */
function EditableTextBlock({
  label,
  value,
  onSave,
  disabled,
  placeholder,
  maxLength,
  clampLines,
  rows,
  displayClassName,
}: EditableTextBlockProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  function commit() {
    setEditing(false);
    const trimmed = draft.trim();
    if (trimmed !== value) onSave(trimmed);
  }

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium uppercase tracking-wide opacity-50">{label}</span>
      {editing ? (
        <div className="flex flex-col gap-1">
          <textarea
            autoFocus
            value={draft}
            disabled={disabled}
            maxLength={maxLength}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setDraft(value);
                setEditing(false);
              }
            }}
            placeholder={placeholder}
            rows={rows}
            className="w-full resize-none rounded border border-border bg-surface p-1.5 text-sm"
          />
          {maxLength && (
            <span className="self-end text-xs opacity-50">
              {draft.length}/{maxLength}
            </span>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => {
            setDraft(value);
            setEditing(true);
          }}
          title={`Click to edit ${label.toLowerCase()}`}
          className={cn(
            "text-left opacity-80 hover:opacity-100",
            displayClassName,
            // Tailwind's scanner needs each class name to appear literally in
            // source -- a template-interpolated `line-clamp-${n}` would never
            // get generated, so this can't be collapsed into one expression.
            clampLines === 3 ? "line-clamp-3" : "line-clamp-4"
          )}
        >
          {value || <span className="italic opacity-60">{placeholder}</span>}
        </button>
      )}
    </div>
  );
}

interface Props {
  dataset: DatasetInfo;
  onUpdate: (input: { name?: string; description?: string; notes?: string }) => void;
  onDelete: () => void;
  deleting: boolean;
  updating: boolean;
}

export function DatasetCard({ dataset, onUpdate, onDelete, deleting, updating }: Props) {
  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-border bg-surface text-sm shadow-md transition-shadow duration-200 hover:shadow-xl">
      {/* Theme-coloured accent strip -- ties the card to whichever of the 6
          colour themes (src/lib/theme.ts) is active, and gives it a distinct
          "lifted" top edge alongside the shadow below. */}
      <div className="h-1.5 shrink-0 bg-accent" />

      <div className="flex flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <NameEditor
              name={dataset.name}
              disabled={updating}
              onSave={(name) => onUpdate({ name })}
            />
          </div>
          <IconButton label={deleting ? "Deleting…" : "Delete dataset"} onClick={onDelete} disabled={deleting}>
            <TrashIcon />
          </IconButton>
        </div>

        <EditableTextBlock
          label="Description"
          value={dataset.description ?? ""}
          onSave={(description) => onUpdate({ description })}
          disabled={updating}
          placeholder="Add a short description…"
          maxLength={DESCRIPTION_MAX_LENGTH}
          clampLines={3}
          rows={3}
          displayClassName="text-sm italic"
        />

        <EditableTextBlock
          label="Notes"
          value={dataset.notes ?? ""}
          onSave={(notes) => onUpdate({ notes })}
          disabled={updating}
          placeholder="Add detailed analysis notes…"
          clampLines={4}
          rows={4}
          displayClassName="border-l-2 border-accent/40 pl-2 text-sm not-italic"
        />

        {/* Read-only facts about the uploaded file itself -- unlike name/
            description/notes above, nothing here is ever user-edited.
            Monospace marks it as raw file data rather than authored text. */}
        <div className="flex flex-col gap-0.5 rounded bg-accent/5 p-2 font-mono text-xs opacity-70">
          <span className="break-words">{dataset.filename}</span>
          <span>
            {dataset.row_count.toLocaleString()} rows · {dataset.schema.length} columns ·{" "}
            {Math.round(dataset.health_score)}% health score
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-2 text-xs">
          <Link href={`/dashboard/${dataset.dataset_id}/types`} className="underline">
            Review types
          </Link>
          <Link href={`/dashboard/${dataset.dataset_id}/reports`} className="underline">
            Visual reports
          </Link>
          <Link href={`/dashboard/${dataset.dataset_id}/presentation`} className="underline">
            Presentation
          </Link>
        </div>
      </div>
    </div>
  );
}
