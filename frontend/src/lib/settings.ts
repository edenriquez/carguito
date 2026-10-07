/**
 * User settings — what the user has chosen, not what they have.
 *
 * Two kinds of preference live here:
 *
 * - **App-wide** (`windows`, `lastWindow`, `editorMode`): things no single
 *   card owns. They stay typed fields; `windows` is edited from the period
 *   row itself in editor mode, `lastWindow` is written as the user navigates.
 * - **Per-panel** (`panels`): each card's own configuration, stored under an
 *   opaque id. This file deliberately does NOT know what a panel's keys mean —
 *   the component declares its defaults and reads them through
 *   `usePanelSettings`, so adding a control never touches this module.
 *
 * The user customizes what shows and which periods exist, never layout.
 *
 * Persistence hides behind `SettingsStore`, async on purpose even though
 * localStorage is sync — when the store becomes a backend endpoint, no
 * caller changes. No React in this file.
 */

import {
    isCustomRange,
    isWindowId,
    WINDOW_VOCABULARY,
    type CustomRange,
    type WindowId,
} from "./window";

export const SETTINGS_VERSION = 3;
export const SETTINGS_STORAGE_KEY = "carguito.settings";

/** A panel's stored config. Values are primitives: anything richer would need
 *  a schema here, which is exactly the coupling `panels` exists to avoid. */
export type PanelConfig = Record<string, string | number | boolean>;

export type Settings = {
    version: typeof SETTINGS_VERSION;
    /** Reveals each panel's own controls in place. Off by default: the
     *  dashboard should read as a document until the user asks to tune it. */
    editorMode: boolean;
    /** Per-panel configuration, keyed by panel id. Unknown ids are kept —
     *  a panel that isn't mounted right now must not lose its settings. */
    panels: Record<string, PanelConfig>;
    /** Bank names the whole app is scoped to. Empty = todas. Stored as
     *  names (what the user chose); resolved to statement ids at read time
     *  by `lib/banks.ts`, so renames and new uploads stay coherent. */
    banks: string[];
    /** Enabled subset of the window vocabulary, in vocabulary order. */
    windows: WindowId[];
    /** The period the user was last reading, and where the app opens next
     *  time. This replaces an explicit "initial period" setting: remembering
     *  where you were is the same feature with nothing to configure, and it
     *  cannot disagree with the period actually on screen. */
    lastWindow: WindowId;
    /** Two dates the user typed or dragged, when the filter is not on a preset.
     *  `null` means "read `lastWindow`". Kept beside it rather than folded into
     *  it so the preset the user was on survives a custom detour and comes back
     *  when the range is cleared. */
    customRange: CustomRange | null;
};

export const DEFAULT_SETTINGS: Settings = {
    version: SETTINGS_VERSION,
    editorMode: false,
    panels: {},
    banks: [],
    windows: ["15d", "30d", "3m", "all"],
    lastWindow: "30d",
    customRange: null,
};

function isRecord(v: unknown): v is Record<string, unknown> {
    return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * Normalize the parts of a settings object that must stay coherent no matter
 * how they were mangled: windows deduped, vocabulary-ordered, never empty;
 * the default window always one of them.
 */
export function normalizeSettings(s: Settings): Settings {
    const enabled = WINDOW_VOCABULARY.filter((w) => s.windows.includes(w));
    const windows = enabled.length ? enabled : DEFAULT_SETTINGS.windows;
    const lastWindow = windows.includes(s.lastWindow) ? s.lastWindow : windows[0];
    return { ...s, windows, lastWindow };
}

/** Keep only the primitive entries — a panel config is a flat bag by contract,
 *  and a nested object here would survive parsing and then confuse every
 *  reader downstream. */
function parsePanelConfig(raw: unknown): PanelConfig {
    if (!isRecord(raw)) return {};
    const out: PanelConfig = {};
    for (const [k, v] of Object.entries(raw)) {
        if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
            out[k] = v;
        }
    }
    return out;
}

function parsePanels(raw: unknown): Record<string, PanelConfig> {
    if (!isRecord(raw)) return {};
    const out: Record<string, PanelConfig> = {};
    for (const [id, cfg] of Object.entries(raw)) out[id] = parsePanelConfig(cfg);
    return out;
}

/**
 * v1 kept the scatter's income toggle as a top-level field, back when the
 * preferences sheet owned every control. It belongs to the panel now.
 */
