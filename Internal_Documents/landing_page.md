Create a polished, production-ready landing page for **CloudDesk**, using the current repository on the `development` branch as the source of truth.

## Start by understanding the project

Before editing anything:

1. Inspect the repository structure, README, package/build configuration, routes, and current application entry points.
2. Identify the actual tech stack, styling system, reusable components, assets, design conventions, and how the app is built and served.
3. Inspect the existing UI and determine whether a landing page already exists or whether one should be added as a route or page.
4. Read relevant project instructions such as `AGENTS.md`, `CLAUDE.md`, or contributor documentation.
5. Summarize your findings briefly, then implement the page in the appropriate location.

Do not assume CloudDesk’s features, audience, architecture, integrations, or claims from its name. Use only information supported by the repository. If the project does not establish a fact, leave it out or use neutral wording.

## Design direction

Create a professional, modern landing page that feels specific to this product and consistent with the existing application. Use the repository’s existing framework, components, design tokens, and dependencies wherever possible. Avoid adding a new framework or large dependency for a single page.

The page should include, where supported by the project:

- A responsive header with the existing logo or wordmark, clear navigation, and a prominent primary action.
- A strong hero section with a concise, accurate value proposition, a short supporting description, and a primary call to action. Add a secondary action only if the destination is real and useful.
- A product visual based on the actual app UI, existing screenshots, or a carefully composed interface using real product concepts. Do not invent features or imply that mock functionality is live.
- A features section that explains the product’s verified capabilities in concrete user terms.
- A “how it works” or workflow section if the repository supports a clear explanation.
- Trust, security, deployment, pricing, testimonials, customer logos, or metrics only when the project provides evidence for them. Do not fabricate social proof or performance claims.
- A closing call to action and a useful footer with links that actually exist.

Use deliberate typography, spacing, contrast, and restrained color. Keep the layout readable and distinctive rather than relying on generic SaaS gradients, decorative blobs, or stock copy. Use existing assets first. If suitable visuals are missing, create the product presentation with the project’s own components and styles; do not introduce remote image dependencies without a clear reason.

## Implementation requirements

- Match the current codebase’s conventions and integrate with its existing routing and build setup.
- Make the page responsive across mobile, tablet, and desktop.
- Ensure navigation and calls to action work; do not add dead buttons or placeholder links.
- Use semantic HTML, accessible labels, visible keyboard focus, and appropriate color contrast.
- Respect reduced-motion preferences if adding animation. Keep motion subtle and nonessential.
- Avoid changing unrelated application behavior, configuration, or backend code.
- Do not add dependencies unless they are necessary; explain any addition.
- Do not overwrite or remove existing work without understanding its purpose.

## Finish

After implementation, review the result against the repository’s existing patterns and fix any obvious layout, accessibility, or responsive issues. Run the project’s relevant existing build, lint, or check commands if available, and report which commands succeeded or failed.

In your final response, summarize the files changed, the landing page sections implemented, any assumptions made because the repository lacked information, and the checks performed.