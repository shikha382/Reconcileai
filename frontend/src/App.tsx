import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { RunProvider } from "./context/RunContext";
import { OverviewPage } from "./pages/OverviewPage";
import { WorkQueuePage } from "./pages/WorkQueuePage";
import { ExceptionsListPage } from "./pages/ExceptionsListPage";
import { ExceptionDetailPage } from "./pages/ExceptionDetailPage";
import { RunsPage } from "./pages/RunsPage";
import { AuditPage } from "./pages/AuditPage";
import { HealthPage } from "./pages/HealthPage";
import { AboutPage } from "./pages/AboutPage";

export function App() {
  return (
    <RunProvider>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<OverviewPage />} />
          <Route path="work-queue" element={<WorkQueuePage />} />
          <Route path="exceptions" element={<ExceptionsListPage />} />
          <Route path="exceptions/:exceptionId" element={<ExceptionDetailPage />} />
          <Route path="runs" element={<RunsPage />} />
          <Route path="audit" element={<AuditPage />} />
          <Route path="health" element={<HealthPage />} />
          <Route path="about" element={<AboutPage />} />
        </Route>
      </Routes>
    </RunProvider>
  );
}
