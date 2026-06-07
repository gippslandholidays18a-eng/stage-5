import { useEffect, useState } from "react";
import { api, SOURCE_COLORS, fmtMoney, fmtNumber } from "@/lib/api";
import KPICard from "@/components/KPICard";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  CartesianGrid,
} from "recharts";
import { Link } from "react-router-dom";
import { Upload } from "lucide-react";

const tooltipStyle = {
  backgroundColor: "#12141A",
  border: "1px solid #22252F",
  borderRadius: 6,
  fontSize: 12,
  color: "#F2F3F5",
};

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/analytics/summary")
      .then((r) => setData(r.data))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <SkeletonBlock />;
  }

  const empty = !data || data.total_bookings === 0;

  return (
    <div data-testid="dashboard-page" className="space-y-8">
      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Overview</div>
          <h1 className="font-display text-3xl tracking-tight mt-1">Booking source analytics</h1>
          <p className="text-sm text-dim mt-2 max-w-xl">
            How your reservations are coming in — across direct channels and OTAs.
          </p>
        </div>
        <Link
          to="/import"
          data-testid="dashboard-cta-import"
          className="inline-flex items-center gap-2 bg-brand text-black text-sm font-medium px-4 py-2 rounded-md hover:opacity-90 transition"
        >
          <Upload className="w-4 h-4" /> Import bookings
        </Link>
      </header>

      {empty ? (
        <EmptyState />
      ) : (
        <>
          <KPIRow data={data} />
          <ChartsGrid data={data} />
          <SourceBreakdownTable data={data} />
        </>
      )}
    </div>
  );
}

function KPIRow({ data }) {
  const totalDirect = data.split.direct.bookings;
  const totalOta = data.split.ota.bookings;
  const totalAll = totalDirect + totalOta;
  const directPct = totalAll ? Math.round((totalDirect / totalAll) * 100) : 0;
  const otaPct = totalAll ? Math.round((totalOta / totalAll) * 100) : 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <KPICard
        testid="kpi-total-bookings"
        label="Total reservations"
        value={fmtNumber(data.total_bookings)}
        sub={`${data.cancelled} cancelled`}
      />
      <KPICard
        testid="kpi-total-revenue"
        label="Total revenue"
        value={fmtMoney(data.total_revenue)}
        sub="Gross of OTA commission"
        accent
      />
      <KPICard
        testid="kpi-direct-share"
        label="Direct share"
        value={`${directPct}%`}
        sub={`${fmtMoney(data.split.direct.revenue)} from direct`}
      />
      <KPICard
        testid="kpi-ota-share"
        label="OTA share"
        value={`${otaPct}%`}
        sub={`${fmtMoney(data.split.ota.revenue)} from OTAs`}
      />
    </div>
  );
}

