import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
    ArrowDown,
    ArrowUp,
    Brain,
    FolderKanban,
    History,
    Pencil,
    Pin,
    PinOff,
    Plus,
    RotateCcw,
    Search,
    Square,
    Trash2,
    X,
} from "lucide-react";
import "./Chat.css";
import type { WorkspaceWorkflow } from "../../app/workflow";
import { API_BASE, clearToken, getToken } from "../../shared/api/client";
import { apiFetch, errorMessage } from "../../shared/api/http";
import { useApiResource } from "../../shared/api/resources";
import WolfHead from "../../shared/brand/WolfHead";
import { usePageTitle } from "../../shared/hooks/usePageTitle";
import Markdown from "../../shared/markdown/Markdown";
import { useNotify } from "../../shared/notifications/context";
import Button from "../../shared/ui/Button";
import ConfirmDialog from "../../shared/ui/ConfirmDialog";
import { emptyReplyMessage, incompleteReason, splitStreamEnd, type StreamEnd } from "../../shared/api/streamEnd";
import { UserFacingError, chatErrorMessage, chatFailureFromResponse } from "../../shared/api/errorMessages";
import Modal from "../../shared/ui/Modal";
import Notice from "../../shared/ui/Notice";
import { SkeletonList } from "../../shared/ui/States";

