# Staff planning – guide for management and the team

**What this guide is for.** It describes the monthly shift plan for the whole team. It has two parts:

- **Part A** is for whoever makes the roster (the Správce rozpisu, Roster manager): **Plánování**
  (Planning), **Personál** (Staff), **Dostupnost a absence** (Availability and absences), **Úseky plánu**
  (Plan sections), **Požadavky na směny** (Shift requests), publishing on the website, the hours
  balance, the overview by person, export and PDF.
- **Part B** is for every team member: **Moje směny** (My shifts) and **Moje dostupnost** (My
  availability).

Setting up doctors, rooms and reservations is covered by the
[Guide for managers](../../../elite_vet_reservation/doc/en/nastaveni.md).

The screens in Odoo are in Czech, so every label below is given in Czech exactly as you see it, with an
English gloss in brackets the first time it appears in a section.

| Where in the menu | Who sees it | What is there |
|---|---|---|
| **Rozpis služeb → Plánování** (Shift roster → Planning) | Správce rozpisu | Monthly plan, Požadavky na směny, **Bilance hodin** (Hours balance), **Přehled po lidech** (Overview by person), export, PDF, publishing on the website |
| **Rozpis služeb → Personál** (Shift roster → Staff) | Správce rozpisu | Role, abbreviation, contract hours, colour, holiday, account |
| **Rozpis služeb → Dostupnost a absence** (Shift roster → Availability and absences) | Správce rozpisu | List of all availability and absence records |
| **Rozpis služeb → Úseky plánu** (Shift roster → Plan sections) | Správce rozpisu | Sections (Recepce, Ordinace 1…), their shifts and times |
| **Moje směny → Moje dostupnost** (My shifts → My availability) | Every team member with an account | Your own availability and planned shifts |

The **Správce rozpisu** right is set in **Nastavení → Uživatelé** (Settings → Users), in the **Rozpis
služeb** part.

---

# Part A – for whoever makes the roster

## 1. How it works

The plan is nothing new alongside the roster. Each person you assign to a shift in the plan is an ordinary
shift in **Rozpis služeb → Rozpis** (Shift roster → Roster). So nothing is entered twice.

Recommended routine for each month:

1. The team marks in **Moje dostupnost** (My availability) when they can work.
2. You enter absences in **Požadavky na směny** (Shift requests).
3. You assign people to shifts in the plan. Clients do not see it on the website yet.
4. You check **Bilance hodin** (Hours balance) and **Přehled po lidech** (Overview by person).
5. You **publish** the finished month on the website (chapter 8).
6. You download the **PDF** for the notice board or export a CSV.

Everything is saved immediately. At the top you see **Ukládání…** (Saving…) and then **Všechny změny
uloženy** (All changes saved); there is no Save button here.

## 2. Personál (Staff)

**Rozpis služeb → Personál** (Shift roster → Staff), or the **Personál** button right in **Plánování**
(Planning). The whole team is here and the rows are edited directly in the list. Drag the handle on the
left to change the order.

| Column | Meaning |
|---|---|
| **Jméno** (Name) | Full name as shown in the plan and on the website. |
| **Zkratka** (Abbreviation) | The label in the plan. It is worked out from the name (without titles) and can be overwritten. |
| **Role** (Role) | **Lékař** (Doctor), **Sestra** (Nurse), **Recepce** (Reception), **Výpomoc / stáž** (Helper / trainee). People are ordered by role in the plan and in **Požadavky na směny** (Shift requests). |
| **Úvazek (h/týden)** (Contract, hours per week) | The hours fund is calculated from this (chapter 9). |
| **Barva** (Colour) | Colour of the label in the plan, the same as in the reservation calendar. |
| **Účet** (Account) | The person's login account. Without it **Moje dostupnost** (My availability) does not work. One account belongs to one person only. |
| **Dovolená na rok (dny)** (Holiday per year, days) | Entitlement for the calendar year. |
| **Zbývá (dny)** (Remaining, days) | Entitlement minus the **D** records this year. Every D record counts. |
| **V plánování** (In planning) | Untick for people who are not planned. They then do not appear in the plan, in Požadavky na směny or in the balance. |

Switch on the hidden columns **Lékařka (rezervace)** (Doctor, reservations) and **Aktivní** (Active) with
the icon on the right of the list header. Someone with **Lékařka (rezervace)** ticked is a doctor for
reservations; ticking it switches their role to Lékař by itself.

## 3. Úseky plánu (Plan sections)

**Rozpis služeb → Úseky plánu** (Shift roster → Plan sections). A section is a block of rows in the plan.
Installation creates **Recepce** (Reception), **Ordinace 1** (Room 1), **Ordinace 2** (Room 2), **Sál**
(Operating theatre) and **Stáž / výpomoc** (Trainees / helpers). Drag to change the order.

For a section, fill in:

| Field | Meaning |
|---|---|
| **Název** (Name) | For example Ordinace 1. |
| **Druh** (Kind) | **Úsek / místnost** (Section / room) or **Stáž / výpomoc** (Trainees / helpers). In Stáž / výpomoc you can also type the name of someone outside the team; these shifts do not go on the website. |
| **Ordinace v rezervacích** (Room in reservations) | The room a doctor's duty in this section is carried over to. Empty (for example Recepce) = not carried over. |
| **Role nahoře v nabídce** (Roles at the top of the list) | Which roles are offered first when choosing a person. Typed in English, separated by commas: `doctor`, `nurse`, `reception`, `helper`. |
| **Aktivní** (Active) | An unticked section is not shown in the plan. |

Below are the section's **shifts**, each one row of the plan:

| Column | Meaning |
|---|---|
| **Název** (Name) | For example **Ranní** (Morning). |
| **Od** (From), **Do** (To) | The default time of the shift. |
| **Dny** (Days) | **Po–Pá** (Mon–Fri), **So–Ne** (Sat–Sun) or **Každý den** (Every day). On other days the cell in the plan is hatched. |
| **Typ směny v rozpisu** (Shift type in the roster) | The type from **Rozpis služeb → Typy směn** (Shift roster → Shift types) the shift is recorded under. It sets the colour and legend on the website. |

## 4. The Plánování screen (Planning)

At the top, the arrows **‹ ›** change the month. Next to the month is the label **Zatím není na webu**
(Not on the website yet) / **Na webu** (On the website) and the button **Zveřejnit na webu** (Publish on
the website) / **Stáhnout z webu** (Hide from the website; chapter 8). On the right are the buttons
**Personál** (Staff), **Export CSV** and **PDF**. Under the bar is the **Požadavky na směny** (Shift
requests) panel (chapter 6), below it the plan, then **Bilance hodin** (Hours balance; chapter 9) and at
the bottom **Přehled po lidech** (Overview by person; chapter 10).

**The plan** has the sections and their shifts in the rows and the days of the month in the columns. The
days of the two tables sit exactly above each other and scroll sideways together.

