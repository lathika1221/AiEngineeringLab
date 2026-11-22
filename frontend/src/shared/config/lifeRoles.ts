/** The roles LATZ suggests during onboarding and on the profile page. Users can also add their own. */
export type RoleOption = {
    role: string;
    description: string;
};

export const ROLE_OPTIONS: RoleOption[] = [
    {
        role: "Student",
        description:
            "Learning, studying, building skills and preparing for your future.",
    },
    {
        role: "Engineer",
        description:
            "Building systems, products, software or technical solutions.",
    },
    {
        role: "Researcher",
        description:
            "Working on research, experiments, publications or discoveries.",
    },
    {
        role: "Entrepreneur",
        description:
            "Building a business, startup, product or venture.",
    },
    {
        role: "Faculty",
        description:
            "Teaching, mentoring, research or academic responsibilities.",
    },
    {
        role: "Parent",
        description:
            "Managing family responsibilities, routines and priorities.",
    },
    {
        role: "Freelancer",
        description:
            "Working independently with clients, projects or services.",
    },
    {
        role: "Professional",
        description:
            "Managing a professional career, workplace and growth.",
    },
];
