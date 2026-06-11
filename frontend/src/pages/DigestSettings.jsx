import { useEffect, useState } from "react";
import { api, API } from "@/lib/api";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Mail, Save, Plus, X, Send, Copy, RefreshCcw, Clock, Eye } from "lucide-react";

const TZS = [
  "Australia/Sydney",
  "Australia/Melbourne",
  "Australia/Brisbane",
  "Australia/Adelaide",
  "Australia/Perth",
  "Pacific/Auckland",
  "UTC",
];

export default function DigestSettings() {
  const [cfg, setCfg] = useState(null);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [daysOfWeek, setDaysOfWeek] = useState([]);
  const [senderEmail, setSenderEmail] = useState("");
  const [newRecipient, setNewRecipient] = useState("");
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [testRecipient, setTestRecipient] = useState("");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get("/settings/digest"),
      api.get("/digest/history"),
    ]).then(([s, h]) => {
      if (cancelled) return;
      setCfg(s.data.config);
      setWebhookUrl(s.data.webhook_url);
      setDaysOfWeek(s.data.days_of_week);
      setSenderEmail(s.data.sender_email);
      setHistory(h.data.items || []);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [version]);

  if (loading || !cfg) return <div className="text-dim text-sm">Loading…</div>;

  const update = (patch) => setCfg((c) => ({ ...c, ...patch }));
  const addRecipient = () => {
    const e = newRecipient.trim().toLowerCase();
    if (!e || !e.includes("@")) {
      toast.error("Enter a valid email");
      return;
    }
    if ((cfg.recipients || []).includes(e)) return;
    update({ recipients: [...(cfg.recipients || []), e] });
    setNewRecipient("");
  };
  const removeRecipient = (e) => update({ recipients: cfg.recipients.filter((x) => x !== e) });

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/settings/digest", {
        recipients: cfg.recipients,
        send_day: cfg.send_day,
        send_hour: cfg.send_hour,
        send_minute: cfg.send_minute,
        timezone: cfg.timezone,
        enabled: cfg.enabled,
      });
      toast.success("Digest settings saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const sendNow = async () => {
    setSending(true);
    try {
      const r = await api.post("/digest/send-now", {
        test_recipient: testRecipient || null,
      });
      if (r.data.status === "sent") {
        toast.success(`Digest sent to ${(r.data.recipients || []).join(", ")}`);
      } else {
        toast.warning(`Digest ${r.data.status}: ${r.data.reason || r.data.error || ""}`);
      }
      setVersion((v) => v + 1);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    } finally {
      setSending(false);
    }
  };

  const rotate = async () => {
    if (!window.confirm("Rotate webhook token? You will need to update cron-job.org with the new URL.")) return;
    try {
      const r = await api.post("/settings/digest/rotate-token");
      setWebhookUrl(r.data.webhook_url);
      toast.success("Webhook token rotated");
    } catch {
      toast.error("Could not rotate");
    }
  };

  const copy = (text) => {
    navigator.clipboard.writeText(text).then(() => toast.success("Copied"));
  };

  return (
    <div data-testid="digest-settings-page" className="space-y-8 max-w-4xl">
      <header>
        <div className="text-[11px] uppercase tracking-[0.22em] text-dim">Settings · Admin</div>
        <h1 className="font-display text-3xl tracking-tight mt-1">Weekly digest</h1>
        <p className="text-sm text-dim mt-2 max-w-2xl">
          Automated weekly KPI summary sent via Resend. The webhook URL below is
          designed to be called once a week by cron-job.org or any external scheduler.
        </p>
      </header>

      {/* Enable */}
      <div className="surface rounded-md p-6 flex items-center justify-between">
        <div>
          <div className="text-sm text-white">Digest enabled</div>
          <div className="text-xs text-dim mt-1">
            When off, the webhook responds but no email is sent.
          </div>
        </div>
        <Switch
          data-testid="digest-enabled-switch"
          checked={cfg.enabled}
          onCheckedChange={(v) => update({ enabled: v })}
        />
      </div>

      {/* Recipients */}
      <div className="surface rounded-md p-6">
        <div className="flex items-center gap-2 mb-3">
          <Mail className="w-4 h-4 text-[#D9A05B]" />
          <div className="text-sm text-white">Recipients</div>
          <span className="text-[11px] text-dim ml-auto">
            From: {senderEmail}
          </span>
        </div>
        <div className="flex flex-wrap gap-2 mb-4" data-testid="recipient-list">
          {(cfg.recipients || []).length === 0 && (
            <span className="text-xs text-dim">No recipients yet.</span>
          )}
          {(cfg.recipients || []).map((e) => (
            <span
              key={e}
              data-testid={`recipient-${e}`}
              className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md bg-[#1A1D24] border divider"
            >
              {e}
              <button
                onClick={() => removeRecipient(e)}
                data-testid={`remove-recipient-${e}`}
                className="text-dim hover:text-[#E05A50]"
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <Input
            data-testid="new-recipient-input"
            placeholder="email@example.com"
            value={newRecipient}
            onChange={(e) => setNewRecipient(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addRecipient(); } }}
            className="bg-transparent border-[#22252F] focus-visible:ring-1 focus-visible:ring-[#D9A05B]"
          />
          <button
            onClick={addRecipient}
            data-testid="add-recipient-button"
            className="inline-flex items-center gap-1.5 bg-[#1A1D24] border divider text-sm px-3 rounded-md hover:bg-[#22252F]"
          >
            <Plus className="w-4 h-4" /> Add
          </button>
        </div>
        <p className="text-[11px] text-dim mt-3">
          Resend test mode only delivers to your verified signup email until you verify a domain. Other recipients are saved but won&apos;t receive emails yet.
        </p>
      </div>

      {/* Schedule */}
      <div className="surface rounded-md p-6">
        <div className="flex items-center gap-2 mb-4">
          <Clock className="w-4 h-4 text-[#D9A05B]" />
          <div className="text-sm text-white">Schedule</div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Day of week</label>
            <Select value={String(cfg.send_day)} onValueChange={(v) => update({ send_day: parseInt(v) })}>
              <SelectTrigger data-testid="send-day" className="mt-1 bg-transparent border-[#22252F] text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
                {daysOfWeek.map((d, i) => (
                  <SelectItem key={d} value={String(i + 1)}>{d}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Time</label>
            <div className="flex gap-2 mt-1">
              <Input
                type="number"
                min="0"
                max="23"
                value={cfg.send_hour}
                data-testid="send-hour"
                onChange={(e) => update({ send_hour: parseInt(e.target.value) || 0 })}
                className="bg-transparent border-[#22252F] text-sm w-20"
              />
              <span className="self-center text-dim">:</span>
              <Input
                type="number"
                min="0"
                max="59"
                value={cfg.send_minute}
                data-testid="send-minute"
                onChange={(e) => update({ send_minute: parseInt(e.target.value) || 0 })}
                className="bg-transparent border-[#22252F] text-sm w-20"
              />
            </div>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-[0.15em] text-dim">Timezone</label>
            <Select value={cfg.timezone} onValueChange={(v) => update({ timezone: v })}>
              <SelectTrigger data-testid="timezone" className="mt-1 bg-transparent border-[#22252F] text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-[#12141A] border-[#22252F] text-white">
                {TZS.map((tz) => <SelectItem key={tz} value={tz}>{tz}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <p className="text-[11px] text-dim mt-3">
          The schedule is informational — actual sending is triggered by the webhook below.
          Configure cron-job.org to call the webhook at this day/time in your timezone.
        </p>
      </div>

      {/* Webhook */}
      <div className="surface rounded-md p-6">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm text-white">Webhook URL</div>
          <button
            onClick={rotate}
            data-testid="rotate-token-button"
            className="text-xs text-dim hover:text-white inline-flex items-center gap-1"
          >
            <RefreshCcw className="w-3 h-3" /> Rotate token
          </button>
        </div>
        <div className="flex gap-2">
          <input
            readOnly
            value={webhookUrl}
            data-testid="webhook-url"
            className="flex-1 bg-[#0E1015] border border-[#22252F] rounded-md px-3 py-2 text-xs font-mono text-dim"
          />
          <button
            onClick={() => copy(webhookUrl)}
            data-testid="copy-webhook-button"
            className="inline-flex items-center gap-1.5 bg-[#1A1D24] border divider text-sm px-3 rounded-md hover:bg-[#22252F]"
          >
            <Copy className="w-4 h-4" />
          </button>
        </div>
        <div className="mt-4 text-[11px] text-dim leading-relaxed">
          <strong className="text-white">Set up cron-job.org:</strong> sign in → Create cronjob →
          paste this URL → choose execution time (Mondays 08:00 Australia/Sydney) → enable.
          The webhook returns <code className="bg-[#0E1015] px-1 rounded">sent</code>, <code className="bg-[#0E1015] px-1 rounded">skipped: no_new_data</code>,
          or <code className="bg-[#0E1015] px-1 rounded">skipped: disabled</code> — all 200 OK so cron-job.org won&apos;t alert on skips.
        </div>
      </div>

      {/* Save bar */}
      <div className="flex flex-wrap gap-3 justify-end">
        <a
          href={`${API}/digest/preview`}
          target="_blank"
          rel="noopener noreferrer"
          data-testid="preview-digest-link"
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md text-sm border border-[#22252F] text-dim hover:text-white hover:bg-[#14161D]"
        >
          <Eye className="w-3.5 h-3.5" /> Preview JSON
        </a>
        <button
          onClick={handleSave}
          disabled={saving}
          data-testid="save-digest-button"
          className="inline-flex items-center gap-2 bg-brand text-black text-sm font-medium px-5 py-2.5 rounded-md hover:opacity-90 disabled:opacity-50"
        >
          <Save className="w-4 h-4" /> {saving ? "Saving…" : "Save settings"}
        </button>
      </div>

      {/* Manual send */}
      <div className="surface rounded-md p-6">
        <div className="flex items-center gap-2">
          <Send className="w-4 h-4 text-[#D9A05B]" />
          <div className="text-sm text-white">Send a test now</div>
        </div>
        <p className="text-xs text-dim mt-2">
          Force-sends the digest immediately, ignoring the &ldquo;no new data&rdquo; guard. Optionally override the recipient list with one test address.
        </p>
        <div className="flex flex-wrap gap-2 mt-3">
          <Input
            placeholder="(optional) test recipient — leave blank to use the saved list"
            value={testRecipient}
            onChange={(e) => setTestRecipient(e.target.value)}
            data-testid="test-recipient-input"
            className="bg-transparent border-[#22252F] text-sm flex-1 min-w-[260px] focus-visible:ring-1 focus-visible:ring-[#D9A05B]"
          />
          <button
            onClick={sendNow}
            disabled={sending}
            data-testid="send-now-button"
            className="inline-flex items-center gap-2 bg-brand text-black text-sm font-medium px-5 py-2.5 rounded-md hover:opacity-90 disabled:opacity-50"
          >
            <Send className="w-4 h-4" /> {sending ? "Sending…" : "Send now"}
          </button>
        </div>
      </div>

      {/* History */}
      <div className="surface rounded-md overflow-hidden">
        <div className="px-6 py-4 border-b divider">
          <h2 className="font-display text-base">Recent sends</h2>
          <p className="text-xs text-dim mt-1">Last 30 events.</p>
        </div>
        {history.length === 0 ? (
          <div className="px-6 py-10 text-center text-dim text-sm">No digest activity yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[#0E1015]">
                <tr className="text-[10px] uppercase tracking-[0.15em] text-[#6B7280]">
                  <th className="text-left px-4 py-3 font-semibold">When</th>
                  <th className="text-left px-4 py-3 font-semibold">Status</th>
                  <th className="text-left px-4 py-3 font-semibold">Recipients</th>
                  <th className="text-left px-4 py-3 font-semibold">Details</th>
                </tr>
              </thead>
              <tbody data-testid="digest-history-body">
                {history.map((h) => (
                  <tr key={h.id} className="tbl-row">
                    <td className="px-4 py-3 text-dim">{new Date(h.sent_at).toLocaleString()}</td>
                    <td className="px-4 py-3">
                      <span
                        className="text-[10px] px-2 py-0.5 rounded uppercase tracking-wider"
                        style={{
                          color: h.status === "sent" ? "#419B72" : h.status === "skipped" ? "#D9A05B" : "#E05A50",
                          backgroundColor: h.status === "sent" ? "#419B7214" : h.status === "skipped" ? "#D9A05B14" : "#E05A5014",
                          border: `1px solid ${(h.status === "sent" ? "#419B72" : h.status === "skipped" ? "#D9A05B" : "#E05A50")}44`,
                        }}
                      >
                        {h.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-dim text-xs">{(h.recipients || []).join(", ") || "—"}</td>
                    <td className="px-4 py-3 text-dim text-xs">{h.reason || h.error || h.email_id || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
