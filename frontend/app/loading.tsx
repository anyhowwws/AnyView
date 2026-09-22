/** Suspense fallback for every top-level route (/, /brain, /practice).
 *  Without this, Next.js updates the URL and the nav's active tab the
 *  moment you click a Link, but leaves the *old* page's content on
 *  screen until the new route's code and data are ready — so toggling
 *  tabs can look like the click did nothing. This makes that gap a
 *  visible loading state instead of a stale one. */
export default function Loading() {
  return (
    <main className="loading-space" role="status">
      Loading…
    </main>
  );
}
