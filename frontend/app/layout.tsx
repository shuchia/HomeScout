import type { Metadata } from "next";
import { DM_Sans } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { ComparisonBar } from "@/components/ComparisonBar";
import { BottomNav } from "@/components/BottomNav";
import { Header } from "@/components/Header";

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "snugd — Find Your Perfect Apartment",
  description: "AI-powered apartment matching across 19 East Coast cities. Search, compare, tour, and decide — all in one place.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${dmSans.variable} antialiased`}>
        <AuthProvider>
          <Header />
          <main className="pb-16 md:pb-0">{children}</main>
          <ComparisonBar />
          <BottomNav />
        </AuthProvider>
      </body>
    </html>
  );
}
