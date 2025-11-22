# Langfuse Tracing - Debug Guide

## Configuration Summary

**Environment Variables** (from `.env`):
```
LANGFUSE_PUBLIC_KEY=pk-lf-REDACTED
LANGFUSE_SECRET_KEY=sk-lf-REDACTED
LANGFUSE_HOST=https://us.cloud.langfuse.com
LANGFUSE_PROJECT_NAME=annie
ENVIRONMENT=dev
```

**Client Configuration**:
- **Release Tag**: `annie-dev` (automatically set based on ENVIRONMENT)
- **Batch Size**: 10 traces
- **Flush Interval**: 1 second
- **Background Flushing**: Enabled
- **Fire-and-Forget**: All tracing failures are logged but don't crash the app

## Checking Traces in Langfuse

### 1. Login to Langfuse Cloud
- Navigate to: https://us.cloud.langfuse.com
- Login with your credentials
- Your API keys link to your organization and project automatically

### 2. Select Project
- Look for project matching your PUBLIC_KEY (pk-lf-5fac8afd...)
- Project name should be visible in the Langfuse dashboard

### 3. View Traces
- Click on "Traces" in the left sidebar
- Filter by:
  - **Release**: `annie-dev`
  - **User ID**: Your Telegram user ID (e.g., `YOUR_USER_ID`)
  - **Name**: `chat_request` (for chat endpoint traces)

### 4. Trace Hierarchy to Expect

**Note**: Annie creates TWO linked traces per conversation because chat and streaming are separate HTTP requests:

**Trace 1: chat_request** (POST /api/chat)
```
Trace: chat_request
├── Session ID: <conversation_id> (links to stream_request)
├── User ID: <your_telegram_id>
└── Metadata: platform, message_length, conversation_ending, needs_decision_support, message
```

**Trace 2: stream_request** (GET /api/stream/{conversation_id})
```
Trace: stream_request
├── Session ID: <conversation_id> (links to chat_request)
├── User ID: <your_telegram_id>
├── Metadata: endpoint
├── Span: llm_streaming (if streaming)
│   ├── Metadata: conversation_id, message_count
│   ├── Output: chunk_count, duration_ms, completion_status
└── Generation: llm_call_grok-4_streaming or llm_call_chatgpt-5_streaming
    ├── Input: Truncated prompt (1000 chars)
    ├── Output: Truncated completion (1000 chars)
    ├── Model: grok-4-fast or chatgpt-5
    ├── Usage: prompt_tokens, completion_tokens, total_tokens
    └── Cost: input_cost, output_cost, total_cost
```

**How to View Linked Traces**:
- In Langfuse, filter by Session ID (conversation_id) to see both traces together
- Or click on a trace and look for the "Session" field to find related traces

## Enhanced Logging (Added)

The following log markers help track Langfuse activity:

### Client Initialization
```
[INFO] Langfuse client initialized successfully
  - host: https://us.cloud.langfuse.com
  - release: annie-dev
  - batch_size: 10
  - flush_interval: 1.0
  - public_key_prefix: pk-lf-5fac...
```

### Trace Events
```
[INFO] [LANGFUSE] Started trace: chat_request
  - trace_name: chat_request
  - user_id: YOUR_USER_ID
  - session_id: None (will be updated after conversation_id is available)
  - trace_id: <uuid>
  - metadata: {...}

[INFO] [LANGFUSE] Updated chat trace with session_id: conv_abc123
  - conversation_id: conv_abc123

[INFO] [LANGFUSE] Started trace: stream_request
  - trace_name: stream_request
  - user_id: system (will be updated with actual user_id)
  - session_id: conv_abc123 (links to chat_request)
  - trace_id: <uuid>
  - metadata: {...}

[INFO] [LANGFUSE] Updated stream trace with user_id: YOUR_USER_ID
  - user_id: YOUR_USER_ID
  - conversation_id: conv_abc123
```

### Generation Events
```
[INFO] [LANGFUSE] Created LLM generation: grok-4
  - provider: grok-4
  - model: grok-4-fast
  - prompt_tokens: 100
  - completion_tokens: 50
  - total_cost: 0.0 (free during promo)
  - duration_ms: 1500
```

### Span Events
```
[DEBUG] Started top-level span
  - span_name: llm_streaming

[DEBUG] Ended span
  - level: DEFAULT
```

## Testing Langfuse Integration

### Step 1: Send a Test Message via Telegram
1. Open your Annie bot in Telegram
2. Send a message: "Hello, how are you?"
3. Wait for the response

### Step 2: Check Backend Logs
```bash
docker compose logs backend --tail=100 | grep -i "\[LANGFUSE\]"
```

**Expected Output**:
```
[INFO] Langfuse client initialized successfully...
[INFO] [LANGFUSE] Started trace: chat_request...
[INFO] [LANGFUSE] Updated chat trace with session_id: conv_...
[INFO] [LANGFUSE] Started trace: stream_request... session_id=conv_...
[INFO] [LANGFUSE] Updated stream trace with user_id: ...
[INFO] [LANGFUSE] Created LLM generation: grok-4...
```

