import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FitVision Control",
  description: "Model and nutrition operations for FitVision",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
