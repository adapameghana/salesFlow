# WhatsApp connector (to be added after approval)

The order system never talks to WhatsApp directly. A connector receives events from the approved
provider and posts each message to the local API:

```
POST /api/messages/import
{
  "source": "whatsapp",
  "external_message_id": "<provider message id>",   // used for duplicate protection
  "sender_reference": "<phone / wa id>",
  "sender_name": "<profile name>",
  "message_text": "<text>",
  "use_ai": false
}
```

Implement `backend/app/connectors/base.py::MessageConnector.to_inbound()` for the chosen provider.
The order core, routing and dashboard need no changes.

Before you build it, decide the following (project document §6 and §19):
- Which integration to use. The recommended route is an approved WhatsApp Business integration. Unofficial WhatsApp Web automation is not recommended for production.
- Live messages need internet connectivity and a way for the provider to reach the connector (for example a webhook).
- Outbound replies stay disabled until message templates, customer consent and business rules are approved.
