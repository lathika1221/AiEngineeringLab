import { useCallback, useEffect, useState } from "react";

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
    const payload = JSON.parse(
      atob(token.split(".")[1]),
    );

    if (!payload.exp) {
      return false;
    }

    return payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

export default function App() {
  const [authenticated, setAuthenticated] =
    useState(isTokenValid());

  const [onboardingRequired, setOnboardingRequired] =
    useState(false);

  const [checkingOnboarding, setCheckingOnboarding] =
    useState(false);

  const handleLogin = () => {
    setAuthenticated(true);
  };

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    setAuthenticated(false);
    setOnboardingRequired(false);
  };

  const checkOnboarding = useCallback(async () => {
    const token =
      localStorage.getItem("access_token");

    if (!token) {
      return;
    }

    setCheckingOnboarding(true);

    try {
      const response = await fetch(
        `${API_BASE}/users/profile`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );

      if (response.status === 401) {
        handleLogout();
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

      setOnboardingRequired(
        profile.onboarding_completed !== "true",
      );
    } catch {
      setOnboardingRequired(false);
    } finally {
      setCheckingOnboarding(false);
    }
  }, []);

  useEffect(() => {
    if (authenticated) {
      checkOnboarding();
    }
  }, [authenticated, checkOnboarding]);

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

  return (
    <WorkspaceLayout
      onLogout={handleLogout}
    />
  );
}