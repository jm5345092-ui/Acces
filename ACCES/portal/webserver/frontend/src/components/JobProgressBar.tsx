import { useEffect, useRef, useState } from "react";
import { api } from "../services/api";

interface Props {
  /** The project, and the job type to watch (e.g. "DECODE", "ANALYZE",
   * "BUILD_PIPELINE") — this component finds the most recent job of that
   * type itself, so it works whether the job was just triggered by this
   * page or started automatically elsewhere (e.g. decode right after
   * upload). Polls while the project's own status says this is in
   * progress; stops and hides itself otherwise. */
  projectId: string;
  jobType: string;
  active: boolean;
  label: string;
}

export default function JobProgressBar({ projectId, jobType, active, label }: Props) {
  const [progress, setProgress] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!active) {
      setProgress(null);
      return;
    }
    let cancelled = false;

    const poll = () => {
      api
        .getLatestJob(projectId, jobType)
        .then((job) => {
          if (cancelled) return;
          if (job.status === "SUCCESS" || job.status === "FAILED") {
            setProgress(job.status === "SUCCESS" ? 100 : null);
            return;
          }
          setProgress(job.progress);
          timerRef.current = setTimeout(poll, 800);
        })
        .catch(() => {
          if (!cancelled) timerRef.current = setTimeout(poll, 1500);
        });
    };
    poll();

    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [projectId, jobType, active]);

  if (!active || progress === null) return null;

  return (
    <div style={{ padding: "6px 14px", borderBottom: "1px solid var(--border)", background: "var(--bg-1)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-dim)", marginBottom: 4 }}>
        <span>{label}</span>
        <span className="monospace">{progress}%</span>
      </div>
      <div style={{ height: 6, background: "var(--bg-2)", borderRadius: 999, overflow: "hidden" }}>
        <div
          style={{
            height: "100%",
            width: `${progress}%`,
            background: "var(--accent)",
            transition: "width 0.4s ease",
          }}
        />
      </div>
    </div>
  );
}
