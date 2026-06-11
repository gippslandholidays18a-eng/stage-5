import { useEffect, useMemo, useState } from "react";
import { api, API, fmtAUD, fmtNumber, fmtPct } from "@/lib/api";
import { toast } from "sonner";
import {
  Target,
  Download,
  ChevronDown,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Minus,
  Mail,
  MessageSquare,
} from "lucide-react";

export default function Campaigns() {
  const [data, setData] = useState(null);
  const [tracker, setTracker] = useState(null);
  const [tab, setTab] = useState(0);
  const [expanded, setExpanded] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get("/campaigns"),
      api.get("/campaigns/growth-tracker"),
    ]).then(([c, t]) => {
      if (cancelled) return;
      setData(c.data);
      setTracker(t.data);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading || !data || !tracker) return <div className="text-dim text-sm">Loading campaigns…</div>;

  const activeTab = data.tabs[tab];
  const cards = (data.grouped && data.grouped[activeTab]) || [];

  return (
    <div data-testid="campaigns-page" className="space-y-6">
      <header>
        <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Campaigns</div>
        <h1 className="font-display text-3xl tracking-tight mt-1">Direct booking growth engine</h1>
        <p className="text-sm text-dim mt-2 max-w-2xl">
          Audience lists, recommended offers, and campaign briefs — exportable into SendFox, Make.com, or any tool. The app never sends; it just tells you who to reach and how.
        </p>
      </header>

      <GrowthTracker tracker={tracker} onTargetSaved={(v) => setTracker({ ...tracker, target_direct_pct: v })} />

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 border-b divider" data-testid="campaign-tabs">
        {data.tabs.map((t, i) => (
          <button
            key={t}
            onClick={() => { setTab(i); setExpanded(null); }}
            data-testid={`tab-${t.replace(/[^a-z0-9]+/gi,'-').toLowerCase()}`}
            className={`px-4 py-2.5 text-sm border-b-2 -mb-px transition-colors ${
              i === tab ? "border-[#D9A05B] text-white" : "border-transparent text-dim hover:text-white"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-testid="campaign-cards">
        {cards.map((c) => (
          <CampaignCard
            key={c.key}
            brief={c}
            expanded={expanded === c.key}
            onToggle={() => setExpanded(expanded === c.key ? null : c.key)}
          />
        ))}
      </div>
    </div>
  );
}

function GrowthTracker({ tracker, onTargetSaved }) {
  const [editingTarget, setEditingTarget] = useState(false);
  const [target, setTarget] = useState(tracker.target_direct_pct);
  const [saving, setSaving] = useState(false);

  const saveTarget = async () => {
    setSaving(true);
    try {
      const r = await api.put("/settings/direct-target", { target_direct_pct: parseFloat(target) });
      toast.success("Target updated");
      onTargetSaved(r.data.target_direct_pct);
      setEditingTarget(false);
    } catch {
      toast.error("Could not save target");
    } finally {
      setSaving(false);
    }
  };

  const arrow = (curr, prev) => {
    if (prev === 0 && curr === 0) return <Minus className="w-3.5 h-3.5 text-dim" />;
    if (curr > prev) return <TrendingUp className="w-3.5 h-3.5 text-[#419B72]" />;
    if (curr < prev) return <TrendingDown className="w-3.5 h-3.5 text-[#E05A50]" />;
    return <Minus className="w-3.5 h-3.5 text-dim" />;
  };

  return (
    <div data-testid="growth-tracker" className="surface rounded-md p-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-[#D9A05B]" />
          <h2 className="font-display text-lg">Direct booking growth</h2>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Target</label>
          {editingTarget ? (
            <>
              <input
                type="number"
                min="0"
                max="100"
                step="1"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                data-testid="target-input"
                className="bg-transparent border border-[#22252F] rounded-md px-2 py-1 text-sm w-20 text-white"
              />
              <button
                onClick={saveTarget}
                disabled={saving}
                data-testid="save-target"
                className="bg-brand text-black text-xs px-3 py-1.5 rounded-md hover:opacity-90"
              >Save</button>
              <button onClick={() => setEditingTarget(false)} className="text-dim text-xs">Cancel</button>
            </>
          ) : (
            <button
              onClick={() => setEditingTarget(true)}
              data-testid="edit-target"
              className="text-white text-sm hover:underline"
            >
              {tracker.target_direct_pct}% <span className="text-dim text-xs">(edit)</span>
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-5">
        <div data-testid="tracker-current">
          <div className="text-[10px] uppercase tracking-[0.15em] text-dim">Current direct %</div>
          <div className="font-display text-3xl mt-2 text-white">{tracker.current_direct_pct}%</div>
          <div className="text-[11px] text-dim mt-1">Last 12 months</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-dim">3 months ago</div>
          <div className="font-display text-2xl mt-2 text-white flex items-center gap-1.5">
            {tracker.three_months_ago_pct}% {arrow(tracker.current_direct_pct, tracker.three_months_ago_pct)}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-dim">6 months ago</div>
          <div className="font-display text-2xl mt-2 text-white flex items-center gap-1.5">
            {tracker.six_months_ago_pct}% {arrow(tracker.current_direct_pct, tracker.six_months_ago_pct)}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-dim">Est. annual savings at target</div>
          <div className="font-display text-2xl mt-2 text-[#419B72]" data-testid="tracker-savings">{fmtAUD(tracker.estimated_annual_savings_if_target_hit)}</div>
          <div className="text-[11px] text-dim mt-1">If direct % reaches target</div>
        </div>
      </div>

      <div className="mt-6">
        <div className="flex justify-between text-[11px] text-dim mb-2">
          <span>Progress vs target</span>
          <span>{tracker.progress_pct}%</span>
        </div>
        <div className="w-full h-2 bg-[#0E1015] rounded">
          <div
            className="h-full rounded transition-all"
            style={{
              width: `${tracker.progress_pct}%`,
              backgroundColor: tracker.progress_pct >= 100 ? "#419B72" : "#D9A05B",
            }}
            data-testid="progress-bar"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6 pt-5 border-t divider">
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-dim">High priority conversion audience</div>
          <div className="font-display text-2xl mt-2">{fmtNumber(tracker.high_priority_audience_size)} guests</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.15em] text-dim">Est. revenue opportunity</div>
          <div className="font-display text-2xl mt-2 text-[#D9A05B]">{fmtAUD(tracker.high_priority_estimated_opportunity)}</div>
        </div>
      </div>
    </div>
  );
}

function CampaignCard({ brief, expanded, onToggle }) {
  const offer = brief.offer_detail;
  const exportUrl = `${API}/campaigns/${brief.key}/export.csv`;
  const testid = `card-${brief.key}`;
  return (
    <div data-testid={testid} className="surface rounded-md overflow-hidden">
      <div
        className="p-5 cursor-pointer hover:bg-[#15181F] transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.15em] text-dim">
              {brief.tab} · {brief.goal}
            </div>
            <h3 className="font-display text-base text-white mt-1.5">{brief.name}</h3>
            <p className="text-xs text-dim mt-1.5 line-clamp-2">{brief.description}</p>
          </div>
          {expanded ? <ChevronDown className="w-4 h-4 text-dim shrink-0 mt-1" /> : <ChevronRight className="w-4 h-4 text-dim shrink-0 mt-1" />}
        </div>

        <div className="grid grid-cols-3 gap-3 mt-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-dim">Audience</div>
            <div className="font-display text-xl mt-1" data-testid={`size-${brief.key}`}>{fmtNumber(brief.audience_size)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-dim">Offer</div>
            <div className="text-sm mt-1 text-[#D9A05B] font-mono">{brief.recommended_offer}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-dim">Est. opportunity</div>
            <div className="font-display text-xl mt-1 text-[#419B72]" data-testid={`opp-${brief.key}`}>{fmtAUD(brief.estimated_opportunity)}</div>
          </div>
        </div>
      </div>

      {expanded && (
        <div className="px-5 pb-5 pt-3 border-t divider space-y-4" data-testid={`expanded-${brief.key}`}>
          {/* Brief details */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <Field label="Campaign type" value={brief.campaign_type} />
            <Field label="Send timing" value={brief.send_timing} />
            <Field label="Conversion rate assumption" value={fmtPct(brief.conversion_rate * 100)} />
            <Field label="Offer category" value={offer?.category || "—"} />
          </div>

          {offer && (
            <div className="bg-[#0E1015] border divider rounded-md p-4">
              <div className="text-[10px] uppercase tracking-[0.15em] text-dim">Recommended offer</div>
              <div className="mt-1.5 flex items-center gap-2">
                <span className="text-[#D9A05B] font-mono text-sm">{offer.code}</span>
                <span className="text-white text-sm">·</span>
                <span className="text-white text-sm">{offer.name}</span>
              </div>
              <div className="text-xs text-dim mt-1.5">{offer.description}</div>
            </div>
          )}

          {/* Content recommendations */}
          <div>
            <div className="text-[10px] uppercase tracking-[0.15em] text-dim mb-2">Content recommendations</div>

            <div className="bg-[#0E1015] border divider rounded-md p-4 space-y-3">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-dim flex items-center gap-1.5">
                  <Mail className="w-3 h-3" /> Subject line variations
                </div>
                <ul className="mt-1.5 space-y-1 text-xs text-white">
                  {(brief.content?.subject_lines || []).map((s, i) => (
                    <li key={i} className="font-mono">• {s}</li>
                  ))}
                </ul>
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-wider text-dim flex items-center gap-1.5">
                  <MessageSquare className="w-3 h-3" /> SMS (≤160 chars)
                </div>
                <div className="mt-1.5 text-xs text-white font-mono bg-[#15181F] px-2 py-1.5 rounded">
                  {brief.content?.sms}
                </div>
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-wider text-dim">Key message points</div>
                <ul className="mt-1.5 space-y-1 text-xs text-white list-disc pl-5">
                  {(brief.content?.key_points || []).map((p, i) => <li key={i}>{p}</li>)}
                </ul>
              </div>

              <div className="flex gap-4 text-[11px] text-dim">
                <span>Tone: <strong className="text-white">{brief.content?.tone}</strong></span>
                <span>Timing: <strong className="text-white">{brief.content?.send_timing}</strong></span>
              </div>
            </div>
          </div>

          <div className="flex justify-end">
            <a
              href={exportUrl}
              data-testid={`export-${brief.key}`}
              className="inline-flex items-center gap-2 bg-brand text-black text-sm font-medium px-4 py-2 rounded-md hover:opacity-90"
            >
              <Download className="w-4 h-4" /> Export audience CSV
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.15em] text-dim">{label}</div>
      <div className="text-sm text-white mt-1">{value}</div>
    </div>
  );
}
