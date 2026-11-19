import { useEffect, useId, useState } from "react";
import type { FormEvent } from "react";
import { AnimatePresence } from "framer-motion";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, MessagesSquare, Pencil, Trash2 } from "lucide-react";
import { ApiError, apiFetch, errorMessage } from "../../shared/api/http";
import { refreshResources } from "../../shared/api/resources";
import type { Conversation, Project } from "../../shared/api/types";
import WolfHead from "../../shared/brand/WolfHead";
import { engineeringModes } from "../../shared/config/engineeringModes";
import { usePageTitle } from "../../shared/hooks/usePageTitle";
import { useNotify } from "../../shared/notifications/context";
import Button from "../../shared/ui/Button";
import ConfirmDialog from "../../shared/ui/ConfirmDialog";
import Notice from "../../shared/ui/Notice";
import PageHeader from "../../shared/ui/PageHeader";
import { EmptyState, ErrorState, SkeletonList } from "../../shared/ui/States";
import "./ProjectDetail.css";

/** The project name column holds 200 characters. */
const NAME_MAX = 200;
const STATUSES = ["active", "paused", "completed", "archived"];
const PROJECTS_CRUMB = [{ label: "Projects", to: "/projects" }];

type ProjectState =
    | { state: "loading" }
    | { state: "not-found" }
    | { state: "error"; message: string }
    | { state: "ready"; project: Project };

type ConversationsState =
    | { state: "loading" }
    | { state: "error"; message: string }
    | { state: "ready"; items: Conversation[] };

type Draft = {
    name: string;
    description: string;
    status: string;
    engine: string;
    tech_stack: string;
};

function toProjectId(value: string | undefined): number | null {
    return value && /^\d{1,9}$/.test(value) ? Number(value) : null;
}

