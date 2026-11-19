import { useEffect, useState } from "react";
import { API_BASE } from "./client";

export type BackendStatus = "checking" | "online" | "offline";

const CHECK_EVERY_MS = 30_000;

/** Reports whether the LATZ backend answers its health route. Rechecks every 30 seconds. */
export function useBackendStatus(): BackendStatus {
    const [status, setStatus] = useState<BackendStatus>("checking");

    useEffect(() => {
        let cancelled = false;

        async function check() {
            try {
                const response = await fetch(`${API_BASE}/health/`);

                if (!cancelled) {
                    setStatus(response.ok ? "online" : "offline");
                }
            } catch {
                if (!cancelled) {
                    setStatus("offline");
                }
            }
        }

        void check();
        const intervalId = window.setInterval(() => void check(), CHECK_EVERY_MS);

        return () => {
            cancelled = true;
            window.clearInterval(intervalId);
        };
    }, []);

    return status;
}
