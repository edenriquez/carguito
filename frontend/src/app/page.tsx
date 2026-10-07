"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { isMetricError, queryMetrics } from "@/lib/metrics";
import { windowToPeriod } from "@/lib/window";
import { track } from "@/lib/telemetry";
import { Skeleton } from "@/components/ui";
import { AppChrome } from "@/components/AppChrome";
import { MovimientosHome } from "@/components/movimientos/MovimientosHome";
import { Onboarding } from "@/components/Onboarding";

/**
 * The switch at the root. Two states, one URL:
 * - no data → the Onboarding (the dropzone + OCR review). The pitch lives on
 *   the standalone landing (`landing/`), which is where visitors arrive from;
 *   repeating it here made a convinced visitor read it twice;
 * - has data → the app shell.
 *
 * Which state shows is a claim about the user's data, so it is only ever made
 * from a successful probe:
 * - the probe is year-wide, not window-wide, so the answer doesn't flip when
 *   a narrower window happens to be empty;
 * - a probe *error* falls through to the app, which says "backend
 *   unreachable" per view. Telling a user with three years of statements to
 *   upload their first one is the worse failure.
 */

/**
 * The root is also the address the phone hands out. After a device upload the
 * backend answers `dashboard_url = <web>/?statement=<id>`, so the boundary
 * below is not ceremony: `useSearchParams` opts this tree out of static
 * prerendering, and Next 14 wants that said out loud. The fallback is the same
 * grey beat the probe already shows, so the handoff is invisible.
 */
export default function Home() {
    return (
        <Suspense fallback={<RootSkeleton />}>
            <Root />
        </Suspense>
    );
}

/** Once per session: where this visit came from. */
const ARRIVED_KEY = "carguito.arrived";

function Root() {
    const [hasData, setHasData] = useState<boolean | null>(null);
    const router = useRouter();
    const params = useSearchParams();
    const arrival = params.get("statement");
    // The landing's CTAs arrive as `?utm_source=landing&utm_medium=cta&utm_content=<hero|nav|…>`
    // (or the shorter `?from=landing`). That visitor already clicked "Comenzar".
    const fromLanding =
        params.get("utm_source") === "landing" || params.get("from") === "landing";

    // The landing's CTAs carry `?from=landing` (or UTMs). Recording the origin
    // once per session is what lets "how many visitors actually upload" be a
    // number rather than a feeling. Direct visits are recorded too, as the
    // denominator.
    useEffect(() => {
        try {
            if (sessionStorage.getItem(ARRIVED_KEY) === "1") return;
            sessionStorage.setItem(ARRIVED_KEY, "1");
        } catch {
            // Storage blocked: the event still goes out, possibly twice.
        }
        track("app.arrive", {
            from: params.get("from") ?? params.get("utm_source") ?? "direct",
            utm_medium: params.get("utm_medium") ?? undefined,
            utm_campaign: params.get("utm_campaign") ?? undefined,
            utm_content: params.get("utm_content") ?? undefined,
            referrer: document.referrer ? new URL(document.referrer).host : undefined,
        });
        // Read once on mount, on purpose: later param changes are navigation,
        // not arrivals.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const probe = useCallback(async () => {
        try {
            const batch = await queryMetrics(windowToPeriod("1y"), [
                { key: "probe", metric: "spend_by_category" },
            ]);
            const entry = batch.results.probe;
            setHasData(
                !!entry &&
                    !isMetricError(entry) &&
                    ((entry.meta.source_txn_count ?? 0) > 0 || entry.rows.length > 0)
            );
        } catch {
            setHasData(true);
        }
    }, []);

    useEffect(() => {
        probe();
    }, [probe]);

    /**
     * The `?statement=` deep link is an *arrival*, and the root has no place to
     * point at one document — Movimientos is a ledger, not an archive. So the
     * param is forwarded to Documentos, which owns the per-statement row, and
     * only once the probe says there is data: a link that lands on an empty
     * account still deserves the onboarding, not an empty archive.
     *
     * `replace`, not `push`: Back should return to wherever the phone's browser
     * came from, not to a URL that immediately redirects again.
     */
    useEffect(() => {
        if (hasData && arrival) {
            router.replace(`/documentos?statement=${encodeURIComponent(arrival)}`);
        }
    }, [hasData, arrival, router]);

    // Holding the skeleton through the handoff, rather than painting a full
    // Movimientos that is about to be replaced. One beat of grey beats a flash
    // of the wrong screen.
    if (hasData === null || (hasData && arrival)) {
        // A beat of grey, deliberately not the onboarding hero: flashing
        // "upload your first statement" at someone with data is worse than
        // a skeleton, and worse than a spinner too.
        return <RootSkeleton />;
    }

    if (!hasData) {
        // `onComplete` fires after the review step (or its skip), not after
        // the raw upload — the user confirms what the OCR understood first.
        return <Onboarding onComplete={probe} fromLanding={fromLanding} />;
    }

    return (
        <AppChrome withWindow onDataChanged={probe}>
            <MovimientosHome />
        </AppChrome>
    );
}

/**
 * The waiting shape of the app, at the app's real geometry: the header row
 * (wordmark, three view pills, the archive and upload buttons), the filter
 * rail (banks, period, lecturas), the chart card, the list card. It used to
 * draw a title and three tiles the real view never had, so the swap to real
 * content was a layout jump instead of a fill-in.
 */
function RootSkeleton() {
    return (
        <main className="mx-auto min-h-dvh w-full max-w-page px-5 pb-16 sm:px-8" aria-busy>
            <div className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-3 py-6 sm:grid-cols-[1fr_auto_1fr] sm:py-8">
                <Skeleton className="h-6 w-20 rounded-control" />
                <div className="order-last col-span-2 flex justify-center sm:order-none sm:col-span-1">
                    <Skeleton className="h-11 w-full rounded-control sm:w-[24rem]" />
                </div>
                <div className="flex items-center gap-2 justify-self-end">
                    <Skeleton className="h-9 w-9 rounded-control sm:w-32" />
                    <Skeleton className="h-9 w-20 rounded-control sm:w-40" />
                </div>
            </div>
            <div className="-mt-2 flex flex-wrap items-center gap-2 pb-6">
                <Skeleton className="h-[42px] w-48 rounded-control" />
            </div>
            <div className="space-y-4 sm:space-y-6">
                <div className="rounded-card border border-mist bg-paper p-5 shadow-card sm:p-6">
                    <Skeleton className="h-6 w-44" />
                    <Skeleton className="mt-2 h-4 w-72" />
                    <Skeleton className="mt-4 h-[320px]" />
                </div>
                <div className="rounded-card border border-mist bg-paper p-5 shadow-card sm:p-6">
                    <Skeleton className="h-6 w-40" />
                    <Skeleton className="mt-4 h-11 rounded-control" />
                    <div className="mt-4 space-y-3">
                        {[0, 1, 2, 3].map((i) => (
                            <Skeleton key={i} className="h-12" />
                        ))}
                    </div>
                </div>
            </div>
        </main>
    );
}
