import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "TaskPilot AI", description: "A planned and traceable document generation agent" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
