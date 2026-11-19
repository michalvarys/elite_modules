# Data and reports – a guide for management

**What this guide is for.** It describes the **WinVet data** app: how to read the overview of revenue,
expenses and profit, how to break the data down and export it, how to record expenses, print the cash
closure and the stock report, and what to do when Odoo reports a problem with the transfer from WinVet.
Only management can see the **WinVet data** app.

**Where the data comes from.** Revenue, documents, payments, deposits, the price list and the stock are
entered in WinVet. A program we call the bridge sends them to Odoo. This data cannot be changed in the
**WinVet data** app. It is corrected in WinVet and the change shows up here after the next transfer. The
only thing you enter directly in Odoo is **expenses**, because WinVet knows only revenue.

**How fresh the data is.** The overview shows „data z WinVetu do …“ (data from WinVet up to …) at the top,
the stock report shows the date of the last movement, and **Stav synchronizace** (Synchronisation status)
shows the time data was last received. When the data is transferred from a WinVet backup, it is as old as
that backup, so you may not see today's revenue yet.

What is in the menu:

| Item | What it is for |
|---|---|
| **Přehled** (Overview) | Revenue, expenses and profit for a period, charts, comparison (chapter 1) |
| **Tržby** (Revenue) | **Uzávěrka** (Cash closure), **Tržby podle položek** (Revenue by item), **Úkony** (Procedures), **Léky a zboží** (Medicines and goods) (chapters 2 and 6) |
| **Regleta skladu** (Stock report) | PDF for the accountant (chapter 7) |
| **Výdaje** (Expenses) | Recording expenses (chapter 3) |
| **Doklady** (Documents), **Platby** (Payments), **Zálohy** (Deposits) | Documents, received payments and client deposits from WinVet (chapters 4 and 5) |
| **Návštěvy** (Visits), **Očkování** (Vaccinations), **Ceník** (Price list), **Uživatelé WinVet** (WinVet users) | WinVet data to read |
| **Kalendář z WinVetu** (Calendar from WinVet) | Appointments from WinVet (chapter 8) |
| **Stav synchronizace** (Synchronisation status), **Změny struktury WinVetu** (WinVet structure changes) | Whether the transfer works (chapters 9 to 11) |
| **Konfigurace** (Configuration) | **API klíč** (API key) for the bridge and **Kategorie výdajů** (Expense categories) |

---

## 1. Overview

**WinVet data → Přehled** (Overview) opens with the heading **Přehled tržeb a výdajů** (Revenue and expense overview).

### What to show and for which period

At the top left you switch between **Tržby i výdaje** (Revenue and expenses), **Jen tržby** (Revenue only)
and **Jen výdaje** (Expenses only). Your browser remembers the choice. Until an expense has been recorded,
the overview starts on **Jen tržby**.

Choose the period with a button or with your own dates in the fields on the right:

| Button | Compared with |
|---|---|
| **Dnes** (Today), **Včera** (Yesterday) | the same day a week earlier |
| **Tento týden** (This week) | the same part of last week |
| **Minulý týden** (Last week) | the week before it |
| **Tento měsíc** (This month, the default) | the same part of last month |
| **Minulý měsíc** (Last month) | the month before it |
| **Letos** (This year) | the same part of last year |
| **Od začátku** (From the start) | no comparison |
| your own dates | a period of the same length right before it |

Under the heading you can see the period, what it is compared with, and the day up to which WinVet data has arrived.

### Tiles

| Tile | What it means |
|---|---|
| **Tržby (položky)** (Revenue, items) | The sum of document items from WinVet by item date, meaning the date of the visit. It does not matter whether the document has been paid yet. |
| **Výdaje bez DPH** (Expenses excl. VAT) | The sum of expenses without VAT. |
| **Zisk (tržby − výdaje)** (Profit, revenue − expenses) | Revenue minus expenses for the same period. A negative profit is red. |
| **Úkony** (Procedures), **Léky a zboží** (Medicines and goods) | The part of the revenue by kind of item. |
| **Přijaté platby** (Payments received) | Payments by payment date. This can differ from revenue: an unpaid document is in revenue but not in payments, and a payment can arrive on a different day than the visit. |
| **Návštěvy s účtem** (Visits with a bill) | The number of visits that have a bill item in the period. |
| **Průměr na návštěvu** (Average per visit) | Revenue divided by visits with a bill. |
| **Počet výdajů** (Number of expenses), **Průměrně za den** (Average per day) | Only in **Jen výdaje** mode. |

