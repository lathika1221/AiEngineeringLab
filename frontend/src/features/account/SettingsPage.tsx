import { useEffect, useId, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Check, LogOut, Moon, Sun } from "lucide-react";
import { useSession } from "../../app/session/context";
import { apiFetch, errorMessage } from "../../shared/api/http";
import { refreshResources } from "../../shared/api/resources";
import type { Profile } from "../../shared/api/types";
import { usePageTitle } from "../../shared/hooks/usePageTitle";
import { useNotify } from "../../shared/notifications/context";
import { setTheme, useTheme } from "../../shared/theme/theme";
import type { Theme } from "../../shared/theme/theme";
import Button from "../../shared/ui/Button";
import Notice from "../../shared/ui/Notice";
import PageHeader from "../../shared/ui/PageHeader";
import TimezoneSelect from "./TimezoneSelect";
import { deviceTimezone, timezoneLabel } from "./timezones";
import "./Account.css";

const THEMES: Array<{ id: Theme; label: string; detail: string; icon: typeof Sun }> = [
    { id: "dark", label: "Dark", detail: "The primary LATZ look: deep navy with blue light.", icon: Moon },
    { id: "light", label: "Light", detail: "A bright workspace with the same cobalt accents.", icon: Sun },
];

export default function SettingsPage() {
    const { account, profile, displayName, setProfile, logout } = useSession();
    const theme = useTheme();
    const notify = useNotify();
    const location = useLocation();
    const timezoneId = useId();

    // null means "showing the saved value"; a string is an unsaved choice.
    const [timezoneDraft, setTimezoneDraft] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    usePageTitle("Account Settings");

    const savedTimezone = profile?.timezone ?? "";
    const timezone = timezoneDraft ?? savedTimezone;
    const timezoneChanged = timezone !== savedTimezone;
    const device = deviceTimezone();

    // "Appearance" in the account menu links to /settings#appearance.
    useEffect(() => {
        if (!location.hash) {
            return;
        }

        const target = document.getElementById(location.hash.slice(1));

        target?.scrollIntoView({ block: "start" });
        target?.focus({ preventScroll: true });
    }, [location.hash, location.key]);

    async function saveTimezone() {
        setSaving(true);
        setError("");

        try {
            // Only the time zone is sent; the backend leaves fields that are absent untouched.
            const updated = await apiFetch<Profile>("/users/profile", {
                method: "PUT",
                body: { timezone },
            });

            setProfile(updated);
            setTimezoneDraft(null);
            refreshResources("/users/context");
            notify({
                mood: "success",
                title: "Time zone saved",
                detail: timezone ? timezoneLabel(timezone) : "Not set",
            });
        } catch (caught) {
            setError(`Your time zone wasn't saved. ${errorMessage(caught, "Something went wrong.")}`);
        } finally {
            setSaving(false);
        }
    }

    return (
        <section className="page account-page">
            <PageHeader title="Account settings" lede="Appearance, time zone and your LATZ account." />

            <div className="settings-stack section">
                <section
                    className="settings-section panel"
                    id="appearance"
                    tabIndex={-1}
                    aria-labelledby="settings-appearance"
                >
                    <div className="settings-section__head">
                        <h2 className="section-title" id="settings-appearance">
                            Appearance
                        </h2>
                        <p className="section-note">Saved in this browser.</p>
                    </div>

                    <div className="theme-options" role="radiogroup" aria-label="Theme">
                        {THEMES.map((option) => {
                            const Icon = option.icon;
                            const selected = theme === option.id;

                            return (
                                <button
                                    type="button"
                                    key={option.id}
                                    role="radio"
                                    aria-checked={selected}
                                    className={`theme-option${selected ? " selected" : ""}`}
                                    onClick={() => setTheme(option.id)}
                                >
                                    <span className={`theme-swatch theme-swatch--${option.id}`} aria-hidden="true">
                                        <i />
                                        <i />
                                        <i />
                                    </span>
                                    <span className="theme-option__copy">
                                        <strong>
                                            <Icon size={14} aria-hidden="true" /> {option.label}
                                        </strong>
                                        <small>{option.detail}</small>
                                    </span>
                                    {selected && <Check size={16} className="theme-option__check" aria-hidden="true" />}
                                </button>
                            );
                        })}
                    </div>
                </section>

                <section className="settings-section panel" aria-labelledby="settings-timezone">
                    <div className="settings-section__head">
                        <h2 className="section-title" id="settings-timezone">
                            Time zone
                        </h2>
                        <p className="section-note">Saved to your LATZ profile.</p>
                    </div>

                    {profile ? (
                        <>
                            <div className="field settings-timezone">
                                <label className="field__label" htmlFor={timezoneId}>
                                    Your time zone
                                </label>
                                <TimezoneSelect
                                    id={timezoneId}
                                    value={timezone}
                                    onChange={setTimezoneDraft}
                                    disabled={saving}
                                />
                            </div>

                            {error && <Notice tone="error">{error}</Notice>}

                            <div className="account-actions account-actions--start">
                                <Button
                                    variant="primary"
                                    onClick={() => void saveTimezone()}
                                    disabled={!timezoneChanged}
                                    busy={saving}
                                >
                                    {saving ? "Saving" : "Save time zone"}
                                </Button>
                                {timezone !== device && (
                                    <Button variant="ghost" onClick={() => setTimezoneDraft(device)} disabled={saving}>
                                        Use this device's: {timezoneLabel(device)}
                                    </Button>
                                )}
                            </div>
                        </>
                    ) : (
                        <Notice tone="error">
                            LATZ couldn't load your profile. Check that the backend is running, then reload.
                        </Notice>
                    )}
                </section>

                <section className="settings-section panel" aria-labelledby="settings-account">
                    <div className="settings-section__head">
                        <h2 className="section-title" id="settings-account">
                            Account
                        </h2>
                        <Link className="settings-link" to="/profile">
                            Edit profile
                        </Link>
                    </div>

                    <dl className="profile-facts">
                        <div>
                            <dt>Display name</dt>
                            <dd>{displayName}</dd>
                        </div>
                        <div>
                            <dt>Username</dt>
                            <dd>{account?.username ?? <span className="unset">Couldn't load</span>}</dd>
                        </div>
                        <div>
                            <dt>Email</dt>
                            <dd>{account?.email ?? <span className="unset">Couldn't load</span>}</dd>
                        </div>
                    </dl>

                    <p className="settings-note">
                        Username and email are fixed. Changing your password and deleting your account aren't
                        available in LATZ yet.
                    </p>
                </section>

                <section className="settings-section panel" aria-labelledby="settings-session">
                    <div className="settings-section__head">
                        <h2 className="section-title" id="settings-session">
                            Session
                        </h2>
                    </div>
                    <p className="settings-note">
                        Signing out removes your session from this browser. Your projects and conversations stay
                        in your account.
                    </p>
                    <div className="account-actions account-actions--start">
                        <Button variant="danger" onClick={logout}>
                            <LogOut size={14} aria-hidden="true" />
                            Sign out
                        </Button>
                    </div>
                </section>
            </div>
        </section>
    );
}
