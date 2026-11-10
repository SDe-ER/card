---
title: Equipment
description: The Card Equipment master — identity, ownership, rental direction, rates, Asset link, status and the documents of every machine.
sidebar:
  order: 2
---

## Overview

**Card Equipment** is the master record of every machine CARD manages: owned machines, machines rented from a
supplier, machines rented out to a customer, and machines managed for another owner. Every other CARD document —
assignments, transports, monthly cards, diesel fills, equipment needs and tool custody — points to a Card Equipment
record, and the equipment's company decides the company of all of them.

The form keeps everything about one machine in one place: what it is (type, make, model, chassis and plate numbers),
who owns it and in which direction it is rented, the commercial terms used to price its monthly cards, its link to
the ERPNext **Asset**, where it is working now, its meter and maintenance data, its legal documents and how it
leaves the fleet.

<!-- screenshot: equipment-form -->

## Key concepts

| Concept | Meaning |
|---|---|
| **Ownership** (الملكية) | «ملك» (Owned), «إيجار» (Rented) or «طرف ثالث» (Third Party, managed for another owner). |
| **Rental direction** (اتجاه التأجير) | Who is billed and who bills: rented from a supplier, rented to a customer, sub-rental, or internal operation. It is the single source of truth for which commercial fields apply. |
| **Commercial fields** | Ownership, direction, supplier and customer, rates, contract and rental dates, fuel and operator terms. Only a Card Manager or System Manager may change them, and every change needs a new reason. |
| **Financial fields** | Asset purchase value, internal rates and cost centers. Readable only by System Manager, Card Manager and Accounts Manager. |
| **Identity** | Chassis number and plate number, each unique per company. |
| **Asset link** | An owned or third-party machine can be linked to one ERPNext Asset, which then supplies its name, brand and type. |
| **Status** | «نشطة» (Active), «متوقفة» (Stopped), «في الصيانة» (Under Maintenance), «منتهية» (Ended). Only Ended stops new use. |

Records are numbered `CEQ-0001`, `CEQ-0002`, … and shown by their **Equipment name**. The list can be searched by
equipment type, plate number and chassis number, and equipment can be imported and renamed.

## Features

### Form layout

The form is organised in tabs:

