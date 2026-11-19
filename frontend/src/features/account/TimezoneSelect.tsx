import { useMemo } from "react";
import { listTimezones, timezoneLabel } from "./timezones";

type TimezoneSelectProps = {
    id: string;
    value: string;
    onChange: (zone: string) => void;
    disabled?: boolean;
};

/** A select of every time zone the browser knows, with "Not set" first. */
export default function TimezoneSelect({ id, value, onChange, disabled }: TimezoneSelectProps) {
    const zones = useMemo(() => listTimezones(value), [value]);

    return (
        <select
            id={id}
            className="input"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            disabled={disabled}
        >
            <option value="">Not set</option>
            {zones.map((zone) => (
                <option key={zone} value={zone}>
                    {timezoneLabel(zone)}
                </option>
            ))}
        </select>
    );
}
