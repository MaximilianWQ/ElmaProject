import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

// Kept deliberately small: rules that catch defects stay errors, rules that
// express a preference are warnings. A lint run that is always red is a lint
// run nobody looks at.
export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Rules of hooks and impure work during render are real defects.
      "react-hooks/rules-of-hooks": "error",
      // Copying a fetched record into form state is what these effects do, and
      // it is the intended pattern here; keep it visible, not blocking.
      "react-hooks/set-state-in-effect": "warn",
      // `set.has(x) ? set.delete(x) : set.add(x)` — both branches are effects.
      "@typescript-eslint/no-unused-expressions": "warn",
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
);
