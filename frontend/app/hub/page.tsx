"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Timeline } from "@/components/timeline";
import { Chat } from "@/components/chat";
import { BuddyCard } from "@/components/buddy-card";

export default function HubPage() {
  const { data } = useQuery({ queryKey: ["roadmap"], queryFn: api.getRoadmap });
  const payload = (data?.json_payload ?? {}) as { buddy?: { name?: string; role?: string; timezone?: string; calendar_link?: string } };

  return (
    <main id="main" className="mx-auto max-w-5xl space-y-4 px-4 py-8 motion-safe:animate-rise">
      <p className="text-xs font-semibold uppercase tracking-[0.3em] text-cyan-300/80">
        Orbit
      </p>
      <h1 className="title-gradient text-3xl font-bold">Employee Hub</h1>
      <div className="grid gap-4 md:grid-cols-[2fr_1fr]">
        <div className="space-y-4">
          <Timeline />
          <Chat />
        </div>
        <div>
          <BuddyCard buddy={payload.buddy} />
        </div>
      </div>
    </main>
  );
}
