import { useState } from "react";
import "./Auth.css";

type AuthProps = {
    onLogin: () => void;
};

export default function Auth({ onLogin }: AuthProps) {
    const [mode, setMode] = useState<"login" | "register">("login");

    const [username, setUsername] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");

    function switchMode(nextMode: "login" | "register") {
        setMode(nextMode);
        setError("");
        setSuccess("");
        setPassword("");
    }

    async function login() {
        if (!username.trim() || !password) {
            setError("Enter your username and password.");
            return;
        }

        setLoading(true);
        setError("");
        setSuccess("");

        try {
            const formData = new URLSearchParams();

            formData.append("grant_type", "password");
            formData.append("username", username.trim());
            formData.append("password", password);

            const response = await fetch(
                "http://127.0.0.1:8000/auth/login",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/x-www-form-urlencoded",
                    },
                    body: formData,
                },
            );

            if (!response.ok) {
                throw new Error(
                    "Invalid username or password.",
                );
            }

            const data = await response.json();

            localStorage.setItem(
                "access_token",
                data.access_token,
            );

            onLogin();
        } catch (error) {
            setError(
                error instanceof Error
                    ? error.message
                    : "Login failed.",
            );
        } finally {
            setLoading(false);
        }
    }

    async function register() {
        if (!username.trim()) {
            setError("Enter a username.");
            return;
        }

        if (!email.trim()) {
            setError("Enter your email address.");
            return;
        }

        if (!password) {
            setError("Create a password.");
            return;
        }

        if (password.length < 8) {
            setError(
                "Password must contain at least 8 characters.",
            );
            return;
        }

        setLoading(true);
        setError("");
        setSuccess("");

        try {
            const response = await fetch(
                "http://127.0.0.1:8000/auth/register",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        username: username.trim(),
                        email: email.trim(),
                        password,
                    }),
                },
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.detail ||
                    "Unable to create your account.",
                );
            }

            setMode("login");
            setPassword("");

            setSuccess(
                "Account created successfully. You can sign in now.",
            );
        } catch (error) {
            setError(
                error instanceof Error
                    ? error.message
                    : "Registration failed.",
            );
        } finally {
            setLoading(false);
        }
    }

    function handleKeyDown(
        event: React.KeyboardEvent<HTMLInputElement>,
    ) {
        if (event.key === "Enter") {
            if (mode === "login") {
                login();
            } else {
                register();
            }
        }
    }

    return (
        <main className="auth-page">
            <section className="auth-card">
                <div className="auth-mark">
                    🐺
                </div>

                <span className="auth-eyebrow">
                    AIENGINEERINGLAB
                </span>

                <h1>
                    {mode === "login"
                        ? "Welcome back."
                        : "Create your workspace."}
                </h1>

                <p className="auth-description">
                    {mode === "login"
                        ? "Sign in to continue working with LATZ."
                        : "Create your account and start building with LATZ."}
                </p>

                <div className="auth-mode-switch">
                    <button
                        type="button"
                        className={
                            mode === "login"
                                ? "active"
                                : ""
                        }
                        onClick={() =>
                            switchMode("login")
                        }
                    >
                        Sign in
                    </button>

                    <button
                        type="button"
                        className={
                            mode === "register"
                                ? "active"
                                : ""
                        }
                        onClick={() =>
                            switchMode("register")
                        }
                    >
                        Create account
                    </button>
                </div>

                <div className="auth-form">
                    <label>
                        Username
                    </label>

                    <input
                        value={username}
                        onChange={(event) =>
                            setUsername(
                                event.target.value,
                            )
                        }
                        onKeyDown={handleKeyDown}
                        placeholder="Choose a username"
                        autoComplete="username"
                    />

                    {mode === "register" && (
                        <>
                            <label>
                                Email
                            </label>

                            <input
                                type="email"
                                value={email}
                                onChange={(event) =>
                                    setEmail(
                                        event.target.value,
                                    )
                                }
                                onKeyDown={
                                    handleKeyDown
                                }
                                placeholder="Enter your email"
                                autoComplete="email"
                            />
                        </>
                    )}

                    <label>
                        Password
                    </label>

                    <input
                        type="password"
                        value={password}
                        onChange={(event) =>
                            setPassword(
                                event.target.value,
                            )
                        }
                        onKeyDown={handleKeyDown}
                        placeholder={
                            mode === "register"
                                ? "Create a password"
                                : "Enter your password"
                        }
                        autoComplete={
                            mode === "register"
                                ? "new-password"
                                : "current-password"
                        }
                    />

                    {error && (
                        <div className="auth-error">
                            {error}
                        </div>
                    )}

                    {success && (
                        <div className="auth-success">
                            {success}
                        </div>
                    )}

                    <button
                        onClick={
                            mode === "login"
                                ? login
                                : register
                        }
                        disabled={loading}
                    >
                        {loading
                            ? mode === "login"
                                ? "Signing in..."
                                : "Creating account..."
                            : mode === "login"
                                ? "Sign in"
                                : "Create account"}
                    </button>
                </div>

                <div className="auth-footer">
                    LATZ · Your engineering companion
                </div>
            </section>
        </main>
    );
}