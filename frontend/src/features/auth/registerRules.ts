/**
 * Client-side registration rules. They mirror the backend (`UserCreate` in
 * src/schemas/user.py) exactly, so a form that passes here is not rejected by the
 * server for the same reason. Pure functions, testable with `npm test`.
 */

export const MIN_PASSWORD_LENGTH = 12;
export const MAX_PASSWORD_BYTES = 72;
export const MIN_USERNAME_LENGTH = 3;
export const MAX_USERNAME_LENGTH = 100;

export type RegistrationInput = { username: string; email: string; password: string };

/** The first problem with the form, as a message safe to show, or null when it can be submitted. */
export function validateRegistration({ username, email, password }: RegistrationInput): string | null {
    const name = username.trim();

    if (!name) {
        return "Enter a username.";
    }

    if (name.length < MIN_USERNAME_LENGTH || name.length > MAX_USERNAME_LENGTH) {
        return `Username must be ${MIN_USERNAME_LENGTH} to ${MAX_USERNAME_LENGTH} characters.`;
    }

    if (name.includes("@")) {
        return "Username can't contain @. Your email address is entered separately.";
    }

    // eslint-disable-next-line no-control-regex
    if (/[\s\u0000-\u001f\u007f]/.test(name)) {
        return "Username can't contain spaces.";
    }

    if (!email.trim()) {
        return "Enter your email address.";
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
        return "Enter a valid email address.";
    }

    if (!password) {
        return "Create a password.";
    }

    if (password.length < MIN_PASSWORD_LENGTH) {
        return `Password must contain at least ${MIN_PASSWORD_LENGTH} characters.`;
    }

    if (new TextEncoder().encode(password).length > MAX_PASSWORD_BYTES) {
        return `Password is too long. Use at most ${MAX_PASSWORD_BYTES} bytes (about ${MAX_PASSWORD_BYTES} plain characters).`;
    }

    return null;
}
