import { Suspense, lazy } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { Location } from "react-router-dom";
import { apiFetch } from "../shared/api/http";
import type { Profile } from "../shared/api/types";
import WolfHead from "../shared/brand/WolfHead";
import { engineeringModes } from "../shared/config/engineeringModes";
import { useSession } from "./session/context";

/*
 * Every screen is its own chunk, so the first paint only downloads the shell and the
 * page being opened. The chat chunk carries the Markdown renderer; nothing else does.
 */
const Landing = lazy(() => import("../features/landing/Landing"));
const Auth = lazy(() => import("../features/auth/Auth"));
const Onboarding = lazy(() => import("../features/onboarding/Onboarding"));
const WorkspaceLayout = lazy(() => import("./layouts/WorkspaceLayout"));
const MissionControl = lazy(() => import("../features/workspace/MissionControl"));
const ChatRoute = lazy(() => import("../features/chat/ChatRoute"));
const EngineeringWorkspace = lazy(() => import("../features/workspace/EngineeringWorkspace"));
const ExperimentsLab = lazy(() => import("../features/workspace/ExperimentsLab"));
const MemoriesPage = lazy(() => import("../features/workspace/MemoriesPage"));
const GoalsPage = lazy(() => import("../features/workspace/GoalsPage"));
const ProjectDetailPage = lazy(() => import("../features/workspace/ProjectDetailPage"));
const ProfilePage = lazy(() => import("../features/account/ProfilePage"));
const SettingsPage = lazy(() => import("../features/account/SettingsPage"));
const NotFound = lazy(() => import("../features/system/NotFound"));

const HOME = "/mission-control";

function AppLoading({ label }: { label: string }) {
    return (
        <div className="app-loading" role="status">
            <WolfHead size={72} mood="thinking" />
            <span>{label}</span>
        </div>
    );
}

/** Where to send someone after signing in: the page they were trying to reach, or home. */
function destinationAfterLogin(location: Location): string {
    const from: unknown = (location.state as { from?: unknown } | null)?.from;

    return typeof from === "string" && from.startsWith("/") ? from : HOME;
}

/** Landing, sign in and registration. Signed-in users are sent on to the workspace. */
function GuestOnly() {
    const { authenticated } = useSession();
    const location = useLocation();

    if (authenticated) {
        return <Navigate to={destinationAfterLogin(location)} replace />;
    }

    return <Outlet />;
}

/** Everything inside the workspace. Requires a session and a finished onboarding. */
function RequireAuth() {
    const { authenticated, onboarding } = useSession();
    const location = useLocation();

    if (!authenticated) {
        return (
            <Navigate
                to="/login"
                replace
                state={{ from: `${location.pathname}${location.search}` }}
            />
        );
    }

    if (onboarding === "checking") {
        return <AppLoading label="Preparing your LATZ workspace" />;
    }

    if (onboarding === "required") {
        return <Navigate to="/onboarding" replace />;
    }

    return <WorkspaceLayout />;
}

function LandingRoute() {
    const navigate = useNavigate();

    return (
        <Landing onGetStarted={() => navigate("/register")} onSignIn={() => navigate("/login")} />
    );
}

/** One element for both /login and /register, so switching tabs keeps what was typed. */
function AuthRoute() {
    const { login } = useSession();
    const location = useLocation();
    const navigate = useNavigate();

    return (
        <Auth
            mode={location.pathname === "/register" ? "register" : "login"}
            onModeChange={(mode) => navigate(`/${mode}`, { replace: true, state: location.state })}
            onLogin={login}
            onBack={() => navigate("/")}
        />
    );
}

function OnboardingRoute() {
    const { authenticated, onboarding, setProfile } = useSession();
    const navigate = useNavigate();

    if (!authenticated) {
        return <Navigate to="/login" replace state={{ from: "/onboarding" }} />;
    }

    if (onboarding === "checking") {
        return <AppLoading label="Preparing your LATZ workspace" />;
    }

    if (onboarding === "complete") {
        return <Navigate to={HOME} replace />;
    }

    return (
        <Onboarding
            onComplete={() => {
                apiFetch<Profile>("/users/profile")
                    .then(setProfile)
                    .catch(() => navigate(HOME, { replace: true }));
            }}
        />
    );
}

export default function AppRoutes() {
    return (
        <Suspense fallback={<AppLoading label="Loading LATZ" />}>
            <Routes>
                <Route element={<GuestOnly />}>
                    <Route path="/" element={<LandingRoute />} />
                    <Route element={<AuthRoute />}>
                        <Route path="/login" element={null} />
                        <Route path="/register" element={null} />
                    </Route>
                </Route>

                <Route path="/onboarding" element={<OnboardingRoute />} />

                <Route element={<RequireAuth />}>
                    <Route path="/mission-control" element={<MissionControl />} />
                    <Route path="/chat/:conversationId?" element={<ChatRoute />} />
                    <Route path="/projects" element={<EngineeringWorkspace key="projects" mode="projects" />} />
                    <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
                    <Route path="/experiments" element={<ExperimentsLab />} />
                    {engineeringModes.map((mode) => (
                        <Route
                            key={mode.id}
                            path={`/${mode.id}`}
                            element={<EngineeringWorkspace key={mode.id} mode={mode.id} />}
                        />
                    ))}
                    <Route path="/profile" element={<ProfilePage />} />
                    <Route path="/settings" element={<SettingsPage />} />
                    <Route path="/goals" element={<GoalsPage />} />
                    <Route path="/memories" element={<MemoriesPage />} />
                </Route>

                <Route path="*" element={<NotFound />} />
            </Routes>
        </Suspense>
    );
}
