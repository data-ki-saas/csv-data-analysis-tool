"use client";

import { useState } from "react";
import Link from "next/link";
import type { DatasetInfo } from "@/lib/api";
import { IconButton, TrashIcon } from "@/components/IconButton";

const DESCRIPTION_MAX_LENGTH = 200;

function autoDescription(dataset: DatasetInfo): string {
  return (
    `${dataset.row_count.toLocaleString()} rows · ${dataset.schema.length} columns · ` +
    `${Math.round(dataset.health_score)}% health score`
  );
}

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
        className="text-left font-medium underline decoration-dotted underline-offset-2"
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
      className="w-full rounded border border-border bg-surface px-1 py-0.5 font-medium"
    />
  );
}

function DescriptionEditor({
  dataset,
  onSave,
  disabled,
}: {
  dataset: DatasetInfo;
  onSave: (description: string) => void;
  disabled: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(dataset.description ?? "");

  function commit() {
    setEditing(false);
    const trimmed = value.trim();
    if (trimmed !== (dataset.description ?? "")) onSave(trimmed);
  }

  if (editing) {
    return (
      <div className="flex flex-col gap-1">
        <textarea
          autoFocus
          value={value}
          disabled={disabled}
          maxLength={DESCRIPTION_MAX_LENGTH}
          onChange={(e) => setValue(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setValue(dataset.description ?? "");
              setEditing(false);
            }
          }}
          placeholder="Add a short description…"
          rows={3}
          className="w-full resize-none rounded border border-border bg-surface p-1.5 text-sm"
        />
        <span className="self-end text-xs opacity-50">
          {value.length}/{DESCRIPTION_MAX_LENGTH}
        </span>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      title="Click to edit description"
      className="line-clamp-3 text-left text-sm opacity-80 hover:opacity-100"
    >
      {dataset.description || <span className="italic opacity-70">{autoDescription(dataset)}</span>}
    </button>
  );
}

interface Props {
  dataset: DatasetInfo;
  onUpdate: (input: { name?: string; description?: string }) => void;
  onDelete: () => void;
  deleting: boolean;
  updating: boolean;
}

export function DatasetCard({ dataset, onUpdate, onDelete, deleting, updating }: Props) {
  return (
    <div className="flex flex-col gap-3 rounded border border-black/10 p-4 text-sm dark:border-white/20">
      <div className="flex items-start justify-between gap-2">
        <NameEditor
          name={dataset.name}
          disabled={updating}
          onSave={(name) => onUpdate({ name })}
        />
        <IconButton label={deleting ? "Deleting…" : "Delete dataset"} onClick={onDelete} disabled={deleting}>
          <TrashIcon />
        </IconButton>
      </div>

      <DescriptionEditor
        dataset={dataset}
        disabled={updating}
        onSave={(description) => onUpdate({ description })}
      />

      <p className="text-xs opacity-60">{dataset.row_count.toLocaleString()} rows</p>

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
  );
}
