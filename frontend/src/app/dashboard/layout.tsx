"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { getToken, setToken } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Agentes" },
  { href: "/dashboard/simulacros", label: "Configuración" },
  { href: "/dashboard/dev", label: "Dev" },
  { href: "/dashboard/log", label: "Logs" },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!getToken()) router.replace("/");
  }, [router]);

  const isActive = (href: string) =>
    href === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(href);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border bg-card">
        <div className="w-full px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-10">
            <h1 className="font-semibold whitespace-nowrap">Magister Simulacros</h1>
            <nav className="flex gap-8 text-sm">
              {NAV.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  className={isActive(n.href) ? "text-white font-medium border-b-2 border-accent pb-1" : "text-muted hover:text-white"}
                >
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
          <button
            onClick={() => { setToken(null); router.replace("/"); }}
            className="text-sm text-muted hover:text-white"
          >
            Salir
          </button>
        </div>
      </header>
      <main className="w-full px-6 py-6 flex-1">{children}</main>
    </div>
  );
}
