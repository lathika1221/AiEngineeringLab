import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

export type MenuItem = {
    label: string;
    icon?: LucideIcon;
    onSelect: () => void;
    danger?: boolean;
    /** Draws a divider above this item. */
    separated?: boolean;
};

type MenuProps = {
    /** Accessible name of the button that opens the menu. */
    label: string;
    trigger: ReactNode;
    /** Extra class for the wrapper, for layout (full width, hidden at a breakpoint). */
    className?: string;
    triggerClassName?: string;
    items: MenuItem[];
    /** Which edge of the trigger the menu lines up with, and whether it opens upward. */
    placement?: "bottom-end" | "top-start" | "bottom-start";
    /** Content shown above the items, such as who is signed in. */
    header?: ReactNode;
};

/** A button that opens a short list of actions. Arrow keys move, Escape closes. */
export default function Menu({
    label,
    trigger,
    className = "",
    triggerClassName = "",
    items,
    placement = "bottom-end",
    header,
}: MenuProps) {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);
    const triggerRef = useRef<HTMLButtonElement>(null);
    const menuId = useId();

    useEffect(() => {
        if (!open) {
            return;
        }

        function handlePointerDown(event: PointerEvent) {
            if (!rootRef.current?.contains(event.target as Node)) {
                setOpen(false);
            }
        }

        document.addEventListener("pointerdown", handlePointerDown);
        rootRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();

        return () => document.removeEventListener("pointerdown", handlePointerDown);
    }, [open]);

    function close(returnFocus: boolean) {
        setOpen(false);

        if (returnFocus) {
            triggerRef.current?.focus();
        }
    }

    function handleKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
        if (!open) {
            return;
        }

        const options = Array.from(
            rootRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [],
        );
        const index = options.indexOf(document.activeElement as HTMLElement);

        if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            close(true);
        } else if (event.key === "ArrowDown") {
            event.preventDefault();
            options[(index + 1) % options.length]?.focus();
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            options[(index - 1 + options.length) % options.length]?.focus();
        } else if (event.key === "Home") {
            event.preventDefault();
            options[0]?.focus();
        } else if (event.key === "End") {
            event.preventDefault();
            options[options.length - 1]?.focus();
        } else if (event.key === "Tab") {
            setOpen(false);
        }
    }

    return (
        <div className={`menu ${className}`.trim()} ref={rootRef} onKeyDown={handleKeyDown}>
            <button
                ref={triggerRef}
                type="button"
                className={triggerClassName}
                aria-label={label}
                aria-haspopup="menu"
                aria-expanded={open}
                aria-controls={open ? menuId : undefined}
                onClick={() => setOpen((current) => !current)}
            >
                {trigger}
            </button>

            {open && (
                <div className={`menu__panel menu__panel--${placement}`} id={menuId} role="menu" aria-label={label}>
                    {header && <div className="menu__header">{header}</div>}
                    {items.map((item) => {
                        const Icon = item.icon;

                        return (
                            <button
                                key={item.label}
                                type="button"
                                role="menuitem"
                                className={`menu__item${item.danger ? " menu__item--danger" : ""}${
                                    item.separated ? " menu__item--separated" : ""
                                }`}
                                onClick={() => {
                                    close(true);
                                    item.onSelect();
                                }}
                            >
                                {Icon && <Icon size={15} aria-hidden="true" />}
                                {item.label}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
