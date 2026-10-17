
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./Chat.css";
import type { WorkspaceWorkflow } from "../workspace/EngineeringWorkspace";

type Message = {
    role: "user" | "assistant";
    content: string;
};

type ChatHistoryItem = {
    id: number;
    user_message: string;
    ai_response: string;
    created_at: string;
};

type ConversationCategory =
    | "projects"
    | "learning"
    | "experiments"
    | "research"
    | "general";

type Conversation = {
    id: number;
    title: string;
    category: ConversationCategory;
    project_id: number | null;
    created_at: string;
    updated_at: string;
};

type MemoryCandidate = {
    memory_type: string;
    content: string;
    memory_key: string;
};

type ChatProps = {
    onLogout?: () => void;
    initialWorkflow?: WorkspaceWorkflow | null;
    projectId?: number | null;
};

const API_URL = "http://127.0.0.1:8000";

const INITIAL_MESSAGE: Message = {
    role: "assistant",
    content:
        "I'm LATZ. Tell me what you're building, debugging, researching, or trying to understand.",
};

const CATEGORIES: {
    label: string;
    value: ConversationCategory | "all";
}[] = [
        { label: "All chats", value: "all" },
        { label: "Projects", value: "projects" },
        { label: "Learning", value: "learning" },
        { label: "Experiments", value: "experiments" },
        { label: "Research", value: "research" },
        { label: "General", value: "general" },
    ];

