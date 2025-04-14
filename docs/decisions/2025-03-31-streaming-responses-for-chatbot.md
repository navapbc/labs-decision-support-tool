# Implementing Streaming Responses for Chatbot

- Status: proposed
- Deciders: Kevin Boyer, Yoom Lam
- Date: 2025-04-14

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
- Built-in reconnection handling through the Last-Event-ID header (note: this is only useful for network blips but not for disconnections where the user refreshes the page)
- Supported by all major browsers (Chrome, Firefox, Safari, Edge, Opera), with the exception of Internet Explorer ([1](https://sii.pl/blog/en/server-side-events-implementation-and-highlights/), [2](https://www.lambdatest.com/web-technologies/eventsource))
- When used over HTTP/2, supports up to 100 simultaneous connections by default; over HTTP/1, limited to 6 connections per browser, which could impact multi-tab usage

### WebSockets

- Two-way real-time communication
- Flexible for interactive applications
- Implementation:
  - Setting up WebSocket routes and managing WebSocket connections in application code
  - Handle WebSocket-specific exception cases not present in HTTP endpoints
  - Reconnection logic (needs a resumption call like `socket.resume()` with a tracked last event id)
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

WebSockets offer two-way communication, which is beneficial for real-time interactive applications like chat apps. FastAPI does also provide WebSocket support. Worth noting:
1. Reconnection logic, as WebSockets don't have a built-in Last-Event-ID equivalent
2. Browser framework handles [upgrade mechanism](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Protocol_upgrade_mechanism) to switch from HTTP to WS protocol
2. Session state tracking to manage where to resume after disconnections
3. Client-side code to manage connection states and handle reconnection

In contrast, SSE uses standard HTTP connections
1. Built-in reconnections with Last-Event-ID header
2. EventSource API in browsers manages connection states and reconnection
3. You can use server implementation with FastAPI EventSourceResponse that handles SSE-specific formatting

While both approaches could be implemented using FastAPI, SSE reconnection handling and client-side implementation with EventSource make it suitable for a one-way streaming use case.

## Requirements

### Server-Side
- Add a POST endpoint (`/query_init`) to save the question and generate a message_id
- Add a GET endpoint (`/query_stream?id=`) to start the LLM request and stream the response chunks
- Standardize event structure (`message`, `done`, `error`) for client-side handling
- Async functions to store and retrieve question and full response from database
- Optional: manage connection lifecycle, including error handling and reconnection logic

### Client-Side
- submitQuestion function to submit the question and initiate the SSE connection
- handleSSEConnection function for SSE connection lifecycle (opening, closing, errors)
- Client handles incoming events (`message`, `done`, `error`) and progressively renders partial responses

### Proposed Framework

```
Client (Browser)                Server                   LLM Service
    |                             |                          |
    |-- 1. HTTP POST /query_init->|                          |
    |   (question payload)        |                          |
    |                             |--- 2. Save question ---->|
    |                             |   & generate message_id  |
    |                             |                          |
    |<-- 3. Returns message_id ---|                          |
    |   (200 OK, JSON response)   |                          |
    |                             |                          |
    |-- 4. GET /query_stream?id= >|                          |
    |   (with message_id)         |                          |
    |                             |--- 5. Start LLM request->|
    |                             |                          |
    |<-- 7. Opens SSE connection -|<-- 6. Start streaming ---|
    |   (200 OK,                  |                          |
    |    text/event-stream)       |                          |
    |                             |                          |
    |<-- 8. event: chunk ---------|<-- streaming chunks -----|
    |    data: partial_response   |                          |
    |                             |                          |
    |<-- 9. event: chunk ---------|<-- streaming chunks -----|
    |    data: partial_response   |                          |
    |                             |                          |
    |<-- 10. event: chunk --------|<-- streaming chunks -----|
    |    data: partial_response   |                          |
    |                             |                          |
    |<-- 11. event: done ---------|<-- completion signal ----|
    |    data: final_chunk        |                          |
    |                             |                          |
    |                             |-- 12. Save complete -----|
    |                             |    response to database  |
    |                             |                          |
    |--- 13. Connection closed -->|                          |
    |   (client closes after      |                          |
    |    complete response)       |                          |
```

### Reconnection Flow using "Last-Event-ID" for Interupted Connections (Optional)

```
Client (Browser)                Server                   LLM Service
    |                             |                          |
    |-- 1. HTTP POST /query_init->|                          |
    |   (question payload)        |                          |
    |                             |--- 2. Save question ---->|
    |                             |   & generate message_id  |
    |                             |                          |
    |<-- 3. Returns message_id ---|                          |
    |   (200 OK, JSON response)   |                          |
    |                             |                          |
    |-- 4. GET /query_stream?id= >|                          |
    |   (with message_id)         |                          |
    |                             |--- 5. Start LLM request->|
    |                             |                          |
    |<-- 7. Opens SSE connection -|<-- 6. Start streaming ---|
    |   (200 OK,                  |                          |
    |    text/event-stream)       |                          |
    |                             |                          |
    |<-- 8. event: chunk (id: 1) -|<-- streaming chunks -----|
    |    data: partial_response   |                          |
    |                             |                          |
    |<-- 9. event: chunk (id: 2) -|<-- streaming chunks -----|
    |    data: partial_response   |                          |
    |                             |                          |
    X---- CONNECTION LOST --------X                          |
    |                             |<-- Buffers events -------|
    |                             |    (id: 3, 4...)         |
    |                             |                          |
    |-- 10. Reconnect SSE ------->|                          |
    |   (with Last-Event-ID: 2    |                          |
    |    to /query_stream?id=...) |                          |
    |                             |                          |
    |<-- 11. Resume from id: 3 ---|<-- continues streaming --|
    |    data: missed_chunks      |                          |
    |                             |                          |
    |<-- 12. event: chunk (id: 5)-|<-- streaming chunks -----|
    |    data: more_content       |                          |
    |                             |                          |
    |<-- 13. event: done ---------|<-- completion signal ----|
    |     data: final_chunk       |                          |
    |                             |                          |
    |                             |-- 14. Save complete -----|
    |                             |    response to database  |
    |                             |                          |
    |--- 15. Connection closed -->|                          |
    |    (client closes after     |                          |
    |     "done" message)         |                          |
```

We can use an in-memory buffer to store recent event chunks for each active message. When a client reconnects with a Last-Event-ID header, server checks the buffer to retrieve all events that occurred after the specified ID. This allows the client to resume from where it left off without missing events.

#### Implementation Example

**Client-side with EventSource:**
```javascript
// Client submits the question via POST request
async function submitQuestion(question) {
  
  try {
    // POST the question to the server
    const response = await fetch('/query_init', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: question })
    });
    
    const data = await response.json();
    
    // Client opens the SSE connection to receive streaming response
    if (data.status === 'processing') {
      handleSSEConnection(data.message_id);
    }
  } catch (error) {
    console.error('Error submitting question:', error);
  }
}

// Client establishes the SSE connection
function handleSSEConnection(messageId) {
  
  // Create SSE connection
  const eventSource = new EventSource(`/query_stream?id=${messageId}`);
  
  eventSource.onmessage = (event) => {
    // Process and append chunk to the response area
    appendToResponse(event.data);
  };
  
  eventSource.addEventListener('done', (event) => {
    // Process final chunk if needed
    appendToResponse(event.data);
    eventSource.close();
  });
  
  // Handle errors
  eventSource.onerror = (error) => {
    console.error('SSE connection error:', error);
    eventSource.close();
  };
}
```

**Server-side with EventSourceResponse:**
```python
@router.post("/query_init")
async def query_init_endpoint(request: Request):
    data = await request.json()
    question = data.get("question")
    
    request_step = chainlit.Message(
        content=question,
        type="user_message",
        metadata={...}
    ).to_dict()

    message_id = request_step.get("id")

    # Async function to store the question in the database
    await store_question(message_id, question)

    return {"status": "processing", "message_id": message_id}

@router.get("/query_stream")
async def query_stream_endpoint(request: Request, id: str):
    # SSE connection is opened by the browser when the client makes the GET request

    # Async function to get the question from the database
    question = await get_question(id)

    async def event_generator():
        # Stream chunks from LLM
        async for chunk in llm_streaming_response(question):
            full_response += chunk.text
            if chunk.is_final:
                # Async function to save the final response to the database
                await save_response(id, full_response)

                # Send final chunk with "done" event type
                yield {
                    "event": "done",
                    "data": chunk.text
                }
            else:
                # Send partial response chunk
                yield {
                    "data": chunk.text
                }
    
    return EventSourceResponse(event_generator())

async def llm_streaming_response():
    #  LiteLLM client.completion(..., stream=True)
```

## Considerations

### Citations Returned in Streaming Responses

- Stream raw text with citation placeholders (e.g., `(citation-XXX)`) via `message` events
- Send complete citation data in a final `done` event after the full response is generated
- Client-side processing will replace citation placeholders with properly formatted references using the citation data
- This approach maintains fast streaming of text content while preserving the citation functionality

### Handling Temporary Internet Issues (We'll treat this separately from streaming implementation)

- Use SSE's `Last-Event-ID` header for reconnection handling, allowing clients to resume from where they left off during a temporary disconnection (like a network blip, but not for disconnections where the user refreshes the page)
- Server should buffer recent events for each session to support reconnection, ensuring no loss of information during brief connectivity issues

### Server-Side State Management for Multiple Instances (Out of scope for MVP)

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
