import { useEffect, useState } from "react";
import "./WorkspaceLayout.css";
import MissionControl from "../../features/workspace/MissionControl";
import EngineeringWorkspace from "../../features/workspace/EngineeringWorkspace";
import type { WorkspaceWorkflow } from "../../features/workspace/EngineeringWorkspace";
import Chat from "../../features/chat/Chat";
import CommandBar from "../../shared/components/CommandBar";

type WorkspaceLayoutProps = {
    onLogout: () => void;
};

export type WorkspaceAction =
    | "forge"
    | "learn"
    | "research"
    | "explore"
    | "solve"
    | "projects"
    | "experiment";

type View = "mission" | "chat" | "workspace";

type NavigationItem = {
    label: string;
    description: string;
    icon: string;
    onClick: () => void;
    active: boolean;
};

export default function WorkspaceLayout({ onLogout }: WorkspaceLayoutProps) {
    const [view, setView] = useState<View>("mission");
    const [displayName, setDisplayName] = useState("User");
    const [workspaceAction, setWorkspaceAction] = useState<WorkspaceAction>("forge");
    const [workflow, setWorkflow] = useState<WorkspaceWorkflow | null>(null);

    useEffect(() => {
        async function loadProfile() {
            const token = localStorage.getItem("access_token");

            if (!token) return;

            try {
                const response = await fetch("http://127.0.0.1:8000/users/profile", {
                    headers: { Authorization: `Bearer ${token}` },
                });

                if (!response.ok) return;

                const profile = await response.json();

                if (profile.display_name) {
                    setDisplayName(profile.display_name);
                }
            } catch {
                setDisplayName("User");
            }
        }

        loadProfile();
    }, []);

    function openWorkspace(action: WorkspaceAction) {
        setWorkspaceAction(action);
        setWorkflow(null);
        setView("workspace");
    }

    function openChat() {
        setWorkflow(null);
        setView("chat");
    }

    function openWorkflow(selectedWorkflow: WorkspaceWorkflow) {
        setWorkflow(selectedWorkflow);
        setView("chat");
    }

    function openSavedProject(project: { id: number; name: string }) {
        setWorkflow({
            engine: "forge",
            action: "design_architecture",
            label: `Let's continue working on ${project.name}. Use the saved project context and help me identify the next implementation step.`,
            projectId: project.id,
        });
        setView("chat");
    }

    useEffect(() => {
        function handleExperimentsBack() {
            setWorkflow(null);
            setView("mission");
        }

        window.addEventListener("latz:experiments-back", handleExperimentsBack);
        return () => window.removeEventListener("latz:experiments-back", handleExperimentsBack);
    }, []);
    function openMission() {
        setWorkflow(null);
        setView("mission");
    }

    const workspaceTitle =
        workspaceAction.charAt(0).toUpperCase() + workspaceAction.slice(1);

    const navigationItems: NavigationItem[] = [
        {
            label: "Mission Control",
            description: "Your overview",
            icon: "⌂",
            onClick: openMission,
            active: view === "mission",
        },
        {
            label: "Chat with LATZ",
            description: "Think it through",
            icon: "◌",
            onClick: openChat,
            active: view === "chat",
        },
        {
            label: "Build workspace",
            description: "Design and develop",
            icon: "⌘",
            onClick: () => openWorkspace("forge"),
            active: view === "workspace" && workspaceAction === "forge",
        },
        {
            label: "Projects",
            description: "Your project space",
            icon: "▧",
            onClick: () => openWorkspace("projects"),
            active: view === "workspace" && workspaceAction === "projects",
        },
        {
            label: "Experiments",
            description: "Test new ideas",
            icon: "⌬",
            onClick: () => openWorkspace("experiment"),
            active: view === "workspace" && workspaceAction === "experiment",
        },
    ];

    const currentTitle =
        view === "chat"
            ? "Chat with LATZ"
            : view === "workspace"
              ? workspaceTitle
              : "Mission Control";

    return (
        <div className="workspace-layout">
            <aside className="app-sidebar">
                <button
                    type="button"
                    className="sidebar-brand"
                    onClick={openMission}
                    aria-label="Go to Mission Control"
                >
                    <span className="sidebar-brand-mark">🐺</span>
                    <span className="sidebar-brand-copy">
                        <strong>AIEngineeringLab</strong>
                        <small>YOUR ENGINEERING SPACE</small>
                    </span>
                </button>

                <div className="sidebar-section-label">WORKSPACE</div>

                <nav className="sidebar-navigation" aria-label="Main navigation">
                    {navigationItems.map((item) => (
                        <button
                            key={item.label}
                            type="button"
                            className={`sidebar-nav-item${item.active ? " active" : ""}`}
                            onClick={item.onClick}
                            aria-current={item.active ? "page" : undefined}
                        >
                            <span className="sidebar-nav-icon" aria-hidden="true">
                                {item.icon}
                            </span>
                            <span className="sidebar-nav-copy">
                                <strong>{item.label}</strong>
                                <small>{item.description}</small>
                            </span>
                            {item.active && <span className="sidebar-active-indicator" />}
                        </button>
                    ))}
                </nav>

                <div className="sidebar-bottom">
                    <div className="sidebar-status-card">
                        <span className="sidebar-status-icon">✦</span>
                        <div>
                            <strong>LATZ is ready</strong>
                            <p>Your engineering companion</p>
                        </div>
                        <span className="status-dot" />
                    </div>

                    <div className="sidebar-user">
                        <span className="sidebar-avatar" aria-hidden="true">
                            {displayName.trim().charAt(0).toUpperCase() || "U"}
                        </span>
                        <span className="sidebar-user-copy">
                            <strong>{displayName}</strong>
                            <small>Personal workspace</small>
                        </span>
                        <button
                            type="button"
                            className="sidebar-signout"
                            onClick={onLogout}
                            aria-label="Sign out"
                            title="Sign out"
                        >
                            ↗
                        </button>
                    </div>
                </div>
            </aside>

            <div className="workspace-main">
                <header className="workspace-topbar">
                    <div className="topbar-page">
                        <span className="topbar-breadcrumb">LATZ</span>
                        <span className="topbar-separator">/</span>
                        <h1>{currentTitle}</h1>
                    </div>

                    <div className="topbar-actions">
                        <div className="connection-status">
                            <span />
                            Connected
                        </div>
                        <div className="topbar-profile">
                            <span className="topbar-profile-avatar" aria-hidden="true">
                                {displayName.trim().charAt(0).toUpperCase() || "U"}
                            </span>
                            <span>{displayName}</span>
                        </div>
                        <button
                            type="button"
                            className="topbar-signout"
                            onClick={onLogout}
                        >
                            Sign out
                        </button>
                    </div>
                </header>

                <main className={`workspace-content workspace-view-${view}`}>
                    {view === "chat" ? (
                        <Chat
                            onLogout={onLogout}
                            initialWorkflow={workflow}
                            projectId={workflow?.projectId ?? null}
                            onOpenProject={openSavedProject}
                        />
                    ) : view === "workspace" ? (
                        <EngineeringWorkspace
                            mode={workspaceAction}
                            onBack={openMission}
                            onAction={openWorkflow}
                        />
                    ) : (
                        <MissionControl
                            workspaceAction={workspaceAction}
                            onWorkspaceAction={openWorkspace}
                            onAskLatz={openChat}
                        />
                    )}
                </main>

                {view !== "chat" && <CommandBar />}
            </div>
        </div>
    );
}
