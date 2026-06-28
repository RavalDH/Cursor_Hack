import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState, useCallback } from "react";

const API = "http://localhost:8000";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Mine Gas Safety" },
      { name: "description", content: "Underground mine gas-safety control dashboard." },
    ],
  }),
  component: Dashboard,
});

type Zone = {
  id: string;
  methane: number;
  co: number;
  temp: number;
  airflow: number;
  status: "green" | "yellow" | "red";
  trend: "rising" | "stable";
  fan_speed?: number;
  mitigation?: boolean;
  actions?: string[];
};

type Citation = { source: string; text: string };

type Alert = {
  alert: boolean;
  zone?: string;
  metric?: string;
  value?: number;
  threshold?: number;
  trend?: string;
  answer?: string;
  citations?: Citation[];
  recovered?: boolean;
  recovered_zone?: string;
  message?: string;
};

function useInterval(fn: () => void, ms: number) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    ref.current();
    const id = setInterval(() => ref.current(), ms);
    return () => clearInterval(id);
  }, [ms]);
}

function Dashboard() {
  const [zones, setZones] = useState<Zone[]>([]);
  const [alert, setAlert] = useState<Alert>({ alert: false });
  const [online, setOnline] = useState(true);
  const [muted, setMuted] = useState(false);
  const mutedRef = useRef(muted);
  mutedRef.current = muted;
  const lastSpokenKey = useRef<string | null>(null);
  const lastRecoveredKey = useRef<string | null>(null);

  const [recovery, setRecovery] = useState<{ zone?: string; message: string } | null>(null);
  const recoveryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [askAnswer, setAskAnswer] = useState<string | null>(null);
  const [askCitations, setAskCitations] = useState<Citation[]>([]);

  const speak = useCallback((text: string) => {
    try {
      if (typeof window === "undefined" || !window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.rate = 1;
      u.pitch = 1;
      window.speechSynthesis.speak(u);
    } catch {
      /* silent */
    }
  }, []);

  useInterval(() => {
    fetch(`${API}/zones`)
      .then((r) => r.json())
      .then((d) => {
        setZones(d.zones || []);
        setOnline(true);
      })
      .catch(() => setOnline(false));
  }, 2000);

  useInterval(() => {
    fetch(`${API}/alert`)
      .then((r) => r.json())
      .then((d: Alert) => {
        setAlert(d);
        setOnline(true);

        if (d.alert && d.answer) {
          const key = `${d.zone}|${d.metric}`;
          if (lastSpokenKey.current !== key) {
            lastSpokenKey.current = key;
            if (!mutedRef.current) speak(d.answer);
          }
        } else {
          lastSpokenKey.current = null;
        }

        if (d.recovered && d.message) {
          const rkey = `${d.recovered_zone ?? ""}|${d.message}`;
          if (lastRecoveredKey.current !== rkey) {
            lastRecoveredKey.current = rkey;
            setRecovery({ zone: d.recovered_zone, message: d.message });
            if (!mutedRef.current) speak(d.message);
            if (recoveryTimer.current) clearTimeout(recoveryTimer.current);
            recoveryTimer.current = setTimeout(() => setRecovery(null), 5000);
          }
        }
      })
      .catch(() => setOnline(false));
  }, 2000);

  const ask = async () => {
    const q = question.trim();
    if (!q || asking) return;
    setAsking(true);
    try {
      const res = await fetch(`${API}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      const data = await res.json();
      setAskAnswer(data.answer || "");
      setAskCitations(data.citations || []);
      setOnline(true);
    } catch {
      setOnline(false);
    } finally {
      setAsking(false);
    }
  };

  const toggleMute = () => {
    setMuted((m) => {
      const next = !m;
      if (next && typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
      return next;
    });
  };

  return (
    <div className="min-h-screen text-slate-100 bg-[#0a0e14]" style={{ fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif" }}>
      <header className="flex items-center justify-between px-6 py-4 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="size-2.5 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.8)]" />
          <h1 className="text-lg font-semibold tracking-wide uppercase text-slate-200">Mine Gas Safety · Control</h1>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <div
            className={`flex items-center gap-2 px-3 py-1.5 rounded-full border ${
              online
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                : "border-amber-500/40 bg-amber-500/10 text-amber-300"
            }`}
          >
            <span className={`size-1.5 rounded-full ${online ? "bg-emerald-400" : "bg-amber-400 animate-pulse"}`} />
            {online ? "backend online" : "backend offline · retrying"}
          </div>
          <button
            onClick={toggleMute}
            className="px-3 py-1.5 rounded-full border border-white/10 bg-white/5 hover:bg-white/10 transition text-slate-200"
            title={muted ? "Unmute voice" : "Mute voice"}
          >
            {muted ? "🔇 muted" : "🔊 voice"}
          </button>
        </div>
      </header>

      {recovery && (
        <div
          className="mx-6 mt-4 rounded-xl border border-emerald-500/60 bg-gradient-to-r from-emerald-950/80 to-emerald-900/40 p-5 shadow-[0_0_40px_rgba(16,185,129,0.25)] animate-[fadeIn_.25s_ease-out]"
        >
          <div className="flex flex-wrap items-center gap-3">
            <span className="px-2 py-0.5 rounded bg-emerald-500 text-emerald-950 text-xs font-bold tracking-widest">ALL CLEAR</span>
            {recovery.zone && (
              <span className="text-emerald-100 font-semibold">Zone {recovery.zone}</span>
            )}
          </div>
          <p className="mt-3 text-emerald-50/95 leading-relaxed">{recovery.message}</p>
        </div>
      )}

      {alert.alert && (
        <div
          className="mx-6 mt-4 rounded-xl border border-red-500/60 bg-gradient-to-r from-red-950/80 to-red-900/40 p-5 shadow-[0_0_40px_rgba(239,68,68,0.25)] animate-[fadeIn_.25s_ease-out]"
          style={{ animation: "alertPulse 1.6s ease-in-out infinite" }}
        >
          <div className="flex flex-wrap items-center gap-3">
            <span className="px-2 py-0.5 rounded bg-red-500 text-white text-xs font-bold tracking-widest">ALERT</span>
            <span className="text-red-100 font-semibold">Zone {alert.zone}</span>
            <span className="text-red-200/80 text-sm">
              {alert.metric}: <span className="font-mono text-red-50">{alert.value}</span> /
              threshold <span className="font-mono">{alert.threshold}</span>
            </span>
            {alert.trend === "rising" && (
              <span className="px-2 py-0.5 rounded bg-red-500/30 border border-red-400/60 text-red-100 text-xs font-bold">↑ RISING</span>
            )}
          </div>
          {alert.answer && (
            <p className="mt-3 text-red-50/95 leading-relaxed">{alert.answer}</p>
          )}
          {alert.citations && alert.citations.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {alert.citations.map((c, i) => (
                <span
                  key={i}
                  className="px-2 py-1 rounded-md bg-red-500/15 border border-red-400/30 text-red-100 text-xs"
                  title={c.text}
                >
                  📄 {c.source}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <section className="px-6 py-6">
        <div className="text-xs uppercase tracking-widest text-slate-400 mb-3">Zones · live · 2s poll</div>
        {zones.length === 0 ? (
          <div className="text-slate-500 text-sm">Waiting for zone data…</div>
        ) : (
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {zones.map((z) => (
              <ZoneCard key={z.id} zone={z} />
            ))}
          </div>
        )}
      </section>

      <section className="px-6 pb-10">
        <div className="text-xs uppercase tracking-widest text-slate-400 mb-3">Ask</div>
        <div className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") ask();
            }}
            placeholder="e.g. What should I do if methane rises above 1.5% in Zone B?"
            className="flex-1 px-4 py-3 rounded-lg bg-white/5 border border-white/10 focus:border-emerald-400/50 focus:outline-none text-slate-100 placeholder:text-slate-500"
          />
          <button
            onClick={ask}
            disabled={asking || !question.trim()}
            className="px-5 py-3 rounded-lg bg-emerald-500 hover:bg-emerald-400 disabled:bg-slate-700 disabled:text-slate-400 text-slate-950 font-semibold transition"
          >
            {asking ? "Asking…" : "Ask"}
          </button>
        </div>
        {askAnswer !== null && (
          <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-slate-100 leading-relaxed whitespace-pre-wrap">{askAnswer}</p>
            {askCitations.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {askCitations.map((c, i) => (
                  <span
                    key={i}
                    className="px-2 py-1 rounded-md bg-white/5 border border-white/10 text-slate-300 text-xs"
                    title={c.text}
                  >
                    📄 {c.source}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      <style>{`
        @keyframes fadeIn { from { opacity: 0; transform: translateY(-4px);} to { opacity: 1; transform: none;} }
        @keyframes alertPulse {
          0%, 100% { box-shadow: 0 0 30px rgba(239,68,68,0.20); }
          50% { box-shadow: 0 0 55px rgba(239,68,68,0.45); }
        }
        @keyframes statusGlow {
          0%, 100% { transform: scale(1); opacity: .9; }
          50% { transform: scale(1.15); opacity: 1; }
        }
        @keyframes fanSpin { from { transform: rotate(0deg);} to { transform: rotate(360deg);} }
      `}</style>
    </div>
  );
}

function ZoneCard({ zone }: { zone: Zone }) {
  const fanSpeed = typeof zone.fan_speed === "number" ? zone.fan_speed : 0;
  const mitigation = !!zone.mitigation;
  const actions = Array.isArray(zone.actions) ? zone.actions : [];

  const palette = {
    green: {
      border: "border-emerald-500/40",
      bg: "bg-emerald-500/[0.06]",
      dot: "bg-emerald-400 shadow-[0_0_14px_rgba(52,211,153,0.9)]",
      tag: "text-emerald-300",
      ring: "ring-emerald-500/20",
      fan: "text-emerald-300",
    },
    yellow: {
      border: "border-amber-400/60",
      bg: "bg-amber-400/[0.08]",
      dot: "bg-amber-300 shadow-[0_0_14px_rgba(252,211,77,0.9)]",
      tag: "text-amber-300",
      ring: "ring-amber-400/30",
      fan: "text-amber-300",
    },
    red: {
      border: "border-red-500/70",
      bg: "bg-red-500/[0.10]",
      dot: "bg-red-400 shadow-[0_0_16px_rgba(248,113,113,1)]",
      tag: "text-red-300",
      ring: "ring-red-500/40",
      fan: "text-red-300",
    },
  }[zone.status];

  // Faster fan -> faster spin: 0% is 6s/rev, 100% is 0.25s/rev.
  const spinDuration =
    fanSpeed <= 0 ? 0 : Math.max(0.25, 6 - (fanSpeed / 100) * 5.75);

  return (
    <div
      className={`relative rounded-2xl border ${palette.border} ${palette.bg} ring-1 ${palette.ring} p-5 transition-all duration-700 ease-out`}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm font-semibold tracking-widest text-slate-300 uppercase">Zone {zone.id}</div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-bold uppercase tracking-widest ${palette.tag}`}>{zone.status}</span>
          <span
            className={`size-2.5 rounded-full ${palette.dot}`}
            style={zone.status !== "green" ? { animation: "statusGlow 1.4s ease-in-out infinite" } : undefined}
          />
        </div>
      </div>

      <div className="flex items-baseline gap-2">
        <div className="text-5xl font-semibold tabular-nums text-slate-50 transition-colors duration-500">
          {zone.methane.toFixed(2)}
          <span className="text-2xl text-slate-400 ml-1">%</span>
        </div>
        {zone.trend === "rising" && (
          <span className={`text-xl font-bold ${palette.tag}`} title="Rising">↑</span>
        )}
      </div>
      <div className="text-[11px] uppercase tracking-widest text-slate-500 mt-1">Methane (CH₄)</div>

      <div className="mt-5 grid grid-cols-3 gap-3 text-sm">
        <Metric label="CO" value={`${zone.co} ppm`} />
        <Metric label="Temp" value={`${zone.temp}°C`} />
        <Metric label="Airflow" value={`${zone.airflow} m/s`} />
      </div>

      {/* Fan indicator */}
      <div className="mt-4 flex items-center justify-between rounded-lg bg-white/[0.03] border border-white/5 px-3 py-2">
        <div className="flex items-center gap-3">
          <FanIcon className={palette.fan} spinDuration={spinDuration} />
          <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">Fan</div>
            <div className="text-slate-100 font-mono text-sm">{fanSpeed}%</div>
          </div>
        </div>
        {mitigation && (
          <span className="px-2 py-0.5 rounded bg-sky-500/20 border border-sky-400/40 text-sky-200 text-[10px] font-bold tracking-widest uppercase animate-pulse">
            Ventilating
          </span>
        )}
      </div>

      {actions.length > 0 && (
        <ul
          className={`mt-3 space-y-1 text-xs leading-relaxed ${
            zone.status === "red" ? "text-red-200" : "text-slate-300"
          }`}
        >
          {actions.map((a, i) => (
            <li key={i} className="flex gap-2">
              <span
                className={`mt-1 size-1.5 rounded-full shrink-0 ${
                  zone.status === "red"
                    ? "bg-red-400"
                    : zone.status === "yellow"
                    ? "bg-amber-300"
                    : "bg-emerald-400"
                }`}
              />
              <span>{a}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FanIcon({ className = "", spinDuration }: { className?: string; spinDuration: number }) {
  const style =
    spinDuration > 0
      ? { animation: `fanSpin ${spinDuration}s linear infinite` }
      : undefined;
  return (
    <svg
      viewBox="0 0 24 24"
      className={`size-6 ${className}`}
      style={style}
      fill="currentColor"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="1.6" />
      <path d="M12 11c-1.2-2.8-3.6-4.4-6-4 .2 2.6 2 4.8 4.6 5.4.4.1.9-.1 1.1-.5L12 11z" />
      <path d="M13 12c2.8-1.2 4.4-3.6 4-6-2.6.2-4.8 2-5.4 4.6-.1.4.1.9.5 1.1L13 12z" />
      <path d="M12 13c1.2 2.8 3.6 4.4 6 4-.2-2.6-2-4.8-4.6-5.4-.4-.1-.9.1-1.1.5L12 13z" />
      <path d="M11 12c-2.8 1.2-4.4 3.6-4 6 2.6-.2 4.8-2 5.4-4.6.1-.4-.1-.9-.5-1.1L11 12z" />
    </svg>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/[0.03] border border-white/5 px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className="text-slate-100 font-mono text-sm mt-0.5">{value}</div>
    </div>
  );
}
