import { containDialogFocus } from "./shared/dialog";
import { Skeleton } from "./shared/controls";
import { useTheme, type ThemePreference } from "./shared/theme";
import {
  Cable,
  PlayCircle,
  Database,
  FilePlus2,
  PanelLeftClose,
  PanelLeftOpen,
  Tags,
  Menu,
  Trash2,
  Palette,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigation } from "react-router";

import type { Dataset } from "./catalog";
import { useShortcut, useStoredFlag } from "./shared/browser";

export function Shell({ datasets }: { datasets: Dataset[] }) {
  const { preference, setPreference } = useTheme();
  const [drawer, setDrawer] = useState(false);
  const drawerRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (drawer) drawerRef.current?.showModal();
    else drawerRef.current?.close();
  }, [drawer]);
  const navigation = useNavigation();
  const location = useLocation();
  const inspecting = /^\/datasets\/.+/.test(location.pathname);
  const [listCollapsed, setListCollapsed] = useStoredFlag("sidebar-collapsed", false);
  const [detailCollapsed, setDetailCollapsed] = useStoredFlag("sidebar-collapsed-detail", true);
  const collapsed = inspecting ? detailCollapsed : listCollapsed;
  const setCollapsed = inspecting ? setDetailCollapsed : setListCollapsed;
  useShortcut("[", () => setCollapsed((value) => !value));
  return (
    <div className="shell" data-sidebar={collapsed ? "collapsed" : "open"}>
      <aside aria-label="Sidebar" className="sidebar">
        <div className="brand">
          {collapsed ? null : <span>Evaluation hub</span>}
          <button
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="icon-button"
            onClick={() => setCollapsed((value) => !value)}
            title={collapsed ? "Expand sidebar ([)" : "Collapse sidebar ([)"}
            type="button"
          >
            {collapsed ? (
              <PanelLeftOpen aria-hidden="true" size={15} strokeWidth={1.75} />
            ) : (
              <PanelLeftClose aria-hidden="true" size={15} strokeWidth={1.75} />
            )}
          </button>
        </div>
        <Navigation count={datasets.length} collapsed={collapsed} />
        <nav className="utility-nav" aria-label="Utilities">
          <NavLink className="nav-link" title={collapsed ? "Trash" : undefined} to="/trash">
            <Trash2 aria-hidden="true" size={16} />
            <span className="nav-label">Trash</span>
          </NavLink>
        </nav>
        <details className="appearance">
          <summary aria-label="Appearance">
            <Palette size={16} aria-hidden="true" />
            <span>Appearance</span>
          </summary>
          <label>
            Theme{" "}
            <select value={preference} onChange={(event) => setPreference(event.target.value as ThemePreference)}>
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
        </details>
      </aside>
      <button className="mobile-menu-button" type="button" onClick={() => setDrawer(true)}>
        <Menu size={18} /> Menu
      </button>
      <dialog
        onKeyDown={containDialogFocus}
        className="navigation-drawer"
        ref={drawerRef}
        onCancel={(event) => {
          event.preventDefault();
          setDrawer(false);
        }}
      >
        <div className="brand">
          <span>Evaluation hub</span>
          <button type="button" onClick={() => setDrawer(false)}>
            Close
          </button>
        </div>
        <Navigation count={datasets.length} collapsed={false} onNavigate={() => setDrawer(false)} />
        <nav className="nav" aria-label="Utilities">
          <NavLink className="nav-link" to="/trash" onClick={() => setDrawer(false)}>
            <Trash2 aria-hidden="true" size={16} /> Trash
          </NavLink>
        </nav>
        <label>
          Appearance{" "}
          <select value={preference} onChange={(event) => setPreference(event.target.value as ThemePreference)}>
            <option value="system">System</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>
      </dialog>
      <main className="workspace" data-loading={navigation.state === "loading"}>
        <Outlet />
      </main>
    </div>
  );
}

function Navigation({ count, collapsed, onNavigate }: { count: number; collapsed: boolean; onNavigate?: () => void }) {
  return (
    <nav aria-label="Sections" className="nav">
      <NavLink
        className="nav-link"
        title={collapsed ? "Connections" : undefined}
        to="/connections"
        onClick={onNavigate}
      >
        <Cable aria-hidden="true" size={16} />
        <span className="nav-label">Connections</span>
      </NavLink>
      <NavLink
        className="nav-link"
        title={collapsed ? "Inference runs" : undefined}
        to="/inference"
        onClick={onNavigate}
      >
        <PlayCircle aria-hidden="true" size={16} />
        <span className="nav-label">Inference runs</span>
      </NavLink>
      <NavLink className="nav-link" title={collapsed ? "Datasets" : undefined} to="/datasets" onClick={onNavigate}>
        <Database aria-hidden="true" size={16} />
        <span className="nav-label">Datasets</span>
        <span className="nav-count mono">{count}</span>
      </NavLink>
      <NavLink
        className="nav-link"
        title={collapsed ? "Imports" : undefined}
        to="/dataset-imports"
        onClick={onNavigate}
      >
        <FilePlus2 aria-hidden="true" size={16} />
        <span className="nav-label">Imports</span>
      </NavLink>
      <NavLink className="nav-link" title={collapsed ? "Tags" : undefined} to="/tags" onClick={onNavigate}>
        <Tags aria-hidden="true" size={16} />
        <span className="nav-label">Tags</span>
      </NavLink>
    </nav>
  );
}

export function ShellSkeleton() {
  return (
    <div className="shell" aria-busy="true">
      <aside className="sidebar">
        <div className="brand">
          <span>Evaluation hub</span>
        </div>
        <div className="skeleton-stack">
          {Array.from({ length: 5 }, (_, index) => (
            <Skeleton className="skeleton-nav" key={index} />
          ))}
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <h1>Datasets</h1>
        </header>
        <div className="skeleton-stack skeleton-table">
          {Array.from({ length: 8 }, (_, index) => (
            <Skeleton className="skeleton-row" key={index} />
          ))}
        </div>
      </main>
    </div>
  );
}