function formatDate(value: string | null): string | null {
    if (!value) {
        return null;
    }

    const date = new Date(value);

    return Number.isNaN(date.getTime())
        ? null
        : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function statusTag(status: string): string {
    const normalized = status.toLowerCase();

    return ["active", "paused", "completed"].includes(normalized) ? `tag tag--${normalized}` : "tag";
}

function capitalize(value: string): string {
    return value.charAt(0).toUpperCase() + value.slice(1);
}

/** Remounts the page when the address changes to another project, so no state carries over. */
export default function ProjectDetailRoute() {
    const { projectId } = useParams();

    return <ProjectDetailPage key={projectId} />;
}

function ProjectDetailPage() {
    const params = useParams();
    const projectId = toProjectId(params.projectId);
    const navigate = useNavigate();
    const notify = useNotify();
    const formId = useId();

    const [project, setProject] = useState<ProjectState>(
        projectId === null ? { state: "not-found" } : { state: "loading" },
    );
    const [conversations, setConversations] = useState<ConversationsState>({ state: "loading" });
    const [attempt, setAttempt] = useState(0);
    const [draft, setDraft] = useState<Draft | null>(null);
    const [nameError, setNameError] = useState("");
    const [saveError, setSaveError] = useState("");
    const [saving, setSaving] = useState(false);
    const [confirmingDelete, setConfirmingDelete] = useState(false);
    const [deleting, setDeleting] = useState(false);

    const loaded = project.state === "ready" ? project.project : null;

    usePageTitle(
        loaded ? loaded.name : project.state === "not-found" ? "Project not found" : "Project",
    );

    // The route element is keyed by the id, so this runs once per project (and again on retry).
    useEffect(() => {
        if (projectId === null) {
            return;
        }

        const controller = new AbortController();
        const { signal } = controller;

        apiFetch<Project>(`/projects/${projectId}`, { signal })
            .then((data) => setProject({ state: "ready", project: data }))
            .catch((caught: unknown) => {
                if (signal.aborted) {
                    return;
                }

                setProject(
                    caught instanceof ApiError && caught.status === 404
                        ? { state: "not-found" }
                        : {
                              state: "error",
                              message: errorMessage(caught, "LATZ couldn't load this project."),
                          },
                );
            });

        apiFetch<Conversation[]>(`/conversations?project_id=${projectId}`, { signal })
            .then((items) => setConversations({ state: "ready", items }))
            .catch((caught: unknown) => {
                if (!signal.aborted) {
                    setConversations({
                        state: "error",
                        message: errorMessage(caught, "LATZ couldn't load this project's conversations."),
                    });
                }
            });

        return () => controller.abort();
    }, [projectId, attempt]);

    function retry() {
        setProject({ state: "loading" });
        setConversations({ state: "loading" });
        setAttempt((current) => current + 1);
    }

    function startEditing() {
        if (!loaded) {
            return;
        }

        setDraft({
            name: loaded.name,
            description: loaded.description ?? "",
            status: loaded.status,
            engine: loaded.engine ?? "",
            tech_stack: loaded.tech_stack ?? "",
        });
        setNameError("");
        setSaveError("");
    }

    function patchDraft(patch: Partial<Draft>) {
        setDraft((current) => (current ? { ...current, ...patch } : current));
        setSaveError("");
    }

    async function save(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();

        if (!draft || !loaded || saving) {
            return;
        }

        const name = draft.name.trim();

        if (!name) {
            setNameError("Project name is required.");
            return;
        }

        setNameError("");
        setSaveError("");
        setSaving(true);

        try {
            const updated = await apiFetch<Project>(`/projects/${loaded.id}`, {
                method: "PATCH",
                // The backend skips null fields, so an emptied field is sent as "".
                body: {
                    name,
                    description: draft.description.trim(),
                    status: draft.status,
                    engine: draft.engine,
                    tech_stack: draft.tech_stack.trim(),
                },
            });

            setProject({ state: "ready", project: updated });
            setDraft(null);
            refreshResources("/projects");
            notify({ mood: "success", title: "Project updated", detail: updated.name });
        } catch (caught) {
            setSaveError(`Your changes weren't saved. ${errorMessage(caught, "Something went wrong.")}`);
        } finally {
            setSaving(false);
        }
    }

    async function deleteProject() {
        if (!loaded) {
            return;
        }

        setDeleting(true);

        try {
            await apiFetch(`/projects/${loaded.id}`, { method: "DELETE" });
            refreshResources("/projects", "/conversations");
            notify({ mood: "success", title: "Project deleted", detail: loaded.name });
            navigate("/projects", { replace: true });
        } catch (caught) {
            setConfirmingDelete(false);
            notify({
                mood: "error",
                title: "Couldn't delete the project",
                detail: errorMessage(caught, "Something went wrong."),
            });
        } finally {
            setDeleting(false);
        }
    }

    if (project.state === "not-found") {
        return (
            <section className="page project-detail">
                <div className="empty project-missing">
                    <WolfHead size={56} mood="error" />
                    <h1>Project not found</h1>
                    <p>
                        There is no project at this address in your account. It may have been deleted, or the
                        link may be mistyped.
                    </p>
                    <Link className="btn btn--primary" to="/projects">
                        <ArrowLeft size={14} aria-hidden="true" />
                        Back to projects
                    </Link>
                </div>
            </section>
        );
    }

    if (project.state === "error") {
        return (
            <section className="page project-detail">
                <PageHeader title="Project" breadcrumbs={PROJECTS_CRUMB} />
                <div className="section">
                    <ErrorState message={project.message} onRetry={retry} />
                </div>
            </section>
        );
    }

    if (!loaded) {
        return (
            <section className="page project-detail" aria-busy="true">
                <PageHeader title="Project" breadcrumbs={PROJECTS_CRUMB} />
                <div className="section">
                    <span className="visually-hidden" role="status">
                        Loading project
                    </span>
                    <SkeletonList rows={2} height={120} />
                </div>
            </section>
        );
    }

    const mode = engineeringModes.find((item) => item.id === loaded.engine);
    const stack = (loaded.tech_stack ?? "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
    const created = formatDate(loaded.created_at);
    const updated = formatDate(loaded.updated_at);
    const chatPath = `/chat?project=${loaded.id}`;

    return (
        <section className="page project-detail">
            <PageHeader
                title={loaded.name}
                breadcrumbs={PROJECTS_CRUMB}
                actions={
                    !draft && (
                        <>
                            <Button variant="primary" onClick={() => navigate(chatPath)}>
                                <MessagesSquare size={14} aria-hidden="true" />
                                Open project chat
                            </Button>
                            <Button onClick={startEditing}>
                                <Pencil size={14} aria-hidden="true" />
                                Edit project
                            </Button>
                            <Button variant="danger" onClick={() => setConfirmingDelete(true)}>
                                <Trash2 size={14} aria-hidden="true" />
                                Delete
                            </Button>
                        </>
                    )
                }
            />

            <div className="section project-detail__layout">
                {draft ? (
                    <form className="project-info panel panel--lit" onSubmit={(event) => void save(event)} noValidate>
                        <h2 className="section-title">Edit project</h2>

                        <div className="field">
                            <label className="field__label" htmlFor={`${formId}-name`}>
                                Project name
                            </label>
                            <input
                                id={`${formId}-name`}
                                className="input"
                                value={draft.name}
                                maxLength={NAME_MAX}
                                onChange={(event) => {
                                    patchDraft({ name: event.target.value });
                                    setNameError("");
                                }}
                                aria-invalid={nameError ? true : undefined}
                                aria-describedby={nameError ? `${formId}-name-error` : undefined}
                                disabled={saving}
                            />
                            {nameError && (
                                <p className="field__error" id={`${formId}-name-error`} role="alert">
                                    {nameError}
                                </p>
                            )}
                        </div>

                        <div className="field">
                            <label className="field__label" htmlFor={`${formId}-description`}>
                                Description
                                <span className="field__hint">Optional</span>
                            </label>
                            <textarea
                                id={`${formId}-description`}
                                className="input"
                                rows={4}
                                value={draft.description}
                                onChange={(event) => patchDraft({ description: event.target.value })}
                                placeholder="What are you building?"
                                disabled={saving}
                            />
                        </div>

                        <div className="project-form-row">
                            <div className="field">
                                <label className="field__label" htmlFor={`${formId}-status`}>
                                    Status
                                </label>
                                <select
                                    id={`${formId}-status`}
                                    className="input"
                                    value={draft.status}
                                    onChange={(event) => patchDraft({ status: event.target.value })}
                                    disabled={saving}
                                >
                                    {/* A status set outside this list (by the API) stays selectable. */}
                                    {[...new Set([...STATUSES, draft.status])].map((status) => (
                                        <option key={status} value={status}>
                                            {capitalize(status)}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div className="field">
                                <label className="field__label" htmlFor={`${formId}-engine`}>
                                    Engineering mode
                                </label>
                                <select
                                    id={`${formId}-engine`}
                                    className="input"
                                    value={draft.engine}
                                    onChange={(event) => patchDraft({ engine: event.target.value })}
                                    disabled={saving}
                                >
                                    <option value="">Not set</option>
                                    {engineeringModes.map((item) => (
                                        <option key={item.id} value={item.id}>
                                            {item.title}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        <div className="field">
                            <label className="field__label" htmlFor={`${formId}-stack`}>
                                Technology stack
                                <span className="field__hint">Separate with commas</span>
                            </label>
                            <input
                                id={`${formId}-stack`}
                                className="input"
                                value={draft.tech_stack}
                                onChange={(event) => patchDraft({ tech_stack: event.target.value })}
                                placeholder="e.g. FastAPI, React, PostgreSQL"
                                disabled={saving}
                            />
                        </div>

                        {saveError && <Notice tone="error">{saveError}</Notice>}

                        <div className="project-form-actions">
                            <Button onClick={() => setDraft(null)} disabled={saving}>
                                Cancel
                            </Button>
                            <Button type="submit" variant="primary" busy={saving}>
                                {saving ? "Saving" : "Save changes"}
                            </Button>
                        </div>
                    </form>
                ) : (
                    <div className="project-info panel panel--lit">
                        <div>
                            <h2 className="project-info__label">Description</h2>
                            <p className="project-info__description">
                                {loaded.description?.trim() || (
                                    <span className="project-unset">No description yet.</span>
                                )}
                            </p>
                        </div>

                        <dl className="project-facts">
                            <div>
                                <dt>Status</dt>
                                <dd>
                                    <span className={statusTag(loaded.status)}>{loaded.status}</span>
                                </dd>
                            </div>
                            <div>
                                <dt>Engineering mode</dt>
                                <dd>
                                    {mode ? (
                                        <Link to={`/${mode.id}`}>{mode.title}</Link>
                                    ) : loaded.engine ? (
                                        loaded.engine
                                    ) : (
                                        <span className="project-unset">Not set</span>
                                    )}
                                </dd>
                            </div>
                            {created && (
                                <div>
                                    <dt>Created</dt>
                                    <dd>{created}</dd>
                                </div>
                            )}
                            {updated && (
                                <div>
                                    <dt>Last updated</dt>
                                    <dd>{updated}</dd>
                                </div>
                            )}
                            <div className="project-facts__wide">
                                <dt>Technology stack</dt>
                                <dd>
                                    {stack.length > 0 ? (
                                        <ul className="project-stack">
                                            {stack.map((item) => (
                                                <li key={item}>{item}</li>
                                            ))}
                                        </ul>
                                    ) : (
                                        <span className="project-unset">Not specified</span>
                                    )}
                                </dd>
                            </div>
                        </dl>
                    </div>
                )}

                <section className="project-conversations" aria-labelledby="project-conversations-title">
                    <div className="section-head">
                        <h2 className="section-title" id="project-conversations-title">
                            Conversations
                            {conversations.state === "ready" && (
                                <span className="project-count">{conversations.items.length}</span>
                            )}
                        </h2>
                        {conversations.state === "ready" && conversations.items.length > 0 && (
                            <Link className="project-conversations__new" to={chatPath}>
                                Open project chat
                            </Link>
                        )}
                    </div>

                    {conversations.state === "loading" ? (
                        <SkeletonList rows={3} height={62} />
                    ) : conversations.state === "error" ? (
                        <ErrorState message={conversations.message} onRetry={retry} />
                    ) : conversations.items.length === 0 ? (
                        <EmptyState
                            title="No conversations yet"
                            action={
                                <Link className="btn btn--primary btn--sm" to={chatPath}>
                                    Start a conversation
                                </Link>
                            }
                        >
                            Conversations you have with LATZ about this project are listed here.
                        </EmptyState>
                    ) : (
                        <ul className="project-conversation-list">
                            {conversations.items.map((conversation) => (
                                <li key={conversation.id}>
                                    <Link to={`/chat/${conversation.id}?project=${loaded.id}`}>
                                        <MessagesSquare size={16} aria-hidden="true" />
                                        <span className="project-conversation__main">
                                            <strong>{conversation.title || "New Chat"}</strong>
                                            <small>
                                                Started {formatDate(conversation.created_at)}, last active{" "}
                                                {formatDate(conversation.updated_at)}
                                            </small>
                                        </span>
                                        <span className="tag">{conversation.category}</span>
                                        <ArrowRight size={15} aria-hidden="true" />
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>
            </div>

            <AnimatePresence>
                {confirmingDelete && (
                    <ConfirmDialog
                        title={`Delete "${loaded.name}"?`}
                        description="This removes the project from your account. It cannot be undone."
                        confirmLabel={deleting ? "Deleting" : "Delete project"}
                        cancelLabel="Keep project"
                        busy={deleting}
                        onConfirm={() => void deleteProject()}
                        onCancel={() => setConfirmingDelete(false)}
                    />
                )}
            </AnimatePresence>
        </section>
    );
}
