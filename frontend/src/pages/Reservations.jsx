import { useEffect, useMemo, useState } from "react";
import { api, ALL_SOURCES, SOURCE_COLORS, fmtMoney, fmtDate } from "@/lib/api";
import { toast } from "sonner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { ArrowUpDown, Pencil, Check } from "lucide-react";

const COLUMNS = [
  { key: "guest", label: "Guest" },
  { key: "property_name", label: "Property" },
  { key: "checkin_date", label: "Check-in" },
  { key: "checkout_date", label: "Check-out" },
  { key: "nights", label: "Nights", align: "right" },
  { key: "booking_value", label: "Value", align: "right" },
  { key: "raw_booking_source", label: "Raw source" },
  { key: "classified_source", label: "Classified" },
];

export default function Reservations() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterSource, setFilterSource] = useState("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState({ key: "checkin_date", dir: "desc" });

  useEffect(() => {
    let cancelled = false;
    api
      .get("/reservations", { params: { source: filterSource, limit: 2000 } })
      .then((r) => {
        if (cancelled) return;
        setItems(r.data.items || []);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filterSource]);

  const filtered = useMemo(() => {
    let xs = items;
    if (search.trim()) {
      const q = search.toLowerCase();
      xs = xs.filter(
        (r) =>
          (r.guest_first_name || "").toLowerCase().includes(q) ||
          (r.guest_last_name || "").toLowerCase().includes(q) ||
          (r.guest_email || "").toLowerCase().includes(q) ||
          (r.property_name || "").toLowerCase().includes(q) ||
          (r.reservation_id || "").toLowerCase().includes(q)
      );
    }
    const dir = sort.dir === "asc" ? 1 : -1;
    const key = sort.key;
    return [...xs].sort((a, b) => {
      let av = a[key];
      let bv = b[key];
      if (key === "guest") {
        av = `${a.guest_first_name} ${a.guest_last_name}`;
        bv = `${b.guest_first_name} ${b.guest_last_name}`;
      }
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [items, search, sort]);

  const onSort = (key) => {
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));
  };

  const onOverride = async (rid, newSource) => {
    try {
      await api.patch(`/reservations/${rid}/source`, { classified_source: newSource });
      toast.success(`Reclassified as ${newSource}`);
      setItems((xs) => xs.map((r) => (r.id === rid ? { ...r, classified_source: newSource, manually_overridden: true } : r)));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to update");
    }
  };

  return (
    <div data-testid="reservations-page" className="space-y-6">
      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Reservations</div>
          <h1 className="font-display text-3xl tracking-tight mt-1">All bookings</h1>
          <p className="text-sm text-dim mt-2">
            {filtered.length} of {items.length} shown
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Input
            data-testid="reservations-search"
            placeholder="Search guest, email, property…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-64 bg-transparent border-[#22252F] text-sm focus-visible:ring-1 focus-visible:ring-[#D9A05B]"
          />
          <Select value={filterSource} onValueChange={setFilterSource}>
            <SelectTrigger
              data-testid="reservations-source-filter"
              className="w-52 bg-transparent border-[#22252F] text-sm"
            >
              <SelectValue placeholder="Filter source" />
            </SelectTrigger>
            <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
              <SelectItem value="all">All sources</SelectItem>
              {ALL_SOURCES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </header>

      <div className="surface rounded-md overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[#0E1015]">
              <tr className="text-[10px] uppercase tracking-[0.15em] text-[#6B7280]">
                {COLUMNS.map((c) => (
                  <th
                    key={c.key}
                    onClick={() => onSort(c.key)}
                    className={`px-4 py-3 font-semibold cursor-pointer hover:text-white select-none ${
                      c.align === "right" ? "text-right" : "text-left"
                    }`}
                    data-testid={`sort-${c.key}`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {c.label}
                      <ArrowUpDown className="w-3 h-3 opacity-50" />
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody data-testid="reservations-table-body">
              {loading ? (
                <tr>
                  <td colSpan={COLUMNS.length} className="text-center py-12 text-dim">
                    Loading…
                  </td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={COLUMNS.length} className="text-center py-16">
                    <div className="text-dim text-sm">No reservations match these filters.</div>
                  </td>
                </tr>
              ) : (
                filtered.map((r) => (
                  <tr key={r.id} className="tbl-row">
                    <td className="px-4 py-3">
                      <div className="text-white">
                        {r.guest_first_name} {r.guest_last_name}
                      </div>
                      <div className="text-[11px] text-dim">{r.guest_email || ""}</div>
                    </td>
                    <td className="px-4 py-3 text-dim">{r.property_name || "—"}</td>
                    <td className="px-4 py-3 text-dim">{fmtDate(r.checkin_date)}</td>
                    <td className="px-4 py-3 text-dim">{fmtDate(r.checkout_date)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-dim">{r.nights ?? "—"}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{fmtMoney(r.booking_value)}</td>
                    <td className="px-4 py-3 text-dim font-mono text-[11px]">{r.raw_booking_source || "—"}</td>
                    <td className="px-4 py-3">
                      <SourceCell row={r} onChange={onOverride} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function SourceCell({ row, onChange }) {
  const [editing, setEditing] = useState(false);
  const color = SOURCE_COLORS[row.classified_source] || "#6B7280";

  if (editing) {
    return (
      <Select
        defaultValue={row.classified_source}
        onValueChange={(v) => {
          onChange(row.id, v);
          setEditing(false);
        }}
      >
        <SelectTrigger
          data-testid={`source-select-${row.id}`}
          className="w-48 h-8 bg-transparent border-[#22252F] text-xs"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
          {ALL_SOURCES.map((s) => (
            <SelectItem key={s} value={s}>
              {s}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  return (
    <div className="flex items-center gap-2 group">
      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
      <span className="text-white text-[12px]">{row.classified_source}</span>
      {row.manually_overridden && <Check className="w-3 h-3 text-[#419B72]" />}
      <button
        data-testid={`override-source-${row.id}`}
        onClick={() => setEditing(true)}
        className="opacity-0 group-hover:opacity-100 transition text-dim hover:text-white ml-1"
        title="Override classification"
      >
        <Pencil className="w-3 h-3" />
      </button>
    </div>
  );
}
