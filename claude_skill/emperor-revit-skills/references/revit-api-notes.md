# run_revit_script notes (IronPython 2.7, Revit 2024 / 2025)

- Python 2.7 syntax: no f-strings, `print(x)` works, `u''` for text, integer division with `//`.
- Revit 2025 runs on .NET 8: `ElementId.IntegerValue` still works but `ElementId.Value` is the 64-bit
  id; `hash()` of .NET objects changes between sessions - never use it as a stored key.
- Internal units are FEET. Use the helpers `M(meters)` -> feet and `F(feet)` -> meters.
- Type names: `elem.Name` can fail on ElementTypes in IronPython - use
  `DB.Element.Name.__get__(t)` or the parameter `ALL_MODEL_TYPE_NAME`.
- `System.Windows.Media.Color` and `Autodesk.Revit.DB.Color` clash after star imports - use
  `DB.Color(r, g, b)` explicitly.
- The script already runs in ONE transaction (one undo step). Do not start your own Transaction unless
  you pass use_transaction=false. Use `Attempt` for steps that may fail without losing the rest.
- Temporary changes (e.g. hide links, change filters for an export): TransactionGroup -> Transaction
  -> commit -> do the work -> TransactionGroup.RollBack().
- View filters controlled by a view template must be changed on the template
  (`view.ViewTemplateId`), unless VIS_GRAPHICS_FILTERS is in GetNonControlledTemplateParameterIds().
- `View.SetIsFilterEnabled(filterId, bool)` switches a filter off without removing it (Revit 2021+).
- Linked elements: `RevitLinkInstance.GetLinkDocument()` + `GetTotalTransform()`; read only.
- Long loops: call `progress(msg, done, total)` and `checkpoint()` so the user can cancel.
- Keep printed output short: counts and a few ids, not whole lists.
