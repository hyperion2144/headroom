/**
 * Headroom Proxy Extension for OMP
 *
 * Intercepts LLM API requests by monkey-patching globalThis.fetch.
 * Rewrites the request to the correct proxy handler path so streaming works,
 * and sets the x-headroom-base-url / x-headroom-original-path headers
 * so the proxy can reconstruct the full upstream URL.
 */

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

const PORT = parseInt(process.env.HEADROOM_PROXY_PORT ?? "8787", 10);
const PROXY_ORIGIN = `http://127.0.0.1:${PORT}`;

// Known provider hosts to route through the proxy.
const PROVIDER_HOST_SUFFIXES = [
  "anthropic.com",
  "openai.com",
  "minimaxi.com",
  "volces.com",
  "aliyuncs.com",
  "siliconflow.cn",
  "deepseek.com",
  "googleapis.com",
  "aiplatform.googleapis.com",
  "groq.com",
  "together.xyz",
  "cerebras.net",
  "mistral.ai",
  "cohere.ai",
  "perplexity.ai",
];

export default function headroomProxy(_pi: ExtensionAPI) {
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

    // Only intercept known provider hosts
    const isProviderHost = PROVIDER_HOST_SUFFIXES.some(suffix =>
      url.hostname.endsWith(suffix)
    );
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
      // Route to Anthropic handler (/v1/messages).
      // x-headroom-base-url preserves the path prefix (e.g. /anthropic).
      proxyPath = "/v1/messages";
      const messagesIdx = path.indexOf("/v1/messages");
      headroomBaseUrl = url.origin + (messagesIdx > 0 ? path.slice(0, messagesIdx) : "");
    } else if (isOpenAIFormat) {
      // Route to OpenAI handler (/v1/chat/completions).
      // x-headroom-original-path preserves the full path for reconstruction.
      proxyPath = "/v1/chat/completions";
      headroomBaseUrl = url.origin;
    } else {
      proxyPath = path;
      headroomBaseUrl = url.origin;
    }

    const proxyUrl = `${PROXY_ORIGIN}${proxyPath}${url.search}`;
    const origHeaders = new Headers(init?.headers || {});
    origHeaders.set("x-headroom-base-url", headroomBaseUrl);

    if (isOpenAIFormat) {
      origHeaders.set("x-headroom-original-path", path);
    }

    return originalFetch(proxyUrl, { ...init, headers: origHeaders });
  };
}
