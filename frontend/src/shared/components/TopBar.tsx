import "./TopBar.css";

export default function TopBar() {
    return (
        <header className="topbar">

            <div className="topbar-left">

                <div className="logo">
                    🐺
                </div>

                <div>

                    <h2>AIEngineeringLab</h2>

                    <span>Mission Control</span>

                </div>

            </div>

            <div className="topbar-right">

                <div className="status">

                    <span className="dot"></span>

                    Connected

                </div>

                <div className="user">

                    👤 Latz

                </div>

            </div>

        </header>
    );
}