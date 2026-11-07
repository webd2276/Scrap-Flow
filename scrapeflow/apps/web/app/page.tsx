import { redirect } from "next/navigation";
import type { ReactNode } from "react";

export default function HomePage(): ReactNode {
  redirect("/jobs");
}
