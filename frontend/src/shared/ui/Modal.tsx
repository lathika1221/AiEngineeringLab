import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import { motion } from "framer-motion";

type ModalProps = {
    title: string;
    description?: string;
    onClose: () => void;
    actions?: ReactNode;
    children?: ReactNode;
};

/** Dialog with a dimmed backdrop. Escape and a backdrop click both close it. */
export default function Modal({ title, description, onClose, actions, children }: ModalProps) {
    const titleId = useId();
    const dialogRef = useRef<HTMLDivElement>(null);
    const closeRef = useRef(onClose);

    // Callers usually pass a new function each render. Reading it through a ref keeps
    // the focus effect below from re-running (and stealing focus) on every keystroke.
    useEffect(() => {
        closeRef.current = onClose;
    }, [onClose]);

    useEffect(() => {
        const previouslyFocused = document.activeElement;
        const dialog = dialogRef.current;
        const firstField = dialog?.querySelector<HTMLElement>("input, textarea, select");
        (firstField ?? dialog)?.focus();

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === "Escape") {
                event.stopPropagation();
                closeRef.current();
                return;
            }

            // Keep Tab inside the dialog while it is open.
            if (event.key === "Tab" && dialog) {
                const focusable = Array.from(
                    dialog.querySelectorAll<HTMLElement>(
                        "button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href]",
                    ),
                );

                if (focusable.length === 0) {
                    event.preventDefault();
                    return;
                }

                const first = focusable[0];
                const last = focusable[focusable.length - 1];
                const active = document.activeElement;

                if (event.shiftKey && (active === first || active === dialog)) {
                    event.preventDefault();
                    last.focus();
                } else if (!event.shiftKey && active === last) {
                    event.preventDefault();
                    first.focus();
                }
            }
        }

        document.addEventListener("keydown", handleKeyDown);

        return () => {
            document.removeEventListener("keydown", handleKeyDown);

            if (previouslyFocused instanceof HTMLElement) {
                previouslyFocused.focus();
            }
        };
    }, []);

    return (
        <motion.div
            className="modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.16 }}
            onMouseDown={(event) => {
                if (event.target === event.currentTarget) {
                    onClose();
                }
            }}
        >
            <motion.div
                ref={dialogRef}
                className="modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                tabIndex={-1}
                initial={{ opacity: 0, y: 12, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 8 }}
                transition={{ duration: 0.2 }}
            >
                <h2 id={titleId} className="modal__title">
                    {title}
                </h2>
                {description && <p className="modal__description">{description}</p>}
                {children && <div className="modal__body">{children}</div>}
                {actions && <div className="modal__actions">{actions}</div>}
            </motion.div>
        </motion.div>
    );
}
