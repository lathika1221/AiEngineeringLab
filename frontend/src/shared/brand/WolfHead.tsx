import { useEffect, useId, useRef } from "react";
import "./WolfHead.css";

/** `offline` is the disconnected state: eyes dim and nothing moves. */
export type WolfMood = "idle" | "thinking" | "success" | "error" | "offline";

type WolfHeadProps = {
    /** Rendered width and height in pixels. */
    size?: number;
    mood?: WolfMood;
    /** Adds the blue halo behind the head. Use for large hero placements only. */
    halo?: boolean;
    /**
     * Adds a metallic sheen and layered depth that shift slightly with the pointer.
     * For hero placements. Does nothing under reduced motion or on touch screens.
     */
    depth?: boolean;
    /** Accessible name. Leave empty when the head is decorative. */
    title?: string;
    className?: string;
};

/*
 * The LATZ wolf head: front-facing, faceted navy and silver metal, electric-blue eyes.
 *
 * This is a vector mark drawn in code so it stays sharp at every size and can react
 * (thinking, success, error) through CSS. It stands in for the final 3D render.
 * See frontend/docs/LATZ_FRONTEND.md for the asset brief and how to swap the render in.
 *
 * The left half is drawn once and mirrored. A shadow on the mirrored half gives the
 * head a single light source from the upper left.
 */
