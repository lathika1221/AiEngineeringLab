export interface EngineeringMode {
    id: string;
    title: string;
    description: string;
}

export const engineeringModes: EngineeringMode[] = [
    {
        id: "forge",
        title: "Forge",
        description: "Build software, APIs and AI agents.",
    },
    {
        id: "learn",
        title: "Learn",
        description: "Master new technologies.",
    },
    {
        id: "research",
        title: "Research",
        description: "Analyze papers and datasets.",
    },
    {
        id: "explore",
        title: "Explore",
        description: "Discover new tools and ideas.",
    },
    {
        id: "solve",
        title: "Solve",
        description: "Debug and solve engineering problems.",
    },
];