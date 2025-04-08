# Implementing Streaming Responses for Chatbot

- Status: proposed
- Deciders: Kevin Boyer, Yoom Lam
- Date: 2025-03-31

## Context and Problem Statement

Our chatbot currently uses a request-response model, where users submit a query and wait for the entire response (often >10 seconds) before seeing any output. This approach has some limitations:

- **Delayed feedback:** Users experience uncertainty and disengagement while waiting for the full response.
- **Connection vulnerability:** Longer-running requests are at risk of being dropped due to intermittent connectivity, causing users to lose responses entirely.

Implementing streaming responses addresses these issues by providing immediate visual feedback as content is generated, improving perceived responsiveness, and reducing the risk of losing responses due to connectivity issues.

## Decision Drivers

* User experience (responsiveness, feedback, and engagement)
* Reliability of connection to the chatbot
* Implementation effort for both Nava and third-party clients
* Maintainability

## Solution Options

### Polling

- Handles intermittent connectivity through client-side retry logic
- Introduces latency dependent on polling intervals  
- Requires writing client-side logic for managing accumulated response chunks and state.

### Server-Sent Events (SSE)

- Immediate/event-driven updates provide a responsive user experience
- Built-in browser support simplifies client-side implementation 
- Straightforward server-side implementation
- Built-in reconnection handling through the Last-Event-ID header, client automatically uses this
- Supported by all major browsers (Chrome, Firefox, Safari, Edge, Opera), with the exception of Internet Explorer
- One TCP connection per client (vs. one per tab)
- When used over HTTP/2, supports up to 100 simultaneous connections by default; over HTTP/1, limited to 6 connections per browser, which could impact multi-tab usage

### WebSockets

