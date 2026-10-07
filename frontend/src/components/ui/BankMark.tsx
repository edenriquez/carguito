import { colors } from "@/design/tokens";

/**
 * Carguito's mark: a small bank that smiles. The building is Signal and the
 * face is Soot, so it reads the same on paper, on Night and on its own tile.
 */
export function BankMark({
    size = 16,
    x,
    y,
    className,
}: {
    size?: number;
    /** Position when nested inside another SVG. */
    x?: number;
    y?: number;
    className?: string;
}) {
    return (
        <svg width={size} height={size} x={x} y={y} viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
            <path d="M12 2.5l9.4 5.6a.9.9 0 0 1-.46 1.67H3.06a.9.9 0 0 1-.46-1.67z" fill={colors.signal} />
            <rect x="4" y="10.8" width="16" height="8" rx="1.6" fill={colors.signal} />
            <rect x="2.5" y="19.6" width="19" height="2" rx="1" fill={colors.signal} />
            <circle cx="9" cy="13.8" r="1.2" fill={colors.soot} />
            <circle cx="15" cy="13.8" r="1.2" fill={colors.soot} />
            <path d="M9.5 16.2q2.5 2 5 0" stroke={colors.soot} strokeWidth="1.4" strokeLinecap="round" />
        </svg>
    );
}
