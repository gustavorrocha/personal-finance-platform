import { useEffect, useRef, type ReactNode } from "react";

/** Modal window on the native <dialog>: focus trap, Esc and backdrop click close it. */
export function Dialog({
  open,
  title,
  closeLabel,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  closeLabel: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby="dialog-title"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      {open && (
        <div className="dialog-body">
          <header className="dialog-header">
            <h2 id="dialog-title">{title}</h2>
            <button
              type="button"
              className="icon-button"
              aria-label={closeLabel}
              onClick={onClose}
            >
              ×
            </button>
          </header>
          {children}
        </div>
      )}
    </dialog>
  );
}

export type MenuItem = {
  label: string;
  onSelect: () => void;
  disabled?: boolean;
};

/** Dropdown of actions; closes on selection, outside click or Esc. */
export function Menu({ label, items }: { label: string; items: MenuItem[] }) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const close = (event: Event) => {
      const menu = ref.current;
      if (!menu?.open) return;
      if (event instanceof KeyboardEvent) {
        if (event.key !== "Escape") return;
        menu.open = false;
        menu.querySelector("summary")?.focus();
      } else if (!menu.contains(event.target as Node)) {
        menu.open = false;
      }
    };
    document.addEventListener("click", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", close);
    };
  }, []);
  return (
    <details className="menu" ref={ref}>
      <summary aria-label={label} title={label}>
        ⋯
      </summary>
      <div className="menu-items" role="menu">
        {items.map((item) => (
          <button
            key={item.label}
            type="button"
            role="menuitem"
            disabled={item.disabled}
            onClick={() => {
              if (ref.current) ref.current.open = false;
              item.onSelect();
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
    </details>
  );
}

/** Short-lived notice in a corner, visible wherever the page is scrolled. */
export function Toast({
  message,
  tone = "info",
  closeLabel,
  onDone,
}: {
  message?: string;
  tone?: "info" | "error";
  closeLabel: string;
  onDone: () => void;
}) {
  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(onDone, tone === "error" ? 8000 : 4000);
    return () => window.clearTimeout(timer);
  }, [message, tone, onDone]);
  return (
    <div className="toast-region" role={tone === "error" ? "alert" : "status"}>
      {message && (
        <div className={`toast ${tone}`}>
          <span>{message}</span>
          <button
            type="button"
            className="icon-button"
            onClick={onDone}
            aria-label={closeLabel}
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}

/** Explanation that stays collapsed behind an ⓘ until asked for. */
export function Help({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <details className="help">
      <summary>
        <span aria-hidden="true">ⓘ </span>
        {label}
      </summary>
      <p>{children}</p>
    </details>
  );
}
