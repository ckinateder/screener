import { useEffect, type ReactNode } from "react";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  width?: string;
}

export function Modal({ title, onClose, children, width = "max-w-xl" }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-[10vh]" onMouseDown={onClose}>
      <div
        className={`w-full ${width} mx-4 flex max-h-[75vh] flex-col overflow-hidden rounded-md border border-border bg-pane shadow-2xl`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-base font-medium">{title}</h2>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-hover hover:text-text" title="Close">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