export default function WolfHead({
    size = 48,
    mood = "idle",
    halo = false,
    depth = false,
    title,
    className = "",
}: WolfHeadProps) {
    const id = useId();
    const ref = useRef<SVGSVGElement>(null);

    useEffect(() => {
        const element = ref.current;

        if (!depth || !element) {
            return;
        }

        const calm = window.matchMedia("(prefers-reduced-motion: reduce)");
        const touch = window.matchMedia("(pointer: coarse)");

        if (calm.matches || touch.matches) {
            return;
        }

        let frame = 0;

        function move(event: PointerEvent) {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(() => {
                const x = Math.max(-1, Math.min(1, (event.clientX / window.innerWidth - 0.5) * 2));
                const y = Math.max(-1, Math.min(1, (event.clientY / window.innerHeight - 0.5) * 2));

                element?.style.setProperty("--wolf-x", x.toFixed(3));
                element?.style.setProperty("--wolf-y", y.toFixed(3));
            });
        }

        window.addEventListener("pointermove", move, { passive: true });

        return () => {
            window.removeEventListener("pointermove", move);
            cancelAnimationFrame(frame);
        };
    }, [depth]);
    const steel = `${id}-steel`;
    const silver = `${id}-silver`;
    const navy = `${id}-navy`;
    const deep = `${id}-deep`;
    const eye = `${id}-eye`;
    const glow = `${id}-glow`;
    const half = `${id}-half`;
    const sheen = `${id}-sheen`;
    const clip = `${id}-clip`;
    const outline = "40,10 82,50 100,56 118,50 160,10 174,80 180,118 162,148 120,182 100,192 80,182 38,148 20,118 26,80";

    return (
        <svg
            ref={ref}
            className={`wolf wolf--${mood}${halo ? " wolf--halo" : ""}${depth ? " wolf--depth" : ""} ${className}`.trim()}
            width={size}
            height={size}
            viewBox="0 0 200 200"
            role={title ? "img" : undefined}
            aria-label={title}
            aria-hidden={title ? undefined : true}
            focusable="false"
        >
            <defs>
                <linearGradient id={silver} x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0" stopColor="#f2f6fc" />
                    <stop offset="1" stopColor="#8fa3c6" />
                </linearGradient>
                <linearGradient id={steel} x1="0" y1="0" x2="0.6" y2="1">
                    <stop offset="0" stopColor="#7d93bb" />
                    <stop offset="1" stopColor="#3a517f" />
                </linearGradient>
                <linearGradient id={navy} x1="0" y1="0" x2="0.4" y2="1">
                    <stop offset="0" stopColor="#2b467c" />
                    <stop offset="1" stopColor="#14254a" />
                </linearGradient>
                <linearGradient id={deep} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor="#13234a" />
                    <stop offset="1" stopColor="#070f24" />
                </linearGradient>
                <radialGradient id={eye} cx="0.5" cy="0.5" r="0.6">
                    <stop offset="0" stopColor="#ffffff" />
                    <stop offset="0.45" className="wolf__eye-mid" />
                    <stop offset="1" className="wolf__eye-edge" />
                </radialGradient>
                <linearGradient id={sheen} x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0" stopColor="#ffffff" stopOpacity="0" />
                    <stop offset="0.5" stopColor="#ffffff" stopOpacity="0.32" />
                    <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
                </linearGradient>
                <clipPath id={clip}>
                    <polygon points={outline} />
                </clipPath>
                <filter id={glow} x="-80%" y="-80%" width="260%" height="260%">
                    <feGaussianBlur stdDeviation="5" />
                </filter>

                <g id={half}>
                    {/* Ear */}
                    <polygon points="40,10 26,80 54,62" fill={`url(#${navy})`} />
                    <polygon points="40,10 54,62 82,50" fill={`url(#${steel})`} />
                    <polygon points="45,30 53,58 70,50" fill={`url(#${deep})`} />
                    {/* Skull */}
                    <polygon points="82,50 100,56 100,100 86,104" fill={`url(#${silver})`} />
                    <polygon points="54,62 82,50 86,104 40,95" fill={`url(#${steel})`} />
                    <polygon points="26,80 54,62 40,95" fill={`url(#${navy})`} />
                    {/* Cheek */}
                    <polygon points="26,80 40,95 46,124 20,118" fill={`url(#${steel})`} />
                    <polygon points="20,118 46,124 72,160 38,148" fill={`url(#${navy})`} />
                    {/* Eye socket */}
                    <polygon points="40,95 86,104 84,128 46,124" fill={`url(#${deep})`} />
                    {/* Muzzle */}
                    <polygon points="86,104 100,100 100,156 88,158 84,128" fill={`url(#${silver})`} />
                    <polygon points="46,124 84,128 88,158 72,160" fill={`url(#${steel})`} />
                    <polygon points="38,148 72,160 80,182" fill={`url(#${deep})`} />
                    <polygon points="72,160 88,158 100,176 100,192 80,182" fill={`url(#${navy})`} />
                </g>
            </defs>

            {halo && <circle className="wolf__halo" cx="100" cy="104" r="92" />}

            <g className="wolf__head">
                <use href={`#${half}`} />
                <g transform="translate(200 0) scale(-1 1)">
                    <use href={`#${half}`} />
                    <polygon
                        className="wolf__shade"
                        points="40,10 26,80 20,118 38,148 80,182 100,192 100,56 82,50"
                    />
                </g>
                {depth && (
                    <g clipPath={`url(#${clip})`} className="wolf__sheen" aria-hidden="true">
                        <rect x="-10" y="-20" width="70" height="240" fill={`url(#${sheen})`} transform="skewX(-18)" />
                    </g>
                )}
            </g>

            {/* Nose */}
            <polygon points="88,158 112,158 100,176" fill="#060c1c" />
            <polygon points="92,160 108,160 100,164" fill="#3a517f" opacity="0.7" />

            {/* Rim light */}
            <polygon className="wolf__rim" points={outline} />

            {/* Eyes: a soft glow underneath, the lit iris on top */}
            <g className="wolf__eyes">
                <g filter={`url(#${glow})`} className="wolf__eye-glow">
                    <polygon points="50,103 80,111 76,121 58,116" />
                    <polygon points="150,103 120,111 124,121 142,116" />
                </g>
                <polygon points="50,103 80,111 76,121 58,116" fill={`url(#${eye})`} />
                <polygon points="150,103 120,111 124,121 142,116" fill={`url(#${eye})`} />
            </g>
        </svg>
    );
}
