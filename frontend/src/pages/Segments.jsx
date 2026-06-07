import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtMoney, fmtNumber } from "@/lib/api";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from "recharts";
import { Users } from "lucide-react";
import { SegmentBadge, segmentColor } from "@/components/SegmentBadge";

const tooltipStyle = {
  backgroundColor: "#12141A",
  border: "1px solid #22252F",
  borderRadius: 6,
  fontSize: 12,
  color: "#F2F3F5",
};

export default function Segments() {
  const [segments, setSegments] = useState([]);
  const [guests, setGuests] = useState([]);
  const [totals, setTotals] = useState({ total_guests: 0, unsegmented: 0 });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    Promise.all([api.get("/segments"), api.get("/guests")])
      .then(([s, g]) => {
        setSegments(s.data.segments || []);
        setTotals({ total_guests: s.data.total_guests, unsegmented: s.data.unsegmented });
        setGuests(g.data.items || []);
      })
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    let xs = guests;
    if (filter !== "all") {
      xs = xs.filter((g) => (g.segments || []).includes(filter));
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      xs = xs.filter(
        (g) =>
          (g.email || "").toLowerCase().includes(q) ||
          (`${g.first_name} ${g.last_name}`).toLowerCase().includes(q)
      );
    }
    return xs;
  }, [guests, filter, search]);

  if (loading) {
    return <div className="text-dim text-sm">Loading segments…</div>;
  }

  return (
    <div data-testid="segments-page" className="space-y-8">
      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Segments</div>
          <h1 className="font-display text-3xl tracking-tight mt-1">Guest segmentation</h1>
          <p className="text-sm text-dim mt-2 max-w-2xl">
            {totals.total_guests} unique guests · {totals.unsegmented} unsegmented. Segments recompute on every import or source override.
          </p>
        </div>
      </header>

      {/* Segment summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3" data-testid="segment-cards">
        {segments.map((s) => (
          <button
            key={s.name}
            onClick={() => setFilter(filter === s.name ? "all" : s.name)}
            data-testid={`segment-card-${s.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`}
            className={`surface rounded-md p-4 text-left transition ${
              filter === s.name ? "border-[#D9A05B]" : "hover:bg-[#15181F]"
            }`}
          >
            <div className="flex items-center gap-2">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: segmentColor(s.name) }}
              />
              <span className="text-[10px] uppercase tracking-[0.12em] text-dim">
                {s.kind === "cancellation" ? "Cancellation" : "Standard"}
              </span>
            </div>
            <div className="font-display text-2xl mt-2 tabular-nums">{s.guest_count}</div>
            <div className="text-[11px] text-white mt-1 leading-tight">{s.name}</div>
          </button>
        ))}
      </div>

      {/* Bar chart */}
      <div className="surface rounded-md p-6">
        <h2 className="font-display text-lg">Guest count by segment</h2>
        <p className="text-xs text-dim mt-1">Click a card above to filter the guest list below.</p>
        <div className="h-72 mt-5" data-testid="segments-bar-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={segments.map((s) => ({ name: s.name, guests: s.guest_count }))}
              margin={{ top: 10, right: 10, left: -10, bottom: 80 }}
            >
              <CartesianGrid stroke="#1c1f27" vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fill: "#8F95A3", fontSize: 10 }}
                interval={0}
                angle={-30}
                textAnchor="end"
                height={80}
              />
              <YAxis tick={{ fill: "#8F95A3", fontSize: 11 }} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
              <Bar dataKey="guests" radius={[4, 4, 0, 0]}>
                {segments.map((s, i) => (
                  <Cell key={i} fill={segmentColor(s.name)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Guest table */}
      <div className="surface rounded-md overflow-hidden">
        <div className="px-6 py-5 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 border-b divider">
          <div>
            <h2 className="font-display text-lg">Guests</h2>
            <p className="text-xs text-dim mt-1">{filtered.length} of {guests.length} shown</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Input
              data-testid="guests-search"
              placeholder="Search name or email…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-64 bg-transparent border-[#22252F] text-sm focus-visible:ring-1 focus-visible:ring-[#D9A05B]"
            />
            <Select value={filter} onValueChange={setFilter}>
              <SelectTrigger
                data-testid="segments-filter"
                className="w-64 bg-transparent border-[#22252F] text-sm"
              >
                <SelectValue placeholder="Filter segment" />
              </SelectTrigger>
              <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
                <SelectItem value="all">All segments</SelectItem>
                {segments.map((s) => (
                  <SelectItem key={s.name} value={s.name}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[#0E1015]">
              <tr className="text-[10px] uppercase tracking-[0.15em] text-[#6B7280]">
                <th className="text-left px-4 py-3 font-semibold">Guest</th>
                <th className="text-left px-4 py-3 font-semibold">Email</th>
                <th className="text-right px-4 py-3 font-semibold">Stays</th>
                <th className="text-right px-4 py-3 font-semibold">Lifetime spend</th>
                <th className="text-left px-4 py-3 font-semibold">Primary</th>
                <th className="text-left px-4 py-3 font-semibold">Segments</th>
                <th className="text-right px-4 py-3 font-semibold">Score</th>
              </tr>
            </thead>
            <tbody data-testid="guests-table-body">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-16">
                    <Users className="w-6 h-6 mx-auto text-dim" />
                    <div className="text-dim text-sm mt-3">No guests match.</div>
                  </td>
                </tr>
              ) : (
                filtered.map((g) => (
                  <tr key={g.id} className="tbl-row">
                    <td className="px-4 py-3">
                      <Link
                        to={`/guests/${encodeURIComponent(g.id)}`}
                        data-testid={`guest-row-${g.email.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`}
                        className="text-white hover:underline"
                      >
                        {g.first_name} {g.last_name}
                      </Link>
                      {g.cancellation_count > 0 && (
                        <span className="ml-2 text-[10px] uppercase tracking-wider text-[#E05A50]">⚠ cancel</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-dim">{g.email}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{fmtNumber(g.total_stays)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{fmtMoney(g.lifetime_spend)}</td>
                    <td className="px-4 py-3 text-dim">{g.primary_channel}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {(g.segments || []).map((s) => (
                          <SegmentBadge key={s} name={s} />
                        ))}
                        {(g.segments || []).length === 0 && (
                          <span className="text-dim text-xs">—</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      <ScorePill score={g.remarketing_priority_score} />
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

function ScorePill({ score }) {
  if (!score) return <span className="text-dim">0</span>;
  let color = "#419B72";
  if (score >= 70) color = "#E05A50";
  else if (score >= 40) color = "#D9A05B";
  return (
    <span
      className="inline-block min-w-[2.5rem] text-center text-xs font-medium px-2 py-0.5 rounded"
      style={{ color, backgroundColor: `${color}1A`, border: `1px solid ${color}33` }}
    >
      {score}
    </span>
  );
}
