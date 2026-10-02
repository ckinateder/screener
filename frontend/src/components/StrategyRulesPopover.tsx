import { marked } from "marked";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useStrategyRules } from "../api/hooks";
import { Spinner } from "./ui/Spinner";

const CLOSE_DELAY_MS = 200; // grace period to move the mouse from the icon onto the popover
const MAX_HEIGHT_VH = 70;
const WIDTH_PX = 640;
const GAP_PX = 8;

/**
 * ⓘ button that shows strategy-rules.md in a popover to the left of the sidebar while hovered.
 * Hovering the popover itself keeps it open, so it can be scrolled.
 */
export function StrategyRulesPopover() {
  const [position, setPosition] = useState<{ top: number; right: number } | null>(null);
  const iconRef = useRef<HTMLButtonElement>(null);
  const closeTimer = useRef<number | undefined>(undefined);
  const rules = useStrategyRules(position !== null);
  // The file is the user's own local document, so its HTML is rendered as-is.
  const html = useMemo(() => (rules.data ? (marked.parse(rules.data, { async: false }) as string) : ""), [rules.data]);

  useEffect(() => () => window.clearTimeout(closeTimer.current), []);

  const open = () => {
    window.clearTimeout(closeTimer.current);
    if (position || !iconRef.current) return;
    const icon = iconRef.current.getBoundingClientRect();
    const sidebarLeft = iconRef.current.closest("aside")?.getBoundingClientRect().left ?? icon.left;
    const maxHeight = (window.innerHeight * MAX_HEIGHT_VH) / 100;
    setPosition({
      top: Math.max(GAP_PX, Math.min(icon.top - GAP_PX, window.innerHeight - maxHeight - GAP_PX)),
      right: window.innerWidth - sidebarLeft + GAP_PX,
    });
  };
  const scheduleClose = () => {
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => setPosition(null), CLOSE_DELAY_MS);
  };

  return (
    <>
      <button
        ref={iconRef}
        onMouseEnter={open}
        onMouseLeave={scheduleClose}
        onFocus={open}
        onBlur={scheduleClose}
        className="rounded p-0.5 text-muted hover:bg-hover hover:text-text"
        aria-label="Show strategy rules"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4M12 8h.01" />
        </svg>
      </button>
      {/* Portal to <body>: the panel header is position:sticky, which creates a stacking context that
          would trap the popover's z-index below the chart canvas. */}
      {position && createPortal(
        <div
          role="dialog"
          aria-label="Strategy rules"
          onMouseEnter={open}
          onMouseLeave={scheduleClose}
          className="fixed z-50 overflow-y-auto rounded-md border border-border bg-pane p-4 shadow-2xl"
          style={{ top: position.top, right: position.right, width: WIDTH_PX, maxHeight: `${MAX_HEIGHT_VH}vh` }}
        >
          {rules.isLoading && <Spinner />}
          {rules.error && <p className="text-down">{rules.error.message}</p>}
          {html && <div className="md" dangerouslySetInnerHTML={{ __html: html }} />}
        </div>,
        document.body,
      )}
    </>
  );
}