export default function Chat({
    onLogout,
    initialWorkflow,
    projectId = null,
}: ChatProps) {
    const [messages, setMessages] = useState<Message[]>([
        INITIAL_MESSAGE,
    ]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [historyLoading, setHistoryLoading] = useState(true);
    const [conversationsLoading, setConversationsLoading] =
        useState(true);
    const [conversations, setConversations] = useState<Conversation[]>(
        [],
    );
    const [activeConversationId, setActiveConversationId] =
        useState<number | null>(null);
    const [categoryFilter, setCategoryFilter] = useState<
        ConversationCategory | "all"
    >("all");
    const [memoryCandidate, setMemoryCandidate] =
        useState<MemoryCandidate | null>(null);
    const [workflowStarted, setWorkflowStarted] = useState(false);
    const [activeWorkflow, setActiveWorkflow] =
        useState<WorkspaceWorkflow | null>(initialWorkflow ?? null);
    const [sidebarError, setSidebarError] = useState("");

    const activeConversation = conversations.find(
        (conversation) => conversation.id === activeConversationId,
    );

    const filteredConversations = conversations.filter(
        (conversation) =>
            categoryFilter === "all" ||
            conversation.category === categoryFilter,
    );

    function handleUnauthorized() {
        localStorage.removeItem("access_token");

        if (onLogout) {
            onLogout();
        } else {
            window.location.reload();
        }
    }

    async function refreshConversations(token: string) {
        const params = new URLSearchParams();

        if (projectId !== null && projectId !== undefined) {
            params.set("project_id", String(projectId));
        }

        const query = params.toString();
        const url = query
            ? `${API_URL}/conversations?${query}`
            : `${API_URL}/conversations`;

        const response = await fetch(url, {
            headers: {
                Authorization: `Bearer ${token}`,
            },
        });

        if (response.status === 401) {
            handleUnauthorized();
            throw new Error("Authentication required.");
        }

        if (!response.ok) {
            throw new Error(
                `Conversation list failed: ${response.status}`,
            );
        }

        const data: Conversation[] = await response.json();
        setConversations(data);
        return data;
    }

    async function createConversation(
        token: string,
    ): Promise<Conversation> {
        const category: ConversationCategory =
            categoryFilter === "all" ? "general" : categoryFilter;

        const response = await fetch(`${API_URL}/conversations`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
                title: "New Chat",
                category,
                ...(projectId !== null && projectId !== undefined
                    ? { project_id: projectId }
                    : {}),
            }),
        });

        if (response.status === 401) {
            handleUnauthorized();
            throw new Error("Authentication required.");
        }

        if (!response.ok) {
            const detail = await response.text();
            throw new Error(
                `Could not create conversation: ${response.status} ${detail}`,
            );
        }

        const conversation: Conversation = await response.json();

        setConversations((current) => [
            conversation,
            ...current.filter((item) => item.id !== conversation.id),
        ]);

        setActiveConversationId(conversation.id);
        setMessages([INITIAL_MESSAGE]);
        setMemoryCandidate(null);
        setSidebarError("");

        return conversation;
    }

    async function checkMemoryCandidate(
        message: string,
        token: string,
    ) {
        try {
            const response = await fetch(
                `${API_URL}/ai/memory-candidate`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify({ message }),
                },
            );

            if (response.status === 401) {
                handleUnauthorized();
                return;
            }

            if (!response.ok) {
                return;
            }

            const data = await response.json();

            if (data.candidate && !data.duplicate) {
                setMemoryCandidate({
                    memory_type: data.candidate.memory_type,
                    content: data.candidate.content,
                    memory_key: data.candidate.memory_key,
                });
            }
        } catch (error) {
            console.error("Memory candidate check failed:", error);
        }
    }

    async function saveMemory() {
        if (!memoryCandidate) {
            return;
        }

        try {
            const token = localStorage.getItem("access_token");

            if (!token) {
                handleUnauthorized();
                return;
            }

            const response = await fetch(
                `${API_URL}/ai/memory-confirm`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        memory_type: memoryCandidate.memory_type,
                        content: memoryCandidate.content,
                    }),
                },
            );

            if (response.status === 401) {
                handleUnauthorized();
                return;
            }

            if (!response.ok) {
                throw new Error(
                    `Memory save failed: ${response.status}`,
                );
            }

            const data = await response.json();

            if (data.saved || data.duplicate) {
                setMemoryCandidate(null);
            }
        } catch (error) {
            console.error("Memory save failed:", error);
        }
    }

    function dismissMemory() {
        setMemoryCandidate(null);
    }

    async function handleNewChat() {
        if (loading) {
            return;
        }

        const token = localStorage.getItem("access_token");

        if (!token) {
            handleUnauthorized();
            return;
        }

        setHistoryLoading(true);
        setSidebarError("");
        setWorkflowStarted(true);
        setActiveWorkflow(null);
        setInput("");

        try {
            await createConversation(token);
        } catch (error) {
            console.error(error);
            setSidebarError(
                "Couldn't create a chat. Check that the backend is running.",
            );
        } finally {
            setHistoryLoading(false);
        }
    }

    function selectConversation(conversation: Conversation) {
        if (loading || conversation.id === activeConversationId) {
            return;
        }

        setWorkflowStarted(true);
        setActiveWorkflow(null);
        setMemoryCandidate(null);
        setActiveConversationId(conversation.id);
    }

    useEffect(() => {
        let cancelled = false;

        async function loadConversations() {
            setConversationsLoading(true);
            setHistoryLoading(true);
            setSidebarError("");

            const token = localStorage.getItem("access_token");

            if (!token) {
                handleUnauthorized();
                return;
            }

            try {
                const params = new URLSearchParams();

                if (projectId !== null && projectId !== undefined) {
                    params.set("project_id", String(projectId));
                }

                const query = params.toString();
                const url = query
                    ? `${API_URL}/conversations?${query}`
                    : `${API_URL}/conversations`;

                const response = await fetch(url, {
                    headers: {
                        Authorization: `Bearer ${token}`,
                    },
                });

                if (response.status === 401) {
                    handleUnauthorized();
                    return;
                }

                if (!response.ok) {
                    throw new Error(
                        `Conversation list failed: ${response.status}`,
                    );
                }

                const data: Conversation[] = await response.json();

                if (cancelled) {
                    return;
                }

                setConversations(data);

                setActiveConversationId((currentId) => {
                    if (
                        currentId !== null &&
                        data.some((item) => item.id === currentId)
                    ) {
                        return currentId;
                    }

                    return data.length > 0 ? data[0].id : null;
                });
            } catch (error) {
                console.error("Conversations failed to load:", error);

                if (!cancelled) {
                    setSidebarError(
                        "Couldn't load saved conversations.",
                    );
                    setConversations([]);
                    setActiveConversationId(null);
                }
            } finally {
                if (!cancelled) {
                    setConversationsLoading(false);
                }
            }
        }

        void loadConversations();

        return () => {
            cancelled = true;
        };
    }, [projectId]);

    useEffect(() => {
        let cancelled = false;

        async function loadHistory() {
            setHistoryLoading(true);
            setMessages([]);
            setMemoryCandidate(null);

            const token = localStorage.getItem("access_token");

            if (!token) {
                handleUnauthorized();
                return;
            }

            try {
                const params = new URLSearchParams();

                if (activeConversationId !== null) {
                    params.set(
                        "conversation_id",
                        String(activeConversationId),
                    );
                } else if (
                    projectId !== null &&
                    projectId !== undefined
                ) {
                    params.set("project_id", String(projectId));
                }

                const query = params.toString();
                const url = query
                    ? `${API_URL}/ai/history?${query}`
                    : `${API_URL}/ai/history`;

                const response = await fetch(url, {
                    headers: {
                        Authorization: `Bearer ${token}`,
                    },
                });

                if (response.status === 401) {
                    handleUnauthorized();
                    return;
                }

                if (!response.ok) {
                    throw new Error(
                        `History request failed: ${response.status}`,
                    );
                }

                const history: ChatHistoryItem[] =
                    await response.json();

                if (cancelled) {
                    return;
                }

                const restoredMessages: Message[] = [];

                for (const item of history) {
                    restoredMessages.push(
                        {
                            role: "user",
                            content: item.user_message,
                        },
                        {
                            role: "assistant",
                            content: item.ai_response,
                        },
                    );
                }

                setMessages(
                    restoredMessages.length > 0
                        ? restoredMessages
                        : [INITIAL_MESSAGE],
                );
            } catch (error) {
                console.error("Chat history failed to load:", error);

                if (!cancelled) {
                    setMessages([INITIAL_MESSAGE]);
                }
            } finally {
                if (!cancelled) {
                    setHistoryLoading(false);
                }
            }
        }

        void loadHistory();

        return () => {
            cancelled = true;
        };
    }, [activeConversationId, projectId]);

    async function sendMessage(
        messageOverride?: string,
        workflowOverride?: WorkspaceWorkflow | null,
    ) {
        const message = (messageOverride ?? input).trim();

        if (!message || loading || historyLoading) {
            return;
        }

        const token = localStorage.getItem("access_token");

        if (!token) {
            handleUnauthorized();
            return;
        }

        setMessages((current) => [
            ...current,
            { role: "user", content: message },
            { role: "assistant", content: "" },
        ]);

        if (!messageOverride) {
            setInput("");
        }

        setLoading(true);
        void checkMemoryCandidate(message, token);

        try {
            let conversationId = activeConversationId;

            if (conversationId === null) {
                const conversation = await createConversation(token);
                conversationId = conversation.id;
            }

            const workflow = workflowOverride ?? activeWorkflow;

            const requestBody: {
                message: string;
                conversation_id: number;
                engine?: string;
                action?: string;
                project_id?: number;
            } = {
                message,
                conversation_id: conversationId,
            };

            if (projectId !== null && projectId !== undefined) {
                requestBody.project_id = projectId;
            }

            if (workflow?.engine) {
                requestBody.engine = workflow.engine;
            }

            if (workflow?.action) {
                requestBody.action = workflow.action;
            }

            const response = await fetch(
                `${API_URL}/ai/chat/stream`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify(requestBody),
                },
            );

            if (response.status === 401) {
                handleUnauthorized();
                return;
            }

            if (!response.ok) {
                throw new Error(
                    `Chat request failed: ${response.status}`,
                );
            }

            if (!response.body) {
                throw new Error(
                    "Streaming is not supported by this response.",
                );
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let accumulated = "";

            while (true) {
                const { value, done } = await reader.read();

                if (done) {
                    break;
                }

                accumulated += decoder.decode(value, {
                    stream: true,
                });

                setMessages((current) => {
                    const updated = [...current];
                    updated[updated.length - 1] = {
                        role: "assistant",
                        content: accumulated,
                    };
                    return updated;
                });
            }

            accumulated += decoder.decode();

            setMessages((current) => {
                const updated = [...current];
                updated[updated.length - 1] = {
                    role: "assistant",
                    content: accumulated,
                };
                return updated;
            });

            setConversations((current) =>
                current.map((conversation) =>
                    conversation.id === conversationId &&
                        conversation.title === "New Chat"
                        ? {
                            ...conversation,
                            title: message.slice(0, 60),
                            updated_at: new Date().toISOString(),
                        }
                        : conversation,
                ),
            );

            void refreshConversations(token).catch((error) =>
                console.error("Conversation refresh failed:", error),
            );
        } catch (error) {
            console.error(error);

            setMessages((current) => {
                const updated = [...current];
                updated[updated.length - 1] = {
                    role: "assistant",
                    content:
                        "I couldn't complete the request. Check that the AEL backend is running and you're authenticated.",
                };
                return updated;
            });
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        if (
            initialWorkflow &&
            !workflowStarted &&
            !historyLoading &&
            !conversationsLoading
        ) {
            setWorkflowStarted(true);
            setActiveWorkflow(null);

            void sendMessage(
                initialWorkflow.label,
                initialWorkflow,
            );
        }
    }, [
        initialWorkflow,
        workflowStarted,
        historyLoading,
        conversationsLoading,
    ]);

    function handleKeyDown(
        event: React.KeyboardEvent<HTMLInputElement>,
    ) {
        if (event.key === "Enter") {
            void sendMessage();
        }
    }

    return (
        <section className="chat-workspace">
            <aside className="conversation-sidebar">
                <div className="conversation-sidebar-header">
                    <div>
                        <span className="chat-eyebrow">LATZ AI</span>
                        <h2>Conversations</h2>
                    </div>

                    <button
                        type="button"
                        className="new-chat-button"
                        onClick={() => void handleNewChat()}
                        disabled={loading || historyLoading}
                    >
                        + New Chat
                    </button>
                </div>

                <div className="conversation-filters">
                    {CATEGORIES.map((category) => (
                        <button
                            type="button"
                            key={category.value}
                            className={
                                categoryFilter === category.value
                                    ? "conversation-filter active"
                                    : "conversation-filter"
                            }
                            onClick={() =>
                                setCategoryFilter(category.value)
                            }
                        >
                            {category.label}
                        </button>
                    ))}
                </div>

                <div className="conversation-list">
                    {conversationsLoading ? (
                        <p className="conversation-empty">
                            Loading conversations...
                        </p>
                    ) : filteredConversations.length === 0 ? (
                        <p className="conversation-empty">
                            No saved chats in this category.
                        </p>
                    ) : (
                        filteredConversations.map((conversation) => (
                            <button
                                type="button"
                                key={conversation.id}
                                className={
                                    conversation.id ===
                                        activeConversationId
                                        ? "conversation-item active"
                                        : "conversation-item"
                                }
                                onClick={() =>
                                    selectConversation(conversation)
                                }
                                disabled={loading}
                            >
                                <span className="conversation-item-title">
                                    {conversation.title || "New Chat"}
                                </span>
                                <span className="conversation-item-meta">
                                    {conversation.category}
                                </span>
                            </button>
                        ))
                    )}

                    {sidebarError && (
                        <p className="conversation-error">
                            {sidebarError}
                        </p>
                    )}
                </div>
            </aside>

            <div className="chat-panel">
                <div className="chat-header">
                    <div>
                        <span className="chat-eyebrow">LATZ AI</span>
                        <h2>
                            {activeConversation?.title || "Chat with LATZ"}
                        </h2>
                        <p>
                            {projectId !== null &&
                                projectId !== undefined
                                ? "Working in your selected engineering project."
                                : "Think through an engineering problem, idea, or decision."}
                        </p>
                    </div>

                    <div className="chat-status">
                        <span />
                        {historyLoading
                            ? "Loading history"
                            : loading
                                ? "Generating"
                                : "Ready"}
                    </div>
                </div>

                <div className="chat-messages">
                    {messages.map((message, index) => (
                        <div
                            key={`${activeConversationId ?? "legacy"}-${message.role}-${index}`}
                            className={`chat-message ${message.role}`}
                        >
                            <div className="message-label">
                                {message.role === "user" ? "You" : "LATZ"}
                            </div>

                            <div className="message-content">
                                {message.role === "assistant" ? (
                                    message.content ? (
                                        <ReactMarkdown
                                            remarkPlugins={[remarkGfm]}
                                        >
                                            {message.content.replace(
                                                /<br\s*\/?>/gi,
                                                "\n",
                                            )}
                                        </ReactMarkdown>
                                    ) : (
                                        <span className="typing">
                                            Thinking...
                                        </span>
                                    )
                                ) : (
                                    message.content
                                )}
                            </div>
                        </div>
                    ))}

                    {memoryCandidate && (
                        <div className="memory-candidate">
                            <div className="memory-candidate-icon">
                                🧠
                            </div>

                            <div className="memory-candidate-content">
                                <strong>Remember this?</strong>
                                <p>{memoryCandidate.content}</p>

                                <div className="memory-candidate-actions">
                                    <button
                                        type="button"
                                        onClick={() => void saveMemory()}
                                    >
                                        Remember
                                    </button>
                                    <button
                                        type="button"
                                        onClick={dismissMemory}
                                    >
                                        Not now
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                <div className="chat-input-area">
                    <input
                        value={input}
                        onChange={(event) =>
                            setInput(event.target.value)
                        }
                        onKeyDown={handleKeyDown}
                        placeholder="Ask LATZ anything..."
                        disabled={loading || historyLoading}
                    />

                    <button
                        type="button"
                        onClick={() => void sendMessage()}
                        disabled={
                            loading ||
                            historyLoading ||
                            !input.trim()
                        }
                    >
                        →
                    </button>
                </div>
            </div>
        </section>
    );
}
