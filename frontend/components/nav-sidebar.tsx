"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquare, FileText } from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { useStore } from "@/lib/store";

const NAV = [
  { href: "/", label: "Chat", icon: MessageSquare },
  { href: "/documentos", label: "Documentos", icon: FileText },
];

export function NavSidebar() {
  const pathname = usePathname();
  const { user, role, setUser, setRole } = useStore();

  return (
    <aside className="w-52 flex-shrink-0 flex flex-col h-full bg-[#fafaf8] border-r border-[#d4d4c8]">
      {/* Logo */}
      <div className="px-5 py-4">
        <span
          className="text-base font-bold tracking-tight"
          style={{ fontFamily: "var(--font-lora, Lora), serif", color: "#1a1a2e" }}
        >
          memor<span style={{ color: "#2563b0" }}>IA</span>
        </span>
      </div>

      <Separator className="bg-[#d4d4c8]" />

      {/* Nav links */}
      <nav className="flex-1 px-3 py-3 space-y-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                active
                  ? "bg-[#dbeafe] text-[#1d4ed8]"
                  : "text-[#4a4a6a] hover:bg-[#f0f0ea] hover:text-[#1a1a2e]"
              }`}
            >
              <Icon size={15} />
              {label}
            </Link>
          );
        })}
      </nav>

      <Separator className="bg-[#d4d4c8]" />

      {/* User selector */}
      <div className="px-4 py-4 space-y-2">
        <input
          className="w-full text-xs px-2 py-1.5 rounded border border-[#d4d4c8] bg-white text-[#1a1a2e] focus:outline-none focus:border-[#2563b0]"
          value={user}
          onChange={(e) => setUser(e.target.value)}
          placeholder="usuario@empresa.com"
        />
        <select
          className="w-full text-xs px-2 py-1.5 rounded border border-[#d4d4c8] bg-white text-[#1a1a2e] focus:outline-none focus:border-[#2563b0]"
          value={role}
          onChange={(e) => setRole(e.target.value as "developer" | "admin")}
        >
          <option value="developer">developer</option>
          <option value="admin">admin</option>
        </select>
      </div>
    </aside>
  );
}
