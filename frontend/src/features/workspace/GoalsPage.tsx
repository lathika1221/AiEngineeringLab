import { useId, useState } from "react";
import type { FormEvent } from "react";
import { AnimatePresence } from "framer-motion";
import { Plus, Target, Trash2 } from "lucide-react";
import { apiFetch, errorMessage } from "../../shared/api/http";
import { refreshResources, updateResource, useApiResource } from "../../shared/api/resources";
import type { Goal } from "../../shared/api/types";
import { usePageTitle } from "../../shared/hooks/usePageTitle";
import { useNotify } from "../../shared/notifications/context";
import Button from "../../shared/ui/Button";
import ConfirmDialog from "../../shared/ui/ConfirmDialog";
import Modal from "../../shared/ui/Modal";
import Notice from "../../shared/ui/Notice";
import PageHeader from "../../shared/ui/PageHeader";
import { EmptyState, ErrorState, SkeletonList } from "../../shared/ui/States";
import "./Goals.css";

/** The backend stores status as free text and only "completed" has meaning elsewhere (Mission Control). */
const STATUSES = ["active", "paused", "completed"];
const GOALS_PATH = "/users/goals";
const TITLE_MAX = 200;

function formatDate(value: string | null): string | null {
    if (!value) {
        return null;
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date.toLocaleDateString(undefined, { dateStyle: "medium" });
}

function capitalize(value: string): string {
    return value.charAt(0).toUpperCase() + value.slice(1);
}

type Draft = { title: string; description: string; category: string; priority: string; target_date: string };
const EMPTY: Draft = { title: "", description: "", category: "", priority: "1", target_date: "" };

export default function GoalsPage() {
    usePageTitle("Goals");
    const notify = useNotify();
    const formId = useId();
    const goals = useApiResource<Goal[]>(GOALS_PATH);
    const [creating, setCreating] = useState(false);
    const [draft, setDraft] = useState<Draft>(EMPTY);
    const [titleError, setTitleError] = useState("");
    const [formError, setFormError] = useState("");
    const [saving, setSaving] = useState(false);
    const [updatingId, setUpdatingId] = useState<number | null>(null);
    const [toDelete, setToDelete] = useState<Goal | null>(null);
    const [deleting, setDeleting] = useState(false);

    function openCreate() {
        setDraft(EMPTY);
        setTitleError("");
        setFormError("");
        setCreating(true);
    }

    async function create(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (saving) {
            return;
        }
        const title = draft.title.trim();
        if (!title) {
            setTitleError("Goal title is required.");
            return;
        }
        const priority = Number(draft.priority);
        if (!Number.isInteger(priority) || priority < 1) {
            setFormError("Priority must be a whole number, 1 or higher.");
            return;
        }

        setSaving(true);
        setFormError("");
        try {
            await apiFetch<Goal>(GOALS_PATH, {
                method: "POST",
                body: {
                    title,
                    description: draft.description.trim() || null,
                    category: draft.category.trim() || null,
                    priority,
                    target_date: draft.target_date ? `${draft.target_date}T00:00:00` : null,
                },
            });
            setCreating(false);
            refreshResources(GOALS_PATH);
            notify({ mood: "success", title: "Goal created", detail: title });
        } catch (caught) {
            setFormError(`The goal wasn't created. ${errorMessage(caught, "Something went wrong.")}`);
        } finally {
            setSaving(false);
        }
    }

    async function changeStatus(goal: Goal, status: string) {
        if (status === goal.status || updatingId !== null) {
            return;
        }
        setUpdatingId(goal.id);
        try {
            const updated = await apiFetch<Goal>(`${GOALS_PATH}/${goal.id}/status?status=${encodeURIComponent(status)}`, {
                method: "PATCH",
            });
            updateResource<Goal[]>(GOALS_PATH, (current) => current.map((item) => (item.id === updated.id ? updated : item)));
            refreshResources("/users/context");
        } catch (caught) {
            notify({ mood: "error", title: "Couldn't update the goal", detail: errorMessage(caught, "Something went wrong.") });
        } finally {
            setUpdatingId(null);
        }
    }

    async function remove() {
        if (!toDelete) {
            return;
        }
        setDeleting(true);
        try {
            await apiFetch(`${GOALS_PATH}/${toDelete.id}`, { method: "DELETE" });
            const removed = toDelete;
            updateResource<Goal[]>(GOALS_PATH, (current) => current.filter((item) => item.id !== removed.id));
            refreshResources("/users/context");
            notify({ mood: "success", title: "Goal deleted", detail: removed.title });
            setToDelete(null);
        } catch (caught) {
            setToDelete(null);
            notify({ mood: "error", title: "Couldn't delete the goal", detail: errorMessage(caught, "Something went wrong.") });
        } finally {
            setDeleting(false);
        }
    }

    const items = goals.data;
    const createButton = (
        <Button variant="primary" onClick={openCreate}>
            <Plus size={14} aria-hidden="true" />
            Create goal
        </Button>
    );

    return (
        <section className="page goals-page">
            <PageHeader title="Goals" lede="What you are working toward." actions={items && items.length > 0 ? createButton : undefined} />

            <div className="section">
                {goals.error && !items ? (
                    <ErrorState message={goals.error} onRetry={goals.reload} />
                ) : goals.loading || !items ? (
                    <SkeletonList rows={3} height={96} />
                ) : items.length === 0 ? (
                    <EmptyState title="No goals yet" action={createButton}>
                        Set a goal to keep track of what you are building or learning.
                    </EmptyState>
                ) : (
                    <ul className="goal-list">
                        {items.map((goal) => {
                            const created = formatDate(goal.created_at);
                            const target = formatDate(goal.target_date);
                            const options = [...new Set([...STATUSES, goal.status])];
                            return (
                                <li className={`goal-card panel${goal.status === "completed" ? " goal-card--done" : ""}`} key={goal.id}>
                                    <div className="goal-card__main">
                                        <h2>
                                            <Target size={15} aria-hidden="true" />
                                            {goal.title}
                                        </h2>
                                        {goal.description && <p>{goal.description}</p>}
                                        <dl className="goal-meta">
                                            {goal.category && (
                                                <div>
                                                    <dt>Category</dt>
                                                    <dd>{goal.category}</dd>
                                                </div>
                                            )}
                                            <div>
                                                <dt>Priority</dt>
                                                <dd>{goal.priority}</dd>
                                            </div>
                                            {target && (
                                                <div>
                                                    <dt>Target date</dt>
                                                    <dd>{target}</dd>
                                                </div>
                                            )}
                                            {created && (
                                                <div>
                                                    <dt>Created</dt>
                                                    <dd>{created}</dd>
                                                </div>
                                            )}
                                        </dl>
                                    </div>
                                    <div className="goal-card__actions">
                                        <label className="visually-hidden" htmlFor={`${formId}-status-${goal.id}`}>
                                            Status of {goal.title}
                                        </label>
                                        <select
                                            id={`${formId}-status-${goal.id}`}
                                            className={`input goal-status goal-status--${goal.status}`}
                                            value={goal.status}
                                            disabled={updatingId === goal.id}
                                            onChange={(event) => void changeStatus(goal, event.target.value)}
                                        >
                                            {options.map((status) => (
                                                <option key={status} value={status}>
                                                    {capitalize(status)}
                                                </option>
                                            ))}
                                        </select>
                                        <button
                                            type="button"
                                            className="icon-btn goal-delete"
                                            onClick={() => setToDelete(goal)}
                                            aria-label={`Delete ${goal.title}`}
                                            title="Delete"
                                        >
                                            <Trash2 size={15} />
                                        </button>
                                    </div>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </div>

            <AnimatePresence>
                {creating && (
                    <Modal title="Create goal" onClose={() => !saving && setCreating(false)}>
                        <form className="goal-form" onSubmit={(event) => void create(event)} noValidate>
                            <div className="field">
                                <label className="field__label" htmlFor={`${formId}-title`}>
                                    Goal title
                                </label>
                                <input
                                    id={`${formId}-title`}
                                    className="input"
                                    value={draft.title}
                                    maxLength={TITLE_MAX}
                                    onChange={(event) => {
                                        setDraft({ ...draft, title: event.target.value });
                                        setTitleError("");
                                    }}
                                    aria-invalid={titleError ? true : undefined}
                                    aria-describedby={titleError ? `${formId}-title-error` : undefined}
                                    disabled={saving}
                                />
                                {titleError && (
                                    <p className="field__error" id={`${formId}-title-error`} role="alert">
                                        {titleError}
                                    </p>
                                )}
                            </div>
                            <div className="field">
                                <label className="field__label" htmlFor={`${formId}-description`}>
                                    Description<span className="field__hint">Optional</span>
                                </label>
                                <textarea
                                    id={`${formId}-description`}
                                    className="input"
                                    rows={3}
                                    value={draft.description}
                                    onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                                    disabled={saving}
                                />
                            </div>
                            <div className="goal-form__row">
                                <div className="field">
                                    <label className="field__label" htmlFor={`${formId}-category`}>
                                        Category<span className="field__hint">Optional</span>
                                    </label>
                                    <input
                                        id={`${formId}-category`}
                                        className="input"
                                        value={draft.category}
                                        onChange={(event) => setDraft({ ...draft, category: event.target.value })}
                                        disabled={saving}
                                    />
                                </div>
                                <div className="field">
                                    <label className="field__label" htmlFor={`${formId}-priority`}>
                                        Priority
                                    </label>
                                    <input
                                        id={`${formId}-priority`}
                                        className="input"
                                        type="number"
                                        min={1}
                                        step={1}
                                        value={draft.priority}
                                        onChange={(event) => setDraft({ ...draft, priority: event.target.value })}
                                        disabled={saving}
                                    />
                                </div>
                            </div>
                            <div className="field">
                                <label className="field__label" htmlFor={`${formId}-target`}>
                                    Target date<span className="field__hint">Optional</span>
                                </label>
                                <input
                                    id={`${formId}-target`}
                                    className="input"
                                    type="date"
                                    value={draft.target_date}
                                    onChange={(event) => setDraft({ ...draft, target_date: event.target.value })}
                                    disabled={saving}
                                />
                            </div>
                            {formError && <Notice tone="error">{formError}</Notice>}
                            <div className="goal-form__actions">
                                <Button onClick={() => setCreating(false)} disabled={saving}>
                                    Cancel
                                </Button>
                                <Button type="submit" variant="primary" busy={saving}>
                                    Create goal
                                </Button>
                            </div>
                        </form>
                    </Modal>
                )}
                {toDelete && (
                    <ConfirmDialog
                        title={`Delete "${toDelete.title}"?`}
                        description="This removes the goal from your account. It cannot be undone."
                        confirmLabel={deleting ? "Deleting" : "Delete goal"}
                        cancelLabel="Keep goal"
                        busy={deleting}
                        onConfirm={() => void remove()}
                        onCancel={() => setToDelete(null)}
                    />
                )}
            </AnimatePresence>
        </section>
    );
}
