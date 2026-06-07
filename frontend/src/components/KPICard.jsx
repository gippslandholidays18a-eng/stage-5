export default function KPICard({ label, value, sub, accent = false, testid }) {
  return (
    <div
      data-testid={testid}
      className={`surface rounded-md p-6 flex flex-col justify-between min-h-[140px] ${
        accent ? "border-[#D9A05B]/40" : ""
      }`}
    >
      <div className="text-[11px] uppercase tracking-[0.18em] text-dim">{label}</div>
      <div className="font-display text-4xl sm:text-5xl font-light tracking-tighter text-white mt-3">
        {value}
      </div>
      {sub && <div className="text-xs text-dim mt-2">{sub}</div>}
    </div>
  );
}
