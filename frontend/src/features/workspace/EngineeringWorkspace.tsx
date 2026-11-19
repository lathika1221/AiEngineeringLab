import { useEffect, useId, useState } from "react";
import "./EngineeringWorkspace.css";
import { AnimatePresence } from "framer-motion";
import { ArrowLeft, ArrowRight, Check, FolderKanban, Pencil, Plus, Trash2 } from "lucide-react";
import { API_BASE, clearToken, getToken } from "../../shared/api/client";
import WolfHead from "../../shared/brand/WolfHead";
import { engineeringModes } from "../../shared/config/engineeringModes";
import { useNotify } from "../../shared/notifications/context";
import Button from "../../shared/ui/Button";
import Modal from "../../shared/ui/Modal";
import Notice from "../../shared/ui/Notice";

import { Link, useNavigate } from "react-router-dom";
import { queueWorkflow } from "../../app/workflow";
import type { WorkspaceWorkflow } from "../../app/workflow";
import { refreshResources, useApiResource } from "../../shared/api/resources";
import type { Project } from "../../shared/api/types";
import type { EngineeringModeId } from "../../shared/config/engineeringModes";
import { usePageTitle } from "../../shared/hooks/usePageTitle";

/** The screens this component renders: one per engineering mode, plus the project list. */
export type WorkspaceMode = EngineeringModeId | "projects";

type EngineeringWorkspaceProps = {
    mode: WorkspaceMode;
};

type WorkspaceContent = {
    eyebrow: string;
    title: string;
    description: string;
    actions: WorkspaceWorkflow[];
};

type ProjectForm = {
    name: string;
    description: string;
    status: string;
    engine: string;
    tech_stack: string;
};

type DashboardProject = {
    id: number;
    name: string;
    description: string | null;
    status: string;
    engine: string | null;
    tech_stack: string | null;
    created_at?: string | null;
    updated_at?: string | null;
};

type CreatedProject = {
    id: number;
    name: string;
    description: string | null;
    status: string;
    engine: string | null;
    tech_stack: string | null;
};

const workspaceContent: Record<
    WorkspaceMode,
    WorkspaceContent
> = {
    forge: {
        eyebrow: "FORGE",
        title: "Build something real.",
        description:
            "Turn an idea into a working software system, API, AI agent, or engineering project.",
        actions: [
            {
                engine: "forge",
                action: "create_project",
                label: "Create new project",
            },
            {
                engine: "forge",
                action: "design_architecture",
                label: "Design system architecture",
            },
            {
                engine: "forge",
                action: "build_ai_agent",
                label: "Build an AI agent",
            },
        ],
    },

    learn: {
        eyebrow: "LEARN",
        title: "Understand. Practice. Master.",
        description:
            "Build technical understanding through structured learning, examples, experiments, and practice.",
        actions: [
            {
                engine: "learn",
                action: "start_learning_path",
                label: "Start a learning path",
            },
            {
                engine: "learn",
                action: "explore_concept",
                label: "Explore a concept",
            },
            {
                engine: "learn",
                action: "practice",
                label: "Practice with LATZ",
            },
        ],
    },

    research: {
        eyebrow: "RESEARCH",
        title: "Investigate the unknown.",
        description:
            "Explore research questions, literature, experiments, hypotheses, and technical evidence.",
        actions: [
            {
                engine: "research",
                action: "start_research",
                label: "Start research topic",
            },
            {
                engine: "research",
                action: "review_literature",
                label: "Review literature",
            },
            {
                engine: "research",
                action: "design_experiment",
                label: "Design an experiment",
            },
        ],
    },

    explore: {
        eyebrow: "EXPLORE",
        title: "Discover what is possible.",
        description:
            "Explore technologies, ideas, architectures, tools, and possibilities before committing to a direction.",
        actions: [
            {
                engine: "explore",
                action: "explore_technology",
                label: "Explore a technology",
            },
            {
                engine: "explore",
                action: "compare_approaches",
                label: "Compare approaches",
            },
            {
                engine: "explore",
                action: "discover_ideas",
                label: "Discover ideas",
            },
        ],
    },

    solve: {
        eyebrow: "SOLVE",
        title: "Break the problem down.",
        description:
            "Turn difficult engineering problems into smaller, testable and actionable steps.",
        actions: [
            {
                engine: "solve",
                action: "define_problem",
                label: "Define the problem",
            },
            {
                engine: "solve",
                action: "break_into_steps",
                label: "Break it into steps",
            },
            {
                engine: "solve",
                action: "work_through_solution",
                label: "Work through a solution",
            },
        ],
    },

    projects: {
        eyebrow: "PROJECTS",
        title: "Your engineering projects.",
        description:
            "Continue building, reviewing, and organizing the projects in your workspace.",
        actions: [
            {
                engine: null,
                action: "create_project",
                label: "Create new project",
            },
            {
                engine: null,
                action: "open_project",
                label: "Open existing project",
            },
            {
                engine: null,
                action: "review_project_progress",
                label: "Review project progress",
            },
        ],
    },

};

