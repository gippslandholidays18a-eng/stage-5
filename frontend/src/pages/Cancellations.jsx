import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, API, fmtMoney, fmtNumber, fmtDate, SOURCE_COLORS } from "@/lib/api";
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
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { Download, AlertTriangle } from "lucide-react";
import { segmentColor } from "@/components/SegmentBadge";

const tooltipStyle = {
  backgroundColor: "#12141A",
  border: "1px solid #22252F",
  borderRadius: 6,
  fontSize: 12,
  color: "#F2F3F5",
};

export default function Cancellations() {
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [segments, setSegments] = useState([]);
  const [filterSegment, setFilterSegment] = useState("all");
  const [filterSource, setFilterSource] = useState("all");
  const [filterProperty, setFilterProperty] = useState("all");

  const loadSummary = () =>
    api.get("/cancellations/summary").then((r) => setSummary(r.data));

  const loadRows = () => {
    const params = {};
    if (filterSegment !== "all") params.segment = filterSegment;
    if (filterSource !== "all") params.source = filterSource;
    if (filterProperty !== "all") params.property_name = filterProperty;
    return api.get("/cancellations", { params }).then((r) => setRows(r.data.items || []));
  };

  useEffect(() => {
    Promise.all([
      loadSummary(),
      api.get("/segments").then((r) => setSegments(r.data.segments || [])),
    ]).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadRows();
  }, [filterSegment, filterSource, filterProperty]);

  const properties = useMemo(() => {
    if (!summary) return [];
    return summary.rate_by_property.map((p) => p.property);
  }, [summary]);

  const sources = useMemo(() => {
    if (!summary) return [];
    return summary.rate_by_source.map((s) => s.source);
  }, [summary]);

  const exportUrl = useMemo(() => {
    const u = new URL(`${API}/cancellations/export.csv`);
    if (filterSegment !== "all") u.searchParams.set("segment", filterSegment);
    if (filterSource !== "all") u.searchParams.set("source", filterSource);
    if (filterProperty !== "all") u.searchParams.set("property_name", filterProperty);
    return u.toString();
  }, [filterSegment, filterSource, filterProperty]);

  if (loading || !summary) return <div className="text-dim text-sm">Loading cancellations…</div>;

  const isEmpty = summary.total_cancelled === 0;

  return (
    <div data-testid="cancellations-page" className="space-y-8">
      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Cancellations</div>
          <h1 className="font-display text-3xl tracking-tight mt-1">Cancellation intelligence</h1>
          <p className="text-sm text-dim mt-2 max-w-2xl">
            Identify lost revenue, recover-able guests, and high-intent remarketing audiences.
          </p>
        </div>
        <a
          href={exportUrl}
          data-testid="export-cancellations-csv"
          className="inline-flex items-center gap-2 bg-brand text-black text-sm font-medium px-4 py-2 rounded-md hover:opacity-90"
        >
          <Download className="w-4 h-4" /> Export audience CSV
        </a>
      </header>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Kpi label="Total cancellations" value={fmtNumber(summary.total_cancelled)} testid="kpi-total-cancelled" />
        <Kpi label="Lost revenue" value={fmtMoney(summary.total_lost_revenue)} accent testid="kpi-lost-revenue" />
        <Kpi label="Overall cancellation rate" value={`${summary.overall_rate}%`} testid="kpi-cancel-rate" />
      </div>

      {isEmpty ? (
        <div data-testid="cancellations-empty" className="surface rounded-md p-12 text-center">
          <AlertTriangle className="w-7 h-7 text-[#D9A05B] mx-auto" />
          <div className="font-display text-xl mt-3">No cancellations yet</div>
          <p className="text-sm text-dim mt-2">Once a cancellation lands in an import, you&apos;ll see it here.</p>
        </div>
      ) : (
        <>
          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ChartBox title="Cancellation rate by booking source" testid="chart-rate-by-source">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={summary.rate_by_source}
                  margin={{ top: 10, right: 10, left: -10, bottom: 50 }}
                >
                  <CartesianGrid stroke="#1c1f27" vertical={false} />
                  <XAxis
                    dataKey="source"
                    tick={{ fill: "#8F95A3", fontSize: 10 }}
                    interval={0}
                    angle={-30}
                    textAnchor="end"
                  />
                  <YAxis tick={{ fill: "#8F95A3", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(v, k) => (k === "rate" ? `${v}%` : v)}
                  />
                  <Bar dataKey="rate" name="Cancel rate" radius={[4, 4, 0, 0]}>
                    {summary.rate_by_source.map((d, i) => (
                      <Cell key={i} fill={SOURCE_COLORS[d.source] || "#6B7280"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartBox>

            <ChartBox title="Cancellation rate by property" testid="chart-rate-by-property">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={summary.rate_by_property}
                  margin={{ top: 10, right: 10, left: -10, bottom: 50 }}
                >
                  <CartesianGrid stroke="#1c1f27" vertical={false} />
                  <XAxis
                    dataKey="property"
                    tick={{ fill: "#8F95A3", fontSize: 10 }}
                    interval={0}
                    angle={-25}
                    textAnchor="end"
                  />
                  <YAxis tick={{ fill: "#8F95A3", fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v) => `${v}%`} />
                  <Bar dataKey="rate" fill="#D9A05B" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartBox>

            <ChartBox title="Monthly cancellation trend" testid="chart-monthly-trend">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={summary.monthly_trend} margin={{ top: 10, right: 10, left: -10, bottom: 30 }}>
                  <CartesianGrid stroke="#1c1f27" vertical={false} />
                  <XAxis dataKey="month" tick={{ fill: "#8F95A3", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#8F95A3", fontSize: 11 }} allowDecimals={false} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Line
                    type="monotone"
                    dataKey="cancellations"
                    stroke="#E05A50"
                    strokeWidth={2}
                    dot={{ r: 3, fill: "#E05A50" }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </ChartBox>

            <ChartBox title="Avg days from booking to check-in by source" testid="chart-days-to-cancel">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={summary.avg_days_to_cancel}
                  margin={{ top: 10, right: 10, left: -10, bottom: 50 }}
                >
                  <CartesianGrid stroke="#1c1f27" vertical={false} />
                  <XAxis
                    dataKey="source"
                    tick={{ fill: "#8F95A3", fontSize: 10 }}
                    interval={0}
                    angle={-30}
                    textAnchor="end"
                  />
                  <YAxis tick={{ fill: "#8F95A3", fontSize: 11 }} />
                  <Tooltip contentStyle={tooltipStyle} formatter={(v) => `${v} days`} />
                  <Bar dataKey="avg_days" radius={[4, 4, 0, 0]}>
                    {summary.avg_days_to_cancel.map((d, i) => (
                      <Cell key={i} fill={SOURCE_COLORS[d.source] || "#6B7280"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartBox>

            <ChartBox
              title="Cancelled guest segment breakdown"
              testid="chart-segment-donut"
              className="lg:col-span-2"
            >
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={summary.segment_breakdown}
                    dataKey="guests"
                    nameKey="segment"
                    innerRadius={60}
                    outerRadius={100}
                    stroke="#090A0E"
                    strokeWidth={3}
                  >
                    {summary.segment_breakdown.map((d, i) => (
                      <Cell key={i} fill={segmentColor(d.segment)} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#8F95A3" }} />
                </PieChart>
              </ResponsiveContainer>
            </ChartBox>
          </div>

          {/* Filters + Table */}
          <div className="surface rounded-md overflow-hidden">
            <div className="px-6 py-5 border-b divider flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
              <div>
                <h2 className="font-display text-lg">Cancelled reservations</h2>
                <p className="text-xs text-dim mt-1">{rows.length} matches · sorted by remarketing priority</p>
              </div>
              <div className="flex flex-wrap gap-3">
                <FilterSelect
                  testid="filter-segment"
                  value={filterSegment}
                  onChange={setFilterSegment}
                  placeholder="Segment"
                  options={[
                    { value: "all", label: "All segments" },
                    { value: "Unsegmented", label: "Unsegmented" },
                    ...segments
                      .filter((s) => s.kind === "cancellation")
                      .map((s) => ({ value: s.name, label: s.name })),
                  ]}
                />
                <FilterSelect
                  testid="filter-source"
                  value={filterSource}
                  onChange={setFilterSource}
                  placeholder="Source"
                  options={[
                    { value: "all", label: "All sources" },
                    ...sources.map((s) => ({ value: s, label: s })),
                  ]}
                />
                <FilterSelect
                  testid="filter-property"
                  value={filterProperty}
                  onChange={setFilterProperty}
                  placeholder="Property"
                  options={[
                    { value: "all", label: "All properties" },
                    ...properties.map((p) => ({ value: p, label: p })),
                  ]}
                />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-[#0E1015]">
                  <tr className="text-[10px] uppercase tracking-[0.15em] text-[#6B7280]">
                    <th className="text-left px-4 py-3 font-semibold">Guest</th>
                    <th className="text-left px-4 py-3 font-semibold">Property</th>
                    <th className="text-left px-4 py-3 font-semibold">Check-in</th>
                    <th className="text-right px-4 py-3 font-semibold">Value</th>
                    <th className="text-left px-4 py-3 font-semibold">Source</th>
                    <th className="text-right px-4 py-3 font-semibold">Days to cancel</th>
                    <th className="text-left px-4 py-3 font-semibold">Segment</th>
                    <th className="text-left px-4 py-3 font-semibold">Recovery</th>
                    <th className="text-right px-4 py-3 font-semibold">Score</th>
                  </tr>
                </thead>
                <tbody data-testid="cancellations-table-body">
                  {rows.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="text-center py-10 text-dim">
                        No cancelled reservations match these filters.
                      </td>
                    </tr>
                  ) : (
                    rows.map((r) => (
                      <tr key={r.reservation_id} className="tbl-row">
                        <td className="px-4 py-3">
                          <Link
                            to={`/guests/${encodeURIComponent(r.guest_email)}`}
                            className="text-white hover:underline"
                          >
                            {r.guest_name}
                          </Link>
                          <div className="text-[11px] text-dim">{r.guest_email}</div>
                        </td>
                        <td className="px-4 py-3 text-dim">{r.property_name || "—"}</td>
                        <td className="px-4 py-3 text-dim">{fmtDate(r.checkin_date)}</td>
                        <td className="px-4 py-3 text-right tabular-nums">{fmtMoney(r.booking_value)}</td>
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center gap-1.5 text-xs">
                            <span
                              className="w-2 h-2 rounded-full"
                              style={{ backgroundColor: SOURCE_COLORS[r.classified_source] || "#6B7280" }}
                            />
                            {r.classified_source}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-dim">
                          {r.days_to_cancel ?? "—"}
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className="text-[10px] px-2 py-0.5 rounded border"
                            style={{
                              color: segmentColor(r.cancellation_segment),
                              borderColor: `${segmentColor(r.cancellation_segment)}44`,
                              backgroundColor: `${segmentColor(r.cancellation_segment)}14`,
                            }}
                          >
                            {r.cancellation_segment}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-dim">{r.recovery_status}</td>
                        <td className="px-4 py-3 text-right">
                          <ScorePill score={r.remarketing_priority_score} />
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Kpi({ label, value, sub, accent, testid }) {
  return (
    <div
      data-testid={testid}
      className={`surface rounded-md p-6 ${accent ? "border-[#D9A05B]/40" : ""}`}
    >
      <div className="text-[11px] uppercase tracking-[0.18em] text-dim">{label}</div>
      <div className="font-display text-4xl font-light tracking-tighter text-white mt-3">{value}</div>
      {sub && <div className="text-xs text-dim mt-2">{sub}</div>}
    </div>
  );
}

function ChartBox({ title, children, testid, className = "" }) {
  return (
    <div className={`surface rounded-md p-6 ${className}`}>
      <h2 className="font-display text-base text-white">{title}</h2>
      <div className="h-64 mt-4" data-testid={testid}>
        {children}
      </div>
    </div>
  );
}

function FilterSelect({ value, onChange, options, placeholder, testid }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger
        data-testid={testid}
        className="w-48 bg-transparent border-[#22252F] text-sm"
      >
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
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
