import type { Metadata } from "next";
import { DM_Sans, Lora, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { NavSidebar } from "@/components/nav-sidebar";

const dmSans = DM_Sans({ subsets: ["latin"], variable: "--font-dm-sans", display: "swap" });
const lora = Lora({ subsets: ["latin"], variable: "--font-lora", display: "swap" });
const jetbrainsMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });

export const metadata: Metadata = {
  title: "memorIA",
  description: "Documentación inteligente para tu equipo empoderada con IA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${dmSans.variable} ${lora.variable} ${jetbrainsMono.variable} h-full`}>
      <body
        className="h-full overflow-hidden"
        style={{ fontFamily: "var(--font-dm-sans, 'DM Sans'), system-ui, sans-serif" }}
      >
        <div className="flex h-full bg-[#e8e8e2]">
          <NavSidebar />
          <main className="flex-1 overflow-hidden">{children}</main>
        </div>
      </body>
    </html>
  );
}
