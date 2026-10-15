import { Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import GeneratorNew from "./pages/GeneratorNew";
import NewProject from "./pages/NewProject";
import ProjectList from "./pages/ProjectList";
import ProjectWorkspace from "./pages/ProjectWorkspace";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<ProjectList />} />
        <Route path="/new" element={<NewProject />} />
        <Route path="/generator/new" element={<GeneratorNew />} />
        <Route path="/projects/:id" element={<ProjectWorkspace />} />
      </Routes>
    </AppShell>
  );
}
