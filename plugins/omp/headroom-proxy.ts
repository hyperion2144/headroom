/**
 * Headroom Proxy Extension for OMP
 * Intercepts LLM API fetch calls and routes through Headroom proxy.
 * Auto-discovers provider hosts from models.yml and models.db.
 */

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { homedir } from "os";

const PROXY_URL = process.env.HEADROOM_PROXY_URL || "http://127.0.0.1:8787";

const AGENT_DIR = process.env.PI_CODING_AGENT_DIR || process.env.OMP_CODING_AGENT_DIR || join(homedir(), ".omp", "agent");

/** Extract hostnames from models.yml baseUrl lines. */
function hostsFromModelsYml(): string[] {
  try {
    const path = join(AGENT_DIR, "models.yml");
    if (!existsSync(path)) return [];
    const hosts: string[] = [];
    for (const line of readFileSync(path, "utf-8").split("\n")) {
      const t = line.trim();
      if (!t.startsWith("baseUrl:")) continue;
      try { hosts.push(new URL(t.slice(8).trim().replace(/['"]/g, "")).hostname); } catch { /* skip */ }
    }
    return hosts;
  } catch { return []; }
}


/** Extract hostnames from models.db by regex-scanning for "baseUrl":"..." in JSON cells. */
function hostsFromModelsDb(): string[] {
  try {
    const path = join(AGENT_DIR, "models.db");
    if (!existsSync(path)) return [];
    const hosts: string[] = [];
    // SQLite is binary; read as latin1 so every byte is preserved as a character.
    const raw = new TextDecoder("latin1").decode(readFileSync(path));
    const re = /"baseUrl"\s*:\s*"([^"]+)"/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(raw)) !== null) {
      try { hosts.push(new URL(m[1]).hostname); } catch { /* skip */ }
    }
    return [...new Set(hosts)];
  } catch { return []; }
}
export default function headroomProxy(pi: ExtensionAPI) {
  // Build provider host list from all sources
  const providerHosts = [...new Set([
    ...hostsFromModelsYml(),
    ...hostsFromModelsDb(),
  ])].filter(h => h && h !== "127.0.0.1" && h !== "localhost");

  pi.setLabel(`Headroom Proxy (${providerHosts.length} hosts)`);
  const originalFetch = globalThis.fetch.bind(globalThis);

  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const urlStr =
      typeof input === "string" ? input :
      input instanceof URL ? input.href : input.url;
    let url: URL;
    try { url = new URL(urlStr); } catch { return originalFetch(input, init); }

    if (url.hostname === "127.0.0.1" || url.hostname === "localhost") {
      return originalFetch(input, init);
    }

    if (!providerHosts.some(h => url.hostname === h || url.hostname.endsWith("." + h))) {
      return originalFetch(input, init);
    }

    const path = url.pathname;
    const isAnthropicFormat = path.includes("/v1/messages");
    const isOpenAIFormat = path.includes("/chat/completions") || path.includes("/v1/completions") || path.includes("/v1/embeddings");

    let proxyPath: string;
    let headroomBaseUrl: string;

    if (isAnthropicFormat) {
      proxyPath = "/v1/messages";
      const idx = path.indexOf("/v1/messages");
      headroomBaseUrl = url.origin + (idx > 0 ? path.slice(0, idx) : "");
    } else if (isOpenAIFormat) {
      proxyPath = "/v1/chat/completions";
      headroomBaseUrl = url.origin;
    } else {
      proxyPath = path;
      headroomBaseUrl = url.origin;
    }

    const proxyUrl = `${PROXY_URL}${proxyPath}${url.search}`;
    const headers = new Headers(init?.headers || {});
    headers.set("x-headroom-base-url", headroomBaseUrl);
    if (isOpenAIFormat) headers.set("x-headroom-original-path", path);

    return originalFetch(proxyUrl, { ...init, headers });
  };
}
