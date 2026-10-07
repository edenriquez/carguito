/**
 * The product was called Tomin, and its localStorage keys still carry that
 * prefix in browsers that used it: fijos, tagged incomes and settings live
 * only there, so a rename that just changed the keys would erase them.
 * Each `tomin.*` entry moves to `carguito.*` once; an existing new key wins.
 */
const LEGACY_PREFIX = "tomin.";
const PREFIX = "carguito.";

export function adoptLegacyStorage(): void {
    if (typeof window === "undefined") return;
    try {
        const store = window.localStorage;
        const legacy: string[] = [];
        for (let i = 0; i < store.length; i++) {
            const key = store.key(i);
            if (key?.startsWith(LEGACY_PREFIX)) legacy.push(key);
        }
        for (const key of legacy) {
            const next = PREFIX + key.slice(LEGACY_PREFIX.length);
            const value = store.getItem(key);
            if (value !== null && store.getItem(next) === null) store.setItem(next, value);
            store.removeItem(key);
        }
    } catch {
        // Storage blocked: there is nothing to carry over.
    }
}