> **Profit is only a guide.** Revenue is the amounts from documents including VAT, while expenses are
> counted without VAT. It is not an accounting result, and it counts only the expenses recorded in Odoo.

Under the amount is the change against the comparison period: ▲ / ▼ with a percentage, „nové“ (new) when
the comparison period was zero, or „víc než 10×“ (more than 10×). Green is a change for the better, red for
the worse, so a rise in expenses is red.

### Charts and tables

- **Tržby, výdaje a zisk v čase** (Revenue, expenses and profit over time; depending on the mode **Tržby
  v čase** or **Výdaje v čase**) – by day, or by month for a period longer than 62 days.
- **Výdaje podle kategorií** (Expenses by category) and **Největší výdaje** (Largest expenses) – the ten
  highest expenses.
- **Podle toho, kdo zapsal** (By who entered it) – revenue by WinVet user.
- **Formy platby** (Payment methods) and **Druhy zvířat** (Animal species).
- **Nejčastější úkony** (Most frequent procedures) and **Nejprodávanější léky a zboží** (Best-selling
  medicines and goods) – the ten items with the highest amount, with the count next to it.

### Drilling down

Click a tile, a table row or a part of a chart (a user, a payment method, a species, an expense category)
and the records behind the number open, already limited to the chosen period. From there you can sort and
export them further (chapter 2). The breadcrumbs at the top left take you back.

The **Zapsat výdaj** (Record expense) button at the top right opens a new expense. The overview recalculates
by itself after you save.

## 2. Revenue: pivot tables, charts and export

**WinVet data → Tržby** (Revenue) has three views of the same data:

- **Tržby podle položek** (Revenue by item) – all items, rows are months, columns the kind of item.
- **Úkony** (Procedures) – procedures only, rows are items, columns months.
- **Léky a zboží** (Medicines and goods) – medicines and goods only, rows are items, columns months, with
  quantity and amount.

At the top right you switch between the pivot table, the chart and the list.

**Pivot table.** In **Měřítka** (Measures) you choose what is added up: **Částka** (Amount, with VAT),
**Základ DPH** (VAT base), **DPH** (VAT) or **Množství** (Quantity). Click the name of a row or column to
add a further breakdown.

**Filters and grouping** are under the arrow on the right of the search field:

- The filters **Úkony** (Procedures), **Léky a zboží** (Medicines and goods), **Ostatní** (Other) and
  **Datum** (Date).
- **Seskupit** (Group by): **Měsíc** (Month), **Týden** (Week), **Den** (Day), **Druh položky** (Kind of
  item), **Forma úhrady** (Payment method), **Sazba DPH** (VAT rate), **Položka** (Item), **Zapsal(a)**
  (Entered by), **Lékařka** (Doctor), **Druh zvířete** (Species), **Majitel** (Owner).
- **Oblíbené** (Favourites) has views ready for everyone: **Úkony podle měsíců** (Procedures by month),
  **Léky a zboží podle položek** (Medicines and goods by item) and **Tržby podle toho, kdo zapsal** (Revenue
  by who entered it).

**Forma úhrady** (Payment method) comes from the document: **Hotově** (Cash), **Kartou** (Card), **Převodem**
(Transfer), **Jinak** (Other), **Kombinovaně** (Combined: several methods on one document) or **Bez úhrady**
(Unpaid: no payment with a non-zero amount).

**Export.** The pivot table has a download icon that saves the table to Excel (**Stáhnout xlsx** – Download
xlsx). In the list, click the gear next to the title and choose **Exportovat vše** (Export all), or tick
rows and use **Akce → Export** (Actions → Export).

## 3. Expenses

