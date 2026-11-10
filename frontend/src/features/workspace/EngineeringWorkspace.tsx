import { useEffect, useState } from "react";
import "./EngineeringWorkspace.css";
import { motion } from "framer-motion";

import type { WorkspaceAction } from "../../app/layouts/WorkspaceLayout";

import ExperimentsLab from "./ExperimentsLab";

export type WorkspaceWorkflow = {
    engine:
    | "forge"
    | "learn"
    | "research"
    | "explore"
    | "solve"
    | null;
    action: string;
    label: string;
    projectId?: number;
};

type EngineeringWorkspaceProps = {
    mode: WorkspaceAction;
    onBack: () => void;
    onAction: (workflow: WorkspaceWorkflow) => void;
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
    WorkspaceAction,
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

    experiment: {
        eyebrow: "EXPERIMENT",
        title: "Test an idea.",
        description:
            "Run controlled experiments with models, prompts, datasets, architectures, and engineering ideas.",
        actions: [
            {
                engine: null,
                action: "new_model_experiment",
                label: "New model experiment",
            },
            {
                engine: null,
                action: "prompt_experiment",
                label: "Prompt experiment",
            },
            {
                engine: null,
                action: "dataset_experiment",
                label: "Dataset experiment",
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
    onBack,
    onAction,
}: EngineeringWorkspaceProps) {
    const content = workspaceContent[mode];
    const [projects, setProjects] = useState<DashboardProject[]>([]);
    const [projectsLoading, setProjectsLoading] = useState(false);
    const [projectsError, setProjectsError] = useState("");
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
        const token = localStorage.getItem("access_token");
        if (!token) {
            setProjectsError("Please sign in again to load your projects.");
            return;
        }

        setProjectsLoading(true);
        setProjectsError("");
        try {
            const response = await fetch("http://127.0.0.1:8000/projects", {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (response.status === 401) {
                localStorage.removeItem("access_token");
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
        const token = localStorage.getItem("access_token");
        if (!token) {
            setProjectsError("Please sign in again.");
            return;
        }

        setSavingProject(true);
        setProjectsError("");
        try {
            const response = await fetch(`http://127.0.0.1:8000/projects/${editingProject.id}`, {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({
                    name: editForm.name.trim(),
                    description: editForm.description.trim() || null,
                    status: editForm.status,
                    engine: editForm.engine || null,
                    tech_stack: editForm.tech_stack.trim() || null,
                }),
            });
            if (response.status === 401) {
                localStorage.removeItem("access_token");
                window.location.reload();
                return;
            }
            if (!response.ok) throw new Error(`Request failed: ${response.status}`);
            const updated = await response.json() as DashboardProject;
            setProjects(current => current.map(item => item.id === updated.id ? updated : item));
            setEditingProject(null);
        } catch (error) {
            console.error("Project update failed:", error);
            setProjectsError("Could not update the project.");
        } finally {
            setSavingProject(false);
        }
    }

    async function deleteProject(project: DashboardProject) {
        if (!window.confirm(`Delete "${project.name}"? This cannot be undone.`)) return;
        const token = localStorage.getItem("access_token");
        if (!token) {
            setProjectsError("Please sign in again.");
            return;
        }

        setDeletingProjectId(project.id);
        setProjectsError("");
        try {
            const response = await fetch(`http://127.0.0.1:8000/projects/${project.id}`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` },
            });
            if (response.status === 401) {
                localStorage.removeItem("access_token");
                window.location.reload();
                return;
            }
            if (!response.ok) throw new Error(`Request failed: ${response.status}`);
            setProjects(current => current.filter(item => item.id !== project.id));
            if (editingProject?.id === project.id) setEditingProject(null);
        } catch (error) {
            console.error("Project deletion failed:", error);
            setProjectsError("Could not delete the project.");
        } finally {
            setDeletingProjectId(null);
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
            localStorage.getItem(
                "access_token",
            );

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
                "http://127.0.0.1:8000/projects",
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
                localStorage.removeItem(
                    "access_token",
                );

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

    if (mode === "experiment") {
        return <ExperimentsLab />;
    }

    return (
        <motion.section
            className="engineering-workspace"
            initial={{
                opacity: 0,
                y: 20,
            }}
            animate={{
                opacity: 1,
                y: 0,
            }}
            transition={{
                duration: 0.35,
            }}
        >
            <button
                type="button"
                className="workspace-back"
                onClick={onBack}
            >
                ← Mission Control
            </button>

            <div className="engineering-workspace-header">
                <span>{content.eyebrow}</span>

                <h1>{content.title}</h1>

                <p>{content.description}</p>
            </div>

            {mode === "projects" && !showProjectForm ? (
                <section className="project-dashboard">
                    <div className="project-dashboard-toolbar">
                        <div>
                            <span className="project-dashboard-eyebrow">YOUR WORKSPACE</span>
                            <h2>Saved projects <span>{projects.length}</span></h2>
                            <p>Manage your engineering work from one place.</p>
                        </div>
                        <button type="button" className="project-primary-button" onClick={() => handleAction({ engine: null, action: "create_project", label: "Create new project" })}>
                            + New project
                        </button>
                    </div>

                    {projectsError && <p className="project-dashboard-error">{projectsError}</p>}

                    {projectsLoading ? (
                        <div className="project-dashboard-empty">Loading your projects...</div>
                    ) : projects.length === 0 ? (
                        <div className="project-dashboard-empty">
                            <span>✦</span>
                            <h3>No projects yet</h3>
                            <p>Create your first project to start building with LATZ.</p>
                            <button type="button" className="project-primary-button" onClick={() => handleAction({ engine: null, action: "create_project", label: "Create new project" })}>Create a project</button>
                        </div>
                    ) : (
                        <div className="project-dashboard-grid">
                            {projects.map(project => (
                                <article className="project-dashboard-card" key={project.id}>
                                    <div className="project-dashboard-card-top">
                                        <span className="project-dashboard-icon">⌘</span>
                                        <span className={`project-status status-${project.status.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>{project.status}</span>
                                    </div>
                                    <h3>{project.name}</h3>
                                    <p className="project-dashboard-description">{project.description || "No description added yet."}</p>
                                    <div className="project-dashboard-metadata">
                                        <div><span>ENGINE</span><strong>{project.engine || "Not set"}</strong></div>
                                        <div><span>TECH STACK</span><strong>{project.tech_stack || "Not specified"}</strong></div>
                                        {project.updated_at && <div><span>UPDATED</span><strong>{new Date(project.updated_at).toLocaleDateString()}</strong></div>}
                                    </div>
                                    <div className="project-dashboard-actions">
                                        <button type="button" className="project-secondary-button" onClick={() => startEditing(project)}>Edit</button>
                                        <button type="button" className="project-primary-button" onClick={() => onAction({ engine: "forge", action: "design_architecture", label: `Continue building ${project.name}. Review the existing project and help me identify the next implementation step.`, projectId: project.id })}>Open with LATZ →</button>
                                        <button type="button" className="project-delete-button" disabled={deletingProjectId === project.id} onClick={() => void deleteProject(project)}>{deletingProjectId === project.id ? "Deleting..." : "Delete"}</button>
                                    </div>
                                </article>
                            ))}
                        </div>
                    )}

                    {editingProject && (
                        <div className="project-edit-overlay" role="presentation">
                            <section className="project-edit-modal" role="dialog" aria-modal="true" aria-labelledby="project-edit-title">
                                <div className="project-form-header">
                                    <span>PROJECT SETTINGS</span>
                                    <h2 id="project-edit-title">Edit project</h2>
                                    <p>Changes are saved to your account.</p>
                                </div>
                                <div className="project-form">
                                    <label><span>Project name</span><input value={editForm.name} onChange={event => setEditForm(current => ({ ...current, name: event.target.value }))} /></label>
                                    <label><span>Description</span><textarea rows={3} value={editForm.description} onChange={event => setEditForm(current => ({ ...current, description: event.target.value }))} /></label>
                                    <label><span>Status</span><select value={editForm.status} onChange={event => setEditForm(current => ({ ...current, status: event.target.value }))}><option value="active">Active</option><option value="paused">Paused</option><option value="completed">Completed</option><option value="archived">Archived</option></select></label>
                                    <label><span>Engine</span><select value={editForm.engine} onChange={event => setEditForm(current => ({ ...current, engine: event.target.value }))}><option value="">Not set</option><option value="forge">Forge</option><option value="learn">Learn</option><option value="research">Research</option><option value="explore">Explore</option><option value="solve">Solve</option></select></label>
                                    <label><span>Technology stack</span><input value={editForm.tech_stack} onChange={event => setEditForm(current => ({ ...current, tech_stack: event.target.value }))} /></label>
                                </div>
                                {projectsError && <p className="project-dashboard-error">{projectsError}</p>}
                                <div className="project-form-actions">
                                    <button type="button" className="project-secondary-button" disabled={savingProject} onClick={() => setEditingProject(null)}>Cancel</button>
                                    <button type="button" className="project-primary-button" disabled={savingProject} onClick={() => void saveProjectChanges()}>{savingProject ? "Saving..." : "Save changes"}</button>
                                </div>
                            </section>
                        </div>
                    )}
                </section>
            ) : showProjectForm ? (
                <motion.div
                    className="project-creation-panel"
                    initial={{
                        opacity: 0,
                        y: 15,
                    }}
                    animate={{
                        opacity: 1,
                        y: 0,
                    }}
                >
                    {createdProject ? (
                        <>
                            <div className="project-success">
                                <div className="project-success-icon">
                                    ✓
                                </div>

                                <div>
                                    <span>
                                        PROJECT CREATED
                                    </span>

                                    <h2>
                                        {
                                            createdProject.name
                                        }
                                    </h2>

                                    <p>
                                        Your project
                                        has been
                                        persisted
                                        to
                                        PostgreSQL.
                                    </p>
                                </div>
                            </div>

                            <div className="project-summary">
                                <div>
                                    <span>
                                        STATUS
                                    </span>
                                    <strong>
                                        {
                                            createdProject.status
                                        }
                                    </strong>
                                </div>

                                <div>
                                    <span>
                                        ENGINE
                                    </span>
                                    <strong>
                                        {createdProject.engine ||
                                            "—"}
                                    </strong>
                                </div>

                                <div>
                                    <span>
                                        STACK
                                    </span>
                                    <strong>
                                        {createdProject.tech_stack ||
                                            "Not specified"}
                                    </strong>
                                </div>
                            </div>

                            <div className="project-form-actions">
                                <button
                                    type="button"
                                    className="project-secondary-button"
                                    onClick={
                                        closeProjectForm
                                    }
                                >
                                    Back to Forge
                                </button>

                                <button
                                    type="button"
                                    className="project-primary-button"
                                    onClick={
                                        continueWithLatz
                                    }
                                >
                                    Continue with LATZ →
                                </button>
                            </div>
                        </>
                    ) : (
                        <>
                            <div className="project-form-header">
                                <span>
                                    NEW PROJECT
                                </span>

                                <h2>
                                    Start something real.
                                </h2>

                                <p>
                                    Give LATZ enough
                                    context to
                                    establish your
                                    project workspace.
                                </p>
                            </div>

                            <div className="project-form">
                                <label>
                                    <span>
                                        Project name
                                    </span>

                                    <input
                                        value={
                                            projectForm.name
                                        }
                                        onChange={(
                                            event,
                                        ) =>
                                            updateProjectField(
                                                "name",
                                                event
                                                    .target
                                                    .value,
                                            )
                                        }
                                        placeholder="e.g. Smart IoT Security Platform"
                                    />
                                </label>

                                <label>
                                    <span>
                                        Description
                                    </span>

                                    <textarea
                                        value={
                                            projectForm.description
                                        }
                                        onChange={(
                                            event,
                                        ) =>
                                            updateProjectField(
                                                "description",
                                                event
                                                    .target
                                                    .value,
                                            )
                                        }
                                        placeholder="What are you building?"
                                        rows={4}
                                    />
                                </label>

                                <label>
                                    <span>
                                        Technology stack
                                    </span>

                                    <input
                                        value={
                                            projectForm.tech_stack
                                        }
                                        onChange={(
                                            event,
                                        ) =>
                                            updateProjectField(
                                                "tech_stack",
                                                event
                                                    .target
                                                    .value,
                                            )
                                        }
                                        placeholder="e.g. FastAPI, React, PostgreSQL, Groq"
                                    />
                                </label>

                                {projectError && (
                                    <div className="project-error">
                                        {
                                            projectError
                                        }
                                    </div>
                                )}

                                <div className="project-form-actions">
                                    <button
                                        type="button"
                                        className="project-secondary-button"
                                        onClick={
                                            closeProjectForm
                                        }
                                        disabled={
                                            creatingProject
                                        }
                                    >
                                        Cancel
                                    </button>

                                    <button
                                        type="button"
                                        className="project-primary-button"
                                        onClick={
                                            createProject
                                        }
                                        disabled={
                                            creatingProject
                                        }
                                    >
                                        {creatingProject
                                            ? "Creating..."
                                            : "Create project →"}
                                    </button>
                                </div>
                            </div>
                        </>
                    )}
                </motion.div>
            ) : (
                <div className="engineering-workspace-grid">
                    {content.actions.map(
                        (
                            workflow,
                            index,
                        ) => (
                            <motion.button
                                type="button"
                                className="engineering-action-card"
                                key={workflow.action}
                                onClick={() =>
                                    handleAction(
                                        workflow,
                                    )
                                }
                                whileHover={{
                                    y: -5,
                                }}
                                whileTap={{
                                    scale: 0.98,
                                }}
                            >
                                <span>
                                    0{index + 1}
                                </span>

                                <h3>
                                    {
                                        workflow.label
                                    }
                                </h3>

                                <p>
                                    Start working with
                                    LATZ on this path.
                                </p>

                                <strong>
                                    →
                                </strong>
                            </motion.button>
                        ),
                    )}
                </div>
            )}
        </motion.section>
    );
}
