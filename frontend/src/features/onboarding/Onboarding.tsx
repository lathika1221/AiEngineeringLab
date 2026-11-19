import { useEffect, useId, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Plus } from "lucide-react";
import { API_BASE, getToken } from "../../shared/api/client";
import WolfHead from "../../shared/brand/WolfHead";
import Wordmark from "../../shared/brand/Wordmark";
import Button from "../../shared/ui/Button";
import Notice from "../../shared/ui/Notice";
import { usePageTitle } from "../../shared/hooks/usePageTitle";
import { ROLE_OPTIONS } from "../../shared/config/lifeRoles";
import "./Onboarding.css";



type OnboardingProps = {
    onComplete: () => void;
};

export default function Onboarding({
    onComplete,
}: OnboardingProps) {
    usePageTitle("Set up your workspace");
    const [step, setStep] = useState(1);

    const [displayName, setDisplayName] = useState("");
    const [bio, setBio] = useState("");

    const [selectedRoles, setSelectedRoles] = useState<string[]>([]);

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    const nameId = useId();
    const bioId = useId();

    useEffect(() => {
        async function loadExistingOnboarding() {
            const token = getToken();

            if (!token) {
                setLoading(false);
                return;
            }

            try {
                const profileResponse = await fetch(
                    `${API_BASE}/users/profile`,
                    {
                        headers: {
                            Authorization: `Bearer ${token}`,
                        },
                    },
                );

                if (profileResponse.ok) {
                    const profile =
                        await profileResponse.json();

                    setDisplayName(
                        profile.display_name || "",
                    );

                    setBio(profile.bio || "");

                    if (
                        profile.onboarding_completed ===
                        "true"
                    ) {
                        onComplete();
                        return;
                    }
                }

                const rolesResponse = await fetch(
                    `${API_BASE}/users/roles`,
                    {
                        headers: {
                            Authorization: `Bearer ${token}`,
                        },
                    },
                );

                if (rolesResponse.ok) {
                    const roles =
                        await rolesResponse.json();

                    setSelectedRoles(
                        roles.map(
                            (item: { role: string }) =>
                                item.role,
                        ),
                    );
                }
            } catch {
                setError(
                    "Unable to load your onboarding data.",
                );
            } finally {
                setLoading(false);
            }
        }

        loadExistingOnboarding();
    }, [onComplete]);

    function toggleRole(role: string) {
        setSelectedRoles((current) => {
            if (current.includes(role)) {
                return current.filter(
                    (item) => item !== role,
                );
            }

            return [...current, role];
        });
    }

    function continueToRoles() {
        setError("");

        if (!displayName.trim()) {
            setError(
                "Tell LATZ what you would like to be called.",
            );
            return;
        }

        setStep(2);
    }

    async function finishOnboarding() {
        setError("");

        if (selectedRoles.length === 0) {
            setError(
                "Select at least one role that is part of your life.",
            );
            return;
        }

        const token = getToken();

        if (!token) {
            setError(
                "Your session has expired. Please log in again.",
            );
            return;
        }

        setSaving(true);

        try {
            const profileResponse = await fetch(
                `${API_BASE}/users/profile`,
                {
                    method: "POST",
                    headers: {
                        Authorization: `Bearer ${token}`,
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        display_name:
                            displayName.trim(),
                        bio: bio.trim() || null,
                        timezone:
                            Intl.DateTimeFormat().resolvedOptions()
                                .timeZone,
                    }),
                },
            );

            if (
                !profileResponse.ok &&
                profileResponse.status !== 409
            ) {
                throw new Error(
                    "Profile could not be saved.",
                );
            }

            for (
                let index = 0;
                index < selectedRoles.length;
                index += 1
            ) {
                const role = selectedRoles[index];

                const roleResponse = await fetch(
                    `${API_BASE}/users/roles`,
                    {
                        method: "POST",
                        headers: {
                            Authorization: `Bearer ${token}`,
                            "Content-Type": "application/json",
                        },
                        body: JSON.stringify({
                            role,
                            description:
                                ROLE_OPTIONS.find(
                                    (item) =>
                                        item.role === role,
                                )?.description || null,
                            priority: index + 1,
                        }),
                    },
                );

                if (
                    !roleResponse.ok &&
                    roleResponse.status !== 409
                ) {
                    throw new Error(
                        `Unable to save role: ${role}`,
                    );
                }
            }

            const completeResponse = await fetch(
                `${API_BASE}/users/profile/complete`,
                {
                    method: "POST",
                    headers: {
                        Authorization: `Bearer ${token}`,
                    },
                },
            );

            if (!completeResponse.ok) {
                throw new Error(
                    "Unable to complete onboarding.",
                );
            }

            onComplete();
        } catch (err) {
            setError(
                err instanceof Error
                    ? err.message
                    : "Something went wrong.",
            );
        } finally {
            setSaving(false);
        }
    }

    if (loading) {
        return (
            <div className="app-loading" role="status">
                <WolfHead size={72} mood="thinking" />
                <span>Loading your LATZ workspace</span>
            </div>
        );
    }

    return (
        <main className="guest">
            <section className="guest__card guest__card--wide panel panel--lit">
                <header className="onboarding-header">
                    <Wordmark descriptor />
                    <span className="onboarding-step-count">Step {step} of 2</span>
                </header>

                <div
                    className="onboarding-progress"
                    role="progressbar"
                    aria-label="Setup progress"
                    aria-valuemin={1}
                    aria-valuemax={2}
                    aria-valuenow={step}
                >
                    <span className="done" />
                    <span className={step === 2 ? "done" : ""} />
                </div>

                {step === 1 && (
                    <form
                        className="onboarding-step"
                        onSubmit={(event) => {
                            event.preventDefault();
                            continueToRoles();
                        }}
                        noValidate
                    >
                        <h1>Tell LATZ who it's working with</h1>

                        <p className="onboarding-description">
                            LATZ uses this to address you and to shape its answers around your background.
                        </p>

                        <div className="field">
                            <label className="field__label" htmlFor={nameId}>
                                What should LATZ call you?
                            </label>
                            <input
                                id={nameId}
                                className="input"
                                value={displayName}
                                onChange={(event) => setDisplayName(event.target.value)}
                                placeholder="Your name"
                                autoComplete="nickname"
                            />
                        </div>

                        <div className="field">
                            <label className="field__label" htmlFor={bioId}>
                                A little about you
                                <span className="field__hint">Optional</span>
                            </label>
                            <textarea
                                id={bioId}
                                className="input"
                                value={bio}
                                onChange={(event) => setBio(event.target.value)}
                                placeholder="What you study, build or work on"
                                rows={4}
                            />
                        </div>

                        {error && <Notice tone="error">{error}</Notice>}

                        <div className="onboarding-actions">
                            <span />
                            <Button type="submit" variant="primary">
                                Continue
                                <ArrowRight size={15} aria-hidden="true" />
                            </Button>
                        </div>
                    </form>
                )}

                {step === 2 && (
                    <section className="onboarding-step">
                        <h1>Which roles are part of your life right now?</h1>

                        <p className="onboarding-description">
                            Choose every role that applies. LATZ treats the first one you pick as the
                            highest priority.
                        </p>

                        <div className="role-grid">
                            {ROLE_OPTIONS.map((item) => {
                                const selected = selectedRoles.includes(item.role);

                                return (
                                    <button
                                        type="button"
                                        key={item.role}
                                        className={`role-card${selected ? " selected" : ""}`}
                                        aria-pressed={selected}
                                        onClick={() => toggleRole(item.role)}
                                    >
                                        <span className="role-card__header">
                                            <strong>{item.role}</strong>
                                            <span className="role-card__mark" aria-hidden="true">
                                                {selected ? <Check size={13} /> : <Plus size={13} />}
                                            </span>
                                        </span>
                                        <span className="role-card__detail">{item.description}</span>
                                    </button>
                                );
                            })}
                        </div>

                        {error && <Notice tone="error">{error}</Notice>}

                        <div className="onboarding-actions">
                            <Button
                                variant="ghost"
                                onClick={() => {
                                    setError("");
                                    setStep(1);
                                }}
                            >
                                <ArrowLeft size={15} aria-hidden="true" />
                                Back
                            </Button>

                            <span className="onboarding-selected" aria-live="polite">
                                {selectedRoles.length > 0 &&
                                    `${selectedRoles.length} role${selectedRoles.length !== 1 ? "s" : ""} selected`}
                            </span>

                            <Button variant="primary" busy={saving} onClick={() => void finishOnboarding()}>
                                {saving ? "Setting up" : "Enter LATZ"}
                            </Button>
                        </div>
                    </section>
                )}
            </section>
        </main>
    );
}
