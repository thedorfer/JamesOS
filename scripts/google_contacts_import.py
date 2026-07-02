from jamesos.integrations.google_contacts_importer import import_google_contacts
from jamesos.services.contacts_plugin import build_people_profiles

print(import_google_contacts())
print(build_people_profiles())
