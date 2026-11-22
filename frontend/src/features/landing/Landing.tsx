import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import WolfHead from "../../shared/brand/WolfHead";
import Wordmark from "../../shared/brand/Wordmark";
import Button from "../../shared/ui/Button";
import { usePageTitle } from "../../shared/hooks/usePageTitle";
import "./Landing.css";

type LandingProps = {
    onGetStarted: () => void;
    onSignIn: () => void;
};

const modules = [
    {
        name: "Mission Control",
        detail: "Your goals, projects and recent conversations in one view, with a way into every mode.",
    },
    {
        name: "LATZ Chat",
        detail: "Streaming answers with saved history. LATZ keeps the context of each project you open.",
    },
    {
        name: "Engineering modes",
        detail: "Forge, Learn, Research, Explore and Solve. Each one starts LATZ on a different kind of work.",
    },
    {
        name: "Experiments Lab",
        detail: "Edit an instruction, run it against your model and read the output as it arrives.",
    },
];

const rise = {
    hidden: { opacity: 0, y: 18 },
    shown: { opacity: 1, y: 0 },
};

export default function Landing({ onGetStarted, onSignIn }: LandingProps) {
    usePageTitle(null);

    return (
        <div className="landing" data-theme="dark">
            <header className="landing-nav">
                <Wordmark size="sm" />
                <nav className="landing-nav__links" aria-label="Landing">
                    <a href="#inside">Inside LATZ</a>
                    <button type="button" onClick={onSignIn}>
                        Sign in
                    </button>
                </nav>
                <Button variant="primary" size="sm" onClick={onGetStarted}>
                    Get started
                </Button>
            </header>

            <main>
                <motion.section
                    className="landing-hero"
                    initial="hidden"
                    animate="shown"
                    transition={{ staggerChildren: 0.12, delayChildren: 0.1 }}
                >
                    <motion.div
                        className="landing-hero__mark"
                        variants={{ hidden: { opacity: 0, scale: 0.92 }, shown: { opacity: 1, scale: 1 } }}
                        transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
                    >
                        <span className="orbit orbit--outer" aria-hidden="true" />
                        <span className="orbit orbit--mid" aria-hidden="true" />
                        <span className="orbit orbit--inner" aria-hidden="true" />
                        <WolfHead size={260} halo depth title="LATZ wolf head" className="landing-hero__wolf" />
                    </motion.div>

                    <motion.p className="label landing-hero__label" variants={rise}>
                        AI Engineering Lab
                    </motion.p>

                    <motion.h1 className="display landing-hero__title" variants={rise} transition={{ duration: 0.6 }}>
                        Engineer
                        <br />
                        the future.
                    </motion.h1>

                    <motion.p className="landing-hero__lede" variants={rise} transition={{ duration: 0.6 }}>
                        LATZ is one workspace for building software, learning new technology, researching
                        hard questions and testing ideas, with an AI partner that remembers your projects.
                    </motion.p>

                    <motion.div className="landing-hero__actions" variants={rise} transition={{ duration: 0.6 }}>
                        <Button variant="primary" size="lg" className="landing-cta" onClick={onGetStarted}>
                            Get started
                            <ArrowRight size={16} aria-hidden="true" />
                        </Button>
                        <Button variant="ghost" size="lg" onClick={onSignIn}>
                            I have an account
                        </Button>
                    </motion.div>
                </motion.section>

                <section className="landing-inside" id="inside" aria-labelledby="inside-title">
                    <h2 className="display landing-inside__title" id="inside-title">
                        Inside the workspace
                    </h2>
                    <dl className="landing-inside__list">
                        {modules.map((module) => (
                            <div className="landing-inside__row" key={module.name}>
                                <dt>{module.name}</dt>
                                <dd>{module.detail}</dd>
                            </div>
                        ))}
                    </dl>
                </section>
            </main>

            <footer className="landing-footer">
                <span>LATZ</span>
                <span>Engineer the future.</span>
            </footer>
        </div>
    );
}
