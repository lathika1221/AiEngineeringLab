import { useCallback } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { clearWorkflow, usePendingWorkflow } from "../../app/workflow";
import { useSession } from "../../app/session/context";
import { refreshResources } from "../../shared/api/resources";
import Chat from "./Chat";

function toId(value: string | null | undefined): number | null {
    const id = Number(value);

    return value && Number.isInteger(id) && id > 0 ? id : null;
}

/**
 * Connects chat to the URL:
 *   /chat              the most recent conversation
 *   /chat/42           conversation 42
 *   /chat?project=7    conversations that belong to project 7
 */
export default function ChatRoute() {
    const { logout } = useSession();
    const params = useParams();
    const [search] = useSearchParams();
    const navigate = useNavigate();
    const pending = usePendingWorkflow();

    const conversationId = toId(params.conversationId);
    const projectId = toId(search.get("project"));
    const query = projectId !== null ? `?project=${projectId}` : "";

    const handleConversationChange = useCallback(
        (nextId: number | null) => {
            if (nextId === null || nextId === conversationId) {
                return;
            }

            // The first conversation shown on /chat replaces the entry; later ones add history.
            navigate(`/chat/${nextId}${query}`, { replace: conversationId === null });
        },
        [conversationId, navigate, query],
    );

    const handleSelectConversation = useCallback(
        (nextId: number) => navigate(`/chat/${nextId}${query}`),
        [navigate, query],
    );

    const handleOpenProject = useCallback(
        (project: { id: number }) => navigate(`/chat?project=${project.id}`),
        [navigate],
    );

    const handleConversationsChanged = useCallback(() => refreshResources("/conversations"), []);

    return (
        <Chat
            // A new workflow or a different project starts chat from a clean state.
            key={`${pending.id}:${projectId ?? "all"}`}
            onLogout={logout}
            initialWorkflow={pending.workflow}
            onWorkflowStarted={clearWorkflow}
            projectId={projectId}
            routeConversationId={conversationId}
            onConversationChange={handleConversationChange}
            onSelectConversation={handleSelectConversation}
            onConversationsChanged={handleConversationsChanged}
            onOpenProject={handleOpenProject}
            onLeaveProject={() => navigate("/chat")}
        />
    );
}
