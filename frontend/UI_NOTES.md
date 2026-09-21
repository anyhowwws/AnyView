# Workspace refresh

The Digital Garden is a map of the user's confirmed experience. The graph is a
read-only projection of existing API data, rendered with SVG edges and native
HTML buttons; it needs no graph database, inference call, or new dependency.

The workspace uses Geist, a slate text color (#203638), a pale background
(#f4f7f7), white content surfaces, and teal actions (#24685e). Display text is
32–48px; body text is 14–16px. The relationship map is the main visual feature.
On wide screens its details sit beside the graph; below 900px they move below
it. On phones, the graph scrolls within its own region instead of widening the
page. Controls support keyboard use, visible focus, and reduced motion.

Graph, Entries, and Coverage are alternate views of the same confirmed brain.
Search and type selection highlight matching nodes while retaining relationship
context. The expandable entry index provides a text navigation alternative.
Select a node to inspect its details and traverse related entries. Connections
to missing/retired entities are excluded. Achievements remain isolated because
the current API has no achievement relationship fields.

Run `npm run test` for graph relationship integrity tests, alongside lint,
typecheck, and a production build. The tests use Node's built-in runner and
TypeScript stripping (Node 22.6+), without another dependency.

Future work: larger-brain layout clustering and directly editing the selected
entry in the inspector. Currently editing stays in the existing Entries view.
