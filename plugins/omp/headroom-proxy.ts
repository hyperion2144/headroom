/**
 * Headroom Proxy Extension for OMP
 *
 * Intercepts LLM API requests and rewrites the baseUrl to the Headroom proxy,
 * adding the original upstream URL as the `x-headroom-base-url` header so the
 * proxy can forward the request to the correct provider.
 *
 * The proxy port is read from the `HEADROOM_PROXY_PORT` environment variable
 * (default: 8787).
 */

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

export default function headroomProxy(pi: ExtensionAPI) {
  pi.setLabel("Headroom Proxy");

  pi.on("before_provider_request", async (event) => {
    const port = parseInt(process.env.HEADROOM_PROXY_PORT ?? "8787", 10);
    const proxyUrl = `http://127.0.0.1:${port}`;

    // The event payload contains the provider request details.
    // We need to rewrite the baseUrl and add the x-headroom-base-url header.
    const request = event as Record<string, unknown>;

    // Get the original base URL from the request
    const originalBaseUrl = (request.baseUrl as string) || (request.url as string) || "";
    if (!originalBaseUrl) {
      return; // passthrough if no URL to rewrite
    }

    // Don't rewrite if already pointing at the proxy
    if (originalBaseUrl.startsWith(proxyUrl)) {
      return;
    }

    // Rewrite the baseUrl to the proxy
    request.baseUrl = proxyUrl;
    request.url = undefined; // clear url if set

    // Add the original upstream URL as a header
    const headers = (request.headers as Record<string, string>) || {};
    headers["x-headroom-base-url"] = originalBaseUrl;
    request.headers = headers;

    return request;
  });
}