You record expenses by hand: **WinVet data → Výdaje → Nový** (Expenses → New), or **Zapsat výdaj** (Record
expense) in the overview.

| Field | What to fill in |
|---|---|
| **Popis** (Description) | e.g. October rent, supplier invoice |
| **Datum** (Date), **Kategorie** (Category) | required |
| **Částka s DPH** (Amount incl. VAT) | the whole amount the clinic paid; it must be greater than zero |
| **DPH** (VAT) | **Bez DPH** (No VAT), **12 %** or **21 %**. Use **Bez DPH** also for a supplier who is not a VAT payer. **Bez DPH** (Excl. VAT) further down the form shows the amount that goes into profit. |
| **Zaplaceno** (Paid) | how it was paid (default **Převodem**, by transfer) |
| **Dodavatel** (Supplier), **Číslo dokladu** (Document number), **Poznámka** (Note) | optional |
| **Opakovat měsíčně do** (Repeat monthly until) | only when creating, see below |

**Regular payments.** For rent, fill in **Opakovat měsíčně do**. The expense is copied to the same day of
each following month up to that date, for 36 months at most. Each copy is a separate expense, so it can be
edited or deleted on its own. Copies with a future date count only in their own month.

**Document.** Attach a photo or PDF with the paperclip in the right-hand panel. The filter **Bez přiloženého
dokladu** (Without an attached document) shows where it is missing.

**Reports.** The list has the filter **Tento měsíc** (This month), grouping by category, supplier and month,
and it offers a pivot table and a chart. Export works the same way as in chapter 2.

**Kategorie výdajů** (Expense categories) are edited in **Konfigurace → Kategorie výdajů** (Configuration →
Expense categories): the name, the colour in the chart and whether the category is active. A category that
already has expenses cannot be deleted, you can only switch it off.

**Expenses from goods receipts.** While WinVet runs the stock, a goods receipt in Odoo does not record an
expense. After moving to the stock in Odoo the expense is recorded automatically, see the guide
[Till and stock](../../../elite_vet_sale/doc/en/pokladna-a-sklad.md). Until then, record purchases by hand so
that profit includes them.

## 4. Documents

**WinVet data → Doklady** (Documents) is the list of documents from WinVet: **Účet majitele** (Owner account),
**Doklad PODP** (Receipt document), **Faktura vydaná** (Issued invoice) and **Vratka** (Refund). An open
document shows its items and payments.

- **Celkem** (Total) and **Zaplaceno** (Paid) are amounts from the document; **Ze zálohy** (From deposit) is
  the part paid from the client's deposit.
- **Forma úhrady** (Payment method) is worked out from the payments, **Forma na dokladu** (Method on the
  document) is what is written on the document in WinVet. On a refund it says how the money was returned.
  On a document without a payment it does not by itself mean the money arrived.
- You can group by month, type, payment method, who created the document, and owner.
- The filter **Nedoplacené** (Not fully paid) shows all documents with a positive amount, not just the unpaid
  ones. Compare paid documents with the **Zaplaceno** column. Grouping by **Forma úhrady** → **Bez úhrady**
  (Unpaid) reliably shows documents without a payment.

## 5. Payments and deposits

**WinVet data → Platby** (Payments) shows received payments by payment date. It opens as a pivot table: rows
are months, columns the payment method. The filters are **Hotově** (Cash), **Kartou** (Card), **Převodem**
(Transfer), **Vrácené** (Refunded) and **Datum** (Date). The **Ze zálohy** (From deposit) column shows the part
of a payment paid from a deposit.

**WinVet data → Zálohy** (Deposits) shows client deposits: when and how they were received, how much was used
and refunded, and what remains. The filter **S zůstatkem** (With a balance) shows deposits the client has not
used up yet. An open deposit shows how it was used in documents. A received deposit is not a payment, so it is
not in **Platby**. WinVet does not keep a payment method for a deposit refund, so Odoo treats it as cash.

## 6. Cash closure (PDF)

**WinVet data → Tržby → Uzávěrka** (Revenue → Cash closure), or the **Uzávěrka (PDF)** button in the lists
**Tržby podle položek**, **Doklady** and **Platby**.

