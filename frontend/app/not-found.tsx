import type { Metadata } from "next";
import Link from "next/link";
import { BrandLogo } from "@/components/brand-logo";
import { buttonVariants } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Page not found · AnyView",
};

/** The 404 page. The static export writes it to out/404.html, which Firebase
 *  Hosting serves with a real 404 status for any path that has no file
 *  (firebase.json has no catch-all rewrite, so unknown paths reach it). */
export default function NotFound() {
  return (
    <>
      <header className="workspace-header">
        <BrandLogo />
      </header>
      <main id="main-content" className="workspace-main">
        <div className="workspace-panel mx-auto mt-6 flex w-full max-w-lg flex-col items-center gap-6 text-center">
          <div className="space-y-3">
            <p className="eyebrow">404 · Page not found</p>
            <h1 className="text-4xl font-semibold tracking-tight">Nothing planted here<span className="text-primary">.</span></h1>
            <p className="text-sm text-muted-foreground">
              This page doesn&apos;t exist, or it has moved. Your Digital Garden is where you left it.
            </p>
          </div>
          <Link href="/" className={buttonVariants({ className: "h-11 px-5 text-base" })}>
            Back to your Digital Garden
          </Link>
        </div>
      </main>
    </>
  );
}
