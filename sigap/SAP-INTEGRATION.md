# SAP integration

> How this system actually talks to SAP: where it points, every service it
> reads, every join it has to make, what refuses, and what changes when you
> move it to a real tenant.
>
> `DATA-SOURCES.md` says where data could come from. This says how the code
> gets it. Written 15 October 2026.

---

## Where it points right now

```
SAP_BASE_URL  https://sandbox.api.sap.com      (measured, not assumed)
is_mock_sap() True
```

**This is SAP's public demonstration sandbox, not a company's system.** It is a
real S/4HANA Cloud behind a gateway, so the entity shapes, the pagination
fields, the date format and the error bodies are identical to a customer
tenant. The *data* in it is SAP's sample data: somebody else's materials,
somebody else's suppliers.

That distinction is load-bearing, not pedantry, and it decides what the system
believes. `tools/fetcher.pull()` reads in this order:

```
host is a mock AND an upload exists   -> the upload          CACHED
SAP reachable                         -> SAP                 LIVE
an upload exists                      -> the upload          CACHED
                                      -> the fixture         MODELLED
```

A company's own uploaded file **outranks the sandbox**, because a demonstration
dataset carrying other people's materials is less authoritative than the
company's own records, just less fresh. A genuine tenant outranks the upload.
That is why the test is on the base URL rather than on a flag: swap the host
for a real one and the precedence inverts by itself.

### The three hosts this can be

| Host | What it is | `is_mock_sap()` |
|---|---|---|
| `sandbox.api.sap.com` | SAP's public sample tenant. Where it points today | **true** |
| `my######.s4hana.ondemand.com` | a real S/4HANA Cloud tenant | false |
| your BTP destination | a tenant reached through a BTP destination service | false |

**The hackathon BTP tenant is not one of these.** `SEAIO_aws-sap-hackathon-si4ykj9d`
carries AI Core, Joule and a Cloud Foundry runtime. It has **no ERP**, so there
is nothing in it to read master data from or write a purchase requisition to.
That is why the integration points at the sandbox and not at the tenant the
competition gave us.

## The client

`clients/sap_s4.py`, about 150 lines of `urllib`. No SDK, and that is a
deliberate choice: the OData calls are simple and a dependency that wraps them
would be a dependency to audit.

| | |
|---|---|
| Auth | header `APIKey: <SAP_API_KEY>`. No OAuth on the sandbox |
| URL | `{base_url}{odata_prefix()}/{service}/{entity}?$format=json` |
| Timeout | `SAP_TIMEOUT`, default 30 seconds |
| Response | gzip handled; both OData v2 (`d.results`) and v4 (`value`) unwrapped |
| Writes | CSRF token fetched first, cookie carried, `Idempotency-Key` sent |

### The OData path is derived, not hardcoded

The sandbox fronts its tenant and puts `/s4hanacloud` in front of every
service. A real tenant serves them at its own root. That prefix used to be
written into three f-strings, so `SAP_BASE_URL` looked like it could be pointed
anywhere and could not:

```python
odata_prefix()
  sandbox.api.sap.com        -> /s4hanacloud/sap/opu/odata/sap
  my123456.s4hana.ondemand.com -> /sap/opu/odata/sap
  SAP_ODATA_PREFIX set        -> whatever you set
```

Set `SAP_ODATA_PREFIX` when a gateway in front of the tenant uses neither shape.

## What it reads

Seven entities, in `fetcher.ENTITIES`. Four need more than one call.

| Entity | Service | OData entity | Joined |
|---|---|---|---|
| MaterialStock | `API_MATERIAL_STOCK_SRV` | `A_MatlStkInAcctMod` | |
| PurchaseOrder | `API_PURCHASEORDER_PROCESS_SRV` | `A_PurchaseOrder` | **yes** |
| BillOfMaterial | `API_BILL_OF_MATERIAL_SRV` | `A_BillOfMaterial` | **yes** |
| SalesOrder | `API_SALES_ORDER_SRV` | `A_SalesOrder` | **yes** |
| AlternateSource | `API_PURCHASING_INFO_RECORD_SRV` | `A_PurchasingInfoRecord` | **derived** |
| Supplier | `API_BUSINESS_PARTNER` | `A_Supplier` | |
| Quotation | `API_QTN_PROCESS_SRV` | `A_SupplierQuotation` | |

### Why the joins exist, and the bug that taught us

A purchase order lives across **three** entities and a bill of materials across
**two**. The header carries the supplier, the item carries the material and the
quantity, the schedule line carries the delivery date.

Reading the header alone returns a row with no material on it, which produced
`KeyError: 'Material'` the first time the system ran against live SAP. The fix
was not a guard around the KeyError. It was realising the read was one entity
level too high, and joining in `fetcher.JOINS` so every engine downstream gets
the single flat row it has always expected.

Specific things the joins have to get right:

- Schedule lines key on `PurchasingDocument` and `PurchasingDocumentItem`,
  **not** `PurchaseOrder`. Same value, different field name on that entity.
- `PurchaseOrderDate` lives on the header and the joined row dropped it, so
  every lead time in the system had to be assumed rather than measured. It is
  carried now, and that is what makes a reorder point real.
- Sales order items carry `RequestedQuantity`, and leaving it out meant nothing
  could work out how much of a scarce component one customer order consumes.
- `LoadingPort` **has no SAP equivalent.** The port a shipment loads at is not
  on the purchase order, so lane concentration cannot be answered from live
  data and the field stays absent rather than being invented.

### Dates

OData V2 returns `/Date(1629936000000)/`, milliseconds since the epoch.
`fetcher.sap_date()` converts it to ISO. A value it does not recognise comes
back as `None` rather than a guess: a date nobody can read is better absent
than silently wrong, and every caller already treats a missing date as missing.

