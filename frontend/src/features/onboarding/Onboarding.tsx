import { useEffect, useState } from "react";
import "./Onboarding.css";

const API_BASE = "http://127.0.0.1:8000";

type RoleOption = {
    role: string;
    description: string;
};

const ROLE_OPTIONS: RoleOption[] = [
    {
        role: "Student",
        description:
            "Learning, studying, building skills and preparing for your future.",
    },
    {
        role: "Engineer",
        description:
            "Building systems, products, software or technical solutions.",
    },
    {
        role: "Researcher",
        description:
            "Working on research, experiments, publications or discoveries.",
    },
    {
        role: "Entrepreneur",
        description:
            "Building a business, startup, product or venture.",
    },
    {
        role: "Faculty",
        description:
            "Teaching, mentoring, research or academic responsibilities.",
    },
    {
        role: "Parent",
        description:
            "Managing family responsibilities, routines and priorities.",
    },
    {
        role: "Freelancer",
        description:
            "Working independently with clients, projects or services.",
    },
    {
        role: "Professional",
        description:
            "Managing a professional career, workplace and growth.",
    },
];

type OnboardingProps = {
    onComplete: () => void;
};

export default function Onboarding({
    onComplete,
}: OnboardingProps) {
    const [step, setStep] = useState(1);

    const [displayName, setDisplayName] = useState("");
    const [bio, setBio] = useState("");

    const [selectedRoles, setSelectedRoles] = useState<string[]>([]);

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        async function loadExistingOnboarding() {
            const token = localStorage.getItem("access_token");

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

        const token = localStorage.getItem("access_token");

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
            <div className="onboarding-shell">
                <div className="onboarding-loading">
                    Loading your LATZ workspace...
                </div>
            </div>
        );
    }

    return (
        <div className="onboarding-shell">
            <div className="onboarding-card">
                <div className="onboarding-brand">
                    <div className="onboarding-wolf">
                        🐺
                    </div>

                    <div>
                        <div className="onboarding-brand-name">
                            LATZ
                        </div>

                        <div className="onboarding-brand-subtitle">
                            Your personal AI companion
                        </div>
                    </div>
                </div>

                <div className="onboarding-progress">
                    <span
                        className={
                            step === 1
                                ? "active"
                                : "completed"
                        }
                    />

                    <span
                        className={
                            step === 2
                                ? "active"
                                : ""
                        }
                    />
                </div>

                {step === 1 && (
                    <section className="onboarding-step">
                        <div className="onboarding-eyebrow">
                            LET'S START WITH YOU
                        </div>

                        <h1>
                            Before we get started,
                            <br />
                            tell me about yourself.
                        </h1>

                        <p className="onboarding-description">
                            LATZ works better when it
                            understands the person behind
                            the account.
                        </p>

                        <label>
                            What should LATZ call you?
                        </label>

                        <input
                            value={displayName}
                            onChange={(event) =>
                                setDisplayName(
                                    event.target.value,
                                )
                            }
                            placeholder="Your name"
                        />

                        <label>
                            Tell LATZ a little about you
                            <span>Optional</span>
                        </label>

                        <textarea
                            value={bio}
                            onChange={(event) =>
                                setBio(event.target.value)
                            }
                            placeholder="A short description about you..."
                            rows={4}
                        />

                        {error && (
                            <div className="onboarding-error">
                                {error}
                            </div>
                        )}

                        <button
                            className="onboarding-primary"
                            onClick={continueToRoles}
                        >
                            Continue
                            <span>→</span>
                        </button>
                    </section>
                )}

                {step === 2 && (
                    <section className="onboarding-step">
                        <div className="onboarding-eyebrow">
                            YOUR LIFE
                        </div>

                        <h1>
                            What roles are part of
                            <br />
                            your life right now?
                        </h1>

                        <p className="onboarding-description">
                            Choose everything that applies.
                            You can change these later.
                        </p>

                        <div className="role-grid">
                            {ROLE_OPTIONS.map((item) => {
                                const selected =
                                    selectedRoles.includes(
                                        item.role,
                                    );

                                return (
                                    <button
                                        key={item.role}
                                        className={`role-card ${selected
                                            ? "selected"
                                            : ""
                                            }`}
                                        onClick={() =>
                                            toggleRole(
                                                item.role,
                                            )
                                        }
                                    >
                                        <div className="role-card-header">
                                            <strong>
                                                {item.role}
                                            </strong>

                                            <span>
                                                {selected
                                                    ? "✓"
                                                    : "+"}
                                            </span>
                                        </div>

                                        <p>
                                            {
                                                item.description
                                            }
                                        </p>
                                    </button>
                                );
                            })}
                        </div>

                        {selectedRoles.length > 0 && (
                            <div className="selected-summary">
                                {selectedRoles.length} role
                                {selectedRoles.length !== 1
                                    ? "s"
                                    : ""}{" "}
                                selected
                            </div>
                        )}

                        {error && (
                            <div className="onboarding-error">
                                {error}
                            </div>
                        )}

                        <div className="onboarding-actions">
                            <button
                                className="onboarding-secondary"
                                onClick={() => {
                                    setError("");
                                    setStep(1);
                                }}
                            >
                                ← Back
                            </button>

                            <button
                                className="onboarding-primary"
                                onClick={finishOnboarding}
                                disabled={saving}
                            >
                                {saving
                                    ? "Setting things up..."
                                    : "Enter LATZ"}

                                {!saving && (
                                    <span>→</span>
                                )}
                            </button>
                        </div>
                    </section>
                )}
            </div>
        </div>
    );
}