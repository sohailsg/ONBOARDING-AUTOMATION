import Link from "next/link";

export default function Home() {
  return (
    <main id="main" className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-bold">Employee Onboarding</h1>
      <p className="mt-2 text-slate-600">
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
