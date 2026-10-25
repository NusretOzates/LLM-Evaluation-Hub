import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import type { ReactNode } from "react";
import { isRouteErrorResponse, Links, Meta, Scripts, ScrollRestoration } from "react-router";

import type { Route } from "./+types/root";
import "./app.css";
import { listDatasets, listTags } from "./catalog";
import { Shell, ShellSkeleton } from "./shell";

export function meta() {
  return [{ title: "Evaluation hub" }];
}

export async function clientLoader() {
  const [tags, datasets] = await Promise.all([listTags(), listDatasets(null)]);
  return { tags, datasets };
}

export function shouldRevalidate({
  currentUrl,
  defaultShouldRevalidate,
  formMethod,
  nextUrl,
}: {
  currentUrl: URL;
  defaultShouldRevalidate: boolean;
  formMethod?: string;
  nextUrl: URL;
}) {
  if (formMethod !== undefined || currentUrl.pathname !== nextUrl.pathname) return defaultShouldRevalidate;
  return false;
}

export function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <Meta />
        <Links />
      </head>
      <body>
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

export default function App({ loaderData }: Route.ComponentProps) {
  return <Shell datasets={loaderData.datasets} tags={loaderData.tags} />;
}

export function HydrateFallback() {
  return <ShellSkeleton />;
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  let message = "The catalog could not be loaded.";
  if (isRouteErrorResponse(error)) {
    message = error.status === 404 ? "This page does not exist." : error.statusText || message;
  } else if (error instanceof Error) {
    message = error.message;
  }
  return (
    <main className="outage">
      <h1>{message}</h1>
      <p>Start the catalog API, then reload this page.</p>
      <pre className="mono">LLM_EVAL_CATALOG=data/catalog uv run uvicorn llm_evaluation_hub.api.asgi:app --factory</pre>
      <a className="button-ghost" href="/datasets">
        Reload
      </a>
    </main>
  );
}
