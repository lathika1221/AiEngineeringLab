import { Suspense, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
    FlaskConical,
    FolderKanban,
    House,
    LogOut,
    Brain,
    Menu,
    MessagesSquare,
    Moon,
    Search,
    Settings,
    Target,
    Sun,
    UserRound,
    X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import "./WorkspaceLayout.css";
import { useSession } from "../session/context";
import AccountMenu from "../../features/account/AccountMenu";
import { queueWorkflow } from "../workflow";
import { API_BASE } from "../../shared/api/client";
import { useApiResource } from "../../shared/api/resources";
import type { Conversation, Project } from "../../shared/api/types";
import { useBackendStatus } from "../../shared/api/useBackendStatus";
import WolfHead from "../../shared/brand/WolfHead";
import Wordmark from "../../shared/brand/Wordmark";
import ErrorBoundary from "../../shared/ui/ErrorBoundary";
import CommandBar from "../../shared/components/CommandBar";
import type { Command } from "../../shared/components/CommandBar";
import { engineeringModes } from "../../shared/config/engineeringModes";
import { toggleTheme, useTheme } from "../../shared/theme/theme";

type NavigationItem = {
    id: string;
    label: string;
    hint: string;
    icon: LucideIcon;
    to: string;
};

const STATUS_LABEL = {
    checking: "Checking",
    online: "Connected",
    offline: "Offline",
} as const;

const STATUS_CLASS = {
    checking: "status--busy",
    online: "status--ok",
    offline: "status--error",
} as const;

const PRIMARY_ITEMS: NavigationItem[] = [
    { id: "mission", label: "Mission Control", hint: "Overview", icon: House, to: "/mission-control" },
    { id: "chat", label: "LATZ Chat", hint: "Conversations", icon: MessagesSquare, to: "/chat" },
    { id: "projects", label: "Projects", hint: "Saved work", icon: FolderKanban, to: "/projects" },
    { id: "goals", label: "Goals", hint: "Objectives", icon: Target, to: "/goals" },
    { id: "memories", label: "Memories", hint: "What LATZ knows", icon: Brain, to: "/memories" },
    { id: "experiments", label: "Experiments", hint: "Lab", icon: FlaskConical, to: "/experiments" },
];

const MODE_ITEMS: NavigationItem[] = engineeringModes.map((mode) => ({
    id: mode.id,
    label: mode.title,
    hint: "Engineering mode",
    icon: mode.icon,
    to: `/${mode.id}`,
}));

const ALL_ITEMS = [...PRIMARY_ITEMS, ...MODE_ITEMS];

/** Pages reached from the account menu rather than the sidebar. */
const ACCOUNT_ITEMS: NavigationItem[] = [
    { id: "profile", label: "My Profile", hint: "Account", icon: UserRound, to: "/profile" },
    { id: "settings", label: "Account Settings", hint: "Account", icon: Settings, to: "/settings" },
];

/** The workspace shell: sidebar, header and command bar around the current route's page. */
export default function WorkspaceLayout() {
    const { logout } = useSession();
    const navigate = useNavigate();
    const location = useLocation();
    const [menuOpenAt, setMenuOpenAt] = useState<string | null>(null);
    const [commandBarOpen, setCommandBarOpen] = useState(false);

    const theme = useTheme();
    const backendStatus = useBackendStatus();

    // The mobile drawer is open only for the page it was opened on, so any navigation closes it.
    const menuOpen = menuOpenAt === location.key;
    const section = location.pathname.split("/")[1] ?? "";
    const isChat = section === "chat";

    useEffect(() => {
        function handleShortcut(event: KeyboardEvent) {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                setCommandBarOpen((open) => !open);
            }
        }

        window.addEventListener("keydown", handleShortcut);
        return () => window.removeEventListener("keydown", handleShortcut);
    }, []);

    const activeItem = [...ALL_ITEMS, ...ACCOUNT_ITEMS].find((item) => item.to === `/${section}`);
    const currentTitle = activeItem?.label ?? "LATZ";
    const ThemeIcon = theme === "dark" ? Sun : Moon;
    const themeLabel = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";

    const projectList = useApiResource<Project[]>(commandBarOpen ? "/projects" : null);
    const conversationList = useApiResource<Conversation[]>(commandBarOpen ? "/conversations" : null);

    const commands: Command[] = [
        ...[...ALL_ITEMS, ...ACCOUNT_ITEMS].map((item) => ({
            id: item.id,
            label: `Go to ${item.label}`,
            hint: item.hint,
            icon: item.icon,
            run: () => navigate(item.to),
        })),
        ...(projectList.data ?? []).map((project) => ({
            id: `project-${project.id}`,
            label: `Project: ${project.name}`,
            hint: "Open details",
            icon: FolderKanban,
            searchOnly: true,
            run: () => navigate(`/projects/${project.id}`),
        })),
        ...(conversationList.data ?? []).map((conversation) => ({
            id: `conversation-${conversation.id}`,
            label: `Chat: ${conversation.title}`,
            hint: "Open conversation",
            icon: MessagesSquare,
            searchOnly: true,
            run: () => navigate(`/chat/${conversation.id}`),
        })),
        {
            id: "theme",
            label: themeLabel,
            hint: "Appearance",
            icon: ThemeIcon,
            run: toggleTheme,
        },
        {
            id: "sign-out",
            label: "Sign out",
            hint: "Account",
            icon: LogOut,
            run: logout,
        },
    ];

    function renderNavItem(item: NavigationItem) {
        const Icon = item.icon;

        return (
            <NavLink
                key={item.id}
                to={item.to}
                className={({ isActive }) => `sidebar-nav-item${isActive ? " active" : ""}`}
            >
                <Icon size={17} aria-hidden="true" />
                <span>{item.label}</span>
            </NavLink>
        );
    }

    return (
        <div className="workspace-layout">
            <a className="skip-link" href="#main-content">
                Skip to content
            </a>
            <aside
                className={`app-sidebar${menuOpen ? " open" : ""}`}
                data-theme="dark"
                aria-label="Workspace"
            >
                <div className="sidebar-top">
                    <NavLink
                        className="sidebar-brand"
                        to="/mission-control"
                        aria-label="LATZ AI Engineering Lab, go to Mission Control"
                    >
                        <Wordmark descriptor mood={backendStatus === "offline" ? "offline" : "idle"} />
                    </NavLink>
                    <button
                        type="button"
                        className="icon-btn sidebar-close"
                        onClick={() => setMenuOpenAt(null)}
                        aria-label="Close menu"
                    >
                        <X size={17} />
                    </button>
                </div>

                <nav className="sidebar-navigation" aria-label="Main navigation">
                    <div className="sidebar-section-label">Workspace</div>
                    {PRIMARY_ITEMS.map(renderNavItem)}

                    <div className="sidebar-section-label">Engineering modes</div>
                    {MODE_ITEMS.map(renderNavItem)}
                </nav>

                <div className="sidebar-user">
                    <AccountMenu variant="sidebar" />
                </div>
            </aside>

            {menuOpen && (
                <button
                    type="button"
                    className="sidebar-scrim"
                    aria-label="Close menu"
                    onClick={() => setMenuOpenAt(null)}
                />
            )}

            <div className="workspace-main">
                <header className="workspace-topbar">
                    <button
                        type="button"
                        className="icon-btn topbar-menu"
                        onClick={() => setMenuOpenAt(location.key)}
                        aria-label="Open menu"
                    >
                        <Menu size={18} />
                    </button>

                    <p className="topbar-title display">{currentTitle}</p>

                    <div className="topbar-actions">
                        <button
                            type="button"
                            className="command-trigger"
                            onClick={() => setCommandBarOpen(true)}
                        >
                            <Search size={15} aria-hidden="true" />
                            <span>Search or ask LATZ</span>
                            <kbd>Ctrl K</kbd>
                        </button>

                        <span
                            className={`status ${STATUS_CLASS[backendStatus]} topbar-status`}
                            role="status"
                            title={`Backend: ${API_BASE}`}
                        >
                            <span className="status__dot" />
                            {STATUS_LABEL[backendStatus]}
                        </span>

                        <button
                            type="button"
                            className="icon-btn"
                            onClick={toggleTheme}
                            aria-label={themeLabel}
                            title={themeLabel}
                        >
                            <ThemeIcon size={17} />
                        </button>

                        <AccountMenu variant="header" />
                    </div>
                </header>

                <main id="main-content" tabIndex={-1} className={`workspace-content${isChat ? " workspace-view-chat" : ""}`}>
                    {/* Keyed by section, so /chat → /chat/42 keeps the chat mounted. */}
                    <motion.div
                        key={section}
                        className="workspace-page"
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                    >
                        <ErrorBoundary key={section}>
                            <Suspense
                                fallback={
                                    <div className="page-loading" role="status">
                                        <WolfHead size={48} mood="thinking" />
                                        <span className="visually-hidden">Loading</span>
                                    </div>
                                }
                            >
                                <Outlet />
                            </Suspense>
                        </ErrorBoundary>
                    </motion.div>
                </main>
            </div>

            <AnimatePresence>
                {commandBarOpen && (
                    <CommandBar
                        commands={commands}
                        onClose={() => setCommandBarOpen(false)}
                        onAsk={(question) =>
                            navigate(
                                queueWorkflow({
                                    engine: null,
                                    action: "",
                                    label: question,
                                    fresh: true,
                                }),
                            )
                        }
                    />
                )}
            </AnimatePresence>
        </div>
    );
}