1. Choose **Tento měsíc** (This month), **Minulý měsíc** (Last month), **Dnes** (Today), **Včera** (Yesterday)
   or **Jiné období** (Other period), and adjust **Od** (From) and **Do** (To) if needed.
2. Click **Vytisknout PDF** (Print PDF).

The report is based on WinVet data, it is not the daily closing of the till in Odoo. It contains:

1. **Tržby podle dokladů** (Revenue by document) – receipt documents, invoices and refunds by document date,
   with refunds deducted. It also includes unpaid documents.
2. **Přijaté platby a vratky** (Payments received and refunds) – by payment method: new payments of documents,
   received deposits, refunded amounts and income after refunds. Using a deposit is not new income.
3. **Denní rozpis** (Daily breakdown) – only for a period longer than one day, and only days with some data.
4. **Faktury a doklady bez úhrady** (Invoices and documents without payment).
5. **Zálohy** (Deposits) – received in the period, their use, refunds and the balance at the end of the period.
6. **Tržby podle položek a formy úhrady** (Revenue by item and payment method). Transfers of an unpaid balance
   from an earlier document are not items and are listed separately under the table in **Peněžní řádky mimo
   položky** (Money lines outside items).
7. **Rozpis DPH** (VAT breakdown) – base and tax by the rate on the document lines.

A one-day closure has no daily breakdown, so the following parts are numbered one lower. At the end there are
signature lines **Předal/a** (Handed over by) and **Převzal/a** (Received by).

## 7. Stock report (PDF for the accountant)

**WinVet data → Regleta skladu** (Stock report): choose **Minulý měsíc** (Last month, the default), **Tento
měsíc** (This month), **Tento rok** (This year), **Minulý rok** (Last year) or **Jiné období** (Other period)
and click **Vytisknout PDF** (Print PDF).

For the period the report shows:

1. **Souhrn** (Summary) – opening stock, receipts, issues and closing stock by group, without and with VAT.
2. **Příjemky v období** (Receipts in the period) with the supplier, and **Rekapitulace DPH příjmu** (VAT summary
   of receipts).
3. **Pohyb po položkách** (Movement by item) – quantities and values of each item.
4. **Položky se záporným stavem** (Items with a negative stock) – only when there are any. More was issued than
   received: a receipt is missing, or an issue was entered with the wrong quantity or unit. This has to be
   corrected in WinVet.

Good to know:

- The data is as old as the last transfer. The date of the last movement is in the report header.
- **The value differs from WinVet.** WinVet adds receipts with VAT but subtracts issues without VAT. The report
  counts both sides the same way, explained at the end of the report in **Jak se počítá** (How it is calculated).
- When the period ends with the latest data, there is a check under the summary showing for how many items the
  closing quantity agrees with WinVet. Items that differ need to be checked in WinVet.
- If the report says no stock movements have arrived from WinVet, a newer version of the bridge is needed.
  Contact the administrator.

## 8. Calendar from WinVet

Appointments entered in WinVet appear in the **Kalendář** (Calendar) in Odoo and in the till as grey hatched
cards with the label **WinVet**, and they occupy the slot for bookings in Odoo. Reception sees them there (see the
guide [Reception in the till](../../../elite_vet_reception/doc/en/recepce-v-pokladne.md)). The period from
yesterday to 60 days ahead is transferred, in one direction only: Odoo writes nothing to WinVet.

Under **WinVet data → Kalendář z WinVetu** (Calendar from WinVet) management has:

- **Záznamy** (Records) – a read-only list of the transferred records. The filters are **Dnes** (Today), **Od
  dneška** (From today, the default), **S časem** (With a time), **Celodenní** (All day), **Bez ordinace**
  (Without a room), **Se zvířetem z kartotéky** (With an animal from the card index).
- **Kalendáře → ordinace** (Calendars → rooms) – which WinVet calendar belongs to which consulting room. It is
  assigned automatically by name. If you choose a room by hand, the transfer no longer changes it. A calendar
  without a room does not appear in the **Kalendář** and blocks nothing.
