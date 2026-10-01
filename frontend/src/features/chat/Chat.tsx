import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./Chat.css";

type Message = {
    role: "user" | "assistant";
    content: string;
};

type MemoryCandidate = {
    memory_type: string;
    content: string;
    memory_key: string;
};

type ChatProps = {
    onLogout?: () => void;
};

export default function Chat({
    onLogout,
}: ChatProps) {
    const [messages, setMessages] = useState<Message[]>([
        {
            role: "assistant",
            content:
                "I'm LATZ. Tell me what you're building, debugging, researching, or trying to understand.",
        },
    ]);

    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [memoryCandidate, setMemoryCandidate] =
        useState<MemoryCandidate | null>(null);

    function handleUnauthorized() {
        localStorage.removeItem("access_token");

        if (onLogout) {
            onLogout();
        } else {
            window.location.reload();
        }
    }

    async function checkMemoryCandidate(
        message: string,
        token: string,
    ) {
        try {
            const response = await fetch(
                "http://127.0.0.1:8000/ai/memory-candidate",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        message,
                    }),
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

            if (
                data.candidate &&
                !data.duplicate
            ) {
                setMemoryCandidate({
                    memory_type:
                        data.candidate.memory_type,
                    content:
                        data.candidate.content,
                    memory_key:
                        data.candidate.memory_key,
                });
            }
        } catch (error) {
            console.error(
                "Memory candidate check failed:",
                error,
            );
        }
    }

    async function saveMemory() {
        if (!memoryCandidate) {
            return;
        }

        try {
            const token =
                localStorage.getItem(
                    "access_token",
                );

            if (!token) {
                handleUnauthorized();
                return;
            }

            const response = await fetch(
                "http://127.0.0.1:8000/ai/memory-confirm",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        memory_type:
                            memoryCandidate.memory_type,
                        content:
                            memoryCandidate.content,
                    }),
                },
            );

            if (response.status === 401) {
                handleUnauthorized();
                return;
            }

            if (!response.ok) {
                throw new Error(
                    `Request failed: ${response.status}`,
                );
            }

            const data = await response.json();

            if (
                data.saved ||
                data.duplicate
            ) {
                setMemoryCandidate(null);
            }
        } catch (error) {
            console.error(
                "Memory save failed:",
                error,
            );
        }
    }

    function dismissMemory() {
        setMemoryCandidate(null);
    }

    async function sendMessage() {
        const message = input.trim();

        if (!message || loading) {
            return;
        }

        const token =
            localStorage.getItem(
                "access_token",
            );

        if (!token) {
            handleUnauthorized();
            return;
        }

        setMessages((current) => [
            ...current,
            {
                role: "user",
                content: message,
            },
            {
                role: "assistant",
                content: "",
            },
        ]);

        setInput("");
        setLoading(true);

        void checkMemoryCandidate(
            message,
            token,
        );

        try {
            const response = await fetch(
                "http://127.0.0.1:8000/ai/chat/stream",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        message,
                    }),
                },
            );

            if (!response.ok) {
                if (response.status === 401) {
                    handleUnauthorized();
                    return;
                }

                throw new Error(
                    `Request failed: ${response.status}`,
                );
            }

            if (!response.body) {
                throw new Error(
                    "Streaming is not supported by this response.",
                );
            }

            const reader =
                response.body.getReader();

            const decoder =
                new TextDecoder();

            let accumulated = "";

            while (true) {
                const {
                    value,
                    done,
                } = await reader.read();

                if (done) {
                    break;
                }

                accumulated += decoder.decode(
                    value,
                    { stream: true },
                );

                setMessages((current) => {
                    const updated = [
                        ...current,
                    ];

                    updated[
                        updated.length - 1
                    ] = {
                        role: "assistant",
                        content:
                            accumulated,
                    };

                    return updated;
                });
            }

            accumulated += decoder.decode();

            setMessages((current) => {
                const updated = [
                    ...current,
                ];

                updated[
                    updated.length - 1
                ] = {
                    role: "assistant",
                    content:
                        accumulated,
                };

                return updated;
            });
        } catch (error) {
            console.error(error);

            setMessages((current) => {
                const updated = [
                    ...current,
                ];

                updated[
                    updated.length - 1
                ] = {
                    role: "assistant",
                    content:
                        "I couldn't reach the AI service right now. Check that the AEL backend is running and you're authenticated.",
                };

                return updated;
            });
        } finally {
            setLoading(false);
        }
    }

    function handleKeyDown(
        event: React.KeyboardEvent<HTMLInputElement>,
    ) {
        if (event.key === "Enter") {
            sendMessage();
        }
    }

    return (
        <section className="chat-panel">
            <div className="chat-header">
                <div>
                    <span className="chat-eyebrow">
                        LATZ AI
                    </span>

                    <h2>
                        Chat with LATZ
                    </h2>

                    <p>
                        Think through an
                        engineering problem,
                        idea, or decision.
                    </p>
                </div>

                <div className="chat-status">
                    <span />
                    {loading
                        ? "Generating"
                        : "Ready"}
                </div>
            </div>

            <div className="chat-messages">
                {messages.map(
                    (message, index) => (
                        <div
                            key={`${message.role}-${index}`}
                            className={`chat-message ${message.role}`}
                        >
                            <div className="message-label">
                                {message.role ===
                                    "user"
                                    ? "You"
                                    : "LATZ"}
                            </div>

                            <div className="message-content">
                                {message.role ===
                                    "assistant" ? (
                                    message.content ? (
                                        <ReactMarkdown
                                            remarkPlugins={[
                                                remarkGfm,
                                            ]}
                                        >
                                            {
                                                message.content
                                            }
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
                    ),
                )}

                {memoryCandidate && (
                    <div className="memory-candidate">
                        <div className="memory-candidate-icon">
                            🧠
                        </div>

                        <div className="memory-candidate-content">
                            <strong>
                                Remember this?
                            </strong>

                            <p>
                                {
                                    memoryCandidate.content
                                }
                            </p>

                            <div className="memory-candidate-actions">
                                <button
                                    onClick={
                                        saveMemory
                                    }
                                >
                                    Remember
                                </button>

                                <button
                                    onClick={
                                        dismissMemory
                                    }
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
                        setInput(
                            event.target.value,
                        )
                    }
                    onKeyDown={
                        handleKeyDown
                    }
                    placeholder="Ask LATZ anything..."
                    disabled={loading}
                />

                <button
                    onClick={sendMessage}
                    disabled={
                        loading ||
                        !input.trim()
                    }
                >
                    →
                </button>
            </div>
        </section>
    );
}