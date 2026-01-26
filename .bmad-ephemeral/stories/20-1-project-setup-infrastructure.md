# Story 20.1: Project Setup & Infrastructure

Status: drafted

## Story

As a developer,
I want to set up a Vite + React project with shadcn/ui and Docker integration,
so that the web UI has a solid foundation for building Annie's responsive interface.

## Acceptance Criteria

1. Vite + React 18 project bootstrapped in `web/` directory
2. TypeScript configuration with strict mode enabled
3. Tailwind CSS properly configured and working
4. shadcn/ui component library installed and configured
5. ESLint + Prettier configuration with consistent code style
6. Dockerfile for containerized deployment using nginx
7. Docker Compose service definition added to main compose file
8. Environment variables configuration (VITE_API_URL, etc.)
9. Development server runs on port 3000
10. Production build completes successfully without errors
11. Nginx config for SPA routing (fallback to index.html)
12. Basic app shell renders with placeholder content

## Tasks / Subtasks

- [ ] Task 1: Initialize Vite + React project (AC: 1, 2)
  - [ ] 1.1 Run `npm create vite@latest web -- --template react-ts`
  - [ ] 1.2 Configure `tsconfig.json` with strict mode and path aliases
  - [ ] 1.3 Add `@/` path alias for clean imports
  - [ ] 1.4 Verify TypeScript compilation works

- [ ] Task 2: Configure Tailwind CSS (AC: 3)
  - [ ] 2.1 Install tailwindcss, postcss, autoprefixer
  - [ ] 2.2 Create `tailwind.config.js` with Annie theme colors
  - [ ] 2.3 Create `postcss.config.js`
  - [ ] 2.4 Add Tailwind directives to `index.css`
  - [ ] 2.5 Verify Tailwind classes work in a test component

- [ ] Task 3: Install and configure shadcn/ui (AC: 4)
  - [ ] 3.1 Run `npx shadcn@latest init` with custom settings
  - [ ] 3.2 Configure `components.json` for Tailwind
  - [ ] 3.3 Add base shadcn/ui components (Button, Card, Input)
  - [ ] 3.4 Create `lib/utils.ts` with `cn()` utility
  - [ ] 3.5 Verify shadcn components render correctly

- [ ] Task 4: Set up linting and formatting (AC: 5)
  - [ ] 4.1 Install ESLint with React and TypeScript plugins
  - [ ] 4.2 Create `.eslintrc.cjs` configuration
  - [ ] 4.3 Install Prettier
  - [ ] 4.4 Create `.prettierrc` configuration
  - [ ] 4.5 Add lint and format scripts to package.json
  - [ ] 4.6 Verify `npm run lint` passes

- [ ] Task 5: Create Docker configuration (AC: 6, 7, 11)
  - [ ] 5.1 Create `web/Dockerfile` with multi-stage build
  - [ ] 5.2 Create `web/nginx.conf` for SPA routing
  - [ ] 5.3 Add web service to `docker-compose.yml`
  - [ ] 5.4 Configure proper networking (annie-network)
  - [ ] 5.5 Verify `docker compose build web` succeeds

- [ ] Task 6: Configure environment variables (AC: 8)
  - [ ] 6.1 Create `.env.example` for web service
  - [ ] 6.2 Configure Vite to expose VITE_* variables
  - [ ] 6.3 Create `src/lib/config.ts` for runtime config
  - [ ] 6.4 Document required environment variables

- [ ] Task 7: Verify development and production builds (AC: 9, 10, 12)
  - [ ] 7.1 Run `npm run dev` and verify port 3000
  - [ ] 7.2 Run `npm run build` and verify dist output
  - [ ] 7.3 Test production build with `npm run preview`
  - [ ] 7.4 Create basic App shell with placeholder

- [ ] Task 8: Test Docker deployment
  - [ ] 8.1 Build and run container locally
  - [ ] 8.2 Verify nginx serves SPA correctly
  - [ ] 8.3 Test SPA routing (refresh on deep route)

## Dev Notes

### Architecture Context

**Tech Stack Decision** (from brainstorming):
- Vite + React 18 chosen over Next.js for simplicity - Annie is a SPA with no SSR requirements
- shadcn/ui chosen over assistant-ui to give Annie a unique identity
- Zustand for state management (lightweight, simple mental model)

### Directory Structure

```
annie/
├── web/                        # NEW - this story creates this
│   ├── src/
│   │   ├── components/
│   │   │   └── ui/             # shadcn/ui components
│   │   ├── lib/
│   │   │   ├── utils.ts        # cn() utility
│   │   │   └── config.ts       # Environment config
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── public/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── Dockerfile
│   └── nginx.conf
└── docker-compose.yml          # MODIFY - add web service
```

### Package.json Dependencies

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "zustand": "^4.4.0",
    "@radix-ui/react-dialog": "^1.0.0",
    "@radix-ui/react-dropdown-menu": "^2.0.0",
    "@radix-ui/react-scroll-area": "^1.0.0",
    "@radix-ui/react-tooltip": "^1.0.0",
    "clsx": "^2.0.0",
    "tailwind-merge": "^2.0.0",
    "lucide-react": "^0.294.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.2.0",
    "typescript": "^5.3.0",
    "tailwindcss": "^3.3.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "eslint": "^8.55.0",
    "prettier": "^3.1.0"
  }
}
```

### Dockerfile Pattern

```dockerfile
# Multi-stage build for minimal production image
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### Nginx SPA Config

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### Project Structure Notes

- New `web/` directory at project root alongside `backend/`, `mcp_server/`, `telegram_bot/`
- Docker service name: `web` (maps to port 3000 in dev, 80 in prod via nginx)
- Depends on: `backend` service for API proxying

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.1]
- [Source: .bmad-ephemeral/tech-contexts/epic-20-tech-context.md#Section-3.1]
- [Source: docs/brainstorming-web-ui-2026-01-25.md#Technology-Stack]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

