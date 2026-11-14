# DESC: Put all air terminals of a family into one duct system of a given system type (creates the system).
# PARAM: family - air terminal family name (required)
# PARAM: system_type - mechanical system type name, e.g. "Return Air" (required)
# PARAM: system_name - name of the new system (default = system_type)
terms = [e for e in cat_elements(doc, DB.BuiltInCategory.OST_DuctTerminal) if family_name(e) == P["family"]]
st = one(doc, DB.Mechanical.MechanicalSystemType, P["system_type"])
cs = DB.ConnectorSet()
n = 0
for e in terms:
    for c in e.MEPModel.ConnectorManager.Connectors:
        if "Hvac" in str(c.Domain):
            cs.Insert(c)
            n += 1
if n == 0:
    raise Exception("no HVAC connectors found on family '%s'" % P["family"])
sysm = DB.Mechanical.MechanicalSystem.Create(doc, st.Id, P.get("system_name", P["system_type"]))
sysm.Add(cs)
doc.Regenerate()
bad = [eint(e.Id) for e in terms if pstr(e, DB.BuiltInParameter.RBS_DUCT_SYSTEM_TYPE_PARAM) != P["system_type"]]
print("terminals: %d | in system '%s': %d | not in it: %s" % (len(terms), sysm.Name, sysm.Elements.Size, bad[:10]))
result = {"in_system": sysm.Elements.Size, "not_in_system": len(bad)}
