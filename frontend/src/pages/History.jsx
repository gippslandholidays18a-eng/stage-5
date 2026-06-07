import { useEffect, useState } from "react";
import { api, fmtNumber } from "@/lib/api";
import { FileText, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";

const statusVisual = {
  completed: { icon: CheckCircle2, color: "#419B72", label: "Completed" },
  partial: { icon: AlertTriangle, color: "#D9A05B", label: "Partial" },
  failed: { icon: XCircle, color: "#E05A50", label: "Failed" },
};

export default function History() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/imports")
      .then((r) => setItems(r.data.items || []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div data-testid="history-page" className="space-y-6 max-w-5xl">
      <header>
        <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Import history</div>
        <h1 className="font-display text-3xl tracking-tight mt-1">All CSV uploads</h1>
        <p className="text-sm text-dim mt-2">A log of every import event with row outcomes.</p>
      </header>

      {loading ? (
        <div className="text-sm text-dim">Loading…</div>
      ) : items.length === 0 ? (
        <div className="surface rounded-md p-12 text-center">
          <FileText className="w-8 h-8 text-[#D9A05B] mx-auto" />
          <div className="text-sm text-dim mt-3">No imports yet.</div>
        </div>
      ) : (
        <div className="surface rounded-md overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-[#0E1015]">
              <tr className="text-[10px] uppercase tracking-[0.15em] text-[#6B7280]">
                <th className="text-left px-4 py-3 font-semibold">Filename</th>
                <th className="text-left px-4 py-3 font-semibold">Imported</th>
                <th className="text-right px-4 py-3 font-semibold">Total</th>
                <th className="text-right px-4 py-3 font-semibold">Successful</th>
                <th className="text-right px-4 py-3 font-semibold">Failed</th>
                <th className="text-left px-4 py-3 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody data-testid="history-table-body">
              {items.map((it) => {
                const vis = statusVisual[it.status] || statusVisual.completed;
                const Icon = vis.icon;
                return (
                  <tr key={it.id} className="tbl-row">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <FileText className="w-3.5 h-3.5 text-dim" />
                        <span className="text-white">{it.filename}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-dim">
                      {new Date(it.imported_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{fmtNumber(it.total_rows)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-[#419B72]">
                      {fmtNumber(it.successful_rows)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-[#E05A50]">
                      {fmtNumber(it.failed_rows)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className="inline-flex items-center gap-1.5 text-xs"
                        style={{ color: vis.color }}
                      >
                        <Icon className="w-3.5 h-3.5" /> {vis.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
