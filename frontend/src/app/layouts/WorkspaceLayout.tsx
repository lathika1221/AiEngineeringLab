import { useEffect, useState } from "react";

import "./WorkspaceLayout.css";

import MissionControl from "../../features/workspace/MissionControl";
import EngineeringWorkspace from "../../features/workspace/EngineeringWorkspace";
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

type View =
    | "mission"
    | "chat"
    | "workspace";

export default function WorkspaceLayout({
    onLogout,
}: WorkspaceLayoutProps) {
    const [view, setView] =
        useState<View>("mission");

    const [displayName, setDisplayName] =
        useState("User");

    const [workspaceAction, setWorkspaceAction] =
        useState<WorkspaceAction>("forge");

    const [workflowPrompt, setWorkflowPrompt] =
        useState<string | null>(null);

    useEffect(() => {
        async function loadProfile() {
            const token =
                localStorage.getItem(
                    "access_token",
                );

            if (!token) {
                return;
            }

            try {
                const response = await fetch(
                    "http://127.0.0.1:8000/users/profile",
                    {
                        headers: {
                            Authorization: `Bearer ${token}`,
                        },
                    },
                );

                if (!response.ok) {
                    return;
                }

                const profile =
                    await response.json();

                if (profile.display_name) {
                    setDisplayName(
                        profile.display_name,
                    );
                }
            } catch {
                setDisplayName("User");
            }
        }

        loadProfile();
    }, []);

    function openWorkspace(
        action: WorkspaceAction,
    ) {
        setWorkspaceAction(action);
        setWorkflowPrompt(null);
        setView("workspace");
    }

    function openChat() {
        setWorkflowPrompt(null);
        setView("chat");
    }

    function openWorkflow(
        action: string,
    ) {
        const prompt =
            `I want to use the ${workspaceAction} mode. ` +
            `Let's start with: ${action}.`;

        setWorkflowPrompt(prompt);
        setView("chat");
    }

    function openMission() {
        setWorkflowPrompt(null);
        setView("mission");
    }

    const workspaceTitle =
        workspaceAction.charAt(0).toUpperCase() +
        workspaceAction.slice(1);

    return (
        <div className="workspace-layout">
            <header className="topbar">
                <button
                    type="button"
                    className="brand-button"
                    onClick={openMission}
                >
                    <div className="brand-mark">
                        🐺
                    </div>

                    <div>
                        <div className="brand">
                            AIEngineeringLab
                        </div>

                        <div className="brand-subtitle">
                            {view === "chat"
                                ? "Chat with LATZ"
                                : view ===
                                    "workspace"
                                    ? workspaceTitle
                                    : "Mission Control"}
                        </div>
                    </div>
                </button>

                <div className="topbar-right">
                    <div className="connection-status">
                        <span />
                        Connected
                    </div>

                    <div className="profile">
                        👤 {displayName}
                    </div>

                    <button
                        type="button"
                        className="logout-button"
                        onClick={onLogout}
                    >
                        Sign out
                    </button>
                </div>
            </header>

            <main className="workspace">
                {view === "chat" ? (
                    <Chat
                        onLogout={onLogout}
                        initialWorkflow={
                            workflowPrompt
                        }
                    />
                ) : view === "workspace" ? (
                    <EngineeringWorkspace
                        mode={
                            workspaceAction
                        }
                        onBack={openMission}
                        onAction={
                            openWorkflow
                        }
                    />
                ) : (
                    <MissionControl
                        workspaceAction={
                            workspaceAction
                        }
                        onWorkspaceAction={
                            openWorkspace
                        }
                        onAskLatz={
                            openChat
                        }
                    />
                )}
            </main>

            <CommandBar />
        </div>
    );
}