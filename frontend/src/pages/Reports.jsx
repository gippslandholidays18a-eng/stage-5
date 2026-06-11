import { useEffect, useMemo, useState } from "react";
import { api, API, fmtNumber } from "@/lib/api";
import AnalyticsFilters, { buildParams } from "@/components/AnalyticsFilters";
import { FileDown, FileText } from "lucide-react";

export default function Reports() {
  const [reports, setReports] = useState([]);
  const [counts, setCounts] = useState({});
  const [loadingCounts, setLoadingCounts] = useState({});
  const [filters, setFilters] = useState({
    preset: "365",
    start_date: "",
    end_date: "",
    property_name: "all",
  });
  const params = useMemo(() => buildParams(filters), [filters]);

  useEffect(() => {
    let cancelled = false;
    api.get("/reports").then((r) => {
      if (cancelled) return;
      setReports(r.data.reports || []);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    reports.forEach((rep) => {
      setLoadingCounts((l) => ({ ...l, [rep.key]: true }));
      api
        .get(`/reports/${rep.key}/count`, { params })
        .then((r) => {
          if (cancelled) return;
          setCounts((c) => ({ ...c, [rep.key]: r.data.count }));
          setLoadingCounts((l) => ({ ...l, [rep.key]: false }));
        });
    });
    return () => {
      cancelled = true;
    };
  }, [reports, params]);

  const buildUrl = (key) => {
    const u = new URL(`${API}/reports/${key}.csv`);
    Object.entries(params).forEach(([k, v]) => u.searchParams.set(k, String(v)));
    return u.toString();
  };

  return (
    <div data-testid="reports-page" className="space-y-6 max-w-6xl">
      <header>
        <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Reports</div>
        <h1 className="font-display text-3xl tracking-tight mt-1">Exportable reports</h1>
        <p className="text-sm text-dim mt-2 max-w-2xl">
          Pre-built CSV exports for operations, marketing and finance. Each report respects the global date range where applicable.
        </p>
      </header>

      <AnalyticsFilters value={filters} onChange={setFilters} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="report-list">
        {reports.map((r) => (
          <div key={r.key} className="surface rounded-md p-5 flex flex-col sm:flex-row sm:items-center gap-4 hover:bg-[#14161D] transition">
            <div className="w-10 h-10 rounded-md bg-[#1A1D24] border divider flex items-center justify-center shrink-0">
              <FileText className="w-4 h-4 text-[#D9A05B]" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm text-white font-medium">{r.label}</div>
              <div className="text-[11px] text-dim mt-1">
                {loadingCounts[r.key] ? "Counting…" : `${fmtNumber(counts[r.key] || 0)} rows`}
              </div>
            </div>
            <a
              href={buildUrl(r.key)}
              data-testid={`download-${r.key}`}
              className="inline-flex items-center gap-2 bg-brand text-black text-xs font-medium px-3 py-2 rounded-md hover:opacity-90 shrink-0"
              download
            >
              <FileDown className="w-3.5 h-3.5" /> Download
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}
