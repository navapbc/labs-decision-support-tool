# API Specification: Assistive Chatbot Integration
This API enables the integration of an Assistive Chatbot with other products.

## Endpoint: `POST /chatbot`

### Description
This endpoint accepts a query from a navigator and responds with a generated answer from the chatbot, along with relevant citations. Each response includes auditing fields to monitor usage by user, organization, and customer.

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
    },
    ...
  ]
}
```

#### Client Error Responses (4xx)

- **400 Bad Request**: Missing or invalid parameters.

#### Server Error Responses (5xx)

- **500 Internal Server Error**: Generic server error.
  
### Example

#### Example request

```json
{
  "user_id": "nav12345",
  "org_id": "org789",
  "customer_id": "cust001",
  "session_id": "sess2024A",
  "query": [
    {
      "role": "user",
      "content": "What benefits are available for single mothers in California?"
    },
    {
      "role": "assistant",
      "content": "There are several programs, including CalWORKs, Medi-Cal, and more. What specific support are you interested in?"
    },
    {
      "role": "user",
      "content": "I’m looking for financial aid specifically."
    }
  ]
}
```

#### Example response

```json
{
  "response_id": "resp6789",
  "response_text": "Here are some financial aid options for single mothers in California:\n\n- **CalWORKs**: This program provides cash aid to families with children.(citation-1)\n- **CalFresh**: A food assistance program for low-income individuals.(citation-2)\n\nFor more details, visit [CalWORKs Program](https://www.cdss.ca.gov/calworks)."
  "citations": [
    {
      "citation_id": "citation-1",
      "source_id": "doc543",
      "source_name": "California Department of Social Services - CalWORKs",
      "uri": "https://www.cdss.ca.gov/calworks",
      "headings": ["Calworks", "CalWORKs Overview"],
      "citation_text": "CalWORKs provides cash aid to families with children in California."
    },
    {
      "citation_id": "citation-2",
      "source_id": "doc1313",
      "source_name": "CalFresh",
      "uri": "https://www.getcalfresh.org/",
      "headings": ["CalFresh"],
      "citation_text": "If you already get CalFresh benefits, you can request replacement benefits for food you lost. If you don't already get CalFresh, learn more about Disaster CalFresh here."
    }
  ]
}
```

# For discussion

## Questions (Nava)
 - Do we need the security key? What are the risks to leaving the API open?
 - What kind of user information would be helpful to track with each request?
    Some possibilities we identified include user_id, org_id, customer_id, and session_id
 - Does this endpoint schema make sense? Are there any changes we should make before implementing this as a v1? (Keeping in mind we can adapt over time as needed.)
