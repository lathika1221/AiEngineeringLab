import { createContext, useContext } from "react";
import type { WolfMood } from "../brand/WolfHead";

export type Notification = {
    mood: Extract<WolfMood, "success" | "error" | "idle">;
    title: string;
    detail?: string;
};

export type Notify = (notification: Notification) => void;

export const NotifyContext = createContext<Notify>(() => undefined);

/** Shows a short LATZ notification: the wolf reacts to a finished task or a failure. */
export function useNotify(): Notify {
    return useContext(NotifyContext);
}
