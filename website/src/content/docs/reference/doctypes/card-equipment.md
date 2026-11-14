---
title: "Card Equipment"
description: "Fields, layout and permissions of the Card Equipment DocType."
editUrl: false
sidebar:
  label: "Card Equipment"
---

:::note
This page is generated from the CARD source code on every build. Edit the code, not this page.
:::

| | |
|---|---|
| Kind | Document |
| Module | Card |
| Open in Desk | `/app/card-equipment` |


## Fields


### Basic details


**Equipment details**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Company | `company` | Link | Company | Yes |
| Ownership | `ownership` | Select | ملك · إيجار · طرف ثالث | Yes |
| Brand | `brand` | Data |  |  |
| Model | `model` | Data |  |  |
| Equipment make | `equipment_make` | Link | [Card Equipment Make](/card/reference/doctypes/card-equipment-make/) |  |
| Equipment model | `equipment_model` | Link | [Card Equipment Model](/card/reference/doctypes/card-equipment-model/) |  |
| Manufacture year | `manufacture_year` | Int |  |  |
| Chassis number | `serial_no` | Data |  |  |
| Plate number | `plate_no` | Data |  |  |
| Chassis number key <small>(hidden, read only)</small> | `serial_no_key` | Data |  |  |
| Plate number key <small>(hidden, read only)</small> | `plate_no_key` | Data |  |  |
| Equipment category <small>(read only)</small> | `equipment_category` | Link | [Card Equipment Category](/card/reference/doctypes/card-equipment-category/) |  |
| Equipment name | `equipment_name` | Data |  | Yes |
| Equipment type | `equipment_type` | Link | [Card Equipment Type](/card/reference/doctypes/card-equipment-type/) | Yes |
| Image <small>(hidden)</small> | `image` | Attach Image |  |  |
| Status | `status` | Select | نشطة · متوقفة · في الصيانة · منتهية |  |
| Unit (two machines bundled) | `is_unit` | Check |  |  |


**Unit components**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Components | `components` | Table | [Card Equipment Component](/card/reference/doctypes/card-equipment-component/) |  |


### Operation and assignment


**Current assignment**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Current project <small>(read only)</small> | `current_project` | Link | Project |  |
| Operator name | `external_operator_name` | Data |  |  |
| Operator | `operator` | Link | Employee |  |
| Assignment date <small>(read only)</small> | `assignment_date` | Date |  |  |
| Cost center | `cost_center` | Link | Cost Center |  |
| Operator mobile | `external_operator_phone` | Data |  |  |
| Operator name <small>(read only)</small> | `operator_name` | Data |  |  |
| Location | `site_location` | Data |  |  |


### Cost and rental


**Rental details**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Lessor / Owner | `supplier` | Link | Supplier |  |
| Rental start | `rental_start_date` | Date |  |  |
| Rate type | `rate_type` | Select | باليوم · بالساعة · بالشهر |  |
| Daily working hours | `daily_hours` | Float |  | Yes |
| Deprecated – not used <small>(hidden, read only)</small> | `min_hours` | Float |  |  |
| Operator charged to | `operator_on` | Select | المؤجر · الشركة |  |
| Contract number | `contract_no` | Data |  |  |
| Rental end | `rental_end_date` | Date |  |  |
| Rate | `rate` | Currency |  |  |
| Day billing basis | `day_billing_basis` | Select | Prorated by hours · Full day |  |
| Fuel charged to | `الوقود_على` | Select | المؤجر · الشركة |  |
| Hourly rate <small>(read only)</small> | `approved_hourly_rate` | Currency |  |  |


**Internal cost**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Asset in ERPNext | `الأصل_في_erpnext` | Link | Asset |  |
| Asset item <small>(read only)</small> | `asset_item` | Data |  |  |
| Asset location <small>(read only)</small> | `asset_location` | Data |  |  |
| Asset cost center <small>(read only)</small> | `asset_cost_center` | Link | Cost Center |  |
| Asset purchase value <small>(read only)</small> | `asset_purchase_value` | Currency |  |  |
| Internal hourly rate | `internal_hourly_rate` | Currency |  |  |
| Internal operating rate basis | `internal_rate_basis` | Select | بالساعة · باليوم |  |
| Internal operating rate | `internal_rate` | Currency |  |  |


