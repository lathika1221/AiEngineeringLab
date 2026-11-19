import { useId, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { Lock, Pencil, Plus, X } from "lucide-react";
import { useSession } from "../../app/session/context";
import { apiFetch, errorMessage } from "../../shared/api/http";
import { loadResource, refreshResources, useApiResource } from "../../shared/api/resources";
import type { LifeRole, Profile } from "../../shared/api/types";
import WolfHead from "../../shared/brand/WolfHead";
import { ROLE_OPTIONS } from "../../shared/config/lifeRoles";
import { usePageTitle } from "../../shared/hooks/usePageTitle";
import { useNotify } from "../../shared/notifications/context";
import Button from "../../shared/ui/Button";
import Notice from "../../shared/ui/Notice";
import PageHeader from "../../shared/ui/PageHeader";
import { ErrorState, SkeletonList } from "../../shared/ui/States";
import TimezoneSelect from "./TimezoneSelect";
import { timezoneLabel } from "./timezones";
import "./Account.css";

/** Limits that match the backend's column sizes (display name and role: 100 characters). */
const NAME_MAX = 100;
const ROLE_MAX = 100;
const BIO_MAX = 2000;

type DraftRole = {
    /** Present for roles already saved; absent for ones added in this edit. */
    id?: number;
    role: string;
    description: string | null;
};

type Draft = {
    displayName: string;
    bio: string;
    timezone: string;
    roles: DraftRole[];
};

const ROLES_PATH = "/users/roles";

function sameRole(a: string, b: string): boolean {
    return a.trim().toLowerCase() === b.trim().toLowerCase();
}

export default function ProfilePage() {
    const { account, profile, displayName, setProfile } = useSession();
    const roles = useApiResource<LifeRole[]>(ROLES_PATH);
    const notify = useNotify();

    const [draft, setDraft] = useState<Draft | null>(null);
    const [newRole, setNewRole] = useState("");
    const [nameError, setNameError] = useState("");
    const [roleError, setRoleError] = useState("");
    const [error, setError] = useState("");
    const [saving, setSaving] = useState(false);
    const [retrying, setRetrying] = useState(false);

    const nameId = useId();
    const bioId = useId();
    const timezoneId = useId();
    const usernameId = useId();
    const emailId = useId();
    const roleInputId = useId();

    usePageTitle("My Profile");

    const savedRoles = roles.data ?? [];
    const initial = displayName.trim().charAt(0).toUpperCase() || "U";
    const editing = draft !== null;

    function startEditing() {
        if (!profile || !roles.data) {
            return;
        }

        setDraft({
            displayName: profile.display_name ?? "",
            bio: profile.bio ?? "",
            timezone: profile.timezone ?? "",
            roles: roles.data.map((role) => ({
                id: role.id,
                role: role.role,
                description: role.description,
            })),
        });
        setNewRole("");
        setNameError("");
        setRoleError("");
        setError("");
    }

    function cancelEditing() {
        setDraft(null);
        setNameError("");
        setRoleError("");
        setError("");
    }

    function patchDraft(patch: Partial<Draft>) {
        setDraft((current) => (current ? { ...current, ...patch } : current));
        // A save error describes the previous attempt; it goes once the form changes.
        setError("");
    }

    function addRole(name: string) {
        const role = name.trim();

        if (!draft || !role) {
            return;
        }

        if (role.length > ROLE_MAX) {
            setRoleError(`A role can be up to ${ROLE_MAX} characters.`);
            return;
        }

        if (draft.roles.some((item) => sameRole(item.role, role))) {
            setRoleError(`"${role}" is already one of your roles.`);
            return;
        }

        const suggestion = ROLE_OPTIONS.find((item) => sameRole(item.role, role));
        // Re-adding a role removed in this same edit keeps its saved record instead of recreating it.
        const existing = savedRoles.find((item) => sameRole(item.role, role));

        patchDraft({
            roles: [
                ...draft.roles,
                existing
                    ? { id: existing.id, role: existing.role, description: existing.description }
                    : { role: suggestion?.role ?? role, description: suggestion?.description ?? null },
            ],
        });
        setNewRole("");
        setRoleError("");
    }

    function removeRole(role: DraftRole) {
        if (draft) {
            patchDraft({ roles: draft.roles.filter((item) => item !== role) });
            setRoleError("");
        }
    }

    function handleRoleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
        // Enter adds the role; it must not submit the whole profile form.
        if (event.key === "Enter") {
            event.preventDefault();
            addRole(newRole);
        }
    }

    async function save(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();

        if (!draft || saving) {
            return;
        }

        const name = draft.displayName.trim();

        if (!name) {
            setNameError("Enter the name LATZ should call you.");
            return;
        }

        if (name.length > NAME_MAX) {
            setNameError(`Use ${NAME_MAX} characters or fewer.`);
            return;
        }

        setNameError("");
        setError("");
        setSaving(true);

        let profileSaved = false;

        try {
            const updated = await apiFetch<Profile>("/users/profile", {
                method: "PUT",
                // The backend skips null fields, so an emptied bio or time zone is sent as "".
                body: { display_name: name, bio: draft.bio.trim(), timezone: draft.timezone },
            });

            setProfile(updated);
            profileSaved = true;

            const removed = savedRoles.filter(
                (saved) => !draft.roles.some((item) => item.id === saved.id),
            );
            const added = draft.roles.filter((item) => item.id === undefined);
            let nextPriority = savedRoles.reduce((max, role) => Math.max(max, role.priority), 0) + 1;

            for (const role of removed) {
                await apiFetch(`${ROLES_PATH}/${role.id}`, { method: "DELETE" });
            }

            for (const role of added) {
                await apiFetch<LifeRole>(ROLES_PATH, {
                    method: "POST",
                    body: { role: role.role, description: role.description, priority: nextPriority },
                });
                nextPriority += 1;
            }

            await loadResource(ROLES_PATH, true);
            refreshResources("/users/context");
            setDraft(null);
            notify({ mood: "success", title: "Profile updated", detail: name });
        } catch (caught) {
            const reason = errorMessage(caught, "Something went wrong.");

            if (profileSaved) {
                // Details are saved; a role change failed part-way. Show what the server now holds.
                await loadResource(ROLES_PATH, true);
                refreshResources("/users/context");
                setDraft(null);
                setError(`Your details were saved, but not every role change was. ${reason}`);
            } else {
                setError(`Your profile wasn't saved. ${reason}`);
            }

            notify({ mood: "error", title: "Couldn't save your profile", detail: reason });
        } finally {
            setSaving(false);
        }
    }

    async function retryProfile() {
        setRetrying(true);

        try {
            setProfile(await apiFetch<Profile>("/users/profile"));
        } catch {
            // The error state stays on screen with its retry button.
        } finally {
            setRetrying(false);
        }
    }

    const suggestions = draft
        ? ROLE_OPTIONS.filter((option) => !draft.roles.some((item) => sameRole(item.role, option.role)))
        : [];

    return (
        <section className="page account-page">
            <PageHeader
                title="My profile"
                lede="How LATZ addresses you and what it knows about your work."
                actions={
                    !editing &&
                    profile && (
                        <Button variant="primary" onClick={startEditing} disabled={!roles.data}>
                            <Pencil size={14} aria-hidden="true" />
                            Edit profile
                        </Button>
                    )
                }
            />

            {!profile ? (
                <div className="section">
                    {retrying ? (
                        <SkeletonList rows={3} height={64} />
                    ) : (
                        <ErrorState
                            message="LATZ couldn't load your profile. Check that the backend is running."
                            onRetry={() => void retryProfile()}
                        />
                    )}
                </div>
            ) : (
                <div className="section profile-layout">
                    <aside className="profile-identity panel panel--lit" aria-label="Identity">
                        <div className="profile-avatar">
                            <span className="profile-avatar__initial" aria-hidden="true">
                                {initial}
                            </span>
                            <span className="profile-avatar__badge" aria-hidden="true">
                                <WolfHead size={26} />
                            </span>
                        </div>
                        <h2 className="profile-identity__name">{displayName}</h2>
                        <p className="profile-identity__handle">
                            {account ? `@${account.username}` : "Loading account"}
                        </p>
                        {account && <p className="profile-identity__email">{account.email}</p>}
                        <Link className="profile-identity__link" to="/settings">
                            Account settings
                        </Link>
                    </aside>

                    {editing && draft ? (
                        <form className="profile-details panel" onSubmit={(event) => void save(event)} noValidate>
                            <h2 className="section-title">Edit profile</h2>

                            <div className="field">
                                <label className="field__label" htmlFor={nameId}>
                                    Display name
                                </label>
                                <input
                                    id={nameId}
                                    className="input"
                                    value={draft.displayName}
                                    maxLength={NAME_MAX}
                                    onChange={(event) => {
                                        patchDraft({ displayName: event.target.value });
                                        setNameError("");
                                    }}
                                    aria-invalid={nameError ? true : undefined}
                                    aria-describedby={nameError ? `${nameId}-error` : undefined}
                                    autoComplete="name"
                                    disabled={saving}
                                />
                                {nameError && (
                                    <p className="field__error" id={`${nameId}-error`} role="alert">
                                        {nameError}
                                    </p>
                                )}
                            </div>

                            <div className="account-row">
                                <div className="field">
                                    <label className="field__label" htmlFor={usernameId}>
                                        Username
                                        <span className="field__hint">
                                            <Lock size={11} aria-hidden="true" /> Can't be changed
                                        </span>
                                    </label>
                                    <input
                                        id={usernameId}
                                        className="input"
                                        value={account?.username ?? ""}
                                        readOnly
                                    />
                                </div>
                                <div className="field">
                                    <label className="field__label" htmlFor={emailId}>
                                        Email
                                        <span className="field__hint">
                                            <Lock size={11} aria-hidden="true" /> Can't be changed
                                        </span>
                                    </label>
                                    <input id={emailId} className="input" value={account?.email ?? ""} readOnly />
                                </div>
                            </div>

                            <div className="field">
                                <label className="field__label" htmlFor={bioId}>
                                    Bio
                                    <span className="field__hint">
                                        {draft.bio.length} / {BIO_MAX}
                                    </span>
                                </label>
                                <textarea
                                    id={bioId}
                                    className="input"
                                    rows={4}
                                    value={draft.bio}
                                    maxLength={BIO_MAX}
                                    onChange={(event) => patchDraft({ bio: event.target.value })}
                                    placeholder="What you study, build or work on"
                                    disabled={saving}
                                />
                            </div>

                            <div className="field">
                                <label className="field__label" htmlFor={timezoneId}>
                                    Time zone
                                </label>
                                <TimezoneSelect
                                    id={timezoneId}
                                    value={draft.timezone}
                                    onChange={(timezone) => patchDraft({ timezone })}
                                    disabled={saving}
                                />
                            </div>

                            <fieldset className="role-editor" disabled={saving}>
                                <legend className="field__label">Engineering roles</legend>

                                {draft.roles.length === 0 ? (
                                    <p className="role-editor__empty">No roles yet. Add one below.</p>
                                ) : (
                                    <ul className="role-list" aria-label="Your roles">
                                        {draft.roles.map((role) => (
                                            <li className="role-pill" key={role.id ?? `new-${role.role}`}>
                                                {role.role}
                                                <button
                                                    type="button"
                                                    onClick={() => removeRole(role)}
                                                    aria-label={`Remove ${role.role}`}
                                                >
                                                    <X size={13} />
                                                </button>
                                            </li>
                                        ))}
                                    </ul>
                                )}

                                {suggestions.length > 0 && (
                                    <div className="role-suggestions" role="group" aria-label="Suggested roles">
                                        {suggestions.map((option) => (
                                            <button
                                                type="button"
                                                className="chip"
                                                key={option.role}
                                                title={option.description}
                                                onClick={() => addRole(option.role)}
                                            >
                                                <Plus size={11} aria-hidden="true" /> {option.role}
                                            </button>
                                        ))}
                                    </div>
                                )}

                                <div className="role-add">
                                    <label className="visually-hidden" htmlFor={roleInputId}>
                                        Add another role
                                    </label>
                                    <input
                                        id={roleInputId}
                                        className="input"
                                        value={newRole}
                                        maxLength={ROLE_MAX}
                                        onChange={(event) => {
                                            setNewRole(event.target.value);
                                            setRoleError("");
                                        }}
                                        onKeyDown={handleRoleKeyDown}
                                        placeholder="Add another role, e.g. Embedded developer"
                                    />
                                    <Button onClick={() => addRole(newRole)} disabled={!newRole.trim()}>
                                        Add role
                                    </Button>
                                </div>
                                {roleError && (
                                    <p className="field__error" role="alert">
                                        {roleError}
                                    </p>
                                )}
                            </fieldset>

                            {error && <Notice tone="error">{error}</Notice>}

                            <div className="account-actions">
                                <Button onClick={cancelEditing} disabled={saving}>
                                    Cancel
                                </Button>
                                <Button type="submit" variant="primary" busy={saving}>
                                    {saving ? "Saving" : "Save changes"}
                                </Button>
                            </div>
                        </form>
                    ) : (
                        <div className="profile-details panel">
                            {error && <Notice tone="error">{error}</Notice>}

                            <dl className="profile-facts">
                                <div>
                                    <dt>Display name</dt>
                                    <dd>{profile.display_name?.trim() || <span className="unset">Not set</span>}</dd>
                                </div>
                                <div>
                                    <dt>Username</dt>
                                    <dd>{account?.username ?? <span className="unset">Loading</span>}</dd>
                                </div>
                                <div>
                                    <dt>Email</dt>
                                    <dd>{account?.email ?? <span className="unset">Loading</span>}</dd>
                                </div>
                                <div>
                                    <dt>Time zone</dt>
                                    <dd>
                                        {profile.timezone ? (
                                            timezoneLabel(profile.timezone)
                                        ) : (
                                            <span className="unset">Not set</span>
                                        )}
                                    </dd>
                                </div>
                                <div className="profile-facts__wide">
                                    <dt>Bio</dt>
                                    <dd className="profile-bio">
                                        {profile.bio?.trim() || <span className="unset">No bio yet</span>}
                                    </dd>
                                </div>
                            </dl>

                            <section className="profile-roles" aria-labelledby="profile-roles-title">
                                <h2 className="section-title" id="profile-roles-title">
                                    Engineering roles
                                </h2>
                                {roles.loading ? (
                                    <SkeletonList rows={2} height={44} />
                                ) : roles.error ? (
                                    <ErrorState message={roles.error} onRetry={roles.reload} />
                                ) : savedRoles.length === 0 ? (
                                    <p className="unset">No roles yet. Choose Edit profile to add some.</p>
                                ) : (
                                    <ul className="role-cards">
                                        {savedRoles.map((role) => (
                                            <li key={role.id}>
                                                <strong>{role.role}</strong>
                                                {role.description && <span>{role.description}</span>}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </section>
                        </div>
                    )}
                </div>
            )}
        </section>
    );
}