### Step 3: Verify in Langfuse Dashboard
1. Go to https://us.cloud.langfuse.com
2. Navigate to "Traces"
3. Look for TWO recent traces per conversation:
   - **Trace 1**: Name: `chat_request`, User ID: Your Telegram user ID
   - **Trace 2**: Name: `stream_request`, User ID: Your Telegram user ID
   - Both should have: Release: `annie-dev`, Timestamp: Within last few minutes
4. **View Linked Traces**:
   - Click "Sessions" in the left sidebar
   - Find session ID matching your conversation_id (e.g., `conv_abc123`)
   - You should see both `chat_request` and `stream_request` traces linked together

### Step 4: Inspect Trace Details
Click on the `stream_request` trace to see the LLM generation:
- ✅ Session ID linking it to `chat_request` trace
- ✅ Trace metadata (endpoint, etc.)
- ✅ Generation data (model, tokens, cost)
- ✅ Span data (streaming metrics)
- ✅ Input/output (truncated to 1000 chars)

## Troubleshooting

### Issue: No Traces Visible in Langfuse

**Possible Causes**:

1. **API Keys Mismatch**
   - Verify your PUBLIC_KEY and SECRET_KEY in `.env` match the project in Langfuse
   - Check the Langfuse dashboard shows the correct project

2. **Traces Not Flushed Yet**
   - Wait 1-2 seconds after request completes (flush interval = 1s)
   - Make 10+ requests to trigger batch flush (batch_size = 10)
   - Or manually flush: restart backend to trigger shutdown flush

3. **Wrong Project Selected**
   - Each PUBLIC_KEY is tied to a specific project in Langfuse
   - Navigate to the project that matches your pk-lf-5fac8afd... key

4. **Traces Filtered Out**
   - Remove all filters in Langfuse UI
   - Check "All traces" instead of specific time ranges
   - Look for release tag "annie-dev"

### Issue: Langfuse Client Not Initializing

Check logs for:
```
[WARNING] Langfuse tracing disabled (keys not configured)
[WARNING] Langfuse package not installed, tracing disabled
[WARNING] Failed to initialize Langfuse client, tracing disabled
```

**Solutions**:
- Verify `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in `.env`
- Ensure langfuse package is installed: `pip install langfuse==2.36.0`
- Restart backend: `docker compose restart backend`

### Issue: Traces Created But Not Showing Details

Check logs for:
```
[WARNING] [LANGFUSE] Failed to start trace: <error>
[WARNING] [LANGFUSE] Failed to track LLM generation: <error>
```

**Solutions**:
- Check network connectivity to https://us.cloud.langfuse.com
- Verify API keys are not expired
- Check Langfuse Cloud status page

## Manual Flush Test

To force an immediate flush of traces to Langfuse:

```bash
# Restart backend (triggers atexit flush)
docker compose restart backend

# Check logs for flush message
docker compose logs backend --tail=20 | grep "Flushing Langfuse"
```

**Expected Output**:
```
[INFO] Flushing Langfuse traces on shutdown...
[INFO] Langfuse traces flushed successfully
```

## Verification Checklist

- [ ] Langfuse credentials configured in `.env`
- [ ] Backend restarted after configuration changes
- [ ] Test message sent via Telegram bot
- [ ] Backend logs show `[LANGFUSE] Started trace` messages
- [ ] Backend logs show `[LANGFUSE] Created LLM generation` messages
- [ ] Langfuse dashboard shows recent traces
- [ ] Trace details include generations and metadata
- [ ] Cost data visible in generation details

## Next Steps

If traces are still not visible after following this guide:

1. **Enable Langfuse SDK Debug Mode**
   - Edit `backend/api/observability/langfuse_client.py`
   - Set `debug=True` in Langfuse() constructor
   - Restart backend
   - Check logs for detailed SDK messages

2. **Test with Small Script**
   ```python
   from langfuse import Langfuse

   client = Langfuse(
       public_key="pk-lf-REDACTED",
       secret_key="sk-lf-REDACTED",
       host="https://us.cloud.langfuse.com"
   )

   trace = client.trace(name="test_trace", user_id="test_user")
   trace.generation(name="test_gen", input="test", output="test", model="test")
   client.flush()
   print("Test complete - check Langfuse dashboard")
   ```

3. **Contact Langfuse Support**
   - Check if your account/project is properly set up
   - Verify API keys are active
   - Confirm no rate limiting or quota issues

## References

- **Langfuse Documentation**: https://langfuse.com/docs
- **Python SDK**: https://langfuse.com/docs/sdk/python/low-level-sdk
- **Trace Hierarchy**: https://langfuse.com/docs/tracing
- **Model Costs**: https://langfuse.com/docs/model-cost
