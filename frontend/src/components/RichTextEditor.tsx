"use client";

import { useEffect, useRef } from "react";

interface Props {
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
}

/** A small hand-rolled WYSIWYG editor -- contentEditable plus a Bold/Italic/
 * Link/line-break toolbar via document.execCommand. No editor library: the
 * footer content this backs (an address/contact block) only ever needs this
 * small, well-supported subset of execCommand, not a general-purpose
 * document editor. The resulting HTML is sanitized server-side on save
 * (src/settings/service.py) before it's ever persisted or rendered to
 * anyone else.
 *
 * Deliberately uncontrolled after mount: `value` seeds the initial content
 * once and is never written back into the DOM again, even as the parent's
 * `onChange`-driven state updates flow back down as new `value` props.
 * Re-applying `value` on every keystroke (e.g. via a reactive
 * `dangerouslySetInnerHTML`) resets the DOM node and, with it, the caret --
 * every browser puts the cursor back at position 0 after such a reset
 * regardless of whether the content actually changed, which (typed fast
 * enough) shows up as each new character being inserted before the last,
 * i.e. the text comes out reversed. Callers needing to load different
 * content must remount via `key` (e.g. the preset id) rather than expect a
 * `value` change to take effect in place. */
export function RichTextEditor({ value, onChange, placeholder }: Props) {
  const editorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (editorRef.current) editorRef.current.innerHTML = value;
    // Intentionally mount-only -- see the component doc comment above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function exec(command: string, arg?: string) {
    editorRef.current?.focus();
    document.execCommand(command, false, arg);
    if (editorRef.current) onChange(editorRef.current.innerHTML);
  }

  function handleLink() {
    const url = window.prompt("Link URL");
    if (url) exec("createLink", url);
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1 rounded-t border border-b-0 border-border bg-accent/5 p-1 text-xs">
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => exec("bold")}
          className="rounded px-2 py-1 font-bold hover:bg-accent/10"
          aria-label="Bold"
        >
          B
        </button>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => exec("italic")}
          className="rounded px-2 py-1 italic hover:bg-accent/10"
          aria-label="Italic"
        >
          I
        </button>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={handleLink}
          className="rounded px-2 py-1 underline hover:bg-accent/10"
          aria-label="Link"
        >
          Link
        </button>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => exec("insertLineBreak")}
          className="rounded px-2 py-1 hover:bg-accent/10"
          aria-label="Line break"
        >
          ↵
        </button>
      </div>
      <div
        ref={editorRef}
        contentEditable
        onInput={(e) => onChange(e.currentTarget.innerHTML)}
        data-placeholder={placeholder}
        className="min-h-24 w-full rounded-b border border-border bg-surface p-2 text-sm empty:before:text-muted empty:before:opacity-60 empty:before:content-[attr(data-placeholder)]"
      />
    </div>
  );
}
