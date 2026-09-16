import { FlatCompat } from "@eslint/eslintrc";

// eslint-config-next 15 still ships legacy-format configs; FlatCompat adapts them
// to ESLint 9's flat config. Drop this when eslint-config-next exports flat configs.
const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const config = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  { ignores: [".next/**", "out/**", "node_modules/**", "next-env.d.ts"] },
];

export default config;
