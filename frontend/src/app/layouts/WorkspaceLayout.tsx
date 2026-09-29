import "./WorkspaceLayout.css";

import TopBar from "../../shared/components/TopBar";
import CommandBar from "../../shared/components/CommandBar";

import MissionControl from "../../features/workspace/MissionControl";

export default function WorkspaceLayout() {

    return (

        <div className="workspace-layout">

            <TopBar />

            <main className="workspace">

                <MissionControl />

            </main>

            <CommandBar />

        </div>

    );

}