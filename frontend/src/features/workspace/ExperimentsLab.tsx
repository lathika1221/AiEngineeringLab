import { useRef, useState } from "react";
import { incompleteReason, splitStreamEnd, type StreamEnd } from "../../shared/api/streamEnd";
import { Link } from "react-router-dom";
import { usePageTitle } from "../../shared/hooks/usePageTitle";
import { ArrowLeft, Beaker, Copy, FlaskConical, Play, Sparkles, Square } from "lucide-react";
import { API_BASE, getToken } from "../../shared/api/client";
import WolfHead from "../../shared/brand/WolfHead";
import { useNotify } from "../../shared/notifications/context";
import Button from "../../shared/ui/Button";
import Markdown from "../../shared/markdown/Markdown";
import Notice from "../../shared/ui/Notice";
import "./ExperimentsLab.css";

const API_URL = API_BASE;

const experiments = [
    { id: "prompt", number: "01", title: "Prompt playground", description: "Explore instructions, tone, and output quality.", engine: "explore", action: "prompt_experiment", icon: Sparkles, color: "violet", prompt: "Compare two approaches to solving this problem. Explain the trade-offs and recommend the strongest approach:" },
    { id: "research", number: "02", title: "Research sandbox", description: "Investigate a question and develop a hypothesis.", engine: "research", action: "research_experiment", icon: FlaskConical, color: "blue", prompt: "Investigate this research question. State a hypothesis, methodology, expected observations, and limitations:" },
    { id: "build", number: "03", title: "Architecture explorer", description: "Prototype and evaluate engineering decisions.", engine: "forge", action: "architecture_experiment", icon: Beaker, color: "cyan", prompt: "Propose an architecture for this engineering problem. Explain the components, data flow, trade-offs, and implementation plan:" },
];

type Run = {
    id: number;
    experimentId: string;
    title: string;
    prompt: string;
    output: string;
    incomplete?: StreamEnd;
    /** True when the user stopped the run on purpose. */
    stopped?: boolean;
    finishedAt: Date;
};

const HISTORY_LIMIT = 10;