const initialProjectForm: ProjectForm = {
    name: "",
    description: "",
    status: "active",
    engine: "forge",
    tech_stack: "",
};

export default function EngineeringWorkspace({
    mode,
}: EngineeringWorkspaceProps) {
    const content = workspaceContent[mode];
    const navigate = useNavigate();
    const modeConfig = engineeringModes.find((item) => item.id === mode);

    usePageTitle(modeConfig?.title ?? "Projects");

    /** Hands a piece of work to chat. Each one starts its own conversation. */
    function onAction(workflow: WorkspaceWorkflow) {
        navigate(
            queueWorkflow({
                ...workflow,
                fresh: true,
                category:
                    workflow.projectId !== undefined
                        ? "projects"
                        : (modeConfig?.category ?? "general"),
            }),
        );
    }
    const notify = useNotify();
    const formId = useId();
    const [projectToDelete, setProjectToDelete] = useState<DashboardProject | null>(null);
    const [projects, setProjects] = useState<DashboardProject[]>([]);
    const [projectsLoading, setProjectsLoading] = useState(false);
    const [projectsError, setProjectsError] = useState("");
    const [projectSearch, setProjectSearch] = useState("");
    const [projectStatus, setProjectStatus] = useState("all");
    const [projectSort, setProjectSort] = useState<"updated" | "name" | "created">("updated");
    const [editingProject, setEditingProject] = useState<DashboardProject | null>(null);
    const [savingProject, setSavingProject] = useState(false);
    const [deletingProjectId, setDeletingProjectId] = useState<number | null>(null);
    const [editForm, setEditForm] = useState({
        name: "",
        description: "",
        status: "active",
        engine: "",
        tech_stack: "",
    });

    async function loadProjects() {
        const token = getToken();
        if (!token) {
            setProjectsError("Please sign in again to load your projects.");
            return;
        }

        setProjectsLoading(true);
        setProjectsError("");
        try {
            const response = await fetch(`${API_BASE}/projects`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (response.status === 401) {
                clearToken();
                window.location.reload();
                return;
            }
            if (!response.ok) throw new Error(`Request failed: ${response.status}`);
            setProjects(await response.json() as DashboardProject[]);
        } catch (error) {
            console.error("Projects dashboard failed to load:", error);
            setProjectsError("Could not load projects. Check that the backend is running.");
        } finally {
            setProjectsLoading(false);
        }
    }

    useEffect(() => {
        if (mode !== "projects") return;

        const timeoutId = window.setTimeout(() => {
            void loadProjects();
        }, 0);

        return () => window.clearTimeout(timeoutId);
    }, [mode]);

    function startEditing(project: DashboardProject) {
        setEditingProject(project);
        setEditForm({
            name: project.name,
            description: project.description ?? "",
            status: project.status,
            engine: project.engine ?? "",
            tech_stack: project.tech_stack ?? "",
        });
        setProjectsError("");
    }

    async function saveProjectChanges() {
        if (!editingProject || !editForm.name.trim()) {
            setProjectsError("Project name is required.");
            return;
        }
        const token = getToken();
        if (!token) {
            setProjectsError("Please sign in again.");
            return;
        }

        setSavingProject(true);
        setProjectsError("");
        try {
            const response = await fetch(`${API_BASE}/projects/${editingProject.id}`, {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({
                    name: editForm.name.trim(),
                    // The backend skips null fields, so an emptied field is sent as "".
                    description: editForm.description.trim(),
                    status: editForm.status,
                    engine: editForm.engine,
                    tech_stack: editForm.tech_stack.trim(),
                }),
            });
            if (response.status === 401) {
                clearToken();
                window.location.reload();
                return;
            }
            if (!response.ok) throw new Error(`Request failed: ${response.status}`);
            const updated = await response.json() as DashboardProject;
            setProjects(current => current.map(item => item.id === updated.id ? updated : item));
            setEditingProject(null);
            notify({ mood: "success", title: "Project updated", detail: updated.name });
            refreshResources("/projects");
        } catch (error) {
            console.error("Project update failed:", error);
            setProjectsError("Could not update the project.");
        } finally {
            setSavingProject(false);
        }
    }

    async function deleteProject(project: DashboardProject) {
        const token = getToken();
        if (!token) {
            setProjectsError("Please sign in again.");
            return;
        }

        setDeletingProjectId(project.id);
        setProjectsError("");
        try {
            const response = await fetch(`${API_BASE}/projects/${project.id}`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            });
            if (response.status === 401) {
                clearToken();
                window.location.reload();
                return;
            }
            if (!response.ok) throw new Error(`Request failed: ${response.status}`);
            setProjects(current => current.filter(item => item.id !== project.id));
            if (editingProject?.id === project.id) setEditingProject(null);
            notify({ mood: "success", title: "Project deleted", detail: project.name });
            refreshResources("/projects");
        } catch (error) {
            console.error("Project deletion failed:", error);
            setProjectsError("Could not delete the project.");
        } finally {
            setDeletingProjectId(null);
            setProjectToDelete(null);
        }
    }

    const [showProjectForm, setShowProjectForm] =
        useState(false);

    const [projectForm, setProjectForm] =
        useState<ProjectForm>(
            initialProjectForm,
        );

    const [creatingProject, setCreatingProject] =
        useState(false);

    const [createdProject, setCreatedProject] =
        useState<CreatedProject | null>(
            null,
        );

    const [projectError, setProjectError] =
        useState("");

    function handleAction(
        workflow: WorkspaceWorkflow,
    ) {
        if (
            workflow.action ===
            "create_project" &&
            (mode === "forge" || mode === "projects")
        ) {
            setShowProjectForm(true);
            setCreatedProject(null);
            setProjectError("");
            return;
        }

        onAction(workflow);
    }

    function updateProjectField(
        field: keyof ProjectForm,
        value: string,
    ) {
        setProjectForm((current) => ({
            ...current,
            [field]: value,
        }));
    }

    async function createProject() {
        if (!projectForm.name.trim()) {
            setProjectError(
                "Project name is required.",
            );
            return;
        }

        const token =
            getToken();

        if (!token) {
            setProjectError(
                "Your session has expired. Please sign in again.",
            );
            return;
        }

        setCreatingProject(true);
        setProjectError("");

        try {
            const response = await fetch(
                `${API_BASE}/projects`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json",
                        Authorization:
                            `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        name:
                            projectForm.name.trim(),
                        description:
                            projectForm.description.trim() ||
                            null,
                        status:
                            projectForm.status,
                        engine:
                            projectForm.engine ||
                            null,
                        tech_stack:
                            projectForm.tech_stack.trim() ||
                            null,
                    }),
                },
            );

            if (response.status === 401) {
                clearToken();

                window.location.reload();
                return;
            }

            if (!response.ok) {
                const errorText =
                    await response.text();

                throw new Error(
                    errorText ||
                    `Request failed: ${response.status}`,
                );
            }

            const project =
                (await response.json()) as CreatedProject;

            setCreatedProject(project);
            setProjectForm(
                initialProjectForm,
            );
            notify({ mood: "success", title: "Project created", detail: project.name });
            refreshResources("/projects");
        } catch (error) {
            console.error(
                "Project creation failed:",
                error,
            );

            setProjectError(
                "Could not create the project. Make sure the AEL backend is running.",
            );
        } finally {
            setCreatingProject(false);
        }
    }

    function closeProjectForm() {
        if (creatingProject) {
            return;
        }

        setShowProjectForm(false);
        setCreatedProject(null);
        setProjectError("");
        setProjectForm(
            initialProjectForm,
        );

        // Show a project created from this screen without leaving and coming back.
        if (mode === "projects" && createdProject) {
            void loadProjects();
        }
    }

    function continueWithLatz() {
        if (!createdProject) {
            return;
        }

        onAction({
            engine: "forge",
            action: "design_architecture",
            label: `Continue building ${createdProject.name}`,
            projectId: createdProject.id,
        });
    }

    const ModeIcon = modeConfig?.icon ?? FolderKanban;
    const newProjectWorkflow: WorkspaceWorkflow = {
        engine: null,
        action: "create_project",
        label: "Create new project",
    };

    const projectQuery = projectSearch.trim().toLowerCase();
    const visibleProjects = projects
        .filter(
            (project) =>
                (projectStatus === "all" || project.status.toLowerCase() === projectStatus) &&
                (!projectQuery ||
                    `${project.name} ${project.description ?? ""} ${project.tech_stack ?? ""}`
                        .toLowerCase()
                        .includes(projectQuery)),
        )
        .sort((a, b) => {
            if (projectSort === "name") {
                return a.name.localeCompare(b.name);
            }

            const key = projectSort === "created" ? "created_at" : "updated_at";

            return (b[key] ?? "").localeCompare(a[key] ?? "");
        });
    const projectFiltersActive = projectQuery !== "" || projectStatus !== "all";

    function statusTag(status: string): string {
        const normalized = status.toLowerCase();

        return ["active", "paused", "completed"].includes(normalized)
            ? `tag tag--${normalized}`
            : "tag";
    }

    return (
        <section className="page engineering-workspace">
            <Link className="page-back" to="/mission-control">
                <ArrowLeft size={15} aria-hidden="true" />
                Mission Control
            </Link>

            <header className="engineering-workspace-header">
                <p className="label">
                    <ModeIcon size={14} aria-hidden="true" />
                    {content.eyebrow}
                </p>

                <h1 className="display page-title">{content.title}</h1>

                <p className="page-lede">{content.description}</p>
            </header>

            {mode === "projects" && !showProjectForm ? (
                <section className="section project-dashboard" aria-labelledby="saved-projects">
                    <div className="section-head">
                        <h2 className="section-title" id="saved-projects">
                            Saved projects
                            {!projectsLoading && <span className="project-count">{projects.length}</span>}
                        </h2>
                        <Button variant="primary" onClick={() => handleAction(newProjectWorkflow)}>
                            <Plus size={15} aria-hidden="true" />
                            New project
                        </Button>
                    </div>

                    {projectsError && !editingProject && <Notice tone="error">{projectsError}</Notice>}

                    {projectsLoading ? (
                        <div className="empty" role="status">
                            <WolfHead size={48} mood="thinking" />
                            <p>Loading your projects</p>
                        </div>
                    ) : projects.length === 0 && !projectsError ? (
                        <div className="empty">
                            <h3>No projects yet</h3>
                            <p>Create your first project to start building with LATZ.</p>
                            <Button variant="primary" onClick={() => handleAction(newProjectWorkflow)}>
                                Create a project
                            </Button>
                        </div>
                    ) : (
                        <>
                        <div className="project-filters" role="search" aria-label="Filter projects">
                            <input
                                className="input"
                                type="search"
                                value={projectSearch}
                                onChange={(event) => setProjectSearch(event.target.value)}
                                placeholder="Search projects"
                                aria-label="Search projects"
                            />
                            <select className="input" value={projectStatus} onChange={(event) => setProjectStatus(event.target.value)} aria-label="Filter by project state">
                                <option value="all">All statuses</option>
                                <option value="active">Active</option>
                                <option value="paused">Paused</option>
                                <option value="completed">Completed</option>
                                <option value="archived">Archived</option>
                            </select>
                            <select className="input" value={projectSort} onChange={(event) => setProjectSort(event.target.value as typeof projectSort)} aria-label="Sort projects">
                                <option value="updated">Recently updated</option>
                                <option value="created">Newest first</option>
                                <option value="name">Name A to Z</option>
                            </select>
                        </div>
                        {visibleProjects.length === 0 && (
                            <div className="empty">
                                <h3>No projects match</h3>
                                <p>Try a different search or status.</p>
                                {projectFiltersActive && (
                                    <Button onClick={() => { setProjectSearch(""); setProjectStatus("all"); }}>Clear filters</Button>
                                )}
                            </div>
                        )}
                        <div className="project-dashboard-grid">
                            {visibleProjects.map(project => (
                                <article className="project-card panel" key={project.id}>
                                    <div className="project-card__top">
                                        <h3><Link to={`/projects/${project.id}`}>{project.name}</Link></h3>
                                        <span className={statusTag(project.status)}>{project.status}</span>
                                    </div>
                                    <p className="project-card__description">{project.description || "No description added yet."}</p>
                                    <dl className="project-card__meta">
                                        <div><dt>Engine</dt><dd>{project.engine || "Not set"}</dd></div>
                                        <div><dt>Tech stack</dt><dd>{project.tech_stack || "Not specified"}</dd></div>
                                        {project.updated_at && <div><dt>Updated</dt><dd>{new Date(project.updated_at).toLocaleDateString()}</dd></div>}
                                    </dl>
                                    <div className="project-card__actions">
                                        <Link className="btn btn--secondary btn--sm" to={`/projects/${project.id}`}>View details</Link>
                                        <Button variant="primary" size="sm" onClick={() => onAction({ engine: "forge", action: "design_architecture", label: `Continue building ${project.name}. Review the existing project and help me identify the next implementation step.`, projectId: project.id })}>
                                            Open with LATZ
                                            <ArrowRight size={14} aria-hidden="true" />
                                        </Button>
                                        <button type="button" className="icon-btn" onClick={() => startEditing(project)} aria-label={`Edit ${project.name}`} title="Edit">
                                            <Pencil size={15} />
                                        </button>
                                        <button type="button" className="icon-btn project-card__delete" disabled={deletingProjectId === project.id} onClick={() => setProjectToDelete(project)} aria-label={`Delete ${project.name}`} title="Delete">
                                            <Trash2 size={15} />
                                        </button>
                                    </div>
                                </article>
                            ))}
                        </div>
                        </>
                    )}

                    <AnimatePresence>
                        {editingProject && (
                            <Modal
                                key="edit"
                                title="Edit project"
                                description="Changes are saved to your account."
                                onClose={() => {
                                    if (!savingProject) setEditingProject(null);
                                }}
                                actions={
                                    <>
                                        <Button disabled={savingProject} onClick={() => setEditingProject(null)}>Cancel</Button>
                                        <Button variant="primary" busy={savingProject} onClick={() => void saveProjectChanges()}>{savingProject ? "Saving" : "Save changes"}</Button>
                                    </>
                                }
                            >
                                <div className="field"><label className="field__label" htmlFor={`${formId}-edit-name`}>Project name</label><input id={`${formId}-edit-name`} className="input" value={editForm.name} onChange={event => setEditForm(current => ({ ...current, name: event.target.value }))} /></div>
                                <div className="field"><label className="field__label" htmlFor={`${formId}-edit-description`}>Description</label><textarea id={`${formId}-edit-description`} className="input" rows={3} value={editForm.description} onChange={event => setEditForm(current => ({ ...current, description: event.target.value }))} /></div>
                                <div className="project-form-row">
                                    <div className="field"><label className="field__label" htmlFor={`${formId}-edit-status`}>Status</label><select id={`${formId}-edit-status`} className="input" value={editForm.status} onChange={event => setEditForm(current => ({ ...current, status: event.target.value }))}><option value="active">Active</option><option value="paused">Paused</option><option value="completed">Completed</option><option value="archived">Archived</option></select></div>
                                    <div className="field"><label className="field__label" htmlFor={`${formId}-edit-engine`}>Engine</label><select id={`${formId}-edit-engine`} className="input" value={editForm.engine} onChange={event => setEditForm(current => ({ ...current, engine: event.target.value }))}><option value="">Not set</option><option value="forge">Forge</option><option value="learn">Learn</option><option value="research">Research</option><option value="explore">Explore</option><option value="solve">Solve</option></select></div>
                                </div>
                                <div className="field"><label className="field__label" htmlFor={`${formId}-edit-stack`}>Technology stack</label><input id={`${formId}-edit-stack`} className="input" value={editForm.tech_stack} onChange={event => setEditForm(current => ({ ...current, tech_stack: event.target.value }))} /></div>
                                {projectsError && <Notice tone="error">{projectsError}</Notice>}
                            </Modal>
                        )}

                        {projectToDelete && (
                            <Modal
                                key="delete"
                                title={`Delete "${projectToDelete.name}"?`}
                                description="This removes the project from your account. It cannot be undone."
                                onClose={() => {
                                    if (deletingProjectId === null) setProjectToDelete(null);
                                }}
                                actions={
                                    <>
                                        <Button disabled={deletingProjectId !== null} onClick={() => setProjectToDelete(null)}>Keep project</Button>
                                        <Button variant="danger" busy={deletingProjectId !== null} onClick={() => void deleteProject(projectToDelete)}>{deletingProjectId !== null ? "Deleting" : "Delete project"}</Button>
                                    </>
                                }
                            />
                        )}
                    </AnimatePresence>
                </section>
            ) : showProjectForm ? (
                <div className="section project-creation-panel panel panel--lit">
                    {createdProject ? (
                        <>
                            <div className="project-success">
                                <WolfHead size={64} mood="success" />

                                <div>
                                    <p className="label project-success__label">
                                        <Check size={13} aria-hidden="true" />
                                        Project created
                                    </p>
                                    <h2>{createdProject.name}</h2>
                                    <p>Saved to your account. LATZ will keep its context between conversations.</p>
                                </div>
                            </div>

                            <dl className="project-card__meta project-summary">
                                <div><dt>Status</dt><dd>{createdProject.status}</dd></div>
                                <div><dt>Engine</dt><dd>{createdProject.engine || "Not set"}</dd></div>
                                <div><dt>Stack</dt><dd>{createdProject.tech_stack || "Not specified"}</dd></div>
                            </dl>

                            <div className="project-form-actions">
                                <Button onClick={closeProjectForm}>
                                    {mode === "projects" ? "Back to projects" : "Back to Forge"}
                                </Button>
                                <Button variant="primary" onClick={continueWithLatz}>
                                    Continue with LATZ
                                    <ArrowRight size={15} aria-hidden="true" />
                                </Button>
                            </div>
                        </>
                    ) : (
                        <form
                            className="project-form"
                            onSubmit={(event) => {
                                event.preventDefault();
                                void createProject();
                            }}
                            noValidate
                        >
                            <div>
                                <h2 className="section-title">New project</h2>
                                <p className="section-note">Give LATZ enough context to set up your project workspace.</p>
                            </div>

                            <div className="field">
                                <label className="field__label" htmlFor={`${formId}-name`}>Project name</label>
                                <input
                                    id={`${formId}-name`}
                                    className="input"
                                    value={projectForm.name}
                                    onChange={(event) => updateProjectField("name", event.target.value)}
                                    placeholder="e.g. Smart IoT Security Platform"
                                />
                            </div>

                            <div className="field">
                                <label className="field__label" htmlFor={`${formId}-description`}>
                                    Description
                                    <span className="field__hint">Optional</span>
                                </label>
                                <textarea
                                    id={`${formId}-description`}
                                    className="input"
                                    value={projectForm.description}
                                    onChange={(event) => updateProjectField("description", event.target.value)}
                                    placeholder="What are you building?"
                                    rows={4}
                                />
                            </div>

                            <div className="field">
                                <label className="field__label" htmlFor={`${formId}-stack`}>
                                    Technology stack
                                    <span className="field__hint">Optional</span>
                                </label>
                                <input
                                    id={`${formId}-stack`}
                                    className="input"
                                    value={projectForm.tech_stack}
                                    onChange={(event) => updateProjectField("tech_stack", event.target.value)}
                                    placeholder="e.g. FastAPI, React, PostgreSQL, Groq"
                                />
                            </div>

                            {projectError && <Notice tone="error">{projectError}</Notice>}

                            <div className="project-form-actions">
                                <Button onClick={closeProjectForm} disabled={creatingProject}>
                                    Cancel
                                </Button>
                                <Button type="submit" variant="primary" busy={creatingProject}>
                                    {creatingProject ? "Creating" : "Create project"}
                                </Button>
                            </div>
                        </form>
                    )}
                </div>
            ) : (
                <ul className="section engineering-actions" aria-label={`${content.eyebrow} actions`}>
                    {content.actions.map((workflow) => (
                        <li key={workflow.action}>
                            <button
                                type="button"
                                className="engineering-action panel panel--interactive"
                                onClick={() => handleAction(workflow)}
                            >
                                <span className="engineering-action__icon" aria-hidden="true">
                                    <ModeIcon size={18} />
                                </span>
                                <span className="engineering-action__copy">
                                    <strong>{workflow.label}</strong>
                                    <small>
                                        {workflow.action === "create_project"
                                            ? "Save a project to your workspace"
                                            : "Opens a conversation with LATZ"}
                                    </small>
                                </span>
                                <ArrowRight size={17} aria-hidden="true" />
                            </button>
                        </li>
                    ))}
                </ul>
            )}

            {mode !== "projects" && !showProjectForm && <ModeProjects mode={mode} />}
        </section>
    );
}

/** Projects saved with this engineering mode, so each mode page leads somewhere real. */
function ModeProjects({ mode }: { mode: EngineeringModeId }) {
    const projects = useApiResource<Project[]>("/projects");
    const matching = (projects.data ?? []).filter((project) => project.engine === mode);

    if (!projects.data || matching.length === 0) {
        return null;
    }

    return (
        <section className="section mode-projects" aria-labelledby={`mode-projects-${mode}`}>
            <h2 className="section-title" id={`mode-projects-${mode}`}>
                Your {mode} projects
            </h2>
            <ul className="mode-projects__list">
                {matching.map((project) => (
                    <li key={project.id}>
                        <Link className="mode-projects__item panel panel--interactive" to={`/projects/${project.id}`}>
                            <strong>{project.name}</strong>
                            <span className="tag">{project.status}</span>
                        </Link>
                    </li>
                ))}
            </ul>
        </section>
    );
}