function ChartsGrid({ data }) {
  const bySource = [...data.by_source];

  const donutData = [
    { name: "Direct", value: data.split.direct.bookings, fill: "#D9A05B" },
    { name: "OTA", value: data.split.ota.bookings, fill: "#4B6BF5" },
  ].filter((d) => d.value > 0);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="surface rounded-md p-6 lg:col-span-2">
        <ChartHeader title="Bookings & revenue by source" sub="Bars show bookings, line shows revenue weight" />
        <div className="h-72 mt-4" data-testid="chart-bookings-by-source">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={bySource} margin={{ top: 6, right: 10, left: -10, bottom: 30 }}>
              <CartesianGrid stroke="#1c1f27" vertical={false} />
              <XAxis
                dataKey="source"
                tick={{ fill: "#8F95A3", fontSize: 10 }}
                interval={0}
                angle={-25}
                textAnchor="end"
              />
              <YAxis tick={{ fill: "#8F95A3", fontSize: 11 }} />
              <Tooltip
                contentStyle={tooltipStyle}
                cursor={{ fill: "rgba(255,255,255,0.04)" }}
                formatter={(v, k) => (k === "revenue" ? fmtMoney(v) : fmtNumber(v))}
              />
              <Bar dataKey="bookings" name="Bookings" radius={[4, 4, 0, 0]}>
                {bySource.map((d, i) => (
                  <Cell key={i} fill={SOURCE_COLORS[d.source] || "#6B7280"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="surface rounded-md p-6">
        <ChartHeader title="OTA vs Direct" sub="By number of bookings" />
        <div className="h-72 mt-4" data-testid="chart-ota-vs-direct">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={donutData}
                dataKey="value"
                nameKey="name"
                innerRadius={60}
                outerRadius={95}
                stroke="#090A0E"
                strokeWidth={3}
              >
                {donutData.map((d, i) => (
                  <Cell key={i} fill={d.fill} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} formatter={(v) => fmtNumber(v)} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#8F95A3" }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="surface rounded-md p-6 lg:col-span-3">
        <ChartHeader title="Revenue by source" sub="Total gross revenue, gross of OTA commission" />
        <div className="h-72 mt-4" data-testid="chart-revenue-by-source">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={bySource} margin={{ top: 6, right: 10, left: 10, bottom: 30 }}>
              <CartesianGrid stroke="#1c1f27" vertical={false} />
              <XAxis
                dataKey="source"
                tick={{ fill: "#8F95A3", fontSize: 10 }}
                interval={0}
                angle={-25}
                textAnchor="end"
              />
              <YAxis tick={{ fill: "#8F95A3", fontSize: 11 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v) => fmtMoney(v)} />
              <Bar dataKey="revenue" name="Revenue" radius={[4, 4, 0, 0]}>
                {bySource.map((d, i) => (
                  <Cell key={i} fill={SOURCE_COLORS[d.source] || "#6B7280"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}

function SourceBreakdownTable({ data }) {
  const total = data.total_bookings || 1;
  return (
    <div className="surface rounded-md p-6">
      <ChartHeader title="Source performance" sub="Detailed mix by booking source" />
      <div className="mt-5 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] uppercase tracking-[0.15em] text-[#6B7280]">
              <th className="text-left font-semibold pb-3">Source</th>
              <th className="text-right font-semibold pb-3">Bookings</th>
              <th className="text-right font-semibold pb-3">Share</th>
              <th className="text-right font-semibold pb-3">Revenue</th>
            </tr>
          </thead>
          <tbody>
            {data.by_source.map((s) => (
              <tr key={s.source} className="tbl-row">
                <td className="py-3">
                  <div className="flex items-center gap-2.5">
                    <span
                      className="w-2.5 h-2.5 rounded-full inline-block"
                      style={{ backgroundColor: SOURCE_COLORS[s.source] || "#6B7280" }}
                    />
                    <span className="text-white">{s.source}</span>
                  </div>
                </td>
                <td className="py-3 text-right tabular-nums">{fmtNumber(s.bookings)}</td>
                <td className="py-3 text-right text-dim tabular-nums">
                  {((s.bookings / total) * 100).toFixed(1)}%
                </td>
                <td className="py-3 text-right tabular-nums">{fmtMoney(s.revenue)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ChartHeader({ title, sub }) {
  return (
    <div>
      <h2 className="font-display text-lg text-white">{title}</h2>
      <p className="text-xs text-dim mt-1">{sub}</p>
    </div>
  );
}

function EmptyState() {
  return (
    <div
      data-testid="dashboard-empty-state"
      className="surface rounded-md p-12 flex flex-col items-center text-center relative overflow-hidden"
    >
      <div
        className="absolute inset-0 opacity-[0.08] pointer-events-none"
        style={{
          backgroundImage:
            "url(https://images.unsplash.com/photo-1770486036751-e55247238964?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NzN8MHwxfHNlYXJjaHwzfHxhYnN0cmFjdCUyMGRhdGElMjBncmlkJTIwZGFya3xlbnwwfHx8fDE3ODA3MDgxMTB8MA&ixlib=rb-4.1.0&q=85)",
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      />
      <div className="relative">
        <div className="text-[11px] uppercase tracking-[0.22em] text-dim">No data yet</div>
        <h2 className="font-display text-2xl mt-3">Import your first CSV to see analytics</h2>
        <p className="text-sm text-dim mt-3 max-w-md mx-auto">
          Upload a booking export from Airbnb, Booking.com, your PMS, or a combined CSV. We&apos;ll classify every
          reservation by source automatically.
        </p>
        <Link
          to="/import"
          data-testid="empty-cta-import"
          className="mt-6 inline-flex items-center gap-2 bg-brand text-black text-sm font-medium px-5 py-2.5 rounded-md hover:opacity-90"
        >
          <Upload className="w-4 h-4" /> Upload CSV
        </Link>
      </div>
    </div>
  );
}

function SkeletonBlock() {
  return (
    <div className="space-y-4">
      <div className="h-10 w-64 surface rounded animate-pulse" />
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-32 surface rounded animate-pulse" />
        ))}
      </div>
      <div className="h-72 surface rounded animate-pulse" />
    </div>
  );
}
