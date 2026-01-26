# Story 20.17: Tool Calling UI (Debug/Admin)

Status: drafted

## Story

As an admin/developer,
I want to manually invoke Annie's tools and see execution history,
so that I can debug tool integrations and test new tools without conversation context.

## Acceptance Criteria

1. Tool palette accessible from sidebar (admin mode)
2. List all available MCP tools
3. Search/filter tools by name
4. Manual tool invocation with parameter form
5. Show tool execution result
6. Tool execution history log
7. Copy tool result to clipboard
8. Hidden behind admin flag or debug mode
9. Show tool schema/parameters documentation
10. Handle tool errors gracefully

## Tasks / Subtasks

- [ ] Task 1: Create tool API client
  - [ ] 1.1 Create `web/src/lib/api/toolClient.ts`
  - [ ] 1.2 Implement list tools endpoint
  - [ ] 1.3 Implement invoke tool endpoint

- [ ] Task 2: Create ToolsPage
  - [ ] 2.1 Create `web/src/pages/ToolsPage.tsx`
  - [ ] 2.2 Layout with tool list and detail

- [ ] Task 3: Create ToolList component
  - [ ] 3.1 Create `web/src/components/tools/ToolList.tsx`
  - [ ] 3.2 Display tool names and descriptions
  - [ ] 3.3 Search/filter functionality

- [ ] Task 4: Create ToolInvoker component
  - [ ] 4.1 Create `web/src/components/tools/ToolInvoker.tsx`
  - [ ] 4.2 Dynamic form from tool schema
  - [ ] 4.3 Execute button
  - [ ] 4.4 Display result

- [ ] Task 5: Create ToolHistory component
  - [ ] 5.1 Create `web/src/components/tools/ToolHistory.tsx`
  - [ ] 5.2 Log recent executions
  - [ ] 5.3 Show input/output for each
  - [ ] 5.4 Store in session storage

- [ ] Task 6: Add admin mode guard
  - [ ] 6.1 Reuse admin check from Memory Browser
  - [ ] 6.2 Show "V3" badge in sidebar

- [ ] Task 7: Backend API (if not exists)
  - [ ] 7.1 GET /api/tools - List available tools
  - [ ] 7.2 POST /api/tools/{name}/invoke - Invoke tool

## Dev Notes

### Purpose

This is a **debug/admin tool** for:
- Testing tool integrations (web search, HA, etc.)
- Debugging tool parameter issues
- Verifying tool responses
- Manual tool execution without LLM

### Tool API

```typescript
// GET /api/tools
interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: {
    type: 'object';
    properties: Record<string, {
      type: string;
      description: string;
      required?: boolean;
    }>;
    required?: string[];
  };
}

// POST /api/tools/{name}/invoke
interface ToolInvocation {
  arguments: Record<string, any>;
  user_id: string;
}
```

### UI Layout

```
┌─────────────────────────────────────────────────┐
│ Tool Debugger                          [Search] │
├─────────────────────────────────────────────────┤
│ ┌─────────────────┐  ┌────────────────────────┐ │
│ │ Available Tools │  │ Tool: web_search       │ │
│ │ ├─ web_search   │  │                        │ │
│ │ ├─ web_crawl    │  │ Parameters:            │ │
│ │ ├─ retrieve_... │  │ ┌────────────────────┐ │ │
│ │ ├─ store_memory │  │ │ query: [          ]│ │ │
│ │ ├─ get_portfolio│  │ │ max_results: [5   ]│ │ │
│ │ ├─ ha_query     │  │ └────────────────────┘ │ │
│ │ └─ ha_control   │  │                        │ │
│ │                 │  │ [Execute Tool]         │ │
│ │                 │  │                        │ │
│ │ History         │  │ Result:                │ │
│ │ ├─ 10:30 web_s.│  │ ┌────────────────────┐ │ │
│ │ ├─ 10:28 ha_qu.│  │ │ { "results": [...] │ │ │
│ │ └─ 10:25 get_p.│  │ │ }                  │ │ │
│ └─────────────────┘  │ └────────────────────┘ │ │
│                      │ [Copy Result]          │ │
│                      └────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### Dynamic Form Generation

```typescript
function ToolForm({ schema, onSubmit }: ToolFormProps) {
  const [values, setValues] = useState<Record<string, any>>({});

  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(values); }}>
      {Object.entries(schema.properties).map(([key, prop]) => (
        <div key={key} className="mb-4">
          <label className="block text-sm font-medium mb-1">
            {key}
            {schema.required?.includes(key) && <span className="text-red-500">*</span>}
          </label>
          <p className="text-xs text-gray-500 mb-1">{prop.description}</p>
          {prop.type === 'string' && (
            <input
              type="text"
              value={values[key] || ''}
              onChange={(e) => setValues({ ...values, [key]: e.target.value })}
              className="w-full border rounded px-2 py-1"
            />
          )}
          {prop.type === 'integer' && (
            <input
              type="number"
              value={values[key] || ''}
              onChange={(e) => setValues({ ...values, [key]: parseInt(e.target.value) })}
              className="w-full border rounded px-2 py-1"
            />
          )}
          {prop.type === 'boolean' && (
            <input
              type="checkbox"
              checked={values[key] || false}
              onChange={(e) => setValues({ ...values, [key]: e.target.checked })}
            />
          )}
        </div>
      ))}
      <button type="submit" className="px-4 py-2 bg-purple-500 text-white rounded">
        Execute Tool
      </button>
    </form>
  );
}
```

### Execution History

```typescript
interface ToolExecution {
  id: string;
  toolName: string;
  arguments: Record<string, any>;
  result: any;
  error?: string;
  timestamp: Date;
  durationMs: number;
}

// Store in session storage
const [history, setHistory] = useState<ToolExecution[]>(() => {
  const stored = sessionStorage.getItem('tool-history');
  return stored ? JSON.parse(stored) : [];
});

useEffect(() => {
  sessionStorage.setItem('tool-history', JSON.stringify(history));
}, [history]);
```

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.17]
- [Source: docs/brainstorming-web-ui-2026-01-25.md#Tool-Calling]
- [Source: mcp_server/tools.py - Tool definitions]

## Dev Agent Record

### Context Reference

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
