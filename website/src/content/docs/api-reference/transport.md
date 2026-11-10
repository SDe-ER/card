---
title: Transport API
description: Endpoints for a machine's current location and the financial decision of a transport whose cost the customer or the equipment supplier bears.
sidebar:
  order: 5
---

## Overview

Equipment moves are **Equipment Transport** records, read and written with the standard resource API
(`/api/resource/Equipment Transport`); the transport's validation resolves the responsibility, the payer, the cost
bearer, the cost project and the amounts on every save. The endpoints below show where a machine is now and let an
Accounts Manager record the financial decision of a submitted transport.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `card.card.doctype.equipment_transport.equipment_transport.get_equipment_location` | Current place of one machine. |
| GET | `card.card.doctype.equipment_transport.equipment_transport.billing_customer` | Suggested billing project and customer for a decision. |
| POST | `card.card.doctype.equipment_transport.equipment_transport.record_financial_decision` | Record the financial decision of a submitted transport. |

## get_equipment_location

`GET /api/method/card.card.doctype.equipment_transport.equipment_transport.get_equipment_location`

Where the machine is now: on the project of its open assignment; otherwise wherever its last approved transport sent it
(workshop, storage, supplier); otherwise in storage at the company's initial place set in Card Settings.

**Permission:** read on the equipment.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `equipment` | string | Yes | Card Equipment name. |

**Returns:** `{"type": "Project"|"Workshop"|"Storage"|"Supplier", "project": "<project or null>", "location": "<place or
null>"}`; the initial place adds `"initial": 1`.

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.equipment_transport.equipment_transport.get_equipment_location" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "equipment=EQ-0001"
```

## billing_customer

`GET /api/method/card.card.doctype.equipment_transport.equipment_transport.billing_customer`

The billing project suggested for a transport's decision (its destination project, when that project names a customer),
or the customer of the project the accountant picks. Read only; the accountant confirms both before recording.

**Permission:** Accounts Manager role and read on the transport.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `transport` | string | Yes | Equipment Transport name. |
| `project` | string | No | Project to check; defaults to the destination project. |

**Returns:** `{"project": "<project>", "customer": "<customer>"}`, or `{}` when the project belongs to another company,
is cancelled or names no customer.

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.equipment_transport.equipment_transport.billing_customer" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "transport=<transport-name>"
```

## record_financial_decision

`POST /api/method/card.card.doctype.equipment_transport.equipment_transport.record_financial_decision`

An Accounts Manager records the financial decision of a submitted transport whose cost the customer or the equipment
supplier bears and whose financial status is **Pending**. The decision is only recorded: customer billing, supplier
recovery and absorption postings stay disabled until the accountant and the tax adviser decide.

**Permission:** Accounts Manager role, read on the transport, the transport's company permitted. **Separation of
duties:** the user may not be the creator, an editor or the submitter of the transport, nor of any transport it
amends.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `transport` | string | Yes | Submitted Equipment Transport with a pending decision. |
| `decision` | string | Yes | Customer cost bearer: `Bill customer`, `Company absorbs` or `Return for correction`. Equipment Supplier cost bearer: `Recover from equipment supplier` or `Return for correction`. |
| `customer` | string | For billing | Active customer to bill; defaults to the billing project's customer; the user must read it. |
| `billing_project` | string | For billing | Project of the transport's company (not cancelled). |
| `billing_amount` | float | For billing | Agreed amount, more than zero. |
| `billing_mode` | string | No | `Monthly invoice` (default) or `Separate invoice`. |
| `billing_reference` | string | For billing | Authorization reference (contract, order or approval). |
| `billing_document` | string | No | A private File attached to this transport (JPEG, PNG, WebP or PDF). |
| `confirmed` | int | For billing | `1`: the accountant confirmed the customer and the billing project. |
| `absorption_reason` | string | For absorption | Why the company absorbs the cost. |
| `recovery_mode` | string | No | `Deduct from monthly dues` (default) or `Adjustment document`. |
| `recovery_amount` | float | For recovery | Amount recovered, more than zero. |
| `note` | string | For rejection | Required with `Return for correction`; optional otherwise. |

**Returns:** `{"financial_status": "Approved"|"Rejected", "financial_decision": "<decision>"}`.

**Side effects:** writes the decision fields, the approver and the time on the submitted transport, adds a Version
recording the status change and a comment "Financial decision recorded." Two simultaneous decisions are serialised by a
row lock. A rejected transport is then cancelled and amended.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.doctype.equipment_transport.equipment_transport.record_financial_decision" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"transport": "<transport-name>", "decision": "Bill customer", "billing_project": "PROJ-0001", "billing_amount": 1000, "billing_reference": "PO-0001", "confirmed": 1}'
```

## Related

- [Transport](/card/features/transport/)
- [Assignments and locations](/card/features/assignments-locations/)
- [Transport and cost reports](/card/reports/transport-costs/)