| What you see | Meaning |
|---|---|
| Grey column | Weekend. |
| Yellow column | Public holiday (the bubble over the day shows its name). Holidays are calculated automatically. |
| Red text under the day | A full-day note from **Rozpis služeb** (Shift roster), for example **Zavřeno** (Closed). |
| Hatched cell | This shift does not apply on that day. |
| Coloured label | A person in the shift. If the time differs from the default, it is shown too. Doctors are on the first line of the cell, nurses and others below them. |
| Crossed-out eye on the label | The doctor's service is **hidden on the website** (chapter 8). |
| Red frame on a label | Watch out: the person has an absence or cannot work that day, or the doctor is not carried over to reservations. The bubble gives the reason. |
| Dashed frame | A duty entered directly in **Rezervace → Rozpis lékařů** (Reservations → Doctors' roster). |
| **Absence** (Absences) row | Who has D, NV, L, PN or Š that day. |
| **Z rozpisu – bez úseku** (From the roster, no section) row | Shifts that fit no section. Read-only, so that nothing gets lost. |

Shifts entered in Rozpis služeb appear in the plan in the shift that fits them best (by room, type and
time).

### Převzít služby z Rozpisu lékařů (Take over duties from the doctors' roster)

The button **Převzít služby z Rozpisu lékařů (počet)** (with a count) appears when the month has duties
entered manually in **Rozpis lékařů** (Doctors' roster). It turns them into shifts in the plan, so that
from then on they are planned here; **Jen tyto úkony** (Only these procedures) and the note stay on them.
The message says "Převzato X služeb, přeskočeno Y (ordinace bez úseku nebo kolize)." (X duties taken over,
Y skipped: room without a section, or a clash.)

### Copying a week

The header of each Monday has a small **⧉** icon. It copies the shifts of the previous week into this
week. It skips a person who is already in that shift or who has an absence or **Nemůžu** (Cannot) that day.
Only days of the displayed month are copied. The message says "Zkopírováno X směn, přeskočeno Y." (X shifts
copied, Y skipped.)

## 5. Adding a person to a shift

1. Click a cell in the plan. A window opens with the name of the section, shift and day.
2. If needed, choose the time in **Čas nové směny** (Time of the new shift): the shift's default time, the
   quick choices (10–18, 8–14, 9–15, 14–20) or your own time in the form 8:00 or 14:30.
3. Click a person. They are added immediately. Another click adds another person to the same cell.
4. Close with **Hotovo** (Done).

People are grouped by role. Next to each name you see what is known about them that day: the availability
they entered, an absence and other shifts. Someone with an absence or **Nemůžu** (Cannot) is paler, but can
still be added; the plan does not forbid it, it only warns you with a red frame.

A person already in the cell has a row at the top of the window. There you change their time or remove them
with **Smazat** (Delete), or with the cross **×** right on the label in the plan. A doctor's row also
has an eye button **Na webu** (On the website) / **Skryto na webu** (Hidden on the website; chapter 8). A shift from **Rozpis
služeb** (Shift roster) and a manually entered duty from **Rozpis lékařů** (Doctors' roster) can be changed
and deleted this way too.

The **Stáž / výpomoc** (Trainees / helpers) section also has a field for the name of a trainee or temp who is
not in **Personál** (Staff), and an **Přidat** (Add) button.

## 6. Požadavky na směny (Shift requests)

The panel above the plan: people by role in the rows, days in the columns. Open and close it by clicking its
name, and change its size by dragging the bottom edge. The browser remembers both.

A click in a cell opens the choice of record. You can add **Poznámka ke dni** (Note for the day), remove the
record with **Smazat záznam** (Delete record), or change only the note of an existing record (**Uložit jen
poznámku**, Save note only). The keyboard is faster: arrows move between cells, a letter writes a record,
**Del** deletes it and **Enter** opens the choice.

| In the cell | Record | Key | Who enters it |
|---|---|---|---|
| ✓ | **Můžu** (Can work) | M | team member and management |
| R | **Jen ráno** (Mornings only) | R | team member and management |
| O | **Jen odpoledne** (Afternoons only) | O | team member and management |
| × | **Nemůžu / volno** (Cannot / day off) | V | team member and management |
| D | **Dovolená** (Holiday) | D | management only |
| NV | **Náhradní volno** (Time off in lieu) | N | management only |
| L | **Lékař** (Doctor's appointment) | L | management only |
| PN | **Nemoc (PN)** (Sick leave) | P | management only |
| Š | **Školení / kongres** (Training / congress) | S | management only |

A dot **•** in the cell means the person entered it themselves; a pencil **✎** means the day has a note. At
the end of the row are the totals of **D** and **NV** for the month and the field **Poznámka k měsíci** (Note
for the month). The arrows **▲ ▼** by a name move the person within their role.

## 7. Dostupnost a absence (Availability and absences)

**Rozpis služeb → Dostupnost a absence** (Shift roster → Availability and absences) holds the same data as
**Požadavky na směny** (Shift requests), but as a list across all months: **Datum** (Date), **Člen týmu**
(Team member), **Záznam** (Record), **Poznámka** (Note) and **Zadal(a) sám/sama** (Entered by themselves).
It is handy for searching: the filters **Absence** (Absences) and **Dovolená** (Holiday), grouping by **Člen
týmu** and **Záznam**. Rows can be edited directly. A person has only one record per day.

## 8. How the plan reaches the reservation calendar

By itself. When you add a doctor to a shift in a section with a room, she gets a duty in **Rezervace →
Rozpis lékařů** (Reservations → Doctors' roster), marked **Z rozpisu služeb** (From the shift roster). It is
visible in **Rezervace → Kalendář** (Reservations → Calendar) and the website offers slots according to it.
A time change or deletion in the plan shows up there immediately.

All of this must be true:

1. The person has **Lékařka – přijímá rezervace** (Doctor – accepts reservations) ticked in **Lékařky**
   (Doctors).
2. The section has **Ordinace v rezervacích** (Room in reservations) filled in.

Nurses, reception and helpers are not carried over to reservations.

**Morning and afternoon in one room = one duty.** If a doctor has shifts on one day in the same room that
overlap or follow on from each other, reservations show one duty (8–16 and 12–20 give 8–20). Only shifts from
the plan are merged. Manually entered shifts that overlap in the same room end with the message "Směnu …
nejde propsat do rezervací: …" (The shift … cannot be carried over into reservations: …).

**Checking.** In the cell window a doctor shows in green "V kalendáři rezervací: …" (In the reservation
calendar: …), or in red the reason she is not there:

| Message | What to do |
|---|---|
| "… nemá v Lékařkách zaškrtnuto „Lékařka – přijímá rezervace“" (… does not have Doctor – accepts reservations ticked) | Tick it in **Rozpis služeb → Lékařky**. Then delete the shift and add it again. |
| "… úsek … nemá v Úsecích plánu vyplněnou ordinaci." (section … has no room in the plan sections) | Fill in the room on the section. Then delete the shift and add it again. |
| "… směna nemá ordinaci." (the shift has no room) | Delete the shift and add it again. |
| "V kalendáři rezervací chybí. Uložte směnu znovu (změňte a vraťte čas)." (Missing from the reservation calendar. Save the shift again: change the time and change it back.) | Change the time and change it back. |

**The shift type in Rozpis služeb follows the time.** A shift is written to the roster with the type
whose time is closest to its own: 8–16 as Ranní (Morning), 12–20 as Odpolední (Afternoon), 8–20 as
Celodenní (Full day). When you change the time in the plan, the type changes with it. On a tie, the type
set for the shift in **Úseky plánu** (Plan sections) wins.

**The website /rozpis-lekaru.** From the plan it shows only doctors' duties in sections, not reception, nurses
or helpers. Manually entered shifts and full-day notes keep showing. On the website a shift has the time of its
type (**Typy směn**, Shift types), not the time from the plan.

**Publishing the month.** Until you publish a month, nothing from the plan goes to the website, so you can
plan in peace. When the plan is finished, click **Zveřejnit na webu** (Publish on the website) at the top;
the label changes to **Na webu** (On the website). **Stáhnout z webu** (Hide from the website) hides it
again, for example while you rework the plan. The reservation calendar and online booking do not depend on
publishing: a doctor's service is there as soon as you add it to the plan.

**Hiding a doctor on the website.** When clients should not see that a doctor is on duty that day (for
example a second doctor strengthening a weekend), click the cell and the eye button by the doctor. It
changes to **Skryto na webu** (Hidden on the website) and her label in the plan gets a crossed-out eye.
Such a service:

- is not listed on /rozpis-lekaru,
- is not offered in online booking (the doctor is not in the list of doctors and adds no free slots),
- stays in Rozpis služeb and in the reservation calendar, and **reception books her as usual**.

A morning and an afternoon merged into one service are both hidden when you hide either of them. The
same **Skryto na webu** tick box is on the shift in **Rozpis služeb → Rozpis** (Shift roster → Roster).

## 9. Bilance hodin (Hours balance)

The table under the plan, one row per person:

| Column | How it is calculated |
|---|---|
| **Úvazek** (Contract) | Hours per week from **Personál** (Staff). |
| **Fond** (Hours fund) | Working days of the month (Mon–Fri without public holidays) × contract / 5. |
| **Odpracováno** (Worked) | Shift hours + D and L on a working day (each day contract / 5). Overlapping shifts on one day count once: 8–16 and 12–20 is 12 hours. The bubble shows the breakdown. |
| **Ranní** (Mornings) | Weekdays under 12 hours starting before noon. |
| **Odpolední** (Afternoons) | Weekdays under 12 hours starting from noon on. |
| **Celodenní (12 h)** (Full days) | Weekdays with 12 hours or more. |
| **Víkendy** (Weekends) | Saturdays and Sundays worked, with the hours in brackets. |
| **Absence** (Absences) | Counts of D, NV, L, PN and Š. |
| **Saldo** (Balance) | Worked − fund. Plus is in green, minus in red. |

NV, PN and Š do not count towards hours worked (Š since 16 Nov). Duties entered manually in **Rozpis lékařů** (Doctors' roster)
are counted too. A night shift counts up to midnight.

## 10. Přehled po lidech (Overview by person)

The table under the balance: people (by role) in the rows, days of the month in the columns. Each day
shows the person's service:

| In the cell | Meaning |
|---|---|
| `R-Ord1` | Morning in Ordinace 1 (section short name: Ord1, Ord2, Rec = Recepce…). |
| `O-Rec` | Afternoon at reception. |
| `C · 12h` | Morning and afternoon on one weekday, 12 hours or more in total. |
| `Ord1 10–18` | Other shifts (weekend, Sál, a non-default time): section and time. |
| D, NV, L, PN, Š | Absences, in their own colours. |

Handy when someone asks "when are my shifts": find their row.

## 11. Export and PDF

**Export CSV** downloads a file `rozpis-sluzeb-YYYY-MM.csv` for Excel. It contains the plan, the **Absence**
(Absences) row, the balance and the requests.

**PDF** downloads an A4 landscape file that opens, can be sent and printed: the plan by section, the hours
balance and the overview by person. For an unpublished month the header says "zatím není na webu" (not on
the website yet). **Požadavky na směny** (Shift requests) and the buttons are not in the PDF.

---

# Part B – for every team member

## 12. Moje dostupnost (My availability)

Open **Moje směny → Moje dostupnost** (My shifts → My availability). Next month opens, because planning is done
ahead; use the arrows **‹ ›** to switch to another month.

If you see the message "Váš účet není propojený s členem týmu" (Your account is not linked to a team member), ask
management to link you.

At the top you see **Úvazek** (Contract), **Fond měsíce** (Month's hours fund), **Naplánováno** (Planned) and
**Zbývá dovolené** (Holiday remaining). Below is the calendar of the month.

**How to enter your availability:**

1. Click a day.
2. Write a note if you wish, such as "chci dovolenou" (I would like holiday) or "do 14:00" (until 14:00).
3. Choose **Můžu** (Can work), **Jen ráno** (Mornings only), **Jen odpoledne** (Afternoons only) or **Nemůžu /
   volno** (Cannot / day off).

Remove a record with the **Smazat** (Delete) button in the same window. The button **Zbytek měsíce: Můžu** (Rest of
the month: Can work) fills in all days from today to the end of the displayed month that have no record yet. Then
you only need to correct the exceptions.

**What you cannot enter:**

- Past days can no longer be changed.
- Holiday, time off in lieu, doctor's appointments, sick leave and training are entered by management. In the
  calendar they have a lock 🔒 and cannot be changed. Write your wish in the note for the day, or talk to
  management.

**My shifts.** You see your planned shifts in a blue label on the day, with the section and time. Only management
changes them. **Naplánováno** (Planned) also includes duties entered in **Rozpis lékařů** (Doctors' roster) and days
of D and L, so the number can be higher than the total of the labels.
