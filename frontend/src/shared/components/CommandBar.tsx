import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { motion } from "framer-motion";
import { CornerDownLeft, MessagesSquare, Search } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import "./CommandBar.css";

export type Command = {
    id: string;
    label: string;
    hint: string;
    icon: LucideIcon;
    run: () => void;
    /** Listed only once the user has typed something (used for long lists such as conversations). */
    searchOnly?: boolean;
};

type CommandBarProps = {
    commands: Command[];
    /** Sends the typed text to LATZ Chat as a new message. */
    onAsk: (question: string) => void;
    onClose: () => void;
};

/**
 * The LATZ command bar: jump to any part of the workspace, or type a question
 * and send it straight to chat. Opened from the header or with Ctrl/Cmd + K.
 */
export default function CommandBar({ commands, onAsk, onClose }: CommandBarProps) {
    const [query, setQuery] = useState("");
    const [activeIndex, setActiveIndex] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);

    const text = query.trim();
    const SEARCH_LIMIT = 6;
    const matches = commands.filter(
        (command) =>
            (!command.searchOnly || text) &&
            `${command.label} ${command.hint}`.toLowerCase().includes(text.toLowerCase()),
    );
    let searchShown = 0;
    const limited = matches.filter((command) => !command.searchOnly || ++searchShown <= SEARCH_LIMIT);

    const items: Command[] = text
        ? [
              ...limited,
              {
                  id: "ask",
                  label: `Ask LATZ: "${text}"`,
                  hint: "Send to chat",
                  icon: MessagesSquare,
                  run: () => onAsk(text),
              },
          ]
        : limited;

    const highlighted = Math.min(activeIndex, items.length - 1);

    useEffect(() => {
        const previouslyFocused = document.activeElement;
        inputRef.current?.focus();

        return () => {
            if (previouslyFocused instanceof HTMLElement) {
                previouslyFocused.focus();
            }
        };
    }, []);

    function runItem(item: Command | undefined) {
        if (!item) {
            return;
        }

        onClose();
        item.run();
    }

    function handleKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
        if (event.key === "Escape") {
            event.preventDefault();
            onClose();
        } else if (event.key === "ArrowDown") {
            event.preventDefault();
            setActiveIndex((highlighted + 1) % Math.max(items.length, 1));
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActiveIndex((highlighted - 1 + items.length) % Math.max(items.length, 1));
        } else if (event.key === "Enter") {
            event.preventDefault();
            runItem(items[highlighted]);
        }
    }

    return (
        <motion.div
            className="command-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            onMouseDown={(event) => {
                if (event.target === event.currentTarget) {
                    onClose();
                }
            }}
        >
            <motion.div
                className="command-bar"
                role="dialog"
                aria-modal="true"
                aria-label="Command bar"
                initial={{ opacity: 0, y: -12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.18 }}
                onKeyDown={handleKeyDown}
            >
                <div className="command-bar__input">
                    <Search size={17} aria-hidden="true" />
                    <input
                        ref={inputRef}
                        value={query}
                        onChange={(event) => {
                            setQuery(event.target.value);
                            setActiveIndex(0);
                        }}
                        placeholder="Go to a workspace, or ask LATZ a question"
                        aria-label="Command or question"
                        aria-controls="command-bar-list"
                        aria-activedescendant={
                            items[highlighted] ? `command-${items[highlighted].id}` : undefined
                        }
                        role="combobox"
                        aria-expanded="true"
                        autoComplete="off"
                    />
                    <kbd>Esc</kbd>
                </div>

                <ul className="command-bar__list" id="command-bar-list" role="listbox">
                    {items.map((item, index) => {
                        const Icon = item.icon;

                        return (
                            <li
                                key={item.id}
                                id={`command-${item.id}`}
                                role="option"
                                aria-selected={index === highlighted}
                                className={index === highlighted ? "active" : ""}
                                onMouseEnter={() => setActiveIndex(index)}
                                onClick={() => runItem(item)}
                            >
                                <Icon size={16} aria-hidden="true" />
                                <span className="command-bar__label">{item.label}</span>
                                <span className="command-bar__hint">{item.hint}</span>
                                {index === highlighted && <CornerDownLeft size={13} aria-hidden="true" />}
                            </li>
                        );
                    })}
                </ul>
            </motion.div>
        </motion.div>
    );
}
