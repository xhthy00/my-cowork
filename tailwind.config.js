/** @type {import('tailwindcss').Config} */
/** Adapted from eigent: tailwind.config.js (DS token subset). */
module.exports = {
  darkMode: ["class"],
  content: ["./renderer/src/**/*.{ts,tsx}", "./renderer/index.html"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "PingFang SC",
          "Hiragino Sans GB",
          "Noto Sans SC",
          "system-ui",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "label-xs": ["calc(10px * var(--ui-font-scale, 1))", { lineHeight: "1.4", fontWeight: "600" }],
        "label-sm": ["calc(13px * var(--ui-font-scale, 1))", { lineHeight: "1.4", fontWeight: "600" }],
        "body-sm": ["calc(13px * var(--ui-font-scale, 1))", { lineHeight: "1.4" }],
        "body-xs": ["calc(11px * var(--ui-font-scale, 1))", { lineHeight: "1.4" }],
        "body-base": ["calc(15px * var(--ui-font-scale, 1))", { lineHeight: "1.5" }],
        "body-md": ["calc(14px * var(--ui-font-scale, 1))", { lineHeight: "1.5" }],
        "heading-sm": ["calc(24px * var(--ui-font-scale, 1))", { lineHeight: "1.25", fontWeight: "700" }],
        "heading-lg": ["calc(28px * var(--ui-font-scale, 1))", { lineHeight: "1.25", fontWeight: "700" }],
      },
      colors: {
        border: "var(--border)",
        input: "var(--border)",
        ring: "var(--ds-ring-neutral-subtle-default)",
        background: "var(--bg-panel)",
        foreground: "var(--text)",
        muted: {
          DEFAULT: "var(--bg-muted)",
          foreground: "var(--text-muted)",
        },
        card: {
          DEFAULT: "var(--bg-elevated)",
          foreground: "var(--text)",
        },
        primary: {
          DEFAULT: "var(--colors-primary-default)",
          foreground: "#ffffff",
        },
        secondary: {
          DEFAULT: "var(--bg-hover)",
          foreground: "var(--text-secondary)",
        },
        destructive: {
          DEFAULT: "var(--danger)",
          foreground: "#ffffff",
        },
        accent: {
          DEFAULT: "var(--accent-soft)",
          foreground: "var(--accent-text)",
        },
        /* Eigent DS utilities */
        "ds-bg-neutral-muted-default": "var(--ds-bg-neutral-muted-default)",
        "ds-bg-neutral-subtle-default": "var(--ds-bg-neutral-subtle-default)",
        "ds-bg-neutral-default-default": "var(--ds-bg-neutral-default-default)",
        "ds-bg-neutral-default-hover": "var(--ds-bg-neutral-default-hover)",
        "ds-bg-neutral-strong-default": "var(--ds-bg-neutral-strong-default)",
        "ds-bg-brand-subtle-default": "var(--ds-bg-brand-subtle-default)",
        "ds-bg-brand-default-default": "var(--ds-bg-brand-default-default)",
        "ds-bg-brand-subtle-disabled": "var(--ds-bg-brand-subtle-disabled)",
        "ds-text-neutral-default-default": "var(--ds-text-neutral-default-default)",
        "ds-text-neutral-muted-default": "var(--ds-text-neutral-muted-default)",
        "ds-text-neutral-subtle-default": "var(--ds-text-neutral-subtle-default)",
        "ds-text-brand-default-default": "var(--ds-text-brand-default-default)",
        "ds-text-brand-subtle-default": "var(--ds-text-brand-subtle-default)",
        "ds-text-brand-muted-default": "var(--ds-text-brand-muted-default)",
        "ds-text-brand-strong-default": "var(--ds-text-brand-strong-default)",
        "ds-text-brand-inverse-default": "var(--ds-text-brand-inverse-default)",
        "ds-text-success-default-default": "var(--ds-text-success-default-default)",
        "ds-text-error-default-default": "var(--ds-text-error-default-default)",
        "ds-text-information-default-default":
          "var(--ds-text-information-default-default)",
        "ds-text-warning-default-default": "var(--ds-text-warning-default-default)",
        "ds-text-terminal-default-default": "var(--ds-text-terminal-default-default)",
        "ds-text-document-default-default": "var(--ds-text-document-default-default)",
        "ds-bg-status-splitting-subtle-default":
          "var(--ds-bg-status-splitting-subtle-default)",
        "ds-bg-splitting-subtle-default": "var(--ds-bg-splitting-subtle-default)",
        "ds-icon-status-splitting-default-default":
          "var(--ds-icon-status-splitting-default-default)",
        "ds-text-status-splitting-default": "var(--ds-text-status-splitting-default)",
        "ds-border-neutral-strong-default": "var(--ds-border-neutral-strong-default)",
        "ds-bg-status-completed-subtle-default":
          "var(--ds-bg-status-completed-subtle-default)",
        "ds-bg-status-completed-default-default":
          "var(--ds-bg-status-completed-default-default)",
        "ds-text-status-completed-default": "var(--ds-text-status-completed-default)",
        "ds-icon-status-completed-default-default":
          "var(--ds-icon-status-completed-default-default)",
        "ds-bg-neutral-default-hover": "var(--ds-bg-neutral-default-hover)",
        "ds-border-neutral-default-default": "var(--ds-border-neutral-default-default)",
        "ds-border-neutral-subtle-default": "var(--ds-border-neutral-subtle-default)",
        "ds-border-neutral-subtle-disabled": "var(--ds-border-neutral-subtle-disabled)",
        "ds-border-information-default-default":
          "var(--ds-border-information-default-default)",
        "ds-icon-neutral-muted-default": "var(--ds-icon-neutral-muted-default)",
        "ds-icon-neutral-default-default": "var(--ds-icon-neutral-default-default)",
        "ds-icon-status-completed-default": "var(--ds-icon-status-completed-default)",
        "ds-bg-success-default-default": "var(--ds-bg-success-default-default)",
        "ds-text-success-inverse-default": "var(--ds-text-success-inverse-default)",
        "ds-icon-neutral-subtle-default": "var(--ds-text-neutral-subtle-default)",
      },
      borderRadius: {
        /* Eigent: sm=4 lg=8 xl=16; md sits between sm/lg */
        sm: "var(--borderRadius-sm, 4px)",
        md: "6px",
        lg: "var(--borderRadius-lg, 8px)",
        xl: "var(--borderRadius-xl, 16px)",
        "2xl": "var(--borderRadius-xl, 16px)",
        "3xl": "24px",
      },
      boxShadow: {
        soft: "var(--shadow-soft)",
        perfect: "var(--shadow-lg)",
        button: "var(--shadow-button)",
        "button-shadow": "var(--shadow-button)",
      },
    },
  },
  plugins: [],
};
