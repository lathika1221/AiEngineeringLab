import { createContext, useContext } from "react";
import type { Account, Profile } from "../../shared/api/types";

export type OnboardingState = "checking" | "required" | "complete";

export type Session = {
    authenticated: boolean;
    /** Username and email from the backend. Null until loaded. */
    account: Account | null;
    profile: Profile | null;
    onboarding: OnboardingState;
    /** Name to address the user by: display name, then username. */
    displayName: string;
    login: (token: string) => void;
    logout: () => void;
    /** Stores a profile the backend just returned (after an edit or onboarding). */
    setProfile: (profile: Profile) => void;
};

export const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
    const session = useContext(SessionContext);

    if (!session) {
        throw new Error("useSession must be used inside SessionProvider.");
    }

    return session;
}
