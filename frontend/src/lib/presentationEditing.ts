import type { PresentationBlock, PresentationPageData } from "@/lib/api";

// Pure functions over the presentation document -- the builder page calls
// these from drag-and-drop handlers and button clicks, then persists the
// result via debounced autosave (PUT .../presentation). Kept separate from
// the component so the reorder/move logic isn't tangled up with DnD event
// wiring.

export function addPage(pages: PresentationPageData[]): PresentationPageData[] {
  const page: PresentationPageData = { id: crypto.randomUUID(), title: `Page ${pages.length + 1}`, blocks: [] };
  return [...pages, page];
}

export function removePage(pages: PresentationPageData[], pageId: string): PresentationPageData[] {
  return pages.filter((page) => page.id !== pageId);
}

export function renamePage(pages: PresentationPageData[], pageId: string, title: string): PresentationPageData[] {
  return pages.map((page) => (page.id === pageId ? { ...page, title } : page));
}

export function removeBlock(
  pages: PresentationPageData[],
  pageId: string,
  blockId: string
): PresentationPageData[] {
  return pages.map((page) =>
    page.id === pageId ? { ...page, blocks: page.blocks.filter((b) => b.id !== blockId) } : page
  );
}

export function addTextBlock(pages: PresentationPageData[], pageId: string): PresentationPageData[] {
  const block: PresentationBlock = { type: "text", id: crypto.randomUUID(), text: "" };
  return pages.map((page) => (page.id === pageId ? { ...page, blocks: [...page.blocks, block] } : page));
}

export function editTextBlock(
  pages: PresentationPageData[],
  pageId: string,
  blockId: string,
  text: string
): PresentationPageData[] {
  return pages.map((page) =>
    page.id === pageId
      ? { ...page, blocks: page.blocks.map((b) => (b.id === blockId && b.type === "text" ? { ...b, text } : b)) }
      : page
  );
}

export function movePage(
  pages: PresentationPageData[],
  sourceId: string,
  targetId: string
): PresentationPageData[] {
  if (sourceId === targetId) return pages;
  const sourceIndex = pages.findIndex((p) => p.id === sourceId);
  const targetIndex = pages.findIndex((p) => p.id === targetId);
  if (sourceIndex === -1 || targetIndex === -1) return pages;
  const next = [...pages];
  const [moved] = next.splice(sourceIndex, 1);
  next.splice(targetIndex, 0, moved);
  return next;
}

export function moveBlockWithinPage(
  pages: PresentationPageData[],
  pageId: string,
  sourceBlockId: string,
  targetBlockId: string
): PresentationPageData[] {
  return pages.map((page) => {
    if (page.id !== pageId || sourceBlockId === targetBlockId) return page;
    const sourceIndex = page.blocks.findIndex((b) => b.id === sourceBlockId);
    if (sourceIndex === -1) return page;
    const blocks = [...page.blocks];
    const [moved] = blocks.splice(sourceIndex, 1);
    const targetIndex = blocks.findIndex((b) => b.id === targetBlockId);
    if (targetIndex === -1) return page;
    blocks.splice(targetIndex, 0, moved);
    return { ...page, blocks };
  });
}

export function moveBlockToPage(
  pages: PresentationPageData[],
  blockId: string,
  fromPageId: string,
  toPageId: string
): PresentationPageData[] {
  if (fromPageId === toPageId) return pages;
  let moved: PresentationBlock | undefined;
  const withoutBlock = pages.map((page) => {
    if (page.id !== fromPageId) return page;
    const blocks = page.blocks.filter((block) => {
      if (block.id === blockId) {
        moved = block;
        return false;
      }
      return true;
    });
    return { ...page, blocks };
  });
  if (!moved) return pages;
  const capturedBlock = moved;
  return withoutBlock.map((page) =>
    page.id === toPageId ? { ...page, blocks: [...page.blocks, capturedBlock] } : page
  );
}
