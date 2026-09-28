import { cn } from "@/lib/cn";

/**
 * A Fog block at the final geometry, with a slow sheen passing over it.
 *
 * The sheen is what says "still coming" without a spinner: a block that sits
 * perfectly still reads as a decision, a block that breathes reads as a wait.
 * It is the one motion the loading state has, and it stops for users who
 * asked the OS for reduced motion (`globals.css`).
 */
export function Skeleton({
    className,
    width,
    height,
}: {
    className?: string;
    width?: number | string;
    height?: number | string;
}) {
    return (
        <div
            aria-hidden
            style={{ width, height }}
            className={cn("skeleton rounded-card bg-fog", className)}
        />
    );
}

/** Placeholder sized for a chart, so the card doesn't jump when data lands. */
export function ChartSkeleton({ height = 320 }: { height?: number }) {
    return (
        <div
            style={{ height }}
            className="skeleton flex w-full items-end gap-2 rounded-card bg-fog p-4"
            aria-hidden
        />
    );
}
