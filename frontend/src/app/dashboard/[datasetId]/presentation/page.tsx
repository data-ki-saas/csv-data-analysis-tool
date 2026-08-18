"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CategoricalChart } from "@/components/charts/CategoricalChart";
import { HistogramChart } from "@/components/charts/HistogramChart";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { usePresentation, useUpdatePresentation } from "@/hooks/usePresentation";
import { useSettings } from "@/hooks/useSettings";
import type { PresentationBlock, PresentationPageData } from "@/lib/api";
import { renderBrandedFooterHtml, renderBrandedHeaderHtml } from "@/lib/branding";
import { downloadStandaloneHtml } from "@/lib/exportPresentation";
import {
  addPage,
  addTextBlock,
  editTextBlock,
  moveBlockToPage,
  moveBlockWithinPage,
  movePage,
  removeBlock,
  removePage,
  renamePage,
} from "@/lib/presentationEditing";
import { renderStaticChart } from "@/lib/staticChart";
import { cn } from "@/lib/utils";

type DragPayload = { kind: "page"; id: string } | { kind: "block"; id: string; pageId: string };

function setDragData(e: React.DragEvent, payload: DragPayload) {
  e.dataTransfer.setData("application/json", JSON.stringify(payload));
  e.dataTransfer.effectAllowed = "move";
}

function readDragData(e: React.DragEvent): DragPayload | null {
  try {
    const raw = e.dataTransfer.getData("application/json");
    return raw ? (JSON.parse(raw) as DragPayload) : null;
  } catch {
    return null;
  }
}

function PageTitleEditor({ title, onRename }: { title: string; onRename: (title: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(title);

  if (!editing) {
    return (
      <span onDoubleClick={() => setEditing(true)} title="Double-click to rename">
        {title}
      </span>
    );
  }

  function commit() {
    setEditing(false);
    const trimmed = value.trim();
    if (trimmed) onRename(trimmed);
    else setValue(title);
  }

  return (
    <input
      autoFocus
      value={value}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") {
          setValue(title);
          setEditing(false);
        }
      }}
      className="w-24 rounded border border-border bg-surface px-1 text-sm"
    />
  );
}

