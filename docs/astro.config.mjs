import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import mermaid from "astro-mermaid";
import { unified } from "@astrojs/markdown-remark";

export default defineConfig({
  outDir: "./_build",
  site: "https://natlabrockies.github.io",
  base: "/r2x-reeds/",
  redirects: { "/how-to/install/": "/r2x-reeds/getting-started/installation/" },
  markdown: { processor: unified() },
  integrations: [
    mermaid({
      enableLog: false,
      mermaidConfig: {
        theme: "base",
        fontFamily: "system-ui, sans-serif",
        flowchart: { curve: "basis" },
      },
    }),
    starlight({
      title: "r2x-reeds",
      logo: {
        light: "./src/assets/r2x-logo-full-color.svg",
        dark: "./src/assets/r2x-logo-white.svg",
        alt: "R2X framework logo",
        replacesTitle: false,
      },
      description: "ReEDS parser and transforms for R2X.",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/NatLabRockies/r2x-reeds",
        },
      ],
      editLink: {
        baseUrl: "https://github.com/NatLabRockies/r2x-reeds/edit/main/docs/",
      },
      customCss: ["./src/styles/brand.css"],
      sidebar: [
        {
          label: "Getting started",
          items: [
            { label: "Installation", link: "/getting-started/installation/" },
            {
              label: "Environment and inputs",
              link: "/getting-started/environment/",
            },
            { label: "Verify installation", link: "/getting-started/verify/" },
            {
              label: "System modifiers",
              link: "/getting-started/system-modifiers/",
            },
          ],
        },
        {
          label: "Tutorials",
          items: [
            {
              label: "Parse a ReEDS run",
              link: "/tutorials/parse-run/",
            },
          ],
        },
        {
          label: "How-to guides",
          items: [
            { label: "Prepare a PCM handoff", link: "/how-to/pcm-handoff/" },
            {
              label: "Inspect a saved system",
              link: "/how-to/inspect-system/",
            },
            {
              label: "CLI pipeline",
              link: "/how-to/reeds-to-x-cli/",
            },
            {
              label: "Python modifiers",
              link: "/how-to/reeds-to-x-script/",
            },
            {
              label: "Purchaser load",
              link: "/how-to/purchaser-load/",
            },
          ],
        },
        {
          label: "Reference",
          items: [
            {
              label: "Python API",
              link: "/reference/python-api/",
            },
            {
              label: "Configuration",
              link: "/reference/configuration/",
            },
            {
              label: "Transforms",
              link: "/reference/transforms/",
            },
            {
              label: "Input upgrades",
              link: "/reference/upgrader/",
            },
          ],
        },
        {
          label: "Explanation",
          items: [
            {
              label: "Architecture",
              link: "/explanation/architecture/",
            },
          ],
        },
        {
          label: "Troubleshooting",
          items: [
            {
              label: "Common problems",
              link: "/troubleshooting/",
            },
          ],
        },
        { label: "Changelog", link: "/changelog/" },
        {
          label: "Contributors",
          items: [
            {
              label: "Development",
              link: "/contributors/",
            },
          ],
        },
      ],
    }),
  ],
});
