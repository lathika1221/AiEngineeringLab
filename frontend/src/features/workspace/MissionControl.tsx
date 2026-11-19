import "./MissionControl.css";
import { Link, useNavigate } from "react-router-dom";
import { FlaskConical, MessagesSquare, Plus } from "lucide-react";
import { useSession } from "../../app/session/context";
import { useApiResource } from "../../shared/api/resources";
import type { Resource } from "../../shared/api/resources";
import WolfHead from "../../shared/brand/WolfHead";
import EngineeringCompass from "../../shared/components/EngineeringCompass";
import { usePageTitle } from "../../shared/hooks/usePageTitle";
import Button from "../../shared/ui/Button";
import Notice from "../../shared/ui/Notice";

type UserContext = {
    profile: {
        display_name: string | null;
        bio: string | null;
        timezone: string | null;
        onboarding_completed: string;
    } | null;
    life_roles: Array<{
        id: number;
        role: string;
        description: string | null;
        priority: number;
    }>;
    goals: Array<{
        id: number;
        title: string;
        description: string | null;
        category: string | null;
        priority: number;
        status: string;
        target_date: string | null;
    }>;
    memories: Array<{
        id: number;
        type: string;
        content: string;
    }>;
};

type ProjectSummary = {
    id: number;
    name: string;
    description: string | null;
    status: string;
    engine: string | null;
};

type ConversationSummary = {
    id: number;
    title: string;
    category: string;
    updated_at: string;
};

type Loadable<T> = { state: "loading" } | { state: "error" } | { state: "ready"; data: T };

const RECENT_LIMIT = 5;

function toLoadable<T>(resource: Resource<T>): Loadable<T> {
    if (resource.data !== undefined) {
        return { state: "ready", data: resource.data };
    }

    return resource.error ? { state: "error" } : { state: "loading" };
}

function formatDay(value: string): string {
    const date = new Date(value);

    return Number.isNaN(date.getTime())
        ? ""
        : date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function statusTag(status: string): string {
    const known = ["active", "paused", "completed"];
    const normalized = status.toLowerCase();

    return known.includes(normalized) ? `tag tag--${normalized}` : "tag";
}

export default function MissionControl() {
    const { displayName } = useSession();
    const navigate = useNavigate();

    usePageTitle("Mission Control");

    // Shared with chat and the project list, so moving between screens does not refetch.
    const context = toLoadable(useApiResource<UserContext>("/users/context"));
    const projects = toLoadable(useApiResource<ProjectSummary[]>("/projects"));
    const conversations = toLoadable(useApiResource<ConversationSummary[]>("/conversations"));

    const contextData = context.state === "ready" ? context.data : null;
    const roles = contextData?.life_roles ?? [];
    const openGoals = (contextData?.goals ?? []).filter((goal) => goal.status !== "completed");

    function count<T>(source: Loadable<T>, value: (data: T) => number): string {
        return source.state === "ready" ? String(value(source.data)) : "—";
    }

    const stats = [
        {
            label: "Projects",
            to: "/projects",
            value: count(projects, (data) => data.length),
            detail: "Saved in your workspace",
        },
        {
            label: "Conversations",
            to: "/chat",
            value: count(conversations, (data) => data.length),
            detail: "Chats with LATZ",
        },
        {
            label: "Open goals",
            to: "/goals",
            value: count(context, (data) => (data.goals ?? []).filter((goal) => goal.status !== "completed").length),
            detail: "Objectives in progress",
        },
        {
            label: "Memories",
            to: "/memories",
            value: count(context, (data) => (data.memories ?? []).length),
            detail: "Facts LATZ keeps about you",
        },
    ];

    const loading =
        context.state === "loading" || projects.state === "loading" || conversations.state === "loading";

    return (
        <section className="page mission-control">
            <div className="mission-hero panel panel--lit">
                <div className="mission-hero__copy">
                    <p className="label">Mission Control</p>
                    <h1 className="display mission-hero__title">Welcome back, {displayName}</h1>

                    {roles.length > 0 ? (
                        <ul className="mission-roles" aria-label="Your roles">
                            {roles.map((role) => (
                                <li className="tag" key={role.id}>
                                    {role.role}
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="mission-hero__lede">
                            Pick up a project, start a conversation, or choose an engineering mode.
                        </p>
                    )}

                    <div className="mission-hero__actions">
                        <Button variant="primary" onClick={() => navigate("/forge")}>
                            <Plus size={15} aria-hidden="true" />
                            New project
                        </Button>
                        <Button onClick={() => navigate("/chat")}>
                            <MessagesSquare size={15} aria-hidden="true" />
                            Ask LATZ
                        </Button>
                        <Button onClick={() => navigate("/experiments")}>
                            <FlaskConical size={15} aria-hidden="true" />
                            New experiment
                        </Button>
                    </div>
                </div>

                <div className="mission-hero__wolf" aria-hidden="true">
                    <span className="mission-hero__ring" />
                    <WolfHead size={148} halo depth mood={loading ? "thinking" : "idle"} />
                </div>
            </div>

            {context.state === "error" && (
                <div className="mission-notice">
                    <Notice tone="error">
                        LATZ couldn't load your workspace context. Check that the backend is running.
                    </Notice>
                </div>
            )}

            <dl className="mission-stats">
                {stats.map((stat) => (
                    <div className="mission-stat" key={stat.label}>
                        <dt>
                            <Link className="mission-stat__link" to={stat.to}>
                                {stat.label}
                            </Link>
                        </dt>
                        <dd>{stat.value}</dd>
                        <dd className="mission-stat__detail">{stat.detail}</dd>
                    </div>
                ))}
            </dl>

            <div className="mission-columns">
                <section className="section" aria-labelledby="mission-projects">
                    <div className="section-head">
                        <h2 className="section-title" id="mission-projects">
                            Projects
                        </h2>
                        <Button variant="ghost" size="sm" onClick={() => navigate("/projects")}>
                            View all
                        </Button>
                    </div>

                    {projects.state === "loading" ? (
                        <div className="mission-list mission-list--loading" aria-busy="true" />
                    ) : projects.state === "error" ? (
                        <Notice tone="error">Couldn't load your projects.</Notice>
                    ) : projects.data.length === 0 ? (
                        <div className="empty">
                            <h3>No projects yet</h3>
                            <p>Create a project so LATZ can keep its context between conversations.</p>
                            <Button variant="primary" size="sm" onClick={() => navigate("/forge")}>
                                Create a project
                            </Button>
                        </div>
                    ) : (
                        <ul className="mission-list">
                            {projects.data.slice(0, RECENT_LIMIT).map((project) => (
                                <li key={project.id}>
                                    <Link
                                        className="mission-row"
                                        to={`/chat?project=${project.id}`}
                                        title={`Open ${project.name} in chat`}
                                    >
                                        <span className="mission-row__main">
                                            <strong>{project.name}</strong>
                                            <small>{project.description || "No description yet"}</small>
                                        </span>
                                        <span className={statusTag(project.status)}>{project.status}</span>
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>

                <section className="section" aria-labelledby="mission-conversations">
                    <div className="section-head">
                        <h2 className="section-title" id="mission-conversations">
                            Recent conversations
                        </h2>
                        <Button variant="ghost" size="sm" onClick={() => navigate("/chat")}>
                            Open chat
                        </Button>
                    </div>

                    {conversations.state === "loading" ? (
                        <div className="mission-list mission-list--loading" aria-busy="true" />
                    ) : conversations.state === "error" ? (
                        <Notice tone="error">Couldn't load your conversations.</Notice>
                    ) : conversations.data.length === 0 ? (
                        <div className="empty">
                            <h3>No conversations yet</h3>
                            <p>Ask LATZ about something you're building, debugging or trying to understand.</p>
                            <Button variant="primary" size="sm" onClick={() => navigate("/chat")}>
                                Start a conversation
                            </Button>
                        </div>
                    ) : (
                        <ul className="mission-list">
                            {conversations.data.slice(0, RECENT_LIMIT).map((conversation) => (
                                <li key={conversation.id}>
                                    <Link className="mission-row" to={`/chat/${conversation.id}`}>
                                        <span className="mission-row__main">
                                            <strong>{conversation.title || "New Chat"}</strong>
                                            <small>{conversation.category}</small>
                                        </span>
                                        <time className="mission-row__time" dateTime={conversation.updated_at}>
                                            {formatDay(conversation.updated_at)}
                                        </time>
                                    </Link>
                                </li>
                            ))}
                        </ul>
                    )}
                </section>
            </div>

            {openGoals.length > 0 && (
                <section className="section" aria-labelledby="mission-goals">
                    <div className="section-head">
                        <h2 className="section-title" id="mission-goals">
                            Open goals
                        </h2>
                        <Button variant="ghost" size="sm" onClick={() => navigate("/goals")}>
                            View all
                        </Button>
                    </div>
                    <ul className="mission-list">
                        {openGoals.slice(0, RECENT_LIMIT).map((goal) => (
                            <li className="mission-row mission-row--static" key={goal.id}>
                                <span className="mission-row__main">
                                    <strong>{goal.title}</strong>
                                    {goal.description && <small>{goal.description}</small>}
                                </span>
                                {goal.target_date && (
                                    <time className="mission-row__time" dateTime={goal.target_date}>
                                        Due {formatDay(goal.target_date)}
                                    </time>
                                )}
                            </li>
                        ))}
                    </ul>
                </section>
            )}

            <section className="section" aria-labelledby="mission-modes">
                <div className="section-head">
                    <h2 className="section-title" id="mission-modes">
                        Engineering modes
                    </h2>
                    <p className="section-note">Choose the kind of work. LATZ adapts to it.</p>
                </div>

                <EngineeringCompass />
            </section>
        </section>
    );
}
