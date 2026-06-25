"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { getToken, setToken } from "@/lib/api";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    if (!getToken()) router.replace("/");
  }, [router]);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border bg-card">
        <div className="w-full px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="font-semibold">Magister Simulacros</h1>
            <nav className="flex gap-4 text-sm">
              <Link href="/dashboard" className="text-muted hover:text-white">Resultados</Link>
              <Link href="/dashboard/simulacros" className="text-muted hover:text-white">Personalidades y config</Link>
              <Link href="/dashboard/dev" className="text-muted hover:text-white">Dev</Link>
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
