/** Time zone helpers. The list comes from the browser, so it always matches what it can format. */

export function deviceTimezone(): string {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    } catch {
        return "UTC";
    }
}

/** Every zone the browser knows, plus UTC and the saved value if the browser does not list it. */
export function listTimezones(saved?: string | null): string[] {
    let zones: string[];

    try {
        zones = Intl.supportedValuesOf("timeZone");
    } catch {
        zones = [];
    }

    const all = new Set<string>(["UTC", deviceTimezone(), ...zones]);

    if (saved) {
        all.add(saved);
    }

    return [...all].sort((a, b) => a.localeCompare(b));
}

/** "Asia/Kolkata" → "Asia / Kolkata", "America/Port_of_Spain" → "America / Port of Spain". */
export function timezoneLabel(zone: string): string {
    return zone.replace(/_/g, " ").replace(/\//g, " / ");
}
