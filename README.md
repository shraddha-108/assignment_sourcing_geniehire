# Recruiter Search

The project is organized into separate application folders:

- `frontend/` contains the React app, static assets, and frontend tests.
- `recruiter-search-api/` contains the backend API, its tests, and data.

The frontend's Vite, TypeScript, and npm configuration stays at the repository root, so the existing npm commands can be run there:

```sh
npm run dev
npm run build
npm run lint
node --test frontend/tests/**/*.test.mjs
```

Frontend environment variables belong in `frontend/.env`.
