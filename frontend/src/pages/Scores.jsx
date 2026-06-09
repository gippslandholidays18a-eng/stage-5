import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, API, fmtMoney, fmtNumber } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
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
import { Download, Sparkles } from "lucide-react";
import { SegmentBadge } from "@/components/SegmentBadge";

const tooltipStyle = {
  backgroundColor: "#12141A",
  border: "1px solid #22252F",
  borderRadius: 6,
  fontSize: 12,
  color: "#F2F3F5",
};

function bandColor(score) {
  if (score >= 75) return "#419B72"; // green
  if (score >= 50) return "#D9A05B"; // amber
  return "#E05A50"; // red
}

function ScoreBar({ score, testid }) {
  const color = bandColor(score || 0);
  return (
    <div className="flex items-center gap-2 min-w-[110px]" data-testid={testid}>
      <div className="flex-1 h-1.5 bg-[#0E1015] rounded">
        <div
          className="h-full rounded"
          style={{ width: `${Math.max(2, score || 0)}%`, backgroundColor: color }}
        />
      </div>
      <span className="tabular-nums text-xs font-medium w-8 text-right" style={{ color }}>
        {score ?? 0}
      </span>
    </div>
  );
}

export default function Scores() {
  const [summary, setSummary] = useState(null);
  const [guests, setGuests] = useState([]);
  const [commissions, setCommissions] = useState(null);
  const [segments, setSegments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [primarySource, setPrimarySource] = useState("all");
  const [minScore, setMinScore] = useState(0);
  const [segment, setSegment] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get("/scores/summary"),
      api.get("/commissions/summary"),
      api.get("/segments"),
    ]).then(([s, c, seg]) => {
      if (cancelled) return;
      setSummary(s.data);
      setCommissions(c.data);
      setSegments(seg.data.segments || []);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const params = {};
    if (primarySource !== "all") params.primary_source = primarySource;
    if (segment !== "all") params.segment = segment;
    if (minScore > 0) params.min_score = minScore;
    api.get("/scores/guests", { params }).then((r) => {
      if (cancelled) return;
      setGuests(r.data.items || []);
    });
    return () => {
      cancelled = true;
    };
  }, [primarySource, segment, minScore]);

  const filtered = useMemo(() => {
    if (!search.trim()) return guests;
    const q = search.toLowerCase();
    return guests.filter(
      (g) =>
        (g.email || "").toLowerCase().includes(q) ||
        `${g.first_name} ${g.last_name}`.toLowerCase().includes(q)
    );
  }, [guests, search]);

  const exportUrl = useMemo(() => {
    const u = new URL(`${API}/scores/guests/export.csv`);
    if (primarySource !== "all") u.searchParams.set("primary_source", primarySource);
    if (segment !== "all") u.searchParams.set("segment", segment);
    if (minScore > 0) u.searchParams.set("min_score", String(minScore));
    return u.toString();
  }, [primarySource, segment, minScore]);

  if (loading || !summary) return <div className="text-dim text-sm">Loading scores…</div>;

  return (
    <div data-testid="scores-page" className="space-y-8">
      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Scores</div>
          <h1 className="font-display text-3xl tracking-tight mt-1">Conversion & opportunity scoring</h1>
          <p className="text-sm text-dim mt-2 max-w-2xl">
            Every guest is scored on four dimensions. Sort by revenue opportunity to focus your direct conversion efforts.
          </p>
        </div>
        <a
          href={exportUrl}
          data-testid="export-scores-csv"
          className="inline-flex items-center gap-2 bg-brand text-black text-sm font-medium px-4 py-2 rounded-md hover:opacity-90"
        >
          <Download className="w-4 h-4" /> Export scored list
        </a>
      </header>

      {/* KPI cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
        <Kpi label="Guests scored" value={fmtNumber(summary.total_guests_scored)} sub={`${summary.ota_guest_count} OTA · ${summary.total_guests_scored - summary.ota_guest_count} Direct`} testid="kpi-total-scored" />
        <Kpi label="Avg direct conversion" value={summary.avg_direct_conversion_score} sub="Across OTA guests" testid="kpi-avg-direct-conv" />
        <Kpi label="Avg rebooking" value={summary.avg_rebooking_score} sub="Across all guests" testid="kpi-avg-rebooking" />
        <Kpi label="OTA commission to date" value={fmtMoney(summary.total_ota_commission_to_date)} sub="Non-cancelled bookings" testid="kpi-commission-total" />
        <Kpi label="Top 20% direct upside" value={fmtMoney(summary.estimated_savings_top20_direct)} sub="If top OTA guests booked direct" accent testid="kpi-savings-top20" />
      </div>

      {/* Filters */}
      <div className="surface rounded-md p-5 flex flex-wrap items-end gap-4">
        <div className="flex-1 min-w-[200px]">
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Search</label>
          <Input
            data-testid="scores-search"
            placeholder="Name or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="mt-1 bg-transparent border-[#22252F] text-sm focus-visible:ring-1 focus-visible:ring-[#D9A05B]"
          />
        </div>
        <div className="w-44">
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Primary source</label>
          <Select value={primarySource} onValueChange={setPrimarySource}>
            <SelectTrigger
              data-testid="filter-primary-source"
              className="mt-1 bg-transparent border-[#22252F] text-sm"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="OTA">OTA</SelectItem>
              <SelectItem value="Direct">Direct</SelectItem>
              <SelectItem value="Unknown">Unknown</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="w-52">
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Segment</label>
          <Select value={segment} onValueChange={setSegment}>
            <SelectTrigger
              data-testid="filter-segment"
              className="mt-1 bg-transparent border-[#22252F] text-sm"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
              <SelectItem value="all">All segments</SelectItem>
              {segments.map((s) => (
                <SelectItem key={s.name} value={s.name}>{s.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex-1 min-w-[200px]">
          <div className="flex items-center justify-between">
            <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Min revenue opportunity</label>
            <span className="text-xs tabular-nums text-white" data-testid="min-score-value">{minScore}</span>
          </div>
          <Slider
            data-testid="min-score-slider"
            value={[minScore]}
            onValueChange={(v) => setMinScore(v[0])}
            min={0}
            max={100}
            step={5}
            className="mt-3"
          />
        </div>
      </div>

      {/* Guest table */}
      <div className="surface rounded-md overflow-hidden">
        <div className="px-6 py-4 border-b divider flex items-center justify-between">
          <div>
            <h2 className="font-display text-lg">Scored guests</h2>
            <p className="text-xs text-dim mt-1">
              {filtered.length} shown · sorted by revenue opportunity
            </p>
          </div>
          <Sparkles className="w-4 h-4 text-[#D9A05B]" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-[#0E1015]">
              <tr className="text-[10px] uppercase tracking-[0.15em] text-[#6B7280]">
                <th className="text-left px-4 py-3 font-semibold">Guest</th>
                <th className="text-left px-4 py-3 font-semibold">Primary</th>
                <th className="text-right px-4 py-3 font-semibold">Stays</th>
                <th className="text-right px-4 py-3 font-semibold">Lifetime</th>
                <th className="text-right px-4 py-3 font-semibold">Raw LTV</th>
                <th className="text-left px-4 py-3 font-semibold">Direct conv</th>
                <th className="text-left px-4 py-3 font-semibold">LTV</th>
                <th className="text-left px-4 py-3 font-semibold">Rebook</th>
                <th className="text-left px-4 py-3 font-semibold">Revenue opp</th>
                <th className="text-left px-4 py-3 font-semibold">Segments</th>
              </tr>
            </thead>
            <tbody data-testid="scores-table-body">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={10} className="text-center py-12 text-dim">
                    No guests match these filters.
                  </td>
                </tr>
              ) : (
                filtered.map((g) => (
                  <tr key={g.id} className="tbl-row">
                    <td className="px-4 py-3">
                      <Link
                        to={`/guests/${encodeURIComponent(g.id)}`}
                        className="text-white hover:underline"
                        data-testid={`score-guest-${g.email.replace(/[^a-z0-9]+/gi,'-').toLowerCase()}`}
                      >
                        {g.first_name} {g.last_name}
                      </Link>
                      <div className="text-[11px] text-dim">{g.email}</div>
                    </td>
                    <td className="px-4 py-3 text-dim">{g.primary_channel}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{g.total_stays}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{fmtMoney(g.lifetime_spend)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-dim">{fmtMoney(g.raw_ltv_value || 0)}</td>
                    <td className="px-4 py-3"><ScoreBar score={g.direct_conversion_score} testid={`bar-dconv-${g.id}`} /></td>
                    <td className="px-4 py-3"><ScoreBar score={g.lifetime_value_score} /></td>
                    <td className="px-4 py-3"><ScoreBar score={g.rebooking_score} /></td>
                    <td className="px-4 py-3"><ScoreBar score={g.revenue_opportunity_score} testid={`bar-revop-${g.id}`} /></td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1 max-w-[260px]">
                        {(g.segments || []).slice(0, 2).map((s) => (
                          <SegmentBadge key={s} name={s} />
                        ))}
                        {(g.segments || []).length > 2 && (
                          <span className="text-[10px] text-dim">+{g.segments.length - 2}</span>
                        )}
                        {(g.segments || []).length === 0 && (
                          <span className="text-[10px] text-dim">—</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Commission section */}
      <CommissionPanel commissions={commissions} />
    </div>
  );
}

function Kpi({ label, value, sub, accent, testid }) {
  return (
    <div data-testid={testid} className={`surface rounded-md p-5 ${accent ? "border-[#D9A05B]/40" : ""}`}>
      <div className="text-[11px] uppercase tracking-[0.18em] text-dim">{label}</div>
      <div className="font-display text-3xl font-light tracking-tighter text-white mt-2">{value}</div>
      {sub && <div className="text-[11px] text-dim mt-2">{sub}</div>}
    </div>
  );
}

function CommissionPanel({ commissions }) {
  if (!commissions) return null;
  const data = commissions.by_source || [];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="surface rounded-md p-6 lg:col-span-2 overflow-hidden">
        <h2 className="font-display text-lg">OTA commission costs</h2>
        <p className="text-xs text-dim mt-1">
          Estimated commission paid to each OTA platform. Adjust rates in <Link to="/settings/commissions" className="brand hover:underline">Settings</Link>.
        </p>
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] uppercase tracking-[0.15em] text-[#6B7280]">
                <th className="text-left pb-3 font-semibold">Platform</th>
                <th className="text-right pb-3 font-semibold">Bookings</th>
                <th className="text-right pb-3 font-semibold">Revenue</th>
                <th className="text-right pb-3 font-semibold">Commission</th>
                <th className="text-right pb-3 font-semibold">Avg / booking</th>
              </tr>
            </thead>
            <tbody data-testid="commission-table-body">
              {data.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-dim">
                    No OTA bookings yet.
                  </td>
                </tr>
              ) : (
                <>
                  {data.map((b) => (
                    <tr key={b.source} className="tbl-row">
                      <td className="py-3">{b.source}</td>
                      <td className="py-3 text-right tabular-nums">{fmtNumber(b.bookings)}</td>
                      <td className="py-3 text-right tabular-nums">{fmtMoney(b.revenue)}</td>
                      <td className="py-3 text-right tabular-nums text-[#E05A50]">{fmtMoney(b.commission)}</td>
                      <td className="py-3 text-right tabular-nums text-dim">{fmtMoney(b.avg_commission_per_booking)}</td>
                    </tr>
                  ))}
                  <tr className="border-t-2 border-[#22252F]">
                    <td className="py-3 font-medium">Total</td>
                    <td className="py-3 text-right tabular-nums">{fmtNumber(commissions.total_bookings)}</td>
                    <td className="py-3 text-right tabular-nums">{fmtMoney(commissions.total_revenue)}</td>
                    <td className="py-3 text-right tabular-nums text-[#E05A50] font-medium">{fmtMoney(commissions.total_commission)}</td>
                    <td className="py-3"></td>
                  </tr>
                </>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="surface rounded-md p-6">
        <h2 className="font-display text-lg">By platform</h2>
        <div className="h-64 mt-4" data-testid="commission-bar-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 6, right: 10, left: -10, bottom: 30 }}>
              <CartesianGrid stroke="#1c1f27" vertical={false} />
              <XAxis dataKey="source" tick={{ fill: "#8F95A3", fontSize: 10 }} interval={0} angle={-25} textAnchor="end" />
              <YAxis tick={{ fill: "#8F95A3", fontSize: 11 }} tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v) => fmtMoney(v)} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
              <Bar dataKey="commission" radius={[4, 4, 0, 0]} fill="#E05A50">
                {data.map((d, i) => (
                  <Cell key={i} fill="#E05A50" />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