function migrateV1(raw: Record<string, unknown>): Record<string, unknown> {
    const showIncome = raw.scatterShowsIncome;
    return {
        ...raw,
        version: 2,
        panels:
            typeof showIncome === "boolean"
                ? { "movimientos.scatter": { showIncome } }
                : {},
    };
}

/**
 * Tolerant parse: anything that isn't a recognizable settings object collapses
 * to defaults — never a throw, because a corrupted localStorage entry must not
 * brick the app. Field-level garbage falls back per field. Older versions are
 * migrated forward; newer ones (a downgrade) fall back to defaults.
 */
/**
 * v3 added the two rolling presets the time filter leads with (15 and 30 days)
 * and the custom range. An existing vocabulary gains the presets rather than
 * being replaced: whatever the user had enabled stays enabled, and the rest of
 * their preferences are untouched.
 */
function migrateV2(raw: Record<string, unknown>): Record<string, unknown> {
    const had = Array.isArray(raw.windows) ? raw.windows.map(String) : [];
    return {
        ...raw,
        version: SETTINGS_VERSION,
        windows: Array.from(new Set([...had, "15d", "30d"])),
        customRange: null,
    };
}

export function parseSettings(raw: unknown): Settings {
    if (!isRecord(raw)) return DEFAULT_SETTINGS;

    let input = raw.version === 1 ? migrateV1(raw) : raw;
    if (input.version === 2) input = migrateV2(input);
    if (input.version !== SETTINGS_VERSION) return DEFAULT_SETTINGS;

    const windows = Array.isArray(input.windows)
        ? (input.windows.filter((w): w is WindowId => isWindowId(String(w))) as WindowId[])
        : DEFAULT_SETTINGS.windows;

    return normalizeSettings({
        version: SETTINGS_VERSION,
        editorMode:
            typeof input.editorMode === "boolean"
                ? input.editorMode
                : DEFAULT_SETTINGS.editorMode,
        panels: parsePanels(input.panels),
        banks: Array.isArray(input.banks)
            ? (input.banks.filter((b) => typeof b === "string") as string[])
            : DEFAULT_SETTINGS.banks,
        windows,
        // `defaultWindow` is the pre-rename name of this field; read it so an
        // existing store keeps opening where the user left it.
        lastWindow: isWindowId(String(input.lastWindow ?? input.defaultWindow))
            ? ((input.lastWindow ?? input.defaultWindow) as WindowId)
            : DEFAULT_SETTINGS.lastWindow,
        customRange: isCustomRange(input.customRange) ? input.customRange : null,
    });
}

/**
 * Widen the literal types TypeScript infers from an inline defaults object:
 * `{ showIncome: false }` infers `false`, and a config the user can't set to
 * `true` is not a setting. Panels get the primitive type back.
 */
export type WidenConfig<T extends PanelConfig> = {
    [K in keyof T]: T[K] extends boolean
        ? boolean
        : T[K] extends number
          ? number
          : T[K] extends string
            ? string
            : T[K];
};

/**
 * Resolve a panel's effective config: the component's declared defaults,
 * overridden by stored values of the *same type*. A stored key whose type no
 * longer matches (the control changed shape) falls back to the default rather
 * than handing the component a value it can't use.
 */
export function resolvePanelConfig<T extends PanelConfig>(
    stored: PanelConfig | undefined,
    defaults: T
): T {
    if (!stored) return defaults;
    const out = { ...defaults };
    for (const key of Object.keys(defaults) as (keyof T & string)[]) {
        const v = stored[key];
        if (v !== undefined && typeof v === typeof defaults[key]) {
            out[key] = v as T[typeof key];
        }
    }
    return out;
}

/** Write a patch into one panel's config, leaving every other panel alone. */
export function withPanelConfig(
    settings: Settings,
    panelId: string,
    patch: PanelConfig
): Settings {
    return {
        ...settings,
        panels: {
            ...settings.panels,
            [panelId]: { ...settings.panels[panelId], ...patch },
        },
    };
}

/** The seam that later becomes a backend endpoint. */
export interface SettingsStore {
    /** `null` means "nothing stored" — first run, so defaults apply. */
    load(): Promise<Settings | null>;
    save(settings: Settings): Promise<void>;
}

export const localSettingsStore: SettingsStore = {
    async load() {
        if (typeof window === "undefined") return null;
        const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
        if (raw === null) return null;
        try {
            return parseSettings(JSON.parse(raw));
        } catch {
            return DEFAULT_SETTINGS;
        }
    },
    async save(settings) {
        if (typeof window === "undefined") return;
        window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
    },
};
