async function enableMocks() {
  if (process.env.NEXT_PUBLIC_USE_MSW !== "1") return;
  if (typeof window === "undefined") return;
  const { worker } = await import("./browser");
  await worker.start({ onUnhandledRequest: "bypass" });
}

enableMocks();

export {};
