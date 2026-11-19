import "./EngineeringCompass.css";
import { Link } from "react-router-dom";
import { engineeringModes } from "../config/engineeringModes";

/** The five engineering modes laid out along one orbital line. Each opens its workspace. */
export default function EngineeringCompass() {
    return (
        <nav className="compass" aria-label="Engineering modes">
            {engineeringModes.map((mode) => {
                const Icon = mode.icon;

                return (
                    <Link key={mode.id} className="compass-node" to={`/${mode.id}`}>
                        <span className="compass-node__dial" aria-hidden="true">
                            <Icon size={20} />
                        </span>
                        <span className="compass-node__title">{mode.title}</span>
                        <span className="compass-node__detail">{mode.description}</span>
                    </Link>
                );
            })}
        </nav>
    );
}
