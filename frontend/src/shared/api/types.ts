/** Shapes returned by the LATZ backend. Field names match the API exactly. */

export type Account = {
    id: number;
    username: string;
    email: string;
};

export type Profile = {
    id: number;
    user_id: number;
    display_name: string | null;
    bio: string | null;
    timezone: string | null;
    onboarding_completed: string;
};

export type LifeRole = {
    id: number;
    role: string;
    description: string | null;
    priority: number;
};

export type Project = {
    id: number;
    name: string;
    description: string | null;
    status: string;
    engine: string | null;
    tech_stack: string | null;
    created_at: string | null;
    updated_at: string | null;
};

export type ProjectInput = {
    name: string;
    description: string | null;
    status: string;
    engine: string | null;
    tech_stack: string | null;
};

export type ConversationCategory = "projects" | "learning" | "experiments" | "research" | "general";

export type Conversation = {
    id: number;
    title: string;
    category: ConversationCategory;
    project_id: number | null;
    created_at: string;
    updated_at: string;
};

export type Goal = {
    id: number;
    title: string;
    description: string | null;
    category: string | null;
    priority: number;
    status: string;
    target_date: string | null;
    created_at: string;
    updated_at: string;
};

export type MemoryType = "preference" | "fact" | "project";

export type Memory = {
    id: number;
    memory_type: MemoryType;
    content: string;
    created_at: string;
    updated_at: string;
};