export default function ExperimentsLab() {
    const [selected, setSelected] = useState(experiments[0]);
    const [prompt, setPrompt] = useState(experiments[0].prompt);
    const [result, setResult] = useState("");
    const [running, setRunning] = useState(false);
    const [error, setError] = useState("");
    const [incomplete, setIncomplete] = useState<StreamEnd | null>(null);
    const [stopped, setStopped] = useState(false);
    const [history, setHistory] = useState<Run[]>([]);
    const [viewingRun, setViewingRun] = useState<number | null>(null);
    const nextRunId = useRef(1);
    const controller = useRef<AbortController | null>(null);
    const notify = useNotify();
    usePageTitle("Experiments");

    function chooseExperiment(experiment: typeof experiments[number]) {
        setSelected(experiment);
        setPrompt(experiment.prompt);
        setResult("");
        setError("");
        setIncomplete(null);
        setStopped(false);
        setViewingRun(null);
    }

    function openRun(run: Run) {
        const experiment = experiments.find((item) => item.id === run.experimentId) ?? selected;

        setSelected(experiment);
        setPrompt(run.prompt);
        setResult(run.output);
        setError("");
        setIncomplete(run.incomplete ?? null);
        setStopped(run.stopped ?? false);
        setViewingRun(run.id);
    }

    async function copyOutput() {
        try {
            await navigator.clipboard.writeText(result);
            notify({ mood: "success", title: "Output copied" });
        } catch {
            notify({ mood: "error", title: "Couldn't copy", detail: "Select the text and copy it manually." });
        }
    }

    function stopExperiment() {
        controller.current?.abort();
    }

    async function runExperiment() {
        const token = getToken();
        if (!token) {
            setError("Your session has expired. Sign in again to run an experiment.");
            return;
        }
        if (!prompt.trim()) {
            setError("Enter an instruction before running the experiment.");
            return;
        }

        setRunning(true);
        setResult("");
        setError("");
        setIncomplete(null);
        setStopped(false);
        setViewingRun(null);

        const abort = new AbortController();
        controller.current = abort;
        let output = "";
        let raw = "";

        try {
            const response = await fetch(`${API_URL}/ai/chat/stream`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({
                    message: prompt.trim(),
                    conversation_id: null,
                    engine: selected.engine,
                    action: selected.action,
                }),
                signal: abort.signal,
            });

            if (response.status === 401) {
                setError("Your session has expired. Sign in again.");
                return;
            }
            if (!response.ok) {
                const detail = await response.text();
                throw new Error(detail || `Request failed (${response.status})`);
            }
            if (!response.body) throw new Error("The server did not return a streaming response.");

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                raw += decoder.decode(value, { stream: true });
                output = splitStreamEnd(raw).text;
                setResult(output);
            }

            raw += decoder.decode();
            const finished = splitStreamEnd(raw);
            output = finished.text;
            setResult(output);
            if (!output.trim()) {
                setError(
                    finished.end === "stop" || finished.end === null
                        ? "The model returned an empty response. Try again."
                        : `No output was produced. ${incompleteReason(finished.end)} Try again.`,
                );
            } else if (finished.end === "stop") {
                recordRun(output);
                notify({ mood: "success", title: "Experiment complete", detail: selected.title });
            } else {
                // Length limit, provider error, or a connection that closed early.
                recordRun(output, finished.end ?? "interrupted");
                setIncomplete(finished.end ?? "interrupted");
                notify({ mood: "error", title: "Experiment incomplete", detail: "Partial output kept." });
            }
        } catch (cause) {
            if (cause instanceof DOMException && cause.name === "AbortError") {
                // The user stopped the run: keep what streamed so far and say it is partial.
                if (output.trim()) {
                    recordRun(output, undefined, true);
                    setStopped(true);
                }
                notify({ mood: "idle", title: "Experiment stopped", detail: output.trim() ? "Partial output kept." : undefined });
            } else if (output.trim()) {
                // The connection broke mid-reply: keep the partial text and say it is incomplete.
                recordRun(output, "interrupted");
                setIncomplete("interrupted");
                notify({ mood: "error", title: "Experiment incomplete", detail: "Partial output kept." });
            } else {
                setError(cause instanceof Error ? cause.message : "Experiment failed. Check that the backend is running.");
            }
        } finally {
            controller.current = null;
            setRunning(false);
        }
    }

    function recordRun(output: string, end?: StreamEnd, wasStopped?: boolean) {
        const id = nextRunId.current++;

        setHistory((current) =>
            [{ id, experimentId: selected.id, title: selected.title, prompt: prompt.trim(), output, incomplete: end, stopped: wasStopped, finishedAt: new Date() }, ...current].slice(
                0,
                HISTORY_LIMIT,
            ),
        );
        setViewingRun(id);
    }

    const status = running ? "running" : error ? "failed" : incomplete ? "incomplete" : stopped ? "stopped" : result ? "complete" : "idle";
    const statusLabel = {
        running: "Running",
        failed: "Failed",
        incomplete: "Incomplete",
        stopped: "Stopped",
        complete: "Complete",
        idle: "Ready to run",
    }[status];
    const statusClass = {
        running: "status--busy",
        failed: "status--error",
        incomplete: "status--error",
        stopped: "",
        complete: "status--ok",
        idle: "",
    }[status];

    return (
        <section className="page experiments-lab">
            <Link className="page-back" to="/mission-control">
                <ArrowLeft size={15} aria-hidden="true" />
                Mission Control
            </Link>

            <header>
                <p className="label lab-label">
                    <FlaskConical size={14} aria-hidden="true" />
                    Experiments Lab
                </p>
                <h1 className="display page-title">Test an idea</h1>
                <p className="page-lede">
                    Pick a starting point, edit the instruction, and run it against your configured AI model.
                </p>
            </header>

            <div className="lab-layout section">
                <div className="lab-experiments" role="radiogroup" aria-label="Experiment type">
                    {experiments.map((experiment) => {
                        const Icon = experiment.icon;
                        const active = selected.id === experiment.id;

                        return (
                            <button
                                type="button"
                                key={experiment.id}
                                role="radio"
                                aria-checked={active}
                                className={`lab-experiment panel panel--interactive${active ? " is-selected" : ""}`}
                                onClick={() => chooseExperiment(experiment)}
                                disabled={running}
                            >
                                <span className="lab-experiment__icon" aria-hidden="true">
                                    <Icon size={18} />
                                </span>
                                <span className="lab-experiment__copy">
                                    <strong>{experiment.title}</strong>
                                    <small>{experiment.description}</small>
                                </span>
                            </button>
                        );
                    })}
                </div>

                <div className="lab-workbench panel panel--lit">
                    <div className="lab-workbench-heading">
                        <h2 className="section-title">{selected.title}</h2>
                        <span className={`status ${statusClass}`} role="status">
                            <span className="status__dot" />
                            {statusLabel}
                        </span>
                    </div>

                    <div className="field">
                        <label className="field__label" htmlFor="lab-prompt">
                            Your instruction
                            <span className="field__hint">
                                {history.length} {history.length === 1 ? "run" : "runs"} this session
                            </span>
                        </label>
                        <textarea
                            id="lab-prompt"
                            className="input lab-prompt-input"
                            value={prompt}
                            onChange={(event) => setPrompt(event.target.value)}
                            placeholder="Describe what you want to test"
                            rows={5}
                            disabled={running}
                        />
                    </div>

                    <div className="lab-run-row">
                        <span className="lab-model-note">Uses your configured AI provider</span>
                        {running && (
                            <Button onClick={stopExperiment}>
                                <Square size={13} aria-hidden="true" />
                                Stop
                            </Button>
                        )}
                        <Button
                            variant="primary"
                            onClick={() => void runExperiment()}
                            disabled={!prompt.trim()}
                            busy={running}
                        >
                            {running ? (
                                "Running"
                            ) : (
                                <>
                                    <Play size={14} aria-hidden="true" />
                                    Run experiment
                                </>
                            )}
                        </Button>
                    </div>

                    {error && <Notice tone="error">{error}</Notice>}
                    {incomplete && !running && (
                        <Notice tone="error">
                            Incomplete output. {incompleteReason(incomplete)} The partial text below is kept; shorten the
                            request or ask for fewer sections and run it again.
                        </Notice>
                    )}

                    {(result || running) && (
                        <section className="lab-result" aria-live="polite" aria-busy={running}>
                            <div className="lab-result-heading">
                                <WolfHead size={30} mood={running ? "thinking" : incomplete ? "error" : "success"} />
                                <h3>Output</h3>
                                {result && !running && (
                                    <Button size="sm" onClick={() => void copyOutput()}>
                                        <Copy size={13} aria-hidden="true" />
                                        Copy
                                    </Button>
                                )}
                            </div>
                            {result ? (
                                <Markdown>{result}</Markdown>
                            ) : (
                                <p className="lab-waiting">Waiting for the first response token</p>
                            )}
                            <p className="lab-storage-note">
                                Runs use the existing AI chat API. The backend may save their prompts and
                                responses to your chat history.
                            </p>
                        </section>
                    )}

                    {history.length > 0 && (
                        <section className="lab-history" aria-labelledby="lab-history-title">
                            <h3 id="lab-history-title">Runs this session</h3>
                            <p className="lab-storage-note">Kept in this tab only. They are cleared when you leave or refresh.</p>
                            <ul>
                                {history.map((run) => (
                                    <li key={run.id}>
                                        <button
                                            type="button"
                                            className={`lab-history__item${viewingRun === run.id ? " is-selected" : ""}`}
                                            aria-current={viewingRun === run.id ? "true" : undefined}
                                            onClick={() => openRun(run)}
                                            disabled={running}
                                        >
                                            <strong>{run.title}</strong>
                                            <span>{run.prompt}</span>
                                            <small>{run.finishedAt.toLocaleTimeString(undefined, { timeStyle: "short" })}</small>
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </section>
                    )}
                </div>
            </div>
        </section>
    );
}
