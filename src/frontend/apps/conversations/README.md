This is the Conversations front-end: a [React](https://react.dev/) single-page app built with [Vite](https://vite.dev/) and routed with [React Router](https://reactrouter.com/) in declarative mode.

## Getting Started

Run the development server:

```bash
yarn dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

Routes are declared in `src/App.tsx`; their page components live in `src/pages/`.

## Commands

```bash
yarn dev      # development server (Vite)
yarn build    # format/style/type checks, then a production build into dist/
yarn start    # serve the production build
yarn lint     # tsc --noEmit + eslint
yarn test     # Vitest
```

## Environment variables

Build-time variables must use the `VITE_` prefix and are read through
`import.meta.env`. They are set in `.env`, `.env.development` and `.env.test`:

| Variable            | Description                                                      |
| ------------------- | ---------------------------------------------------------------- |
| `VITE_API_ORIGIN`   | Backend origin; falls back to the current origin when left empty |
| `VITE_PRODUCT_NAME` | Product name shown in the UI                                     |
