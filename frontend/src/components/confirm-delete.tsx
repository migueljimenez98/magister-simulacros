"use client";

import { useState } from "react";

/** Modal de borrado que exige escribir "confirmar" antes de permitir borrar. */
export function ConfirmDelete({
  title = "Eliminar",
  message,
  onConfirm,
  onClose,
  pending,
}: {
  title?: string;
  message: string;
  onConfirm: () => void;
  onClose: () => void;
  pending?: boolean;
}) {
  const [text, setText] = useState("");
  const ok = text.trim().toLowerCase() === "confirmar";
  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center bg-black/60 p-4 overflow-auto" onClick={onClose}>
      <div className="bg-card border border-rose-800 rounded-2xl p-5 w-full max-w-md my-12" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-rose-300 mb-2">{title}</h3>
        <p className="text-sm text-muted mb-3">{message}</p>
        <p className="text-sm mb-2">
          Escribe <strong className="text-white">confirmar</strong> para borrar (no se puede deshacer):
        </p>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ok && onConfirm()}
          placeholder="confirmar"
          autoFocus
          className="w-full bg-bg border border-border rounded-lg px-3 py-2 mb-3"
        />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="text-sm rounded-lg border border-border px-3 py-2 hover:border-accent">Cancelar</button>
          <button
            onClick={onConfirm}
            disabled={!ok || pending}
            className="text-sm rounded-lg bg-rose-600 text-white font-medium px-3 py-2 hover:bg-rose-500 disabled:opacity-50"
          >
            {pending ? "Borrando…" : "Borrar"}
          </button>
        </div>
      </div>
    </div>
  );
}
