import { Router, Route } from "@solidjs/router";
import type { RouteSectionProps } from "@solidjs/router";
import { lazy } from "solid-js";
import CommandPalette from "./components/layout/CommandPalette";

const Projects = lazy(() => import("./routes/Projects"));
const Studio = lazy(() => import("./routes/Studio"));
const Assets = lazy(() => import("./routes/Assets"));
const PersonaEditor = lazy(() => import("./routes/PersonaEditor"));
const Tasks = lazy(() => import("./routes/Tasks"));
const Workspace = lazy(() => import("./routes/Workspace"));
const Settings = lazy(() => import("./routes/Settings"));
const Onboarding = lazy(() => import("./routes/Onboarding"));
const Restyle = lazy(() => import("./routes/Restyle"));
const Recreate = lazy(() => import("./routes/Recreate"));
const RecreateWorkbench = lazy(() => import("./routes/RecreateWorkbench"));
const RestyleWorkbench = lazy(() => import("./routes/RestyleWorkbench"));

function RootLayout(props: RouteSectionProps) {
  return (
    <>
      {props.children}
      <CommandPalette />
    </>
  );
}

export default function App() {
  return (
    <Router root={RootLayout}>
      <Route path="/" component={Projects} />
      <Route path="/projects" component={Projects} />
      <Route path="/studio/:projectId/:tab?" component={Studio} />
      <Route path="/personas/:personaId?" component={PersonaEditor} />
      <Route path="/restyle" component={Restyle} />
      <Route path="/restyle/:id" component={RestyleWorkbench} />
      <Route path="/recreate" component={Recreate} />
      <Route path="/recreate/:id" component={RecreateWorkbench} />
      <Route path="/assets/:tab?" component={Assets} />
      <Route path="/tasks" component={Tasks} />
      <Route path="/chat/:sessionId?" component={Workspace} />
      <Route path="/settings" component={Settings} />
      <Route path="/onboarding" component={Onboarding} />
      <Route path="*" component={Projects} />
    </Router>
  );
}