function BlockView({
  block,
  onEditText,
}: {
  block: PresentationBlock;
  onEditText: (text: string) => void;
}) {
  if (block.type === "chart") {
    return (
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">{block.title}</h3>
        {/* Live interactive chart for on-screen editing. Recharts'
            ResponsiveContainer measures via ResizeObserver, which print
            layout doesn't reliably trigger -- so print/export instead uses
            the dependency-free static SVG renderer below. */}
        <div className="print:hidden">
          {block.partition_type === "datetime" && <TimeSeriesChart result={block.result} />}
          {block.partition_type === "numerical_bins" && (
            <HistogramChart
              result={block.result}
              chartType={block.chart_type === "bell_curve" ? "bell_curve" : "histogram"}
              binCount={Math.max(block.result.rows.length, 1)}
              onBinCountChange={() => {}}
              onSelectBin={() => {}}
              selectedBin={null}
            />
          )}
          {block.partition_type === "categorical" && (
            <CategoricalChart
              result={block.result}
              chartType={block.chart_type === "pie" ? "pie" : "bar"}
              column={block.column}
              activeFilter={null}
              onToggleFilter={() => {}}
            />
          )}
        </div>
        <div className="hidden print:block" dangerouslySetInnerHTML={{ __html: renderStaticChart(block, 480, 220) }} />
      </div>
    );
  }

  if (block.type === "insights") {
    return (
      <div className="flex flex-col gap-1 rounded bg-accent/5 p-2">
        <h4 className="text-xs font-medium uppercase tracking-wide opacity-70">Key insights</h4>
        <ul className="list-disc pl-5 text-sm">
          {block.bullets.map((bullet, i) => (
            <li key={i}>{bullet}</li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <>
      <textarea
        value={block.text}
        onChange={(e) => onEditText(e.target.value)}
        placeholder="Write a note…"
        className="min-h-20 w-full resize-y rounded border border-border bg-surface p-2 text-sm print:hidden"
      />
      <p className="hidden whitespace-pre-wrap text-sm print:block">{block.text}</p>
    </>
  );
}

export default function PresentationBuilderPage() {
  const { datasetId } = useParams<{ datasetId: string }>();
  const presentationQuery = usePresentation(datasetId);
  const updatePresentation = useUpdatePresentation(datasetId);
  const settingsQuery = useSettings();
  const activeHeader = settingsQuery.data?.header_presets.find((p) => p.enabled) ?? null;
  const activeFooter = settingsQuery.data?.footer_presets.find((p) => p.enabled) ?? null;

  // null = "no local edits yet, defer to server data" -- once the user
  // touches anything, these fork from the query result and become the
  // source of truth until the next full reload. This avoids needing an
  // effect to seed local state from an async query (see CLAUDE.md).
  const [localTitle, setLocalTitle] = useState<string | null>(null);
  const [localPages, setLocalPages] = useState<PresentationPageData[] | null>(null);
  const [localActivePageId, setLocalActivePageId] = useState<string | null>(null);

  const title = localTitle ?? presentationQuery.data?.title ?? "Untitled Presentation";
  const pages = useMemo(
    () => localPages ?? presentationQuery.data?.pages ?? [],
    [localPages, presentationQuery.data]
  );
  const activePageId = localActivePageId ?? pages[0]?.id ?? null;
  const hasEdits = localPages !== null || localTitle !== null;

  useEffect(() => {
    if (!hasEdits) return;
    const timeout = setTimeout(() => {
      updatePresentation.mutate({ title, pages });
    }, 800);
    return () => clearTimeout(timeout);
  }, [hasEdits, title, pages, updatePresentation]);

  function handleAddPage() {
    const next = addPage(pages);
    setLocalPages(next);
    setLocalActivePageId(next[next.length - 1].id);
  }

  function handleRemovePage(pageId: string) {
    const next = removePage(pages, pageId);
    setLocalPages(next);
    if (activePageId === pageId) setLocalActivePageId(next[0]?.id ?? null);
  }

  function handlePageDrop(e: React.DragEvent, targetPageId: string) {
    e.preventDefault();
    const data = readDragData(e);
    if (!data) return;
    setLocalPages(
      data.kind === "page"
        ? movePage(pages, data.id, targetPageId)
        : moveBlockToPage(pages, data.id, data.pageId, targetPageId)
    );
  }

  function handleBlockDrop(e: React.DragEvent, pageId: string, targetBlockId: string) {
    e.preventDefault();
    e.stopPropagation();
    const data = readDragData(e);
    if (!data || data.kind !== "block") return;
    setLocalPages(
      data.pageId === pageId
        ? moveBlockWithinPage(pages, pageId, data.id, targetBlockId)
        : moveBlockToPage(pages, data.id, data.pageId, pageId)
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-12 print:max-w-none print:px-0 print:py-0">
      <h1 className="text-2xl font-semibold print:hidden">Presentation Builder</h1>

      {presentationQuery.isLoading && <p className="text-sm opacity-70 print:hidden">Loading…</p>}

      {/* Print-only -- appears in the exported PDF (window.print() below) but
          not in the live builder UI, same print:hidden/hidden print:block
          pattern BlockView uses for chart rendering. */}
      {(activeHeader || activeFooter) && (
        <div className="hidden print:block">
          {activeHeader && (
            <div
              className="text-center"
              dangerouslySetInnerHTML={{ __html: renderBrandedHeaderHtml(activeHeader, title) }}
            />
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <input
          value={title}
          onChange={(e) => setLocalTitle(e.target.value)}
          placeholder="Presentation title"
          className="rounded border border-border bg-surface px-2 py-1 text-lg font-medium"
        />
        <div className="flex items-center gap-3 text-xs">
          <span className="opacity-60">{updatePresentation.isPending ? "Saving…" : hasEdits ? "Saved" : ""}</span>
          <button
            type="button"
            onClick={() =>
              downloadStandaloneHtml(
                { dataset_id: datasetId, title, pages, updated_at: null },
                activeHeader,
                activeFooter
              )
            }
            disabled={pages.length === 0}
            className="rounded border border-border px-3 py-1.5 disabled:opacity-40"
          >
            Export standalone HTML
          </button>
          <button
            type="button"
            onClick={() => window.print()}
            disabled={pages.length === 0}
            className="rounded bg-accent px-3 py-1.5 text-accent-foreground disabled:opacity-40"
          >
            Export as PDF
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 print:hidden">
        {pages.map((page) => (
          <div
            key={page.id}
            draggable
            onDragStart={(e) => setDragData(e, { kind: "page", id: page.id })}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => handlePageDrop(e, page.id)}
            onClick={() => setLocalActivePageId(page.id)}
            className={cn(
              "flex cursor-pointer items-center gap-2 rounded border px-3 py-1.5 text-sm",
              page.id === activePageId ? "border-accent bg-accent/10" : "border-border"
            )}
          >
            <PageTitleEditor title={page.title} onRename={(t) => setLocalPages(renamePage(pages, page.id, t))} />
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleRemovePage(page.id);
              }}
              aria-label="Remove page"
              className="opacity-60 hover:opacity-100"
            >
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={handleAddPage}
          className="rounded border border-dashed border-border px-3 py-1.5 text-sm"
        >
          + Add page
        </button>
      </div>

      {pages.length === 0 && (
        <p className="py-16 text-center text-sm opacity-60">
          Nothing pinned yet — go to{" "}
          <Link href={`/dashboard/${datasetId}/reports`} className="underline">
            Visual Reports
          </Link>{" "}
          and pin a chart to get started.
        </p>
      )}

      <div className="flex flex-col gap-8">
        {pages.map((page) => (
          <section
            key={page.id}
            className={cn(
              "flex flex-col gap-4 rounded border border-border p-4 print:break-after-page print:border-none",
              page.id === activePageId ? "flex" : "hidden print:flex"
            )}
          >
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium">{page.title}</h2>
              <button
                type="button"
                onClick={() => setLocalPages(addTextBlock(pages, page.id))}
                className="text-xs underline print:hidden"
              >
                + Add note
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 print:grid-cols-1">
              {page.blocks.map((block) => (
                <div
                  key={block.id}
                  draggable
                  onDragStart={(e) => setDragData(e, { kind: "block", id: block.id, pageId: page.id })}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => handleBlockDrop(e, page.id, block.id)}
                  className="flex flex-col gap-2 rounded border border-border bg-surface p-3 print:break-inside-avoid print:border-black/10"
                >
                  <div className="flex items-center justify-between print:hidden">
                    <span className="cursor-grab text-xs opacity-50" title="Drag to reorder or move to another page">
                      ⠿ drag
                    </span>
                    <button
                      type="button"
                      onClick={() => setLocalPages(removeBlock(pages, page.id, block.id))}
                      className="text-xs underline opacity-60 hover:opacity-100"
                    >
                      Remove
                    </button>
                  </div>
                  <BlockView
                    block={block}
                    onEditText={(text) => setLocalPages(editTextBlock(pages, page.id, block.id, text))}
                  />
                </div>
              ))}
              {page.blocks.length === 0 && (
                <p className="py-8 text-center text-sm opacity-50 print:hidden">
                  Drop a block here, or pin one from Visual Reports.
                </p>
              )}
            </div>
          </section>
        ))}
      </div>

      {activeFooter && (
        <div
          className="hidden text-center print:block"
          dangerouslySetInnerHTML={{ __html: renderBrandedFooterHtml(activeFooter, "") }}
        />
      )}
    </main>
  );
}
