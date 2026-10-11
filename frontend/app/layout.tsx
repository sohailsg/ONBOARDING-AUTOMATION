import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { ApiVersionBanner } from "@/components/api-version-banner";

export const metadata: Metadata = {
  title: "Onboarding — Employee Hub & HR Admin Center",
  description: "Role-gated onboarding: roadmap, cited chat, HITL review, trace.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <ApiVersionBanner />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
