from jamesos.tools.notes import list_notes, create_daily_note, create_ticket

print("Notes found:", len(list_notes()))
print(create_daily_note())
print(create_ticket("TEST-001", "JamesOS Test Ticket"))