type Message = {
    role: "user" | "assistant";
    content: string;
    /** True when the request failed and the content is the error text. */
    failed?: boolean;
    /** True when the user stopped the reply before it finished. */
    stopped?: boolean;
    /** Set when the reply ended early (length limit, provider error, dropped connection). */
    incomplete?: StreamEnd;
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

type SavedProject = {
    id: number;
    name: string;
    description: string | null;
    status: string;
    engine: string | null;
    tech_stack: string | null;
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
    /** Conversation named in the URL. Null shows the most recent one. */
    routeConversationId?: number | null;
    /** Reports the conversation on screen so the URL can follow it. */
    onConversationChange?: (conversationId: number | null) => void;
    /**
     * Opens a conversation the user picked from the list by changing the URL.
     * The URL is the single source of truth for that choice, so Back and Forward
     * can never leave a different conversation on screen than the address names.
     */
    onSelectConversation?: (conversationId: number) => void;
    /** Called after a conversation is created or updated, so other screens can refresh. */
    onConversationsChanged?: () => void;
    /** Called once the queued workflow's first message has been sent. */
    onWorkflowStarted?: () => void;
    onOpenProject?: (project: SavedProject) => void;
    onLeaveProject?: () => void;
};

const PINS_KEY = "latz-pinned-conversations";

function readPins(): number[] {
    try {
        const stored: unknown = JSON.parse(localStorage.getItem(PINS_KEY) ?? "[]");

        return Array.isArray(stored) ? stored.filter((id): id is number => typeof id === "number") : [];
    } catch {
        return [];
    }
}

const API_URL = API_BASE;

const SUGGESTIONS = [
    "Help me plan the architecture for a new project",
    "Explain a concept I'm trying to learn",
    "Debug an error with me step by step",
];

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
    routeConversationId = null,
    onConversationChange,
    onSelectConversation,
    onConversationsChanged,
    onWorkflowStarted,
    onOpenProject,
    onLeaveProject,
}: ChatProps) {
    const notify = useNotify();
    const scrollRef = useRef<HTMLDivElement>(null);
    const stickToBottom = useRef(true);
    const composerRef = useRef<HTMLTextAreaElement>(null);
    // Conversation created while a message is already on screen: its (empty) history
    // must not be loaded, or it would wipe the message being sent.
    const skipHistoryLoadFor = useRef<number | null>(null);
    // A workflow marked "fresh" gets its own new conversation instead of the latest one.
    const freshStart = useRef(Boolean(initialWorkflow?.fresh));
    const abortRef = useRef<AbortController | null>(null);
    const [listOpen, setListOpen] = useState(false);
    const [search, setSearch] = useState("");
    const [pins, setPins] = useState<number[]>(readPins);
    const [showJump, setShowJump] = useState(false);
    const savedProjectsResource = useApiResource<SavedProject[]>("/projects");
    const savedProjects = savedProjectsResource.data ?? [];
    const projectsLoading = savedProjectsResource.loading;
    const projectsError = savedProjectsResource.error ? "Couldn't load saved projects." : "";
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
        useState<number | null>(routeConversationId);
    const [seenRouteId, setSeenRouteId] = useState(routeConversationId);

    // Back, forward and direct links change the URL: show the conversation it names.
    if (routeConversationId !== seenRouteId) {
        setSeenRouteId(routeConversationId);

        if (routeConversationId !== null && routeConversationId !== activeConversationId) {
            setActiveConversationId(routeConversationId);
        }
    }
    const [categoryFilter, setCategoryFilter] = useState<
        ConversationCategory | "all"
    >("all");
    const [memoryCandidate, setMemoryCandidate] =
        useState<MemoryCandidate | null>(null);
    const [workflowStarted, setWorkflowStarted] = useState(false);
    const [activeWorkflow, setActiveWorkflow] =
        useState<WorkspaceWorkflow | null>(initialWorkflow ?? null);
    const [sidebarError, setSidebarError] = useState("");
    const [renaming, setRenaming] = useState<Conversation | null>(null);
    const [renameValue, setRenameValue] = useState("");
    const [renameError, setRenameError] = useState("");
    const [renameBusy, setRenameBusy] = useState(false);
    const [deleting, setDeleting] = useState<Conversation | null>(null);
    const [deleteBusy, setDeleteBusy] = useState(false);

    const activeConversation = conversations.find(
        (conversation) => conversation.id === activeConversationId,
    );

    const searchText = search.trim().toLowerCase();
    const filteredConversations = conversations
        .filter(
            (conversation) =>
                (categoryFilter === "all" || conversation.category === categoryFilter) &&
                (!searchText || conversation.title.toLowerCase().includes(searchText)),
        )
        // Pinned conversations first; the backend's newest-first order is kept within each group.
        .sort((a, b) => Number(pins.includes(b.id)) - Number(pins.includes(a.id)));
    const activeProject = savedProjects.find((project) => project.id === projectId);

    const handleUnauthorized = useCallback(() => {
        clearToken();

        if (onLogout) {
            onLogout();
        } else {
            window.location.reload();
        }
    }, [onLogout]);

    const refreshConversations = useCallback(async (token: string) => {
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
    }, [handleUnauthorized, projectId]);

    const createConversation = useCallback(async (
        token: string,
        keepMessages = false,
        categoryOverride?: ConversationCategory,
    ): Promise<Conversation> => {
        const category: ConversationCategory =
            categoryOverride ?? (categoryFilter === "all" ? "general" : categoryFilter);

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

        if (keepMessages) {
            skipHistoryLoadFor.current = conversation.id;
        } else {
            setMessages([INITIAL_MESSAGE]);
            setMemoryCandidate(null);
        }

        freshStart.current = false;
        setActiveConversationId(conversation.id);
        setSidebarError("");
        onConversationsChanged?.();

        return conversation;
    }, [handleUnauthorized, categoryFilter, projectId, onConversationsChanged]);

    const checkMemoryCandidate = useCallback(async (
        message: string,
        token: string,
    ) => {
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
    }, [handleUnauthorized]);

    async function saveMemory() {
        if (!memoryCandidate) {
            return;
        }

        try {
            const token = getToken();

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
                notify({
                    mood: "success",
                    title: data.duplicate ? "Already remembered" : "Memory saved",
                    detail: "LATZ will use it in future answers.",
                });
            }
        } catch (error) {
            console.error("Memory save failed:", error);
            notify({
                mood: "error",
                title: "Couldn't save that memory",
                detail: "Check that the backend is running, then try again.",
            });
        }
    }

    function dismissMemory() {
        setMemoryCandidate(null);
    }

    async function handleNewChat() {
        if (loading) {
            return;
        }

        const token = getToken();

        if (!token) {
            handleUnauthorized();
            return;
        }

        setHistoryLoading(true);
        setSidebarError("");
        setWorkflowStarted(true);
        setActiveWorkflow(null);
        setInput("");
        setListOpen(false);

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
        setListOpen(false);

        if (onSelectConversation) {
            onSelectConversation(conversation.id);
        } else {
            setActiveConversationId(conversation.id);
        }
    }

    useEffect(() => {
        let cancelled = false;

        async function loadConversations() {
            setConversationsLoading(true);
            setHistoryLoading(true);
            setSidebarError("");

            const token = getToken();

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

                    if (freshStart.current) {
                        return null;
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
    }, [projectId, handleUnauthorized]);

    useEffect(() => {
        if (
            activeConversationId !== null &&
            skipHistoryLoadFor.current === activeConversationId
        ) {
            skipHistoryLoadFor.current = null;
            return;
        }

        let cancelled = false;

        async function loadHistory() {
            if (freshStart.current && activeConversationId === null) {
                setMessages([INITIAL_MESSAGE]);
                setHistoryLoading(false);
                return;
            }

            setHistoryLoading(true);
            setMessages([]);
            setMemoryCandidate(null);

            const token = getToken();

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

                if (response.status === 404) {
                    // The conversation no longer exists (deleted here or elsewhere): show a clean start.
                    if (!cancelled) {
                        setMessages([INITIAL_MESSAGE]);
                    }
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
    }, [activeConversationId, projectId, handleUnauthorized]);

    const sendMessage = useCallback(async (
        messageOverride?: string,
        workflowOverride?: WorkspaceWorkflow | null,
    ) => {
        const message = (messageOverride ?? input).trim();

        if (!message || loading || historyLoading) return;

        const token = getToken();
        if (!token) {
            handleUnauthorized();
            return;
        }

        setMessages((current) => [
            ...current,
            { role: "user", content: message },
            { role: "assistant", content: "" },
        ]);

        if (!messageOverride) setInput("");
        stickToBottom.current = true;
        setLoading(true);
        void checkMemoryCandidate(message, token);

        try {
            let conversationId = activeConversationId;

            if (conversationId === null) {
                const conversation = await createConversation(
                    token,
                    true,
                    workflowOverride?.category,
                );
                conversationId = conversation.id;
            }

            const workflow = workflowOverride ?? activeWorkflow;
            const requestBody: {
                message: string;
                conversation_id: number;
                engine?: string;
                action?: string;
                project_id?: number;
            } = { message, conversation_id: conversationId };

            if (projectId !== null && projectId !== undefined) {
                requestBody.project_id = projectId;
            }
            if (workflow?.engine) requestBody.engine = workflow.engine;
            if (workflow?.action) requestBody.action = workflow.action;

            const controller = new AbortController();
            abortRef.current = controller;

            const response = await fetch(`${API_URL}/ai/chat/stream`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify(requestBody),
                signal: controller.signal,
            });

            if (response.status === 401) {
                handleUnauthorized();
                return;
            }
            if (!response.ok) {
                throw await chatFailureFromResponse(response);
            }
            if (!response.body) {
                throw new Error("Streaming is not supported by this response.");
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let raw = "";
            const show = (content: string, incomplete?: StreamEnd) =>
                setMessages((current) => {
                    const updated = [...current];
                    updated[updated.length - 1] = { role: "assistant", content, incomplete };
                    return updated;
                });

            try {
                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;

                    raw += decoder.decode(value, { stream: true });
                    show(splitStreamEnd(raw).text);
                }
            } catch (error) {
                if (error instanceof DOMException && error.name === "AbortError") throw error;
                // The connection broke mid-reply: keep what arrived and mark it incomplete.
                const partial = splitStreamEnd(raw).text;
                if (!partial.trim()) throw error;
                show(partial, "interrupted");
                return;
            }

            raw += decoder.decode();
            const finished = splitStreamEnd(raw);
            if (!finished.text.trim() && finished.end !== "stop") {
                throw new UserFacingError(emptyReplyMessage(finished.end));
            }
            show(finished.text, finished.end === "stop" ? undefined : (finished.end ?? "interrupted"));

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
            onConversationsChanged?.();
        } catch (error) {
            if (error instanceof DOMException && error.name === "AbortError") {
                // Stopped by the user: keep what arrived and say so.
                setMessages((current) => {
                    const updated = [...current];
                    const last = updated[updated.length - 1];

                    if (last?.role === "assistant") {
                        updated[updated.length - 1] = { ...last, stopped: true };
                    }

                    return updated;
                });
                return;
            }

            console.error(error);
            setMessages((current) => {
                const updated = [...current];
                updated[updated.length - 1] = {
                    role: "assistant",
                    content: chatErrorMessage(error),
                    failed: true,
                };
                return updated;
            });
        } finally {
            abortRef.current = null;
            setLoading(false);
            // Typing can continue straight away; the composer was disabled while generating.
            window.requestAnimationFrame(() => composerRef.current?.focus());
        }
    }, [
        input,
        loading,
        historyLoading,
        handleUnauthorized,
        checkMemoryCandidate,
        activeConversationId,
        activeWorkflow,
        projectId,
        createConversation,
        refreshConversations,
        onConversationsChanged,
        setInput,
    ]);

    useEffect(() => {
        if (
            !initialWorkflow ||
            workflowStarted ||
            historyLoading ||
            conversationsLoading
        ) {
            return;
        }

        const timeoutId = window.setTimeout(() => {
            setWorkflowStarted(true);
            setActiveWorkflow(null);
            onWorkflowStarted?.();
            void sendMessage(initialWorkflow.label, initialWorkflow);
        }, 0);

        return () => window.clearTimeout(timeoutId);
    }, [
        initialWorkflow,
        workflowStarted,
        historyLoading,
        conversationsLoading,
        sendMessage,
        onWorkflowStarted,
    ]);

    function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            void sendMessage();
        }
    }

    // Tell the route which conversation is on screen so the URL can follow it.
    useEffect(() => {
        onConversationChange?.(activeConversationId);
    }, [activeConversationId, routeConversationId, onConversationChange]);

    // Stop any reply still streaming when chat is left.
    useEffect(() => () => abortRef.current?.abort(), []);

    // Keep the newest message in view, unless the reader has scrolled up to read.
    useEffect(() => {
        const container = scrollRef.current;

        if (container && stickToBottom.current) {
            container.scrollTop = container.scrollHeight;
        }
    }, [messages, memoryCandidate]);

    // Grow the composer with its content, up to the CSS max-height.
    useEffect(() => {
        const composer = composerRef.current;

        if (composer) {
            composer.style.height = "auto";
            composer.style.height = `${composer.scrollHeight}px`;
        }
    }, [input]);

    function handleScroll() {
        const container = scrollRef.current;

        if (container) {
            const atBottom =
                container.scrollHeight - container.scrollTop - container.clientHeight < 80;

            stickToBottom.current = atBottom;
            setShowJump(!atBottom);
        }
    }

    function jumpToLatest() {
        const container = scrollRef.current;

        if (container) {
            stickToBottom.current = true;
            container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
        }
    }

    function applySuggestion(suggestion: string) {
        setInput(suggestion);
        composerRef.current?.focus();
    }

    function stopGenerating() {
        abortRef.current?.abort();
    }

    /** Sends the last question again after a failed or stopped reply. */
    function retryLast() {
        const lastUser = [...messages].reverse().find((message) => message.role === "user");

        if (!lastUser || loading) {
            return;
        }

        setMessages((current) => current.slice(0, -2));
        void sendMessage(lastUser.content);
    }

    function startRename(conversation: Conversation) {
        setRenaming(conversation);
        setRenameValue(conversation.title);
        setRenameError("");
    }

    async function submitRename(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();

        if (!renaming || renameBusy) {
            return;
        }

        const title = renameValue.trim();

        if (!title) {
            setRenameError("A conversation needs a title.");
            return;
        }

        setRenameBusy(true);
        setRenameError("");

        try {
            const updated = await apiFetch<Conversation>(`/conversations/${renaming.id}`, {
                method: "PATCH",
                body: { title },
            });

            setConversations((current) =>
                current.map((item) => (item.id === updated.id ? { ...item, title: updated.title } : item)),
            );
            onConversationsChanged?.();
            setRenaming(null);
            notify({ mood: "success", title: "Conversation renamed", detail: updated.title });
        } catch (error) {
            setRenameError(`Couldn't rename it. ${errorMessage(error, "Something went wrong.")}`);
        } finally {
            setRenameBusy(false);
        }
    }

    async function confirmDelete() {
        if (!deleting || deleteBusy) {
            return;
        }

        const removed = deleting;

        setDeleteBusy(true);

        try {
            await apiFetch(`/conversations/${removed.id}`, { method: "DELETE" });
        } catch (error) {
            setDeleting(null);
            setDeleteBusy(false);
            notify({
                mood: "error",
                title: "Couldn't delete the conversation",
                detail: errorMessage(error, "Something went wrong."),
            });
            return;
        }

        const remaining = conversations.filter((item) => item.id !== removed.id);

        setConversations(remaining);
        setPins((current) => current.filter((id) => id !== removed.id));
        setDeleting(null);
        setDeleteBusy(false);
        onConversationsChanged?.();
        notify({ mood: "success", title: "Conversation deleted", detail: removed.title });

        if (removed.id !== activeConversationId) {
            return;
        }

        // The open conversation is gone: move to the next most recent one, or start a fresh chat.
        setMemoryCandidate(null);
        setActiveWorkflow(null);

        if (remaining.length > 0) {
            if (onSelectConversation) {
                onSelectConversation(remaining[0].id);
            } else {
                setActiveConversationId(remaining[0].id);
            }
            return;
        }

        const token = getToken();

        if (token) {
            try {
                setHistoryLoading(true);
                await createConversation(token);
            } catch {
                setSidebarError("Couldn't start a new chat. Use New chat to try again.");
            } finally {
                setHistoryLoading(false);
            }
        }
    }

    function togglePin(conversationId: number) {
        setPins((current) => {
            const next = current.includes(conversationId)
                ? current.filter((id) => id !== conversationId)
                : [...current, conversationId];

            try {
                localStorage.setItem(PINS_KEY, JSON.stringify(next));
            } catch {
                // Storage unavailable: the pin still applies until the page is closed.
            }

            return next;
        });
    }

    const isEmpty =
        !historyLoading && messages.length === 1 && messages[0] === INITIAL_MESSAGE;
    const busy = loading || historyLoading;
    const statusClass = busy ? "status--busy" : "status--ok";
    const title = activeConversation?.title || "Chat with LATZ";

    usePageTitle(title);

    return (
        <section className="chat-workspace">
            <aside
                className={`conversation-sidebar${listOpen ? " open" : ""}`}
                aria-label="Conversations"
            >
                <div className="conversation-sidebar-header">
                    <h2 className="label">Conversations</h2>

                    <button
                        type="button"
                        className="icon-btn conversation-close"
                        onClick={() => setListOpen(false)}
                        aria-label="Close conversations"
                    >
                        <X size={16} />
                    </button>
                </div>

                <Button
                    variant="primary"
                    block
                    onClick={() => void handleNewChat()}
                    disabled={loading || historyLoading}
                >
                    <Plus size={15} aria-hidden="true" />
                    New chat
                </Button>

                <label className="search-field">
                    <Search size={15} aria-hidden="true" />
                    <span className="visually-hidden">Search conversations</span>
                    <input
                        type="search"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="Search conversations"
                    />
                </label>

                <div className="conversation-filters" role="group" aria-label="Filter conversations">
                    {CATEGORIES.map((category) => (
                        <button
                            type="button"
                            key={category.value}
                            className={
                                categoryFilter === category.value
                                    ? "chip active"
                                    : "chip"
                            }
                            aria-pressed={categoryFilter === category.value}
                            onClick={() => setCategoryFilter(category.value)}
                        >
                            {category.label}
                        </button>
                    ))}
                </div>

                <div className="conversation-list">
                    {categoryFilter === "projects" ? (
                        projectsLoading ? (
                            <SkeletonList rows={3} height={48} />
                        ) : savedProjects.length === 0 ? (
                            <p className="conversation-empty">
                                No saved projects yet. Create one from Projects.
                            </p>
                        ) : (
                            savedProjects
                                .filter(
                                    (project) =>
                                        !searchText || project.name.toLowerCase().includes(searchText),
                                )
                                .map((project) => (
                                    <button
                                        type="button"
                                        key={project.id}
                                        className={
                                            project.id === projectId
                                                ? "conversation-item active"
                                                : "conversation-item"
                                        }
                                        onClick={() => {
                                            setListOpen(false);
                                            onOpenProject?.(project);
                                        }}
                                        disabled={loading}
                                    >
                                        <span className="conversation-item-title">{project.name}</span>
                                        <span className="conversation-item-meta">
                                            {project.status}
                                            {project.engine ? `, ${project.engine}` : ""}
                                        </span>
                                    </button>
                                ))
                        )
                    ) : conversationsLoading ? (
                        <SkeletonList rows={4} height={48} />
                    ) : filteredConversations.length === 0 ? (
                        <p className="conversation-empty">
                            {searchText
                                ? `No conversations match "${search.trim()}".`
                                : "No saved chats here yet. Start one with New chat."}
                        </p>
                    ) : (
                        filteredConversations.map((conversation) => {
                            const pinned = pins.includes(conversation.id);
                            const active = conversation.id === activeConversationId;

                            return (
                                <div
                                    key={conversation.id}
                                    className={`conversation-row${active ? " active" : ""}${pinned ? " pinned" : ""}`}
                                >
                                    <button
                                        type="button"
                                        className="conversation-item"
                                        aria-current={active ? "true" : undefined}
                                        onClick={() => selectConversation(conversation)}
                                        disabled={loading}
                                    >
                                        <span className="conversation-item-title">
                                            {conversation.title || "New Chat"}
                                        </span>
                                        <span className="conversation-item-meta">
                                            {conversation.category}
                                        </span>
                                    </button>
                                    <button
                                        type="button"
                                        className="conversation-pin"
                                        onClick={() => togglePin(conversation.id)}
                                        aria-pressed={pinned}
                                        aria-label={
                                            pinned
                                                ? `Unpin ${conversation.title || "conversation"}`
                                                : `Pin ${conversation.title || "conversation"}`
                                        }
                                        title={pinned ? "Unpin" : "Pin to top"}
                                    >
                                        {pinned ? <PinOff size={14} /> : <Pin size={14} />}
                                    </button>
                                    <button
                                        type="button"
                                        className="conversation-action"
                                        onClick={() => startRename(conversation)}
                                        aria-label={`Rename ${conversation.title || "conversation"}`}
                                        title="Rename"
                                        disabled={loading}
                                    >
                                        <Pencil size={14} />
                                    </button>
                                    <button
                                        type="button"
                                        className="conversation-action conversation-delete"
                                        onClick={() => setDeleting(conversation)}
                                        aria-label={`Delete ${conversation.title || "conversation"}`}
                                        title="Delete"
                                        disabled={loading}
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            );
                        })
                    )}

                    {categoryFilter === "projects" && projectsError && (
                        <Notice tone="error">{projectsError}</Notice>
                    )}
                    {sidebarError && <Notice tone="error">{sidebarError}</Notice>}
                </div>
            </aside>

            <AnimatePresence>
                {renaming && (
                    <Modal title="Rename conversation" onClose={() => !renameBusy && setRenaming(null)}>
                        <form className="conversation-rename" onSubmit={(event) => void submitRename(event)} noValidate>
                            <div className="field">
                                <label className="field__label" htmlFor="rename-conversation">
                                    Title
                                </label>
                                <input
                                    id="rename-conversation"
                                    className="input"
                                    value={renameValue}
                                    maxLength={200}
                                    onChange={(event) => {
                                        setRenameValue(event.target.value);
                                        setRenameError("");
                                    }}
                                    aria-invalid={renameError ? true : undefined}
                                    disabled={renameBusy}
                                />
                                {renameError && (
                                    <p className="field__error" role="alert">
                                        {renameError}
                                    </p>
                                )}
                            </div>
                            <div className="conversation-rename__actions">
                                <Button onClick={() => setRenaming(null)} disabled={renameBusy}>
                                    Cancel
                                </Button>
                                <Button type="submit" variant="primary" busy={renameBusy}>
                                    Rename
                                </Button>
                            </div>
                        </form>
                    </Modal>
                )}
                {deleting && (
                    <ConfirmDialog
                        title={`Delete "${deleting.title || "this conversation"}"?`}
                        description="The conversation and its messages are removed permanently."
                        confirmLabel={deleteBusy ? "Deleting" : "Delete conversation"}
                        cancelLabel="Keep conversation"
                        busy={deleteBusy}
                        onConfirm={() => void confirmDelete()}
                        onCancel={() => setDeleting(null)}
                    />
                )}
            </AnimatePresence>

            {listOpen && (
                <button
                    type="button"
                    className="conversation-scrim"
                    aria-label="Close conversations"
                    onClick={() => setListOpen(false)}
                />
            )}

            <div className="chat-panel">
                <header className="chat-header">
                    <button
                        type="button"
                        className="icon-btn chat-history-toggle"
                        onClick={() => setListOpen(true)}
                        aria-label="Show conversations"
                    >
                        <History size={17} />
                    </button>

                    <div className="chat-header-copy">
                        <h1>{title}</h1>
                        {projectId !== null ? (
                            <p className="chat-project">
                                <FolderKanban size={13} aria-hidden="true" />
                                <span>{activeProject?.name ?? "Project"}</span>
                                {onLeaveProject && (
                                    <button type="button" onClick={onLeaveProject}>
                                        Show all conversations
                                    </button>
                                )}
                            </p>
                        ) : (
                            <p>Think through an engineering problem, idea, or decision.</p>
                        )}
                    </div>

                    <span className={`status ${statusClass}`} role="status">
                        <span className="status__dot" />
                        {historyLoading ? "Loading history" : loading ? "Generating" : "Ready"}
                    </span>
                </header>

                <div className="chat-scroll-area">
                    <div className="chat-messages" ref={scrollRef} onScroll={handleScroll}>
                        <div className="chat-thread">
                            {historyLoading && messages.length === 0 ? (
                                <div className="chat-placeholder" role="status">
                                    <WolfHead size={56} mood="thinking" />
                                    <p>Loading this conversation</p>
                                </div>
                            ) : isEmpty ? (
                                <div className="chat-placeholder">
                                    <WolfHead size={88} />
                                    <h2>Ask LATZ</h2>
                                    <p>{INITIAL_MESSAGE.content}</p>
                                    <div className="chat-suggestions">
                                        {SUGGESTIONS.map((suggestion) => (
                                            <button
                                                type="button"
                                                key={suggestion}
                                                onClick={() => applySuggestion(suggestion)}
                                            >
                                                {suggestion}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            ) : (
                                messages.map((message, index) => {
                                    const isLast = index === messages.length - 1;
                                    const streaming = loading && isLast && message.role === "assistant";

                                    return message.role === "user" ? (
                                        <div
                                            key={`${activeConversationId ?? "legacy"}-user-${index}`}
                                            className="chat-message user"
                                        >
                                            <span className="visually-hidden">You said:</span>
                                            <div className="message-content">{message.content}</div>
                                        </div>
                                    ) : (
                                        <div
                                            key={`${activeConversationId ?? "legacy"}-assistant-${index}`}
                                            className={`chat-message assistant${message.failed ? " failed" : ""}`}
                                        >
                                            <WolfHead
                                                size={32}
                                                mood={
                                                    message.failed
                                                        ? "error"
                                                        : streaming
                                                          ? "thinking"
                                                          : "idle"
                                                }
                                            />
                                            <div className="message-body">
                                                <div className="message-label">LATZ</div>
                                                <div className="message-content" aria-busy={streaming}>
                                                    {message.content ? (
                                                        <Markdown>{message.content}</Markdown>
                                                    ) : message.stopped ? null : (
                                                        <span className="typing" role="status">
                                                            <span className="visually-hidden">
                                                                LATZ is thinking
                                                            </span>
                                                            <i />
                                                            <i />
                                                            <i />
                                                        </span>
                                                    )}
                                                </div>

                                                {message.incomplete && (
                                                    <p className="message-incomplete" role="status">
                                                        Incomplete reply. {incompleteReason(message.incomplete)}
                                                    </p>
                                                )}

                                                {(message.failed || message.stopped) && isLast && (
                                                    <div className="message-recovery">
                                                        {message.stopped && (
                                                            <span>
                                                                Stopped. This reply was not saved to the
                                                                conversation.
                                                            </span>
                                                        )}
                                                        <Button size="sm" onClick={retryLast}>
                                                            <RotateCcw size={13} aria-hidden="true" />
                                                            {message.failed ? "Try again" : "Ask again"}
                                                        </Button>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })
                            )}

                            <AnimatePresence>
                                {memoryCandidate && (
                                    <motion.div
                                        className="memory-candidate"
                                        initial={{ opacity: 0, y: 8 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0 }}
                                        transition={{ duration: 0.2 }}
                                    >
                                        <Brain size={18} aria-hidden="true" />

                                        <div className="memory-candidate-content">
                                            <strong>Remember this?</strong>
                                            <p>{memoryCandidate.content}</p>

                                            <div className="memory-candidate-actions">
                                                <Button
                                                    variant="primary"
                                                    size="sm"
                                                    onClick={() => void saveMemory()}
                                                >
                                                    Remember
                                                </Button>
                                                <Button variant="ghost" size="sm" onClick={dismissMemory}>
                                                    Not now
                                                </Button>
                                            </div>
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    </div>

                    {showJump && (
                        <button
                            type="button"
                            className="chat-jump"
                            onClick={jumpToLatest}
                            aria-label="Scroll to the latest message"
                        >
                            <ArrowDown size={16} />
                        </button>
                    )}
                </div>

                <div className="chat-input-area">
                    <div className="chat-composer">
                        <textarea
                            ref={composerRef}
                            rows={1}
                            value={input}
                            onChange={(event) => setInput(event.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder={loading ? "LATZ is replying" : "Ask LATZ anything"}
                            aria-label="Message LATZ"
                            disabled={loading || historyLoading}
                        />

                        {loading ? (
                            <button
                                type="button"
                                className="chat-send chat-send--stop"
                                onClick={stopGenerating}
                                aria-label="Stop generating"
                                title="Stop generating"
                            >
                                <Square size={14} fill="currentColor" />
                            </button>
                        ) : (
                            <button
                                type="button"
                                className="chat-send"
                                onClick={() => void sendMessage()}
                                disabled={historyLoading || !input.trim()}
                                aria-label="Send message"
                                title="Send message"
                            >
                                <ArrowUp size={18} />
                            </button>
                        )}
                    </div>
                    <p className="chat-hint">Enter to send. Shift + Enter for a new line.</p>
                </div>
            </div>
        </section>
    );
}
