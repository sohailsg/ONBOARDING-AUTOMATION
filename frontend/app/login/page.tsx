"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

/** MVP SSO stub: picks a role cookie. Prod replaces with OIDC → httpOnly JWT. */
function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") ?? "/hub";
  const [role, setRole] = useState("employee");
  const [error, setError] = useState("");

  async function signIn() {
    setError("");
    try {
      // SSO stub: backend binds the role to a real profile and returns the
      // dev credential the API accepts (Authorization header, see lib/api).
      const { api, setApiToken } = await import("@/lib/api");
      const session = await api.devLogin(role);
      setApiToken(session.token);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Sign-in failed — is the API up?",
      );
      return;
    }
    document.cookie = `ob_role=${role}; path=/; max-age=86400; samesite=lax`;
    router.push(next);
  }

  return (
    <main id="main" className="mx-auto max-w-md px-4 py-16 motion-safe:animate-rise">
      <p className="text-xs font-semibold uppercase tracking-[0.3em] text-cyan-300/80">
        Airlock
      </p>
      <h1 className="title-gradient mt-2 text-3xl font-bold">Sign in</h1>
      {params.get("error") === "forbidden" && (
        <p role="alert" className="mt-2 text-sm text-red-300">
          Forbidden — contact HR.
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-300">
          {error}
        </p>
      )}
      <div className="card card-hover mt-4 space-y-3">
        <label className="block text-sm font-medium" htmlFor="role">
          Role (SSO stub)
        </label>
        <select
          id="role"
          className="input"
          value={role}
          onChange={(e) => setRole(e.target.value)}
        >
          <option value="employee">Employee</option>
          <option value="hr_admin">HR admin</option>
        </select>
        <button className="btn-primary w-full" onClick={signIn}>
          Continue
        </button>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main id="main" className="mx-auto max-w-md px-4 py-16"><p>Loading…</p></main>}>
      <LoginForm />
    </Suspense>
  );
}
