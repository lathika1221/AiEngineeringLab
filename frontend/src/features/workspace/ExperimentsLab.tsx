import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowDown, ArrowUp, Beaker, Check, CircleAlert, FlaskConical, LoaderCircle, Sparkles } from "lucide-react";
import "./ExperimentsLab.css";

const API_URL = "http://127.0.0.1:8000";

const experiments = [
    { id: "prompt", number: "01", title: "Prompt playground", description: "Explore instructions, tone, and output quality.", engine: "explore", action: "prompt_experiment", icon: Sparkles, color: "violet", prompt: "Compare two approaches to solving this problem. Explain the trade-offs and recommend the strongest approach:" },
    { id: "research", number: "02", title: "Research sandbox", description: "Investigate a question and develop a hypothesis.", engine: "research", action: "research_experiment", icon: FlaskConical, color: "blue", prompt: "Investigate this research question. State a hypothesis, methodology, expected observations, and limitations:" },
    { id: "build", number: "03", title: "Architecture explorer", description: "Prototype and evaluate engineering decisions.", engine: "forge", action: "architecture_experiment", icon: Beaker, color: "cyan", prompt: "Propose an architecture for this engineering problem. Explain the components, data flow, trade-offs, and implementation plan:" },
];

export default function ExperimentsLab() {
    const [selected, setSelected] = useState(experiments[0]);
    const [prompt, setPrompt] = useState(experiments[0].prompt);
    const [result, setResult] = useState("");
    const [running, setRunning] = useState(false);
    const [error, setError] = useState("");
    const [runs, setRuns] = useState(0);

    function chooseExperiment(experiment: typeof experiments[number]) {
        setSelected(experiment);
        setPrompt(experiment.prompt);
        setResult("");
        setError("");
    }

    async function runExperiment() {
        const token = localStorage.getItem("access_token");
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
            let output = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                output += decoder.decode(value, { stream: true });
                setResult(output);
            }

            output += decoder.decode();
            setResult(output);
            setRuns((count) => count + 1);
            if (!output.trim()) setError("The model returned an empty response. Try again.");
        } catch (cause) {
            setError(cause instanceof Error ? cause.message : "Experiment failed. Check that the backend is running.");
        } finally {
            setRunning(false);
        }
    }

    return (
        <motion.section
            className="experiments-lab"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
        >
            <header className="lab-topbar">
                <button type="button" className="lab-back" onClick={() => window.dispatchEvent(new CustomEvent("latz:experiments-back"))}>
                    <ArrowDown size={15} /> Workspace
                </button>
                <div className="lab-brand"><span className="lab-brand-mark"><FlaskConical size={17} /></span> Experiments <span className="lab-brand-muted">/ Playground</span></div>
                <div className="lab-live"><span /> AI connected</div>
            </header>

            <div className="lab-intro">
                <div className="lab-kicker"><Sparkles size={14} /> YOUR ENGINEERING PLAYGROUND</div>
                <h1>Curiosity, meet <span>possibility.</span></h1>
                <p>Explore ideas, test instructions, and prototype approaches. Pick an experiment and make it your own.</p>
            </div>

            <div className="lab-section-heading">
                <div><span className="lab-section-label">EXPERIMENT COLLECTION</span><h2>Where do you want to start?</h2></div>
                <span className="lab-count">03 EXPERIMENTS</span>
            </div>

            <div className="lab-experiment-grid">
                {experiments.map((experiment) => {
                    const Icon = experiment.icon;
                    const active = selected.id === experiment.id;
                    return (
                        <motion.button
                            type="button"
                            key={experiment.id}
                            className={`lab-experiment-card lab-${experiment.color}${active ? " is-selected" : ""}`}
                            onClick={() => chooseExperiment(experiment)}
                            whileHover={{ y: -3 }}
                            whileTap={{ scale: 0.99 }}
                        >
                            <div className="lab-card-top"><span className="lab-card-icon"><Icon size={19} /></span><span className="lab-card-number">{experiment.number}</span></div>
                            <h3>{experiment.title}</h3>
                            <p>{experiment.description}</p>
                            <span className="lab-card-action">{active ? "SELECTED" : "EXPLORE"} <ArrowUp size={14} /></span>
                        </motion.button>
                    );
                })}
            </div>

            <div className="lab-workbench">
                <div className="lab-workbench-heading">
                    <div><span className="lab-section-label">THE WORKBENCH</span><h2>{selected.title}</h2><p>Adjust your instruction, then run it against the connected AI model.</p></div>
                    <span className="lab-run-count">{runs} {runs === 1 ? "RUN" : "RUNS"} THIS SESSION</span>
                </div>

                <label className="lab-prompt-label" htmlFor="lab-prompt">YOUR INSTRUCTION <span>EDITABLE</span></label>
                <textarea id="lab-prompt" className="lab-prompt-input" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Describe what you want to test..." rows={5} disabled={running} />

                <div className="lab-run-row">
                    <span className="lab-model-note"><span /> Uses your configured AI provider</span>
                    <button type="button" className="lab-run-button" onClick={() => void runExperiment()} disabled={running || !prompt.trim()}>
                        {running ? <><LoaderCircle className="lab-spin" size={16} /> Running experiment</> : <>Run experiment <ArrowUp size={16} /></>}
                    </button>
                </div>

                {(result || running || error) && (
                    <section className="lab-result" aria-live="polite">
                        <div className="lab-result-heading"><div><Sparkles size={15} /><h3>Experiment output</h3></div>{running ? <span className="lab-result-status"><LoaderCircle className="lab-spin" size={13} /> GENERATING</span> : result ? <span className="lab-result-status lab-result-done"><Check size={13} /> RESPONSE RECEIVED</span> : null}</div>
                        {error && <div className="lab-error"><CircleAlert size={16} /><span>{error}</span></div>}
                        {result && <div className="lab-result-content">{result}{running && <span className="lab-cursor" />}</div>}
                        {!result && running && <div className="lab-waiting"><LoaderCircle className="lab-spin" size={18} /> Waiting for the first response token...</div>}
                        <p className="lab-storage-note">Runs use the existing AI chat API. The backend may save their prompts and responses to your chat history.</p>
                    </section>
                )}
            </div>
            <footer className="lab-footer"><span>BUILT FOR EXPERIMENTATION</span><span>Make something unexpected <Sparkles size={13} /></span></footer>
        </motion.section>
    );
}
