import { useEffect, useRef, useState } from "react";
import type { ChecklistItem, ChecklistScore, SectorEtf } from "../api/client";
import { useChecklist, useSetSectorEtf } from "../api/hooks";
import { formatShortDate } from "../lib/format";
import { useActivePane } from "../store";
import { StrategyRulesPopover } from "./StrategyRulesPopover";
import { Spinner } from "./ui/Spinner";

const NEAR_MIN = 50; // graded checks scoring 50-99 are "near" (◐), below that a fail (✗)

/** ✓ pass · ◐ near (graded, 50-99) · ✗ fail · – not applicable. */
function mark(c: ChecklistItem): { icon: string; cls: string } {
  if (c.passed === null) return { icon: "–", cls: "text-muted" };
  if (c.passed) return { icon: "✓", cls: "text-up" };
  if (c.score !== null && c.score >= NEAR_MIN) return { icon: "◐", cls: "text-amber-400" };
  return { icon: "✗", cls: "text-down" };
}

function scoreClass(score: number): string {
  if (score >= 80) return "bg-up/20 text-up";
  if (score >= 60) return "bg-amber-400/15 text-amber-400";
  return "bg-hover text-muted";
}

/** Chart score, colour-coded; outlined red when a must-have gate fails. Also used as the watchlist badge. */
export function ChecklistBadge({ score, className = "" }: { score: ChecklistScore; className?: string }) {
  const failed = score.gates.failed;
  const title = [
    `Chart score ${score.score ?? "–"} (average of graded checks)`,
    `Gates ${score.gates.passed}/${score.gates.applicable}` + (failed.length ? ` — failed: ${failed.join(", ")}` : ""),
  ].join("\n");
  return (
    <span
      className={`rounded px-1 text-[11px] tabular-nums ${score.score === null ? "bg-hover text-muted" : scoreClass(score.score)}
        ${failed.length ? "outline outline-1 outline-down" : ""} ${className}`}
      title={title}
    >
      {score.score ?? "–"}
    </span>
  );
}

const HEIGHT_KEY = "kaching:checklistHeight";
const MIN_PANEL_PX = 80; // checklist header + a row
const MIN_LIST_PX = 160; // watchlist header + column titles + ~3 rows

function savedHeight(): number | null {
  try {
    const px = Number(localStorage.getItem(HEIGHT_KEY));
    return px > 0 ? px : null;
  } catch {
    return null; // storage unavailable (private mode)
  }
}

