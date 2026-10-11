import { Pipeline } from "@/components/pipeline";

export default function AdminPage() {
  return (
    <main id="main" className="mx-auto max-w-6xl space-y-4 px-4 py-8 motion-safe:animate-rise">
      <p className="text-xs font-semibold uppercase tracking-[0.3em] text-cyan-300/80">
        Command deck
      </p>
      <h1 className="title-gradient text-3xl font-bold">HR Admin Center</h1>
      <Pipeline />
    </main>
  );
}
