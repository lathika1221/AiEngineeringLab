import { useId, useState } from "react";
import type { FormEvent } from "react";
import { ArrowLeft } from "lucide-react";
import { API_BASE } from "../../shared/api/client";
import { submitLogin } from "./loginRequest";
import { usePageTitle } from "../../shared/hooks/usePageTitle";
import WolfHead from "../../shared/brand/WolfHead";
import Button from "../../shared/ui/Button";
import Notice from "../../shared/ui/Notice";
import "./Auth.css";

type AuthMode = "login" | "register";

type AuthProps = {
    /** Which form is showing. Owned by the route (/login or /register). */
    mode: AuthMode;
    onModeChange: (mode: AuthMode) => void;
    /** Receives the access token after a successful sign in. */
    onLogin: (token: string) => void;
    onBack?: () => void;
};

export default function Auth({ mode, onModeChange, onLogin, onBack }: AuthProps) {
    usePageTitle(mode === "login" ? "Sign in" : "Create account");

    const [username, setUsername] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");

    const usernameId = useId();
    const emailId = useId();
    const passwordId = useId();

    function switchMode(nextMode: AuthMode) {
        onModeChange(nextMode);
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
            const result = await submitLogin(fetch, API_BASE, username.trim(), password);

            if (!result.ok) {
                setError(result.message);
                return;
            }

            onLogin(result.token);
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
            setError("Password must contain at least 8 characters.");
            return;
        }

        setLoading(true);
        setError("");
        setSuccess("");

        try {
            const response = await fetch(`${API_BASE}/auth/register`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    username: username.trim(),
                    email: email.trim(),
                    password,
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    typeof data.detail === "string"
                        ? data.detail
                        : "Unable to create your account. Check your details and try again.",
                );
            }

            onModeChange("login");
            setPassword("");

            setSuccess("Account created successfully. You can sign in now.");
        } catch (error) {
            setError(
                error instanceof TypeError
                    ? "Can't reach the LATZ server. Check that the backend is running."
                    : error instanceof Error
                      ? error.message
                      : "Registration failed.",
            );
        } finally {
            setLoading(false);
        }
    }

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();

        if (loading) {
            return;
        }

        if (mode === "login") {
            void login();
        } else {
            void register();
        }
    }

    return (
        <main className="guest">
            {onBack && (
                <button type="button" className="guest__back" onClick={onBack}>
                    <ArrowLeft size={15} aria-hidden="true" />
                    Back
                </button>
            )}

            <section className="guest__card panel panel--lit">
                <div className="auth-brand">
                    <WolfHead size={64} mood={error ? "error" : loading ? "thinking" : "idle"} />
                    <span className="auth-brand__name">LATZ</span>
                </div>

                <h1 className="auth-title">
                    {mode === "login" ? "Welcome back" : "Create your workspace"}
                </h1>

                <p className="auth-description">
                    {mode === "login"
                        ? "Sign in to continue working with LATZ."
                        : "Create an account to start building with LATZ."}
                </p>

                <div className="auth-switch" role="tablist" aria-label="Account">
                    <button
                        type="button"
                        role="tab"
                        aria-selected={mode === "login"}
                        className={mode === "login" ? "active" : ""}
                        onClick={() => switchMode("login")}
                    >
                        Sign in
                    </button>

                    <button
                        type="button"
                        role="tab"
                        aria-selected={mode === "register"}
                        className={mode === "register" ? "active" : ""}
                        onClick={() => switchMode("register")}
                    >
                        Create account
                    </button>
                </div>

                <form className="auth-form" onSubmit={handleSubmit} noValidate>
                    <div className="field">
                        <label className="field__label" htmlFor={usernameId}>
                            Username
                        </label>
                        <input
                            id={usernameId}
                            className="input"
                            value={username}
                            onChange={(event) => setUsername(event.target.value)}
                            placeholder={mode === "register" ? "Choose a username" : "Your username"}
                            autoComplete="username"
                        />
                    </div>

                    {mode === "register" && (
                        <div className="field">
                            <label className="field__label" htmlFor={emailId}>
                                Email
                            </label>
                            <input
                                id={emailId}
                                className="input"
                                type="email"
                                value={email}
                                onChange={(event) => setEmail(event.target.value)}
                                placeholder="you@example.com"
                                autoComplete="email"
                            />
                        </div>
                    )}

                    <div className="field">
                        <label className="field__label" htmlFor={passwordId}>
                            Password
                            {mode === "register" && (
                                <span className="field__hint">At least 8 characters</span>
                            )}
                        </label>
                        <input
                            id={passwordId}
                            className="input"
                            type="password"
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            placeholder={mode === "register" ? "Create a password" : "Your password"}
                            autoComplete={mode === "register" ? "new-password" : "current-password"}
                        />
                    </div>

                    {error && <Notice tone="error">{error}</Notice>}

                    {success && <Notice tone="success">{success}</Notice>}

                    <Button type="submit" variant="primary" size="lg" block busy={loading}>
                        {loading
                            ? mode === "login"
                                ? "Signing in"
                                : "Creating account"
                            : mode === "login"
                              ? "Sign in"
                              : "Create account"}
                    </Button>
                </form>
            </section>
        </main>
    );
}