- Supports two-way real-time communication, though we don't anticipate the client sending any additional message besides the user's queries
- Flexible for interactive applications
- Implementation:
  - Setting up WebSocket routes and managing WebSocket connections in application code
  - Handle WebSocket-specific exception cases not present in HTTP endpoints
  - Reconnection logic (no built-in mechanism like Last-Event-ID in SSE)
  - Message sequences for recovery after disconnections need to be tracked
  - Client-side code for connection management and reconnection (retry logic, but [socket.io](https://socket.io/docs/v4/client-api/#event-reconnect) does this)
- Supported across browsers (including IE!), most chat apps do use WS including [Chainlit](https://docs.chainlit.io/deploy/overview#account-for-websockets)

## Decision Outcome

Server-Sent Events (SSE) is a likely candidate because it provides an event-based approach to streaming responses with relatively low implementation complexity. SSE allows the server to push partial responses (like chunks of text from the LLM or server status updates) to the client as they become available, providing visual feedback that is engaging to users. If we want two-way event messaging, use WebSockets.

Polling achieves similar UX results but with different trade-offs.
1. Client makes periodic requests to check for new content at specific time intervals
2. Consider polling interval - too frequent > unnecessary server load, too infrequent > noticeable latency
3. Client manages accumulated response chunks by storing and concatenating them in the correct order
4. With LiteLLM, while the server-side would use streaming capabilities internally, the client would need additional code to handle polling frequency, manage timeouts, and process the accumulated chunks into a coherent response

WebSockets offer two-way communication, which is beneficial for real-time interactive applications like chat apps. FastAPI does provide WebSocket support, but implementation for our use case would still require more setup work than SSE.
1. Reconnection logic, as WebSockets don't have a built-in Last-Event-ID equivalent
2. Need an [Upgrade mechanism](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Protocol_upgrade_mechanism) to switch from HTTP to WS protocol
2. Session state tracking to manage where to resume after disconnections
3. Client-side code to manage connection states and handle reconnection

In contrast, SSE uses standard HTTP connections with several advantages:
1. Built-in reconnections with Last-Event-ID header
2. EventSource API in browsers manages connection states and reconnection
3. You can use server implementation with FastAPI EventSourceResponse that handles SSE-specific formatting
4. Standard HTTP semantics make it easier to work with existing proxies and infrastructure

While both approaches could be implemented using FastAPI, SSE reconnection handling and client-side implementation with EventSource make it suitable for a one-way streaming use case.

### Positive Consequences

These are true for all streaming options:
* Real-time streaming of partial responses increases user engagement
* Users get immediate feedback that the system is working, rather than waiting for a complete response
* LiteLLM and FastAPI have existing support for streaming

SSE-specific:
* Lower implementation effort than WS
* EventSource API and Last-Event-ID header in browsers manages connection states and reconnection

### Negative Consequences for SSE

- SSE connections are limited to one-way communication (server-to-client only)
- Connection limits may affect users with multiple tabs (6 connections per browser on HTTP/1, 100 on HTTP/2)

## Requirements

### Server-Side

- Add an SSE endpoint (`/query_sse`) using FastAPI's `EventSourceResponse`.
- Modify existing LLM query logic to yield response chunks as they become available.
- Standardize event structure (`message`, `done`, `error`) for client-side handling.
- Implement robust error handling to gracefully manage exceptions.

### Client-Side

- Initiate SSE connection using browser's `EventSource` API.
- Handle incoming events (`message`, `done`, `error`) and progressively render partial responses.
- Manage connection lifecycle, including error handling and reconnection logic.
- Maintain existing non-streaming request mechanism as fallback.

### Proposed Framework

```
┌─────────────┐           ┌─────────────┐           ┌─────────────┐
│             │           │             │           │             │
│   Client    │ SSE Conn. │   Server    │ Streaming │    LLM      │
│  Browser/   │◄──────────┤  FastAPI    │◄──────────┤  Service    │
│   App       │           │  Endpoint   │           │ (LiteLLM)   │
│             │           │             │           │             │
└─────────────┘           └─────────────┘           └─────────────┘
       │                         │                         │
       │  1. Establish SSE       │                         │
       │     (GET /query_sse)    │                         │
       │─────────────────────────►                         │
       │                         │  2. Call LLM service    │
       │                         │     (stream=True)       │
       │                         │────────────────────────►│
       │                         │                         │
       │                         │  3. Receive LLM chunks  │
       │                         │◄────────────────────────│
       │                         │                         │
       │  4. Receive SSE events  │                         │
       │     ('message', 'done') │                         │
       │◄─────────────────────────                         │
       │                         │                         │
```

### Reconnection Flow using "Last-Event-ID" for Interupted Connections

```
┌─────────────┐           ┌─────────────┐           ┌──────────────┐
│             │           │             │           │              │
│   Client    │           │   Server    │           │  Event       │
│  Browser    │           │  FastAPI    │           │  Buffer      │
│             │           │             │           │              │
└─────────────┘           └─────────────┘           └──────────────┘
       │                         │                         │
       │  1. Initial SSE Connect │                         │
       │─────────────────────────►                         │
       │                         │                         │
       │  2. Events (id: 1,2,3)  │                         │
       │◄─────────────────────────                         │
       │                         │  3. Store Events        │
       │                         │────────────────────────►│
       │                         │                         │
       │                         │                         │
       │    X CONNECTION LOST X  │                         │
       │                         │                         │
       │  4. Reconnect with      │                         │
       │     Last-Event-ID: 3    │                         │
       │─────────────────────────►                         │
       │                         │  5. Retrieve events     │
       │                         │     after id 3          │
       │                         │◄────────────────────────│
       │                         │                         │
       │  6. Resume with events  │                         │
       │     (id: 4,5,6...)      │                         │
       │◄─────────────────────────                         │
       │                         │                         │
```

In step 5, we can use an in-memory buffer to store recent event chunks for each active session. When a client reconnects with a Last-Event-ID header, server checks the buffer to retrieve all events that occurred after the specified ID. This allows the client to resume from where it left off without missing events.

#### Implementation Example

**Client-side with EventSource:**
```javascript
// Each browser tab creates its own unique connection
const eventSource = new EventSource('/query_sse?session_id=<unique_session_id>');

eventSource.onmessage = (event) => {
  // process incoming chunks as they arrive
  appendToResponse(event.data);
};

eventSource.onerror = (error) => {
  console.log('Connection error, browser reconnects');
};
```

**Server-side with EventSourceResponse:**
```python
# One dictionary entry per chat session (session_id; eg a user has multiple tabs open)
event_buffers = {}  # session_id -> list of (event_id, data) tuples

@app.get('/query_sse')
async def query_sse_endpoint(request):
    session_id = request.session_id
    last_event_id = request.headers.get("Last-Event-ID")
    
    # create event source response
    async def event_generator():
        # Send missed events
        if last_event_id and session_id in event_buffers:
            for event_id, data in event_buffers[session_id]:
                if int(event_id) > int(last_event_id):
                    yield f"id: {event_id}\ndata: {data}\n\n"
        
        # initialize if needed
        if session_id not in event_buffers:
            event_buffers[session_id] = []
        
        # stream new chunks from LLM
        current_id = len(event_buffers[session_id])
        async for chunk in llm_streaming_response():
            # store in buffer for potential reconnection
            event_buffers[session_id].append((current_id, chunk))
            
            # send to client
            yield f"id: {current_id}\ndata: {chunk}\n\n"
            current_id += 1
    
    return EventSourceResponse(event_generator())
```

## Considerations

### Handling Temporary Internet Issues

- Use SSE's `Last-Event-ID` header for reconnection handling, allowing clients to resume from where they left off during a temporary disconnection
- Server should buffer recent events for each session to support reconnection, ensuring no loss of information during brief connectivity issues
- Client should implement robust reconnection logic with appropriate backoff strategies

### Citations Returned in Streaming Responses

- Stream raw text with citation placeholders (e.g., `(citation-XXX)`) via `message` events
- Send complete citation data in a final `done` event after the full response is generated
- Client-side processing will replace citation placeholders with properly formatted references using the citation data
- This approach maintains fast streaming of text content while preserving the citation functionality

### Server-Side State Management for Multiple Instances

If we were to deploy across multiple server instances, we need a way to maintai the event buffer required for reconnection. We have two primary approaches:

#### Sticky Sessions

- Configure load balancer (NGINX, AWS ELB, etc.) to route client to same server instance for entire session
- We can use `ip_hash` or cookies for sessions
- Allows us to use the in-memory event buffers with no cross-instance tracking/coordination
- Drawback: If a server instance fails or is updated, the client loses event history

#### Shared Storage (e.g. with Redis)

- Shared memory store for event buffers
- Server instances all connect to same Redis instance/cluster
- Client side can reconnect to server instance and still retrieve missed events
- Requires setting up Redis instance

Start with sticky sessions for development and testing, then implementing Redis approach 

### Other Considerations

- Support client-initiated cancellation of in-progress streams

## Links

- [Ensuring Reliable Streaming with Server-Sent Events](https://ithy.com/article/sse-streaming-retries-v0p7rdp1)

Jira Tickets:
  - [Spike: investigate options for supporting intermittent connections](https://navalabs.atlassian.net/browse/DST-842)
  - [Enable streaming responses](https://navalabs.atlassian.net/browse/DST-846)
