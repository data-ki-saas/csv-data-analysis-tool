"use client";

import Link from "next/link";
import { useRef } from "react";
import { useUploadDataset } from "@/hooks/useUploadDataset";
import { useDatasets, useDeleteDataset } from "@/hooks/useDatasets";
import { IconButton, TrashIcon } from "@/components/IconButton";
import { cn } from "@/lib/utils";

export default function DashboardPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadDataset();
  const datasets = useDatasets();
  const deleteDataset = useDeleteDataset();

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) upload.mutate(file);
  }

  function handleDelete(datasetId: string, filename: string) {
    const confirmed = window.confirm(
      `Delete "${filename}"? This removes the uploaded file along with its column types, ` +
        `visual reports, presentation, and any share links -- this can't be undone.`
    );
    if (confirmed) deleteDataset.mutate(datasetId);
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-12">
      <h1 className="text-2xl font-semibold">Upload a CSV</h1>

      <section className="flex flex-col gap-3">
        <label
          className={cn(
            "cursor-pointer rounded border-2 border-dashed border-black/15 px-6 py-10 text-center dark:border-white/20",
            upload.isPending && "opacity-50"
          )}
        >
          {upload.isPending ? "Uploading…" : "Click to select a CSV file"}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={handleFileChange}
            disabled={upload.isPending}
          />
        </label>

        {upload.isError && (
          <p className="text-sm text-red-600">{(upload.error as Error).message}</p>
        )}

        {upload.isSuccess && (
          <div className="flex flex-col gap-2 rounded border border-black/10 p-4 dark:border-white/20">
            <p className="font-medium">
              {upload.data.filename} — {upload.data.row_count.toLocaleString()} rows
            </p>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr>
                    {upload.data.preview.columns.map((col) => (
                      <th key={col} className="border-b border-black/10 px-2 py-1 dark:border-white/20">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {upload.data.preview.rows.map((row, i) => (
                    <tr key={i}>
                      {row.map((cell, j) => (
                        <td key={j} className="px-2 py-1">
                          {String(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-medium">Your datasets</h2>
        {datasets.isLoading && <p className="text-sm opacity-70">Loading…</p>}
        {datasets.data?.length === 0 && (
          <p className="text-sm opacity-70">No datasets uploaded yet.</p>
        )}
        {deleteDataset.isError && (
          <p className="text-sm text-red-600">
            Couldn&apos;t delete that dataset: {(deleteDataset.error as Error).message}
          </p>
        )}
        <ul className="flex flex-col gap-2">
          {datasets.data?.map((dataset) => (
            <li
              key={dataset.dataset_id}
              className="flex items-center justify-between rounded border border-black/10 px-3 py-2 text-sm dark:border-white/20"
            >
              <span>{dataset.filename}</span>
              <div className="flex items-center gap-4">
                <span className="opacity-70">{dataset.row_count.toLocaleString()} rows</span>
                <Link href={`/dashboard/${dataset.dataset_id}/types`} className="underline">
                  Review types
                </Link>
                <Link href={`/dashboard/${dataset.dataset_id}/reports`} className="underline">
                  Visual reports
                </Link>
                <Link href={`/dashboard/${dataset.dataset_id}/presentation`} className="underline">
                  Presentation
                </Link>
                <IconButton
                  label={
                    deleteDataset.isPending && deleteDataset.variables === dataset.dataset_id
                      ? "Deleting…"
                      : "Delete dataset"
                  }
                  onClick={() => handleDelete(dataset.dataset_id, dataset.filename)}
                  disabled={deleteDataset.isPending && deleteDataset.variables === dataset.dataset_id}
                >
                  <TrashIcon />
                </IconButton>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
