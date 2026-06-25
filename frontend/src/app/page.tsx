"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, getToken, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@magister.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // If already logged in, jump straight to the dashboard.
  useEffect(() => {
    if (getToken()) router.replace("/dashboard");
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await api.login(email, password);
      setToken(r.access_token);
      router.replace("/dashboard");
    } catch {
      setError("Email o contraseña incorrectos.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen grid place-items-center px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm bg-card border border-border rounded-2xl p-6 space-y-4 shadow-xl"
      >
        <header className="text-center mb-2">
          <h1 className="text-2xl font-semibold">Magister Simulacros</h1>
          <p className="text-sm text-muted">Formacion comercial — simulacros</p>
        </header>
        <label className="block">
          <span className="text-xs text-muted">Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            className="mt-1 w-full bg-bg border border-border rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-accent"
          />
        </label>
        <label className="block">
          <span className="text-xs text-muted">Contraseña</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            className="mt-1 w-full bg-bg border border-border rounded-lg px-3 py-2 outline-none focus:ring-1 focus:ring-accent"
          />
        </label>
        {error && <p className="text-sm text-danger">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-accent text-bg font-medium py-2 hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </main>
  );
}
