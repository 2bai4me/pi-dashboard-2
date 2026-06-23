import { HashRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./Layout";
import { TTSProvider } from "./TTSContext";
import { DevSettingsProvider } from "./DevSettingsContext";
import Kanban from "./pages/Kanban";
import Idee from "./pages/Idee";
import Status from "./pages/Status";
import SysInfo from "./pages/SysInfo";
import Models from "./pages/Models";
import Tools from "./pages/Tools";
import AgentQuestions from "./pages/AgentQuestions";
import TestRunner from "./pages/TestRunner";
import Skills from "./pages/Skills";
import Sessions from "./pages/Sessions";
import Config from "./pages/Config";
import Logs from "./pages/Logs";
import OpenBrain from "./pages/OpenBrain";
import Extensions from "./pages/Extensions";
import Cost from "./pages/Cost"
import Process from "./pages/Process";
import Terminal from "./pages/Terminal";
import Sops from "./pages/Sops";
import CronJobs from "./pages/CronJobs";
import Mcp from "./pages/Mcp";
import Webhooks from "./pages/Webhooks";
import SelfImprovement from "./pages/SelfImprovement";
import BrainGraph from "./pages/BrainGraph";
import RacWorkflow from "./pages/RacWorkflow";
import Performance from "./pages/Performance";
import SubAgents from "./pages/SubAgents";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

export default function App() {
  return (
    <TTSProvider>
      <QueryClientProvider client={queryClient}>
        <HashRouter>
          <DevSettingsProvider>
            <Layout>
            <Routes>
              <Route path="/" element={<Navigate to="/kanban" replace />} />
              <Route path="/kanban" element={<Kanban />} />
              <Route path="/idee" element={<Idee />} />
              <Route path="/status" element={<Status />} />
              <Route path="/system" element={<SysInfo />} />
              <Route path="/models" element={<Models />} />
              <Route path="/tools" element={<Tools />} />
              <Route path="/tools/agent-questions" element={<AgentQuestions />} />
              <Route path="/tools/agent-questions/:id" element={<AgentQuestions />} />
              <Route path="/test-runner" element={<TestRunner />} />
              <Route path="/skills" element={<Skills />} />
              <Route path="/sessions" element={<Sessions />} />
              <Route path="/config" element={<Config />} />
              <Route path="/logs" element={<Logs />} />
              <Route path="/openbrain" element={<OpenBrain />} />
              <Route path="/extensions" element={<Extensions />} />
              <Route path="/cost" element={<Cost />} />
              <Route path="/process" element={<Process />} />
              <Route path="/terminal" element={<Terminal />} />
              <Route path="/sops" element={<Sops />} />
              <Route path="/cron" element={<CronJobs />} />
              <Route path="/mcp" element={<Mcp />} />
              <Route path="/webhooks" element={<Webhooks />} />
              <Route path="/self-improve" element={<SelfImprovement />} />
              <Route path="/performance" element={<Performance />} />
              <Route path="/subagents" element={<SubAgents />} />
              <Route path="/brain-graph" element={<BrainGraph />} />
              <Route path="/raci" element={<RacWorkflow />} />
              <Route path="*" element={<Navigate to="/kanban" replace />} />
            </Routes>
          </Layout>
          </DevSettingsProvider>
        </HashRouter>
      </QueryClientProvider>
    </TTSProvider>
  );
}
