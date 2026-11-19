import { useId, useState } from "react";
import type { FormEvent } from "react";
import { AnimatePresence } from "framer-motion";
import { Brain, Plus, Trash2 } from "lucide-react";
import { apiFetch, errorMessage } from "../../shared/api/http";
import { refreshResources, updateResource, useApiResource } from "../../shared/api/resources";
import type { Memory, MemoryType } from "../../shared/api/types";
import { usePageTitle } from "../../shared/hooks/usePageTitle";
import { useNotify } from "../../shared/notifications/context";
import Button from "../../shared/ui/Button";
import ConfirmDialog from "../../shared/ui/ConfirmDialog";
import Modal from "../../shared/ui/Modal";
import Notice from "../../shared/ui/Notice";
import PageHeader from "../../shared/ui/PageHeader";
import { EmptyState, ErrorState, SkeletonList } from "../../shared/ui/States";
import "./Memories.css";

const MEMORIES_PATH = "/memory";
const TYPES: { id: MemoryType; label: string; hint: string }[] = [
    { id: "preference", label: "Preference", hint: "How you like things done" },
    { id: "fact", label: "Fact", hint: "Something true about you or your work" },
    { id: "project", label: "Project", hint: "Context about something you are building" },
];
const LABEL: Record<string, string> = Object.fromEntries(TYPES.map((type) => [type.id, type.label]));

function formatDate(value: string): string | null {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date.toLocaleDateString(undefined, { dateStyle: "medium" });
}

export default function MemoriesPage() {
    usePageTitle("Memories");
    const notify = useNotify();
    const formId = useId();
    const memories = useApiResource<Memory[]>(MEMORIES_PATH);
    const [filter, setFilter] = useState<MemoryType | "all">("all");
    const [creating, setCreating] = useState(false);
    const [type, setType] = useState<MemoryType>("preference");
    const [content, setContent] = useState("");
    const [contentError, setContentError] = useState("");
    const [formError, setFormError] = useState("");
    const [saving, setSaving] = useState(false);
    const [toDelete, setToDelete] = useState<Memory | null>(null);
    const [deleting, setDeleting] = useState(false);

    function openCreate() {
        setType(filter === "all" ? "preference" : filter);
        setContent("");
        setContentError("");
        setFormError("");
        setCreating(true);
    }

    async function create(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (saving) {
            return;
        }
        const text = content.trim();
        if (!text) {
            setContentError("Memory content is required.");
            return;
        }
        setSaving(true);
        setFormError("");
        try {
            await apiFetch<Memory>(MEMORIES_PATH, { method: "POST", body: { memory_type: type, content: text } });
            setCreating(false);
            refreshResources(MEMORIES_PATH, "/users/context");
            notify({ mood: "success", title: "Memory saved", detail: LABEL[type] });
        } catch (caught) {
            setFormError(`The memory wasn't saved. ${errorMessage(caught, "Something went wrong.")}`);
        } finally {
            setSaving(false);
        }
    }

    async function remove() {
        if (!toDelete) {
            return;
        }
        const removed = toDelete;
        setDeleting(true);
        try {
            await apiFetch(`${MEMORIES_PATH}/${removed.id}`, { method: "DELETE" });
            updateResource<Memory[]>(MEMORIES_PATH, (current) => current.filter((item) => item.id !== removed.id));
            refreshResources("/users/context");
            notify({ mood: "success", title: "Memory deleted" });
        } catch (caught) {
            notify({ mood: "error", title: "Couldn't delete the memory", detail: errorMessage(caught, "Something went wrong.") });
        } finally {
            setToDelete(null);
            setDeleting(false);
        }
    }

    const all = memories.data;
    const visible = all ? (filter === "all" ? all : all.filter((item) => item.memory_type === filter)) : [];
    const count = (id: MemoryType) => all?.filter((item) => item.memory_type === id).length ?? 0;
    const createButton = (
        <Button variant="primary" onClick={openCreate}>
            <Plus size={14} aria-hidden="true" />
            Add memory
        </Button>
    );

    return (
        <section className="page memories-page">
            <PageHeader
                title="Memories"
                lede="What LATZ keeps in mind about you and your work."
                actions={all && all.length > 0 ? createButton : undefined}
            />

            <div className="section">
                {memories.error && !all ? (
                    <ErrorState message={memories.error} onRetry={memories.reload} />
                ) : memories.loading || !all ? (
                    <SkeletonList rows={3} height={84} />
                ) : all.length === 0 ? (
                    <EmptyState title="No memories yet" action={createButton}>
                        Save preferences, facts and project context so LATZ can use them in your conversations.
                    </EmptyState>
                ) : (
                    <>
                        <div className="chip-row" role="group" aria-label="Filter by type">
                            <button
                                type="button"
                                className={`chip${filter === "all" ? " active" : ""}`}
                                aria-pressed={filter === "all"}
                                onClick={() => setFilter("all")}
                            >
                                All ({all.length})
                            </button>
                            {TYPES.map((item) => (
                                <button
                                    key={item.id}
                                    type="button"
                                    className={`chip${filter === item.id ? " active" : ""}`}
                                    aria-pressed={filter === item.id}
                                    onClick={() => setFilter(item.id)}
                                >
                                    {item.label} ({count(item.id)})
                                </button>
                            ))}
                        </div>
                        {visible.length === 0 ? (
                            <EmptyState title={`No ${LABEL[filter]?.toLowerCase()} memories`} action={createButton}>
                                Nothing saved under this type yet.
                            </EmptyState>
                        ) : (
                            <ul className="memory-list">
                                {visible.map((memory) => {
                                    const created = formatDate(memory.created_at);
                                    return (
                                        <li className="memory-card panel" key={memory.id}>
                                            <div className="memory-card__main">
                                                <span className="tag">
                                                    <Brain size={12} aria-hidden="true" />
                                                    {LABEL[memory.memory_type] ?? memory.memory_type}
                                                </span>
                                                <p>{memory.content}</p>
                                                {created && <small>Saved {created}</small>}
                                            </div>
                                            <button
                                                type="button"
                                                className="icon-btn memory-delete"
                                                onClick={() => setToDelete(memory)}
                                                aria-label={`Delete memory: ${memory.content.slice(0, 40)}`}
                                                title="Delete"
                                            >
                                                <Trash2 size={15} />
                                            </button>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </>
                )}
            </div>

            <AnimatePresence>
                {creating && (
                    <Modal title="Add memory" onClose={() => !saving && setCreating(false)}>
                        <form className="memory-form" onSubmit={(event) => void create(event)} noValidate>
                            <div className="field">
                                <label className="field__label" htmlFor={`${formId}-type`}>
                                    Type
                                </label>
                                <select
                                    id={`${formId}-type`}
                                    className="input"
                                    value={type}
                                    onChange={(event) => setType(event.target.value as MemoryType)}
                                    disabled={saving}
                                >
                                    {TYPES.map((item) => (
                                        <option key={item.id} value={item.id}>
                                            {item.label}: {item.hint}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div className="field">
                                <label className="field__label" htmlFor={`${formId}-content`}>
                                    Memory
                                </label>
                                <textarea
                                    id={`${formId}-content`}
                                    className="input"
                                    rows={4}
                                    value={content}
                                    onChange={(event) => {
                                        setContent(event.target.value);
                                        setContentError("");
                                    }}
                                    aria-invalid={contentError ? true : undefined}
                                    aria-describedby={contentError ? `${formId}-content-error` : undefined}
                                    disabled={saving}
                                />
                                {contentError && (
                                    <p className="field__error" id={`${formId}-content-error`} role="alert">
                                        {contentError}
                                    </p>
                                )}
                            </div>
                            {formError && <Notice tone="error">{formError}</Notice>}
                            <div className="memory-form__actions">
                                <Button onClick={() => setCreating(false)} disabled={saving}>
                                    Cancel
                                </Button>
                                <Button type="submit" variant="primary" busy={saving}>
                                    Save memory
                                </Button>
                            </div>
                        </form>
                    </Modal>
                )}
                {toDelete && (
                    <ConfirmDialog
                        title="Delete this memory?"
                        description="LATZ will stop using it. This cannot be undone."
                        confirmLabel={deleting ? "Deleting" : "Delete memory"}
                        cancelLabel="Keep memory"
                        busy={deleting}
                        onConfirm={() => void remove()}
                        onCancel={() => setToDelete(null)}
                    />
                )}
            </AnimatePresence>
        </section>
    );
}
