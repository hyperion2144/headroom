/**
 * Headroom Proxy Extension for OMP
 *
 * Intercepts LLM API requests by monkey-patching globalThis.fetch.
 * Auto-discovers provider hosts from OMP's models.yml and models.db
 * so ALL providers (configured + built-in) are routed through the proxy.
 */
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import { readFileSync, existsSync } from "fs";
import { join } from "path";
import { homedir } from "os";

const PROXY_URL = process.env.HEADROOM_PROXY_URL || `http://127.0.0.1:${parseInt(process.env.HEADROOM_PROXY_PORT ?? "8787", 10)}`;

const AGENT_DIR = process.env.PI_CODING_AGENT_DIR || process.env.OMP_CODING_AGENT_DIR || join(homedir(), ".omp", "agent");
const MODELS_YML = join(AGENT_DIR, "models.yml");
const MODELS_DB = join(AGENT_DIR, "models.db");

const PORT = parseInt(process.env.HEADROOM_PROXY_PORT ?? "8787", 10);
const PROXY_URL = `http://127.0.0.1:${PORT}`;

/** Extract all provider hosts from models.yml (configured providers). */
function parseHostsFromYml(): string[] {
  try {
    const raw = readFileSync(MODELS_YML, "utf-8");
    const hosts: string[] = [];
    // Naive YAML parsing: find baseUrl lines and extract hostname
    for (const line of raw.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("baseUrl:")) continue;
      const urlStr = trimmed.slice(8).trim().replace(/['"]/g, "");
      try {
        const host = new URL(urlStr).hostname;
        if (host && host !== "127.0.0.1" && host !== "localhost") hosts.push(host);
      } catch { /* skip malformed */ }
    }
    return hosts;
  } catch {
    return [];
  }
}

/** Extract all provider hosts from models.db (built-in + configured providers). */
function parseHostsFromDb(): string[] {
  try {
    if (!existsSync(MODELS_DB)) return [];
    // bun:sqlite is available because OMP runs on Bun
    const { Database } = require("bun:sqlite") as unknown as {
      Database: new (path: string) => {
        query: (sql: string) => {
          all: () => Array<Record<string, unknown>>;
        };
      };
    };
    const db = new Database(MODELS_DB);
    const hosts: string[] = [];
    // model_cache table stores models as JSON in the `models` column
    const rows = db.query("SELECT models FROM model_cache").all() as Array<{ models: string }>;
    for (const row of rows) {
      try {
        const models = JSON.parse(row.models);
        if (!Array.isArray(models)) continue;
        for (const model of models) {
          const url = model?.baseUrl;
          if (typeof url !== "string" || !url) continue;
          try {
            const host = new URL(url).hostname;
            if (host && host !== "127.0.0.1" && host !== "localhost") hosts.push(host);
          } catch { /* skip malformed url */ }
        }
      } catch { /* skip bad json */ }
    }
    db.close();
    return hosts;
  } catch {
    return [];
  }
}

/** Build the provider host suffix list from all sources. */
function buildProviderHosts(): string[] {
  const hosts = new Set<string>();
  for (const h of parseHostsFromYml()) hosts.add(h);
  for (const h of parseHostsFromDb()) hosts.add(h);
  return [...hosts].filter(Boolean);
}

export default function headroomProxy(_pi: ExtensionAPI) {
  const providerHosts = buildProviderHosts();

  // Log discovered hosts so we can debug if something is missing
  // (log to stderr, which OMP captures)
  console.error(`[HEADROOM-EXT] Discovered ${providerHosts.length} provider hosts: ${providerHosts.join(", ")}`);

  const originalFetch = globalThis.fetch.bind(globalThis);

  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const urlStr =
      typeof input === "string" ? input :
      input instanceof URL ? input.href :
      input.url;
    let url: URL;
    try {
      url = new URL(urlStr);
    } catch {
      return originalFetch(input, init);
    }

    // Skip requests already going to proxy
    if (url.hostname === "127.0.0.1" || url.hostname === "localhost") {
      return originalFetch(input, init);
    }

    // Check against discovered provider hosts
    const isProviderHost = providerHosts.some(host => url.hostname === host || url.hostname.endsWith("." + host));
    if (!isProviderHost) {
      return originalFetch(input, init);
    }

    const path = url.pathname;
    const isAnthropicFormat = path.includes("/v1/messages");
    const isOpenAIFormat =
      path.includes("/chat/completions") ||
      path.includes("/v1/completions") ||
      path.includes("/v1/embeddings");

    let proxyPath: string;
    let headroomBaseUrl: string;

    if (isAnthropicFormat) {
      proxyPath = "/v1/messages";
      const messagesIdx = path.indexOf("/v1/messages");
      headroomBaseUrl = url.origin + (messagesIdx > 0 ? path.slice(0, messagesIdx) : "");
    } else if (isOpenAIFormat) {
      proxyPath = "/v1/chat/completions";
      headroomBaseUrl = url.origin;
    } else {
      proxyPath = path;
      headroomBaseUrl = url.origin;
    }

    const proxyUrl = `${PROXY_URL}${proxyPath}${url.search}`;
    const origHeaders = new Headers(init?.headers || {});
    origHeaders.set("x-headroom-base-url", headroomBaseUrl);

    if (isOpenAIFormat) {
      origHeaders.set("x-headroom-original-path", path);
    }

    return originalFetch(proxyUrl, { ...init, headers: origHeaders });
  };
}
