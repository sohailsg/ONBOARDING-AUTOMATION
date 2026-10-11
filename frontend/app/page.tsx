import Link from "next/link";

export default function Home() {
  return (
    <main id="main" className="mx-auto max-w-3xl px-4 py-16 motion-safe:animate-rise">
      <p className="text-xs font-semibold uppercase tracking-[0.3em] text-cyan-300/80">
        Mission control
      </p>
      <h1 className="title-gradient mt-2 text-4xl font-bold">Employee Onboarding</h1>
      <p className="muted mt-2">
        Role-gated workspace. Sign in, then continue to your hub.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <Link href="/hub" className="btn-primary">
          Employee Hub
        </Link>
        <Link href="/admin" className="btn-ghost">
          HR Admin Center
        </Link>
        <Link href="/login" className="btn-ghost">
          Sign in
        </Link>
      </div>
    </main>
  );
}
