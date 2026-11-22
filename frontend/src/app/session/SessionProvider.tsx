import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { API_BASE, clearToken, getToken, setToken } from "../../shared/api/client";
import { onUnauthorized } from "../../shared/api/http";
import { clearResources } from "../../shared/api/resources";
import type { Account, Profile } from "../../shared/api/types";
import { SessionContext } from "./context";
import type { OnboardingState, Session } from "./context";

function isTokenValid(): boolean {
    const token = getToken();

    if (!token) {
        return false;
    }

    try {
        const payload = JSON.parse(atob(token.split(".")[1]));

        if (!payload.exp) {
            return false;
        }

        return payload.exp * 1000 > Date.now();
    } catch {
        return false;
    }
}

export default function SessionProvider({ children }: { children: ReactNode }) {
    const [authenticated, setAuthenticated] = useState(isTokenValid);
    const [onboarding, setOnboarding] = useState<OnboardingState>(() =>
        isTokenValid() ? "checking" : "complete",
    );
    const [account, setAccount] = useState<Account | null>(null);
    const [profile, setProfileState] = useState<Profile | null>(null);

    const login = useCallback((token: string) => {
        setToken(token);
        clearResources();
        setOnboarding("checking");
        setAuthenticated(true);
    }, []);

    const logout = useCallback(() => {
        clearToken();
        clearResources();
        setAuthenticated(false);
        setOnboarding("complete");
        setAccount(null);
        setProfileState(null);
    }, []);

    const setProfile = useCallback((next: Profile) => {
        setProfileState(next);
        setOnboarding(next.onboarding_completed === "true" ? "complete" : "required");
    }, []);

    useEffect(() => {
        onUnauthorized(logout);
        return () => onUnauthorized(null);
    }, [logout]);

    // Load who is signed in and whether they still need onboarding.
    useEffect(() => {
        if (!authenticated) {
            return;
        }

        const token = getToken();

        if (!token) {
            return;
        }

        let cancelled = false;
        const headers = { Authorization: `Bearer ${token}` };

        async function loadProfile() {
            try {
                const response = await fetch(`${API_BASE}/users/profile`, { headers });

                if (cancelled) {
                    return;
                }

                if (response.status === 401) {
                    logout();
                    return;
                }

                if (response.status === 404) {
                    setOnboarding("required");
                    return;
                }

                if (!response.ok) {
                    setOnboarding("complete");
                    return;
                }

                const loaded = (await response.json()) as Profile;

                if (!cancelled) {
                    setProfileState(loaded);
                    setOnboarding(loaded.onboarding_completed === "true" ? "complete" : "required");
                }
            } catch {
                if (!cancelled) {
                    setOnboarding("complete");
                }
            }
        }

        async function loadAccount() {
            try {
                const response = await fetch(`${API_BASE}/users/me`, { headers });

                if (!cancelled && response.ok) {
                    setAccount((await response.json()) as Account);
                }
            } catch {
                // The account card shows its own "couldn't load" state; nothing else depends on it.
            }
        }

        void loadProfile();
        void loadAccount();

        return () => {
            cancelled = true;
        };
    }, [authenticated, logout]);

    const session = useMemo<Session>(
        () => ({
            authenticated,
            account,
            profile,
            onboarding,
            displayName: profile?.display_name?.trim() || account?.username || "User",
            login,
            logout,
            setProfile,
        }),
        [authenticated, account, profile, onboarding, login, logout, setProfile],
    );

    return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}