| Tab | Sections and main fields |
|---|---|
| **Basic details** | Company, Ownership, Rental direction, Asset in ERPNext, Reason for commercial change, Brand, Model, Equipment make, Equipment model, Manufacture year, Chassis number, Plate number, Equipment category, Equipment name, Equipment type, Status, Unit (two machines bundled), Unit components |
| **Documents** | Registration number, expiry and image; periodic inspection expiry and certificate; insurance company, policy number, expiry and file; TUV number, expiry and image |
| **Operation and assignment** | Current project, Assignment date, Cost center, Operator (or external operator name and mobile), Location |
| **Cost and rental** | Operation standards (Daily working hours, Fuel charged to, Operator charged to), Rental details (supplier side), Customer side, Internal cost |
| **Meter and maintenance** | Meter type, Meter reading at receipt, Last reading, Tank capacity, Expected consumption, Daily diesel consumption; Maintenance intervals |
| **Exit** | Exit date, Exit reason, Meter reading at exit, Settlement status, Notes |
| **Connections** | Linked documents and related records (see [Connections](#connections)) |

Sections appear only when they apply: the supplier-side **Rental details** only for a direction that bills a
supplier, the **Customer side** only for a direction that bills a customer, **Internal cost** only for owned and
third-party machines, and **Maintenance** only for owned machines.

### Categories and types

- **Card Equipment Category** — a plain list (category name, description), for example "Earthmoving" or
  "Crushing".
- **Card Equipment Type** — each type belongs to one category and may set a **Meter type** («ساعات» Hours,
  «كيلومترات» Kilometres, «بدون عداد» No Meter) and an ERPNext **Asset category**.

On the equipment, **Equipment type** is mandatory; the **Equipment category** and the **Meter type** are fetched from
the type. One Asset category can be mapped to only one equipment type, because a machine linked to an Asset takes its
type from the Asset's category.

Card User, Card Manager and System Manager may create categories and types; Accounts Manager reads them.

### Makes and models

- **Card Equipment Make** (`CMK-0001`) — the maker of a machine, with a **Disabled** flag. CARD keeps its own list;
  the ERPNext Manufacturer list is for part makers and is not used for machines.
- **Card Equipment Model** (`CEM-0001`) — a model of one make and one equipment type, with a description and a
  **Disabled** flag.

Duplicates are refused by a normalised key: names are compared in upper case without spaces, dashes, dots,
underscores or slashes, so "PC200-8" and "pc 200 8" are the same model. A model is unique per make.

Rules on the equipment:

- The model must belong to the selected make and equipment type. When the make is empty it is taken from the model.
- A disabled make or model cannot be newly selected (a machine that already has it keeps it).
- The make and type of a model already used by equipment or by parts fitment rows cannot change.
- If the equipment type changes later (for example because the linked Asset's category changed), a model that no
  longer fits is cleared with a message — only for a user who may write the model field.

The free-text **Brand** and **Model** fields stay available beside the make and model links. Makes and models are
also used by the parts catalog to decide which parts fit a machine (see
[Maintenance & Parts](/card/features/maintenance-parts/)).

### Ownership and rental direction

Ownership says who owns the machine; the rental direction says how it is billed. The allowed combinations are fixed:

| Ownership | Allowed directions | Default when empty |
|---|---|---|
| «ملك» (Owned) | «مؤجَّرة لعميل» (Rented to Customer), «تشغيل داخلي» (Internal Operation) | «تشغيل داخلي» |
| «إيجار» (Rented) | «مستأجَرة من مورد» (Rented from Supplier), «إيجار من الباطن» (Sub-rental) | «مستأجَرة من مورد» |
| «طرف ثالث» (Third Party) | «مستأجَرة من مورد» (Rented from Supplier), «إيجار من الباطن» (Sub-rental) | «مستأجَرة من مورد» |

What each direction means and requires:

| Direction | Meaning | Required on save |
|---|---|---|
| «مستأجَرة من مورد» | The company rents the machine from a supplier (supplier invoices). | Lessor / Owner, Rate type, Rate |
| «مؤجَّرة لعميل» | The company rents its own machine to a customer (customer invoices). | Customer, Customer rate type, Customer rate |
| «إيجار من الباطن» | Rented from a supplier **and** rented out to a customer. | Both of the above |
| «تشغيل داخلي» | An owned machine used internally, with no billing. | — |

A direction that does not fit the ownership is refused on the server, and a blank direction is derived from the
ownership. On the form, choosing the ownership switches the direction to an allowed one at once; for an owned
machine an empty **Operator charged to** and **Fuel charged to** are set to «الشركة» (Company).

:::note
Monthly cards mirror the direction read-only from the equipment. Customer billing applies to the directions
«مؤجَّرة لعميل» and «إيجار من الباطن»; supplier billing to «مستأجَرة من مورد» and «إيجار من الباطن».
:::

### Commercial fields and change reason

The commercial terms are: Ownership, Lessor / Owner, Rental start, Rental end, Contract number, Rate type, Rate,
Daily working hours, Day billing basis, Fuel charged to, Internal hourly rate, Internal operating rate basis,
Internal operating rate, Customer rate type, Customer rate, Customer rate (night shift), Customer, Rental direction
and Operator charged to.

- They sit at permission level 1: Card Manager and System Manager write them; Card User and Accounts Manager read
  them.
- On an existing equipment, any change to one of them needs a **new** text in **Reason for commercial change**
  (reusing the previous reason is refused). The message lists the changed fields. The check runs on the server, so it
  also covers REST and data import.
- The reason is not copied when an equipment is duplicated, and the change is kept in the document history.

### Rates

**Supplier side** (shown for «مستأجَرة من مورد» and «إيجار من الباطن»):

- **Lessor / Owner** — the supplier.
- **Rate type** — «باليوم» (Per Day), «بالساعة» (Per Hour) or «بالشهر» (Per Month).
- **Rate** — the agreed rate on that basis.
- **Hourly rate** — read-only, computed on save:

| Rate type | Hourly rate |
|---|---|
| «بالساعة» Per Hour | the rate |
| «باليوم» Per Day | rate ÷ Daily working hours (daily hours must be above zero) |
| «بالشهر» Per Month | rate ÷ **Standard month hours** from Card Settings (default 260) |

- **Contract number**, **Rental start**, **Rental end**.

**Customer side** (shown for «مؤجَّرة لعميل» and «إيجار من الباطن»): **Customer**, **Customer rate type**,
**Customer rate** and the optional **Customer rate (night shift)**. A night-shift monthly card of a customer-billing
machine uses the night rate when it is set; a day card, or a machine without a night rate, uses the customer rate.

**Daily working hours** is mandatory on every machine. **Day billing basis** appears when either side is priced per
day:

| Day billing basis | Effect on a per-day side |
|---|---|
| Prorated by hours (default) | billed hours × hourly rate (rate ÷ daily hours) |
| Full day | billed days × rate |

:::note
The day billing basis was added after v4.7.0. Submitted monthly cards keep the basis they were priced with.
:::

**Internal cost** (owned and third-party machines, permission level 2): **Internal hourly rate**, **Internal
operating rate basis** («بالساعة» or «باليوم») and **Internal operating rate**, used to show the internal value of
owned equipment.

New equipment takes defaults from Card Settings when the fields are empty: default daily hours, default fuel charged
to, default operator charged to and the default rate basis (for both the supplier and the customer rate type). A value
already entered is never overridden.

See [Rate Agreements](/card/features/rate-agreements/) and [Monthly Cards](/card/features/monthly-cards/) for how the
rates are used.

### Fuel and operator charged to

- **Fuel charged to** (الوقود على) and **Operator charged to** (المشغّل على): «المؤجر» (Lessor) or «الشركة»
  (Company).
- For an owned machine, or when the operator is on the company, the **Operator** is an ERPNext Employee and the
  **Operator name** is fetched from it.
- For a rented machine whose operator is on the lessor, the form asks instead for the external **Operator name** and
  **Operator mobile**.

### Identity: chassis and plate numbers

A **Chassis number** or **Plate number** belongs to one equipment per company.

- Numbers are compared in a normalised form: Unicode normalisation without invisible marks, Arabic-Indic digits
  read as Western digits, no spaces or `- _ / .`, upper case. "ABC-123" and "abc 123" are the same number.
- The check runs when a number is set or changed, or the company changes; an unrelated save of an older record is not
  blocked. Two saves at the same moment cannot both keep the same number.
- The message names the other equipment only to a user who may read it.
- Two companies may each have a machine with the same number.
- The numbers are not copied when an equipment is duplicated.

### Asset link and Create from Asset

An owned or third-party machine can be linked to an ERPNext **Asset** through **Asset in ERPNext** (shown only for
these ownerships; rented machines have no Asset, and switching to «إيجار» clears the link on the form).

- The picker lists only submitted Assets of the equipment's company that are not Scrapped or Sold and not linked to
  another equipment. It applies the user's own Asset permissions; a user who cannot read Assets cannot link one.
- One Asset links to at most one equipment. A cancelled Asset, or one of another company, is refused.
- From the Asset, the **Equipment name**, **Brand** and **Equipment type** (through the Asset category mapped on the
  equipment type) are taken and become read-only, together with Model, Manufacture year, Chassis and Plate number.
  The Asset image, cost center, custodian (as operator, for owned machines) and insurance details fill only empty
  fields. The Asset item, location, cost center and purchase value are shown read-only.
- The equipment is written back onto the Asset as its **Card Equipment** accounting dimension, so depreciation
  entries reach the machine's ledger.

**Create from Asset** — on a new equipment form, this button asks only for the Asset and the ownership («ملك» or
«طرف ثالث»). When nothing else is needed (an owned machine whose Asset category maps to an equipment type, and a
default daily-hours setting), the equipment is created at once; otherwise the prefilled form opens with the missing
fields to complete. A third-party machine always needs its rental direction and commercial terms.

<!-- screenshot: equipment-create-from-asset -->

### Status and the status guard

**Status** defaults to «نشطة» (Active). «متوقفة» (Stopped) and «في الصيانة» (Under Maintenance) are temporary and do
not block anything.

An equipment with status «منتهية» (Ended) should get no **new** assignment, transport, monthly card or diesel fill.
What happens is decided per company in Card Settings (**Equipment status rule**):

| Rule | Effect |
|---|---|
| Warn only (default, also when empty) | A message is shown and the record is saved. |
| Refuse | The save is stopped. |

Never stopped: a return to the supplier, a move of an owned machine to storage or a workshop, and a monthly card or
diesel fill whose period starts on or before the machine's **Exit date** (or its **Rental end**, once that date has
passed). Existing records are never changed; a transport is checked again on submit.

### Financial privacy

These fields are at permission level 2 and are read only by System Manager, Card Manager and Accounts Manager (System
Manager and Card Manager write them): **Cost center**, **Asset cost center**, **Asset purchase value**, **Internal
hourly rate**, **Internal operating rate basis** and **Internal operating rate**. The supplier **Hourly rate** is at
level 1.

Frappe applies these levels to the form, REST API, list and report views and exports. In addition, new entries in the
equipment's change history keep who changed a field above level 0 and when, but not its values. The Asset values
sent to the form when an Asset is linked contain only the fields the user may read.

### Current assignment and location

**Current project** and **Assignment date** are read-only. They are set only from the assignment in force today (see
[Assignments & Locations](/card/features/assignments-locations/)); a save, REST call or import never writes them.
**Location** is a free text for the place on site.

### Company

The **Company** is mandatory and at permission level 1. Once the equipment is used in a monthly card, assignment,
diesel fill, transport, unit, parts fitment row or ledger entry, its company cannot change: create a new equipment
record for the other company. With only one company on the site, a new form fills it in.

### Meter, tank and service fields

- **Meter type**, **Meter reading at receipt**, **Last reading** (read-only).
- **Tank capacity (liter)**, **Expected consumption (liter/hour)** and **Daily diesel consumption (litres per standard
  day)**. The expected figures are used by the Equipment Diesel Analysis report (the daily figure first, else the
  hourly one).
- For owned machines: **Maintenance every (hour)**, **Last maintenance date**, **Maintenance every (liter of diesel)**
  and **Meter reading at last maintenance**.

These are reference values; CARD does not create maintenance tasks from them. Weekly engine-hour readings are recorded
separately (see [Meter Readings](/card/features/meter-readings/)).

### Documents and expiry alerts

Registration, periodic inspection, insurance and TUV details are kept on the **Documents** tab. The four files are
accepted only as JPEG, PNG, WebP or PDF (checked by content, up to 10 MB) and stay private files of this equipment.
When the form opens, a red headline lists expired documents and an orange one lists documents expiring within 30 days.

### Exit

When a machine leaves the fleet, record **Exit date**, **Exit reason** («انتهاء الإيجار» Rental Ended, «إرجاع
للمؤجر» Returned to Lessor, «بيع» Sold, «تكهين» Scrapped, «نقل لفرع آخر» Transferred to Another Branch), **Meter reading
at exit**, **Settlement status** («لم تتم» Not Settled / «تمت» Settled) and **Notes**. The exit date is the machine's
last working day for the status guard.

### Connections

The Connections tab shows:

- **Operation** — Card Monthly Card and Card Equipment Assignment.
- **Fuel & Transport** — Project Diesel Fill and Equipment Transport (every machine of a multi-machine transport).
- **Parts fitment** — Card Equipment Part rows (only for roles that read them).
- **Linked records** — the Asset, the supplier and the current project.
- **Related records** — direct read-only links to the lessor, the current project and every project the machine has
  worked on (from its monthly cards). No record is created from here.

The dashboard also shows a heatmap of daily operating hours from submitted monthly cards, with separate day-shift and
night-shift heatmaps for two-shift machines.

### Units

A machine can be a **unit** that bundles two machines (for example a crusher and its generator). See
[Units & Components](/card/features/units-components/).

## Workflow

1. Create the categories, types, makes and models you need.
2. Open **Card Equipment** → **New**. For a machine that is already an ERPNext Asset, use **Create from Asset**.
3. Choose the **Company**, **Ownership** and **Rental direction**, then the **Equipment type** and name.
4. Enter the chassis and plate numbers, the operator, and the documents.
5. On **Cost and rental**, enter the daily working hours and the supplier and/or customer rates required by the
   direction.
6. Save. Move the machine to a project with an [Equipment Transport](/card/features/transport/).
7. Later changes to commercial terms: edit the field and write a new **Reason for commercial change**.
8. When the machine leaves, fill the **Exit** tab and set the status to «منتهية» (Ended).

## Permissions

| Role | Basic fields (level 0) | Commercial fields (level 1) | Financial fields (level 2) |
|---|---|---|---|
| System Manager | Read, write, create, delete | Read, write | Read, write |
| Card Manager | Read, write, create | Read, write | Read, write |
| Card User | Read, write | Read | — |
| Accounts Manager | Read | Read | Read |
| Card Supervisor | Read | — | — |

Company User Permissions limit every role to the equipment of its companies. See
[Roles & Permissions](/card/features/roles-permissions/).

## Related

- [Units & Components](/card/features/units-components/)
- [Assignments & Locations](/card/features/assignments-locations/)
- [Transport](/card/features/transport/)
- [Monthly Cards](/card/features/monthly-cards/)
- [Maintenance & Parts](/card/features/maintenance-parts/)
- [API: Equipment](/card/api-reference/equipment/)