/** The Chart Checklist (strategy-rules.md) for the active chart's symbol, measured. */
export function ChecklistPanel() {
  const { symbol } = useActivePane();
  const checklist = useChecklist(symbol);
  const data = checklist.data;
  // null = default (half the sidebar); px once the divider has been dragged.
  const [height, setHeight] = useState<number | null>(savedHeight);
  const sectionRef = useRef<HTMLElement>(null);
  // Natural height of the panel's content: the panel never grows past it (no empty space at the bottom).
  const contentRef = useRef<HTMLDivElement>(null);
  const [contentPx, setContentPx] = useState<number | null>(null);
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setContentPx(el.offsetHeight));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const persist = (px: number | null) => {
    try {
      if (px === null) localStorage.removeItem(HEIGHT_KEY);
      else localStorage.setItem(HEIGHT_KEY, String(Math.round(px)));
    } catch {
      /* storage unavailable */
    }
  };
  const onDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
    const sidebar = sectionRef.current?.parentElement?.getBoundingClientRect();
    if (!sidebar) return;
    const max = Math.min(sidebar.height - MIN_LIST_PX, contentPx ?? Infinity);
    const px = Math.min(Math.max(sidebar.bottom - e.clientY, MIN_PANEL_PX), max);
    setHeight(px);
  };

  return (
    <>
      {/* Drag to resize the checklist against the watchlist; double-click resets. */}
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize checklist"
        title="Drag to resize · double-click to reset"
        className="h-1 shrink-0 cursor-row-resize touch-none bg-border transition-colors hover:bg-accent/60 active:bg-accent"
        onPointerDown={(e) => {
          e.preventDefault(); // no text selection while dragging
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={onDrag}
        onPointerUp={(e) => {
          e.currentTarget.releasePointerCapture(e.pointerId);
          if (height !== null) persist(height); // only once it has actually been dragged
        }}
        onDoubleClick={() => {
          setHeight(null);
          persist(null);
        }}
      />
      <section
        ref={sectionRef}
        className="shrink-0 overflow-y-auto"
        style={{
          height: height ?? "50%",
          maxHeight: contentPx ? `min(calc(100% - ${MIN_LIST_PX}px), ${contentPx}px)` : `calc(100% - ${MIN_LIST_PX}px)`,
        }}
      >
        <div ref={contentRef}>
      <div className="sticky top-0 flex h-9 items-center gap-2 bg-bg px-3">
        <h2 className="font-medium">Checklist</h2>
        <StrategyRulesPopover />
        <span className="text-muted">{symbol}</span>
        <span className="flex-1" />
        {checklist.isFetching && <Spinner size={12} />}
        {data && (
          <span className="text-[11px] text-muted" title={data.gates.failed.join(", ") || "All gates pass"}>
            gates {data.gates.passed}/{data.gates.applicable}
          </span>
        )}
        {data && <ChecklistBadge score={data} />}
      </div>
      {checklist.error && <p className="px-3 pb-2 text-xs text-down">{checklist.error.message}</p>}
      {data && (
        <ul className="pb-2">
          {data.checks.map((c, i) => {
            const m = mark(c);
            return (
              <li key={c.id} className="flex gap-2 px-3 py-1" title={`Pass when: ${c.threshold}`}>
                <span className={`w-3 shrink-0 font-semibold ${m.cls}`}>{m.icon}</span>
                <div className="min-w-0 flex-1">
                  <div className={c.passed === null ? "text-muted" : "text-text"}>
                    {/* numbered to match the Chart Checklist in strategy-rules.md */}
                    <span className="text-muted">{i + 1}.</span> {c.label}
                  </div>
                  <div className="truncate text-xs text-muted" title={c.value}>
                    {c.value}
                  </div>
                  {c.id === "sector_etf" && data.sector_etf && symbol && (
                    <SectorEtfEditor key={symbol} symbol={symbol} current={data.sector_etf} />
                  )}
                </div>
                {c.kind === "graded" && c.score !== null && (
                  <span className={`shrink-0 pt-0.5 text-[11px] tabular-nums ${m.cls}`} title="Score (100 = passes)">
                    {c.score}
                  </span>
                )}
                {c.kind === "gate" && c.passed !== null && (
                  <span className="shrink-0 pt-0.5 text-[10px] uppercase tracking-wide text-muted" title="Must-have: pass/fail only">
                    gate
                  </span>
                )}
              </li>
            );
          })}
          {data.as_of && <li className="px-3 pt-1 text-[11px] text-muted">As of {formatShortDate(data.as_of)} close</li>}
        </ul>
      )}
        </div>
      </section>
    </>
  );
}

/** Row #10: change the sector ETF used for this symbol, or go back to the suggestion. */
function SectorEtfEditor({ symbol, current }: { symbol: string; current: SectorEtf }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(current.etf);
  const save = useSetSectorEtf(symbol);

  const submit = (etf: string | null) => save.mutate(etf, { onSuccess: () => setEditing(false) });
  const link = "text-[11px] text-accent hover:underline disabled:opacity-50";

  if (!editing) {
    return (
      <div className="flex gap-3">
        <button className={link} onClick={() => { setText(current.etf); setEditing(true); }}>
          ✎ change ETF
        </button>
        {current.source === "override" && current.suggested && (
          <button className={link} onClick={() => submit(null)} disabled={save.isPending}>
            use suggestion ({current.suggested})
          </button>
        )}
      </div>
    );
  }
  return (
    <div className="mt-1">
      <div className="flex items-center gap-2">
        <input
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value.toUpperCase())}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit(text.trim() || null);
            if (e.key === "Escape") setEditing(false);
          }}
          placeholder="ETF symbol"
          className="w-24 rounded border border-border bg-bg px-1.5 py-0.5 text-xs text-text uppercase outline-none focus:border-accent"
          aria-label="Sector ETF"
        />
        {save.isPending ? <Spinner size={12} /> : <span className="text-[11px] text-muted">Enter to save · Esc</span>}
      </div>
      {save.error && <p className="text-[11px] text-down">{save.error.message}</p>}
    </div>
  );
}
