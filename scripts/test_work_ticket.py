from jamesos.tools.work import create_work_ticket

print(create_work_ticket(
    ticket_id="88858",
    title="Paving WR Type/Subtype Configuration Change",
    ticket_type="ADO Bug / Work Item",
    customer="WGL",
    environment="SFM2",
    schema="WG_CUSTOM",
    status="Ready for Kevin WR Type update",
    tester="Malcolm / Kevin",
    notes="Paving code changes are deployed in SFM2. Waiting for Kevin to update the WR Type/subtype configuration so testing can continue."
))
