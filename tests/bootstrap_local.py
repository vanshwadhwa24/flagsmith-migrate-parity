"""Local test helper (NOT part of the skill): make a fresh empty project+environment+master API key in a
local self-hosted Flagsmith (run with its Django settings). Writes secrets to files, prints only ids."""
import os, sys, json, uuid, django
django.setup()
from organisations.models import Organisation, OrganisationRole
from users.models import FFAdminUser
from projects.models import Project
from environments.models import Environment
from rest_framework.authtoken.models import Token
out = sys.argv[1]
u, _ = FFAdminUser.objects.get_or_create(email="spike@example.com", defaults={"is_superuser": True, "is_staff": True, "first_name": "s", "last_name": "s"})
org, _ = Organisation.objects.get_or_create(name="spike")
if not u.organisations.filter(id=org.id).exists():
    u.add_organisation(org, role=OrganisationRole.ADMIN)
p = Project.objects.create(name="mig-" + uuid.uuid4().hex[:6], organisation=org)
e = Environment.objects.filter(project=p).first() or Environment.objects.create(name="dev", project=p)
from api_keys.models import MasterAPIKey
_, mk = MasterAPIKey.objects.create_key(name="mig-" + uuid.uuid4().hex[:6], organisation=org)
open(out + ".token", "w").write(mk); open(out + ".envkey", "w").write(e.api_key)
print(json.dumps({"project": p.id, "environment": e.name}))
