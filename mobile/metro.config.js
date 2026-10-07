// Metro configuration for Carguito mobile.
//
// The only non-default piece is a resolver shim for Node built-ins.
//
// Two of the pure-JS dependencies used by the on-device extraction path carry
// Node-only branches that are dead under Hermes but are still *statically
// resolved* by Metro while bundling:
//
//   - pdfjs-dist (legacy build) does `await import("fs" | "http" | "https" |
//     "url" | "canvas" | "path2d")` inside `if (isNodeJS) { … }` blocks.
//   - tweetnacl and js-sha256 do `require("crypto")` when they think they are
//     running on Node.
//
// `isNodeJS` is false in React Native (`process + "" !== "[object process]"`),
// so none of that code ever runs — but without this shim Metro fails the whole
// bundle with "Unable to resolve module fs". The shim is scoped to the exact
// packages that need it, so a genuine missing dependency anywhere else still
// surfaces as a normal resolution error.
const path = require("path");
const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);

const NODE_BUILTINS = new Set(["fs", "http", "https", "url", "crypto", "path2d", "canvas"]);
const SHIMMED_PACKAGES = ["pdfjs-dist", "tweetnacl", "js-sha256"];
const EMPTY_MODULE = path.resolve(__dirname, "src/lib/empty-module.js");

const defaultResolveRequest = config.resolver.resolveRequest;

config.resolver.resolveRequest = (context, moduleName, platform) => {
    const origin = context.originModulePath || "";
    if (NODE_BUILTINS.has(moduleName) && SHIMMED_PACKAGES.some((pkg) => origin.includes(`node_modules${path.sep}${pkg}${path.sep}`))) {
        return { type: "sourceFile", filePath: EMPTY_MODULE };
    }
    return (defaultResolveRequest ?? context.resolveRequest)(context, moduleName, platform);
};

module.exports = config;
