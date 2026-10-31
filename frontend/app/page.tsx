"use client";

import { useState } from "react";
import { Download, LoaderCircle, Play } from "lucide-react";

type Task = { id: string; description: string; status: string; result?: string | null; error?: string | null; tool: string };
type ResponseData = { status: string; message: string; document_type: string; plan: Task[]; assumptions: string[]; execution_summary: Record<string, number>; execution_logs: { task_id: string; event: string; detail: string }[]; document?: { filename: string; content_type: string; base64: string } | null };
const samples = ["Create a professional business proposal for launching a small coffee shop in Almora, Uttarakhand. Include an executive summary, target market, estimated investment, operational plan, marketing strategy and financial projections.", "Prepare a technical project plan for building an AI-powered online learning platform for college students. I have a limited budget and want to launch within six months. Include the technology stack, development phases, team requirements, estimated costs, risks and a launch strategy. Make reasonable assumptions wherever information is missing."];

export default function Home() {
  const [request, setRequest] = useState("");
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<ResponseData | null>(null);
  const [error, setError] = useState("");

  async function generate() {
    setError(""); setData(null); setBusy(true);
    try {
      const base = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
      if (!base) throw new Error("Configure NEXT_PUBLIC_API_BASE_URL before using the generator.");
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 300000);
      let response: Response;
      try { response = await fetch(`${base}/agent`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request }), signal: controller.signal }); }
      finally { clearTimeout(timer); }
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = body.detail;
        if (detail && Array.isArray(detail.plan)) {
          setData({ status: "failed", message: detail.message, document_type: "", plan: detail.plan, assumptions: [], execution_summary: detail.execution_summary, execution_logs: detail.logs, document: null });
          return;
        }
        throw new Error(typeof detail === "string" ? detail : detail?.message || "The backend could not complete the request.");
      }
      setData(body as ResponseData);
    } catch (e) { setError(e instanceof Error ? (e.name === "AbortError" ? "The request timed out. Check the backend and try again." : e.message) : "The backend could not be reached."); }
    finally { setBusy(false); }
  }

  function download() {
    if (!data?.document) return;
    const raw = atob(data.document.base64); const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    const url = URL.createObjectURL(new Blob([bytes], { type: data.document.content_type }));
    const link = document.createElement("a"); link.href = url; link.download = data.document.filename; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
  }

  return <main className="shell">
    <header className="topbar"><div className="brand">TaskPilot AI<small>Plan carefully. Deliver clearly.</small></div><div className="status"><span className="dot"/> Agent workspace</div></header>
    <section className="intro"><h1>Turn a request into a working document</h1><p>Describe the outcome you need. TaskPilot will plan the work, execute the selected tasks and prepare a Word document.</p></section>
    <section className="panel"><h2>What should the agent prepare?</h2><textarea value={request} onChange={e => setRequest(e.target.value)} placeholder="Describe the document, its audience and any requirements…" maxLength={12000}/><div className="actions"><button className="primary" disabled={busy || request.trim().length < 12} onClick={generate}>{busy ? <LoaderCircle size={16} className="spin"/> : <Play size={15}/>} {busy ? "Working on your document…" : "Generate document"}</button><button className="sample" onClick={() => setRequest(samples[0])}>Try business proposal</button><button className="sample" onClick={() => setRequest(samples[1])}>Try technical project plan</button></div>{error && <div className="error">{error}</div>}</section>
    {(busy || data) && <div className="workspace"><section className="panel"><h2>Execution plan {busy && <span className="muted">· running</span>}</h2>{!data && busy && <p className="muted">Planning and task details will appear when the request completes.</p>}{data?.plan.map(task => <article className="task" key={task.id}><div className="taskhead"><span>{task.description}</span><span className="badge">{task.status}</span></div><p>{task.result || task.error || `Tool: ${task.tool}`}</p></article>)}{data?.assumptions.length ? <><h2 style={{marginTop:18}}>Assumptions</h2>{data.assumptions.map((item, i) => <p className="muted" key={i}>• {item}</p>)}</> : null}</section><section className="panel"><h2>Execution record</h2>{!data && busy && <p className="muted">The backend executes synchronously; this panel will show the returned execution record.</p>}{data?.execution_logs.map((log, i) => <div className="log" key={i}><strong>{log.task_id}</strong> · {log.event}<br/>{log.detail}</div>)}{data && <><h2 style={{marginTop:20}}>Result</h2><p className="muted">{data.message} {data.execution_summary.completed_tasks}/{data.execution_summary.total_tasks} tasks completed.</p>{data.document && <button className="download" onClick={download}><Download size={16}/> Download {data.document.filename}</button>}</>}</section></div>}
  </main>;
}
