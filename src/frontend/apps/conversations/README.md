The Conversations front-end: a client-rendered SPA built with [Vite](https://vite.dev/), React and [React Router](https://reactrouter.com/) in declarative mode.

## Getting Started

Run the development server:

```bash
yarn dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

Routing lives in `src/App.tsx`; page components are in `src/pages/`.

## Scripts

| Command           | What it does                                               |
| ----------------- | ---------------------------------------------------------- |
| `yarn dev`        | Vite dev server on port 3000                               |
| `yarn build`      | Format check, stylelint, type-check, then build to `dist/` |
| `yarn start`      | Serve the production build locally (`vite preview`)        |
| `yarn test`       | Run the Vitest suite                                       |
| `yarn test:watch` | Vitest in watch mode                                       |
| `yarn lint`       | Type-check and lint                                        |

## Environment

Build-time variables use the `VITE_` prefix and are read through `import.meta.env`:

- `VITE_API_ORIGIN` - backend origin; falls back to the current origin.
- `VITE_PRODUCT_NAME` - product name shown in the UI.
