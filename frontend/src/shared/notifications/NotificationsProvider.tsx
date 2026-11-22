import { useCallback, useRef, useState } from "react";
import type { ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import WolfHead from "../brand/WolfHead";
import { NotifyContext } from "./context";
import type { Notification } from "./context";

type ActiveNotification = Notification & { id: number };

const VISIBLE_MS = 4200;

export default function NotificationsProvider({ children }: { children: ReactNode }) {
    const [items, setItems] = useState<ActiveNotification[]>([]);
    const nextId = useRef(1);

    const dismiss = useCallback((id: number) => {
        setItems((current) => current.filter((item) => item.id !== id));
    }, []);

    const notify = useCallback(
        (notification: Notification) => {
            const id = nextId.current;
            nextId.current += 1;

            setItems((current) => [...current.slice(-2), { ...notification, id }]);
            window.setTimeout(() => dismiss(id), VISIBLE_MS);
        },
        [dismiss],
    );

    return (
        <NotifyContext.Provider value={notify}>
            {children}

            <div className="toasts" aria-live="polite">
                <AnimatePresence>
                    {items.map((item) => (
                        <motion.div
                            key={item.id}
                            className={`toast toast--${item.mood}`}
                            role={item.mood === "error" ? "alert" : "status"}
                            layout
                            initial={{ opacity: 0, x: 24 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 24 }}
                            transition={{ duration: 0.22 }}
                        >
                            <WolfHead size={38} mood={item.mood} />
                            <div className="toast__copy">
                                <div className="toast__title">{item.title}</div>
                                {item.detail && <div className="toast__detail">{item.detail}</div>}
                            </div>
                            <button
                                type="button"
                                className="icon-btn"
                                onClick={() => dismiss(item.id)}
                                aria-label="Dismiss notification"
                            >
                                <X size={14} />
                            </button>
                        </motion.div>
                    ))}
                </AnimatePresence>
            </div>
        </NotifyContext.Provider>
    );
}
