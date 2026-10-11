/** F-UI-3 buddy card. Rendered from find_slots output embedded in the plan. */
export function BuddyCard({
  buddy,
}: {
  buddy?: {
    name?: string;
    role?: string;
    timezone?: string;
    calendar_link?: string;
    photo?: string;
  } | null;
}) {
  if (!buddy) return null;
  return (
    <section aria-label="Buddy" className="card card-hover">
      <h2 className="text-lg font-semibold">Your buddy</h2>
      <div className="mt-2 flex items-center gap-3">
        <div
          aria-hidden="true"
          className="flex h-12 w-12 items-center justify-center rounded-full font-bold text-white shadow-glow"
          style={{ backgroundImage: "linear-gradient(135deg,#6366f1,#a855f7 60%,#06b6d4 130%)" }}
        >
          {(buddy.name ?? "?").slice(0, 1)}
        </div>
        <div>
          <p className="font-medium">{buddy.name ?? "TBA"}</p>
          <p className="muted text-sm">
            {[buddy.role, buddy.timezone].filter(Boolean).join(" · ")}
          </p>
        </div>
      </div>
      {buddy.calendar_link && (
        <a className="btn-ghost mt-3 inline-flex" href={buddy.calendar_link}>
          Book 1:1
        </a>
      )}
    </section>
  );
}
