"use client";

import type { ReactNode } from "react";
import { SettingsProvider } from "@/components/settings/SettingsProvider";
import { TimeWindowProvider } from "@/components/TimeWindowProvider";
import { WorkspaceProvider } from "@/components/workspace/WorkspaceProvider";
import { LecturaProvider } from "@/components/lectura/LecturaProvider";
import { MovimientosSearchProvider } from "@/components/movimientos/MovimientosSearchProvider";
import { adoptLegacyStorage } from "@/lib/legacyStorage";

// Before any provider reads its key.
adoptLegacyStorage();

/**
 * App-wide state, mounted once above every route.
 *
 * Settings and the time window used to be created inside `AppChrome`, which
 * each page mounts on its own — so every navigation rebuilt them, and the
 * period the user was reading survived only by being written to storage and
 * read back. Here they outlive the page.
 */
export function Providers({ children }: { children: ReactNode }) {
    return (
        <SettingsProvider>
            <TimeWindowProvider>
                <WorkspaceProvider>
                    <LecturaProvider>
                        <MovimientosSearchProvider>{children}</MovimientosSearchProvider>
                    </LecturaProvider>
                </WorkspaceProvider>
            </TimeWindowProvider>
        </SettingsProvider>
    );
}
