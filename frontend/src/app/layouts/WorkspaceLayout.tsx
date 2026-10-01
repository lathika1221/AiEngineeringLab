import { useEffect, useState } from "react";

import "./WorkspaceLayout.css";

import MissionControl from "../../features/workspace/MissionControl";
import Chat from "../../features/chat/Chat";
import CommandBar from "../../shared/components/CommandBar";

type WorkspaceLayoutProps = {
    onLogout: () => void;
};

export default function WorkspaceLayout({
    onLogout,
}: WorkspaceLayoutProps) {
    const [view, setView] =
        useState<"mission" | "chat">("mission");

    const [displayName, setDisplayName] =
        useState("User");

    useEffect(() => {
        async function loadProfile() {
            const token =
                localStorage.getItem("access_token");

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

    return (
        <div className="workspace-layout">
            <header className="topbar">
                <button
                    className="brand-button"
                    onClick={() =>
                        setView("mission")
                    }
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
                    />
                ) : (
                    <MissionControl
                        onAskLatz={() =>
                            setView("chat")
                        }
                    />
                )}
            </main>

            <CommandBar />
        </div>
    );
}