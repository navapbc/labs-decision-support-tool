# API Specification: Assistive Chatbot Integration
This API enables the integration of an Assistive Chatbot with other products.

## Endpoint: `POST /chatbot`

### Description
This endpoint accepts a query from a navigator and responds with a generated answer from the chatbot, along with relevant citations. Each response includes tracking fields to monitor usage by user, organization, and customer.

---

### Request Parameters

**Headers**

- **Authorization**: Bearer token for authenticating API access.

**Parameters**

- **user_id** _(string, required)_: Unique identifier for the navigator within SBN.  
- **org_id** _(string, optional)_: Identifier for the organization the navigator belongs to. 
- **customer_id / beneficiary_id** _(string, optional)_: Anonymized ID for the customer or beneficiary associated with the query, if applicable and distinct from `user_id`.
- **session_id** _(string, optional)_: Unique identifier for the current session, which may represent the user’s duration of activity rather than a specific conversation.

- **query** _(JSON, required)_: User’s question for the chatbot and any prior messages
```json
[
  {
    "role": "string",       // Author of message, one of "user", "assistant", or "system"
    "content": "string"     // Message contents
  },
  ...
]
```
---

### Responses

#### Success Response (200 OK)

**Body**

```json
{
  "response_id": "string",                   // Unique identifier for the chatbot response
  "response_text": "string",                 // Generated answer from the chatbot in Markdown format
  "citations": [                             // Ordered list of citations with mappings to the Markdown response text
    {
      "citation_id": "string",               // Unique ID for each citation
      "source_id": "string",                 // Identifier for the source document
      "source_name": "string",               // Name of the source document
      "page_number": "integer",              // Page number where the citation is found, if available
      "uri": "string",                       // URL link to the source, if available
      "headings": ["string"],                // Headings within the document, if available
      "citation_text": "string"              // Extracted citation text
    }
  ]
}
```

#### Client Error Responses (4xx)

- **400 Bad Request**: Missing or invalid parameters.

#### Server Error Responses (5xx)

- **500 Internal Server Error**: Generic server error.
  


