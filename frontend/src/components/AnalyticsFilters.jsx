import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Calendar as CalIcon, Filter } from "lucide-react";

const PRESETS = [
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
  { value: "365", label: "Last 12 months" },
  { value: "all", label: "All time" },
  { value: "custom", label: "Custom range" },
];

/**
 * Global analytics filter bar. Lives at the top of /  and /reports.
 * Emits the current { preset, start_date, end_date, property_name } via onChange.
 */
export default function AnalyticsFilters({ value, onChange }) {
  const [properties, setProperties] = useState([]);

  useEffect(() => {
    let cancelled = false;
    api.get("/properties").then((r) => {
      if (cancelled) return;
      setProperties(r.data.items || []);
    });
    // Also auto-discover property names from reservations if no managed props exist
    api.get("/reservations", { params: { limit: 5000 } }).then((r) => {
      if (cancelled) return;
      const names = Array.from(
        new Set((r.data.items || []).map((x) => x.property_name).filter(Boolean))
      ).sort();
      setProperties((existing) => {
        if (existing.length > 0) return existing;
        return names.map((n) => ({ id: n, name: n }));
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const set = (patch) => onChange({ ...value, ...patch });

  return (
    <div
      data-testid="analytics-filters"
      className="surface rounded-md p-4 flex flex-wrap items-end gap-3"
    >
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-dim pr-2">
        <Filter className="w-3.5 h-3.5" /> Filters
      </div>

      <div className="w-44">
        <label className="text-[10px] uppercase tracking-[0.15em] text-dim flex items-center gap-1">
          <CalIcon className="w-3 h-3" /> Period
        </label>
        <Select
          value={value.preset}
          onValueChange={(p) => set({ preset: p, start_date: "", end_date: "" })}
        >
          <SelectTrigger
            data-testid="filter-preset"
            className="mt-1 bg-transparent border-[#22252F] text-sm"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
            {PRESETS.map((p) => (
              <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {value.preset === "custom" && (
        <>
          <div>
            <label className="text-[10px] uppercase tracking-[0.15em] text-dim">From</label>
            <input
              type="date"
              data-testid="filter-start-date"
              value={value.start_date || ""}
              onChange={(e) => set({ start_date: e.target.value })}
              className="mt-1 bg-transparent border border-[#22252F] rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-[#D9A05B]"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-[0.15em] text-dim">To</label>
            <input
              type="date"
              data-testid="filter-end-date"
              value={value.end_date || ""}
              onChange={(e) => set({ end_date: e.target.value })}
              className="mt-1 bg-transparent border border-[#22252F] rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-[#D9A05B]"
            />
          </div>
        </>
      )}

      <div className="w-56">
        <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Property</label>
        <Select
          value={value.property_name || "all"}
          onValueChange={(p) => set({ property_name: p })}
        >
          <SelectTrigger
            data-testid="filter-property"
            className="mt-1 bg-transparent border-[#22252F] text-sm"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
            <SelectItem value="all">All properties</SelectItem>
            {properties.map((p) => (
              <SelectItem key={p.id || p.name} value={p.name}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}

export function buildParams(filters) {
  const params = {};
  if (filters.preset && filters.preset !== "custom") params.preset = filters.preset;
  if (filters.preset === "custom") {
    if (filters.start_date) params.start_date = filters.start_date;
    if (filters.end_date) params.end_date = filters.end_date;
  }
  if (filters.property_name && filters.property_name !== "all") {
    params.property_name = filters.property_name;
  }
  return params;
}
