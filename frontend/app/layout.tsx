import type { Metadata, Viewport } from "next";
import { DM_Sans } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { ComparisonBar } from "@/components/ComparisonBar";
import { BottomNav } from "@/components/BottomNav";
import { Header } from "@/components/Header";
import { FeedbackWidget } from "@/components/FeedbackWidget";
import { OnboardingWalkthrough } from "@/components/OnboardingWalkthrough";
import { ServiceWorkerRegistration } from "@/components/ServiceWorkerRegistration";
import { InstallPrompt } from "@/components/InstallPrompt";

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "snugd — Find Your Perfect Apartment",
  description: "AI-powered apartment matching across 19 East Coast cities. Search, compare, tour, and decide — all in one place.",
  manifest: "/manifest.json",
  // iOS Safari uses these for "Add to Home Screen". The Next.js metadata
  // API emits the matching <meta name="apple-mobile-web-app-*"> and
  // <link rel="apple-touch-icon"> tags automatically.
  appleWebApp: {
    capable: true,
    title: "Snugd",
    statusBarStyle: "default",
  },
  icons: {
    apple: "/icons/apple-touch-icon.png",
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  },
  // Next.js's appleWebApp.capable setting no longer emits the legacy
  // <meta name="apple-mobile-web-app-capable"> tag that iOS Safari still
  // checks for fullscreen launch from home screen. Add it explicitly via
  // `other` plus the W3C-standard `mobile-web-app-capable` for parity.
  other: {
    "apple-mobile-web-app-capable": "yes",
    "mobile-web-app-capable": "yes",
  },
};

// Per Next.js 14+, themeColor + viewport live in a separate `viewport` export.
// themeColor tints the mobile browser address bar to match the brand green.
export const viewport: Viewport = {
  themeColor: "#2D6A4F",
  width: "device-width",
  initialScale: 1,
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
          <OnboardingWalkthrough />
          <main className="pb-16 md:pb-0">{children}</main>
          <ComparisonBar />
          <BottomNav />
          <FeedbackWidget />
          <InstallPrompt />
        </AuthProvider>
        <ServiceWorkerRegistration />
      </body>
    </html>
  );
}
