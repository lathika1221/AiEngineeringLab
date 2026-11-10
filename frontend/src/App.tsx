import { useEffect, useState } from "react";

import WorkspaceLayout from "./app/layouts/WorkspaceLayout";
import Auth from "./features/auth/Auth";
import Onboarding from "./features/onboarding/Onboarding";

const API_BASE = "http://127.0.0.1:8000";

function isTokenValid(): boolean {
  const token = localStorage.getItem("access_token");

  if (!token) {
    return false;
  }

  try {
    const payload = JSON.parse(atob(token.split(".")[1]));

    if (!payload.exp) {
      return false;
    }

    return payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(isTokenValid);
  const [onboardingRequired, setOnboardingRequired] = useState(false);
  const [checkingOnboarding, setCheckingOnboarding] = useState(isTokenValid);

  const handleLogin = () => {
    setCheckingOnboarding(true);
    setAuthenticated(true);
  };

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    setAuthenticated(false);
    setOnboardingRequired(false);
    setCheckingOnboarding(false);
  };

  useEffect(() => {
    if (!authenticated) {
      return;
    }

    let cancelled = false;

    const token = localStorage.getItem("access_token");

    if (!token) {
      return;
    }

    async function loadOnboarding() {
      try {
        const response = await fetch(`${API_BASE}/users/profile`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        if (cancelled) {
          return;
        }

        if (response.status === 401) {
          localStorage.removeItem("access_token");
          setAuthenticated(false);
          setOnboardingRequired(false);
          return;
        }

        if (response.status === 404) {
          setOnboardingRequired(true);
          return;
        }

        if (!response.ok) {
          setOnboardingRequired(false);
          return;
        }

        const profile = await response.json();

        if (!cancelled) {
          setOnboardingRequired(
            profile.onboarding_completed !== "true",
          );
        }
      } catch {
        if (!cancelled) {
          setOnboardingRequired(false);
        }
      } finally {
        if (!cancelled) {
          setCheckingOnboarding(false);
        }
      }
    }

    void loadOnboarding();

    return () => {
      cancelled = true;
    };
  }, [authenticated]);

  if (!authenticated) {
    return <Auth onLogin={handleLogin} />;
  }

  if (checkingOnboarding) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#07111f",
          color: "#8fa6bd",
        }}
      >
        Preparing your LATZ workspace...
      </div>
    );
  }

  if (onboardingRequired) {
    return (
      <Onboarding
        onComplete={() => {
          setOnboardingRequired(false);
        }}
      />
    );
  }

  return <WorkspaceLayout onLogout={handleLogout} />;
}
