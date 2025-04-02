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
* Reliabile connection to the chatbot
* Implementation effort for both Nava and third-party clients
* Maintainability

## Considered Options

### Polling

- Handles intermittent connectivity through retry logic
- Introduces latency dependent on polling intervals  
- Requires writing logic for managing accumulated response chunks and state.

### Server-Sent Events (SSE)

- Immediate/event-driven updates provide a responsive user experience
- Built-in browser support simplifies client-side implementation 
- Straightforward server-side implementation

### WebSockets

- Supports two-way real-time communication
- Flexible for interactive applications
- More complex to implement and manage.  

## Decision Outcome

We chose Server-Sent Events (SSE) because it provides an event-driven approach to streaming responses with relatively low implementation complexity. SSE allows the server to push partial responses to the client as they become available, providing visual feedback that is engaging to users.

Polling achieves similar UX results with periodic fetching accumulated response chunks from the server. But this approach introduces latency dependent on polling intervals and requires additional logic to manage state and retries. While LiteLLM supports asynchronous streaming, polling would require managing accumulated chunks and intervals.

WebSockets offer two-way communication, good for real-time interactive applications. But WebSockets introduce more components to maintain for our current use case, requiring explicit connection management and reconnection handling.

### Positive Consequences

* Real-time streaming of partial responses increases user engagement
* Users get immediate feedback that the system is working, rather than waiting for a complete response
* LiteLLM and FastAPI have existing support for streaming
* Low implementation effort

### Negative Consequences

- Requires client-side updates to support SSE connections (same for other all options).
- SSE connections are limited to one-way communication (server-to-client only).

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

### Other Considerations

- Support client-initiated cancellation of in-progress streams
- Implement server-side state management for active SSE connections

## Links

Jira Tickets:
  - [Spike: investigate options for supporting intermittent connections](https://navalabs.atlassian.net/browse/DST-842)
  - [Enable streaming responses](https://navalabs.atlassian.net/browse/DST-846)