### `$select` is not an optimisation here

`A_BillOfMaterialItem` emits malformed JSON on the sandbox:

```
"FixedQuantity":,
```

That is not parseable, and the fix is not a tolerant parser. Naming the fields
with `$select` keeps the broken one out of the response entirely.

### There is no pagination

Reads are capped by `$top` and nothing follows `__next`. On the sandbox that is
invisible: the sample data is small. **On a real tenant with 50,000 purchase
orders, a read returns the first 1,000 and the system will believe that is all
of them.** This is the single most important thing to fix before pointing it at
a production system.

## What refuses

### A read that is not authorised

`API_PURCHASING_INFO_RECORD_SRV` answers 403 on the sandbox key, so the
approved-source list cannot be read. Rather than leaving the feature broken,
alternate sources are **earned from evidence**: a supplier who has delivered
this material before is an alternate source by its own purchase order history,
and that order carries what it charged and how long it took.

What is not derivable stays absent. TKDN is an Indonesian regulatory
calculation that no SAP field holds, so `TkdnAfterPct` is `None` on a derived
source and Kira rules knowing that, instead of ruling on a number invented in
the fetcher.

### Writes

`sender.py` holds three targets. The agents propose, a person approves, this
file sends, and it runs on a schedule rather than inside the agent loop.

| Action | Service | Entity | Status |
|---|---|---|---|
| draft_po | `API_PURCHASEREQ_PROCESS_SRV` | `A_PurchaseRequisitionHeader` | path complete |
| stock_transfer | `API_STOCK_TRANSFER_SRV` | `A_StockTransfer` | **403** |
| create_sourcing_event | `API_SOURCING_PROJECT_SRV` | `A_SourcingProject` | **403** |

The two 403s are permanent for this competition: the sandbox key is not
authorised to post them, and the BTP tenant has no ERP to post them to. So the
operating loop is complete through proposal, approval and recorded outcome, and
the write to SAP is proven against a mock rather than against a production ERP.
**Say that in the demo.** A judge who finds it alone has found a hidden
limitation; a judge who is told has been given a scoped claim.

### The rate limit, which is live right now

```
HTTP 500  {"fault":{"faultstring":"Rate limit quota violation. Quota limit exceeded.
           Identifier : <REDACTED>",
           "detail":{"errorcode":"policies.ratelimit.QuotaViolation"}}}
```

The quota is **per API key**, enforced at SAP's gateway, and it is exhausted as
of 15 October 2026. Every service, read and write, answers this. A fresh key
resets it.

Note the shape: the gateway returns **500**, not 429, with the real reason in
the body. Anything matching on the status code alone will read a quota as a
server fault.

**What the system does about it.** A failed live read falls through to the
upload and then the fixture, carrying the reason:

```
origin: modelled
note:   SAP could not be read, so this is not live. SapError: HTTP 500 ...
        Rate limit quota violation
```

The origin can never become LIVE and the figure stays untrusted, so the
calculator still refuses to price it. The screen stays populated and labelled
rather than going blank. Before this, no key at all left the application
working and a *rate-limited* key emptied it, which is the same inability to
read producing two different behaviours.

## Moving to a real tenant

1. `SAP_BASE_URL` to the tenant host. `odata_prefix()` follows by itself.
2. Replace the API key with that tenant's auth. Communication arrangement and
   OAuth on S/4HANA Cloud, not an `APIKey` header, so `sap_s4.get()` needs its
   auth header changed and a token refresh adding.
3. **Add pagination**, see above. This is the one that silently returns wrong
   answers rather than failing.
4. Re-check the entity names. Private Cloud and on-premise expose different
   services from Public Cloud.
5. Expect `is_mock_sap()` to turn false, which inverts upload precedence: the
   tenant then outranks uploaded files. That is intended.
6. Re-run the probe below and update the status table here.

## What is not in SAP at all

No amount of integration will produce these, and the system is built so they
come from somewhere nameable instead:

| Not in SAP | Where it comes from |
|---|---|
| TKDN local-content position | `references/tkdn-rules.md` + the installation profile |
| LARTAS licensing time | `references/lartas-procedure.md` |
| National holidays | `references/holiday-calendar.md` |
| Port dwell time | `references/priok-dwell-time.md` |
| USD to IDR | `references/fx-rate.md`, with its date |
| Service level, reorder policy targets | `references/operating-targets.md` |
| Loading port per shipment | nowhere. Stated as unanswerable |
| Late-delivery penalty clauses | the sales order in our fixture; a real order carries the clause in the contract, not the document, so a written default is used and reported |
| Daily withdrawal history | `fixtures/consumption_history.json`, or an uploaded `ConsumptionHistory` |

## Re-measuring the status table

Run this when the key changes. It separates a 403 from a quota error, which
matters because both arrive as a 5xx-looking failure:

```bash
cd sigap/agent && PYTHONPATH=. python3 - <<'EOF'
from clients import sap_s4
from tools.fetcher import ENTITIES
from sender import TARGETS
for name, (svc, ent) in list(ENTITIES.items()) + [(f"WRITE {k}", v) for k, v in TARGETS.items()]:
    try:
        print("%-22s OK   %d" % (name, len(sap_s4.rows(sap_s4.get(svc, ent, {"$top": "1"})))))
    except Exception as e:
        m = str(e)
        print("%-22s %-5s %s" % (name, "403" if "403" in m else
              "quota" if "Quota" in m else "?", m[:90]))
EOF
```

**Not yet done:** pagination, OAuth for a real tenant, and a re-measured status
table once the quota resets. The 403s on the two write targets were measured
when the quota was available; they cannot be re-confirmed until it is.