### Meter and maintenance


**Meter**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Meter type | `meter_type` | Select | ساعات · كيلومترات · بدون عداد |  |
| Meter reading at receipt | `opening_meter` | Float |  |  |
| Last reading <small>(read only)</small> | `current_meter` | Float |  |  |
| Tank capacity (liter) | `tank_capacity` | Float |  |  |
| Expected consumption (liter/hour) | `expected_consumption` | Float |  |  |


**Maintenance**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Maintenance every (hour) | `service_interval_hours` | Float |  |  |
| Last maintenance date | `last_service_date` | Date |  |  |
| Maintenance every (liter of diesel) | `service_interval_liters` | Float |  |  |
| Meter reading at last maintenance | `last_service_meter` | Float |  |  |


### Documents


**Equipment documents**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Registration number | `registration_no` | Data |  |  |
| Registration expiry | `registration_expiry` | Date |  |  |
| Registration image | `registration_file` | Attach |  |  |
| Periodic inspection expiry | `inspection_expiry` | Date |  |  |
| Inspection certificate | `inspection_file` | Attach |  |  |
| Insurance company | `insurance_company` | Data |  |  |
| Insurance policy number | `insurance_policy_no` | Data |  |  |
| Insurance expiry | `insurance_expiry` | Date |  |  |
| Insurance file | `insurance_file` | Attach |  |  |
| TUV number | `tuv_no` | Data |  |  |
| TUV expiry | `tuv_expiry` | Date |  |  |
| TUV image | `tuv_file` | Attach |  |  |


### Exit


**Equipment exit**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Exit date | `exit_date` | Date |  |  |
| Exit reason | `exit_reason` | Select | انتهاء الإيجار · إرجاع للمؤجر · بيع · تكهين · نقل لفرع آخر |  |
| Meter reading at exit | `exit_meter` | Float |  |  |
| Settlement status | `settlement_status` | Select | لم تتم · تمت |  |

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Notes | `exit_notes` | Small Text |  |  |


### Connections

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Unit component (no monthly card) <small>(read only)</small> | `is_unit_component` | Check |  |  |
| Customer rate type | `customer_rate_type` | Select | باليوم · بالساعة · بالشهر · بالمتر المكعب |  |
| Customer rate | `customer_rate` | Currency |  |  |
| Customer rate (night shift) | `customer_rate_night` | Currency |  |  |
| Load volume (m³) | `load_volume_m3` | Float |  |  |
| Customer | `default_customer` | Link | Customer |  |
| Rental direction | `rental_direction` | Select | مستأجَرة من مورد · مؤجَّرة لعميل · إيجار من الباطن · تشغيل داخلي |  |
| Reason for commercial change | `commercial_change_reason` | Small Text |  |  |
| Daily diesel consumption (litres per standard day) | `daily_diesel_consumption` | Float |  |  |
| Equipment consumption rates (litres per hour) | `consumption_rates` | Table | [Card Consumption Rate](/card/reference/doctypes/card-consumption-rate/) |  |


**Operation standards**


**Customer side**

| Label | Field name | Type | Options / link | Required |
|---|---|---|---|---|
| Type from asset <small>(hidden, read only)</small> | `equipment_type_from_asset` | Check |  |  |


## Child tables

- [Card Equipment Component](/card/reference/doctypes/card-equipment-component/)
- [Card Consumption Rate](/card/reference/doctypes/card-consumption-rate/)


## Permissions

| Role | Rights |
|---|---|
| System Manager | read, write, create, delete, report, export, print, email |
| Card Manager | read, write, create, report, export, print, email |
| Card User | read, write, report, print, email |
| Accounts Manager | read, report, export, print |
| Card Supervisor | read |
| System Manager (permlevel 1) | read, write |
| Card Manager (permlevel 1) | read, write |
| Card User (permlevel 1) | read |
| Accounts Manager (permlevel 1) | read |
| System Manager (permlevel 2) | read, write |
| Card Manager (permlevel 2) | read, write |
| Accounts Manager (permlevel 2) | read |