- **Činnosti → úkony** (Activities → procedures) – which WinVet activity corresponds to which procedure. The
  filter **Bez úkonu** (Without a procedure) shows what is left to assign.
- **Zapnout / vypnout** (Switch on / off) – **Vypnout kalendář z WinVetu** (Switch off the calendar from WinVet)
  hides the records from the calendar, they stop blocking slots and new ones are not saved (useful for moving
  to bookings in Odoo). **Smazat přenesené záznamy** (Delete transferred records) deletes the transferred
  records in Odoo only, they stay in WinVet; with the calendar switched on, the next transfer fills them in again.

## 9. Synchronisation status

**WinVet data → Stav synchronizace** (Synchronisation status) shows whether the transfer is running.

- **Poslední příjem dat** (Last data received) and **Poslední hlášení stavu** (Last status report) – when the
  bridge was last in touch. If these times do not change, the bridge is not running or cannot reach Odoo. Odoo
  does not warn about this by itself, so look here from time to time.
- **Verze mostu** (Bridge version), **Verze WinVetu** (WinVet version), **Zdroj dat** (Data source: live = the
  live database, backup = a backup).
- **Zablokované oblasti** (Blocked areas) – what the bridge is not reading because of a change in WinVet.
- **Zpráva mostu** (Bridge message) and **Poslední chyba** (Last error) – text for the administrator.

Tabs:

- **Poslední běh** (Last run) – by area (owners, documents, payments…) how many records are new, changed, deleted
  and skipped. **Přeskočené** (Skipped) are shown in yellow.
- **Změny struktury** (Structure changes) – the current differences from the approved state.
- **Otisky struktury** (Structure fingerprints) – technical details for the administrator.
- **Zrcadlo skladu** (Stock mirror) – when the stock was last taken over from WinVet, and warnings about
  differences, for example when the stock layers do not match the stock level of an item.

## 10. WinVet structure changes

After a WinVet update its database may change. The bridge checks this on every run and writes the differences to
**WinVet data → Změny struktury WinVetu** (WinVet structure changes). The list shows only **Neprověřené** (Not
checked). The filter **Blokující a žurnál** (Blocking and journal) picks out what matters.

| Severity | What it means |
|---|---|
| **Blokující** (Blocking) | The affected area is not being read, its data in Odoo stays old. |
| **Žurnál změn** (Change journal) | The transfer of changes is not reliable, so the bridge sends everything instead. The data is fine, the transfer just takes longer. |
| **Upozornění** (Warning) | A change in a table the bridge reads, but reading continues. |
| **Informace** (Information) | A change outside what the bridge reads. For information only. |

With the **Prověřeno** (Checked) switch you mark that someone has reviewed the change. It has no effect on the transfer.

## 11. What to do on an alert

Management gets an activity **WinVet – zkontrolujte synchronizaci** (WinVet – check the synchronisation) and a red
strip **Pozor:** (Warning) appears on **Stav synchronizace**. This happens when WinVet was updated, an area is
blocked, or the structure of tables the bridge reads has changed.

1. Open **Stav synchronizace** and read the strip and **Zablokované oblasti** (Blocked areas).
2. Keep in mind that the data of blocked areas is old. Reports based on it may be incomplete until the block is
   resolved. Nothing has happened to WinVet and the other areas keep transferring.
3. Pass the text of the alert to the administrator, who checks the new WinVet version and approves it in the
   bridge. You do not have to approve anything. After approval the blocked areas catch up by themselves.
4. Click **Potvrdit upozornění** (Acknowledge the alert) once the administrator knows. The button only hides the
   strip and closes the activity, it does not solve the problem. The same block is not reported again, so after
   acknowledging keep an eye on **Zablokované oblasti**.

If there is no alert but the numbers do not add up:

- Look at „data z WinVetu do …“ (data from WinVet up to …) and at **Poslední příjem dat** (Last data received). An
  old time means the transfer is not running.
- Pass **Poslední chyba** (Last error) or **Přeskočené** (Skipped) in **Poslední běh** (Last run) to the administrator.
