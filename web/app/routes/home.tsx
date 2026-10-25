import { redirect } from "react-router";

export function clientLoader() {
  return redirect("/datasets");
}

export default function Home() {
  return null;
}
