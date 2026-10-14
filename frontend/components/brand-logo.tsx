import Image from "next/image";
import Link from "next/link";

/** The same brand mark is also exported as the browser and home-screen icon. */
export function BrandLogo() {
  return (
    <Link href="/" className="wordmark" aria-label="AnyView home">
      <Image src="/brand-mark.svg" alt="" width={36} height={36} className="brand-mark" priority />
      anyview<span className="brand-dot">.</span>
    </Link>
  );
}
