"use client";

import { useEffect, useState } from "react";
import { OPENAPI_HASH } from "@/lib/api";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Rollback §6: client detects OpenAPI hash drift.
 * Fail-open: if the gateway doesn't expose /openapi.json (or is
 * unreachable), no banner is shown — server is the source of truth.
 */
export function ApiVersionBanner() {
  const [drift, setDrift] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/openapi.json`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((spec) => {
        const v = spec?.info?.version as string | undefined;
        if (!cancelled && v && v !== OPENAPI_HASH) setDrift(v);
      })
      .catch(() => {
        /* offline / undiscoverable — stay silent */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!drift) return null;
  return (
    <p
      role="alert"
      className="border-b border-amber-300/25 bg-amber-400/10 px-4 py-2 text-center text-sm text-amber-200"
    >
      API version mismatch: client built for <code>{OPENAPI_HASH}</code>,
      server reports <code>{drift}</code>. Run{" "}
      <code>npm run gen-api</code> and redeploy.
    </p>
  );
}
