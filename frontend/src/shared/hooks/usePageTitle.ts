import { useEffect } from "react";

const SUFFIX = "LATZ";

/** Sets the browser tab title for the current screen. */
export function usePageTitle(title: string | null | undefined): void {
    useEffect(() => {
        document.title = title ? `${title} · ${SUFFIX}` : "LATZ — AI Engineering Lab";
    }, [title]);
}
