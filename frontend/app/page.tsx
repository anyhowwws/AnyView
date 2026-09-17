import { App } from "@/components/app";
import { AuthShell } from "@/components/shell";

export default function Home() {
  return (
    <AuthShell>
      <App />
    </AuthShell>
  );
}
