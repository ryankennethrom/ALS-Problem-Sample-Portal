from django.db import migrations


OLD_WORKFLOW = "Waiting For Customer"
NEW_WORKFLOW = "Waiting for Customer Response"
FIELD_KEY = "current-workflow"


def rename_workflow(apps, schema_editor, old=OLD_WORKFLOW, new=NEW_WORKFLOW):
    ProblemSample = apps.get_model("problem_samples", "ProblemSample")
    ProblemColumn = apps.get_model("problem_samples", "ProblemColumn")
    ProblemContainer = apps.get_model("problem_samples", "ProblemContainer")
    PreparedProblemSample = apps.get_model("problem_samples", "PreparedProblemSample")

    # Keep the dedicated indexed workflow field and its mirrored custom value in sync.
    for sample in ProblemSample.objects.filter(current_workflow=old).iterator():
        values = dict(sample.custom_values or {})
        values[FIELD_KEY] = new
        sample.current_workflow = new
        sample.custom_values = values
        sample.save(update_fields=["current_workflow", "custom_values"])

    # Also repair any mirrored legacy value whose dedicated field had already drifted.
    for sample in ProblemSample.objects.all().iterator():
        values = dict(sample.custom_values or {})
        if values.get(FIELD_KEY) != old:
            continue
        values[FIELD_KEY] = new
        sample.custom_values = values
        sample.save(update_fields=["custom_values"])

    # Current Workflow is represented as an immutable built-in choice column on every table.
    for column in ProblemColumn.objects.filter(field_key=FIELD_KEY).iterator():
        choices = list(column.choices or [])
        changed = False
        rewritten = []
        for choice in choices:
            if choice == old:
                choice = new
                changed = True
            if choice not in rewritten:
                rewritten.append(choice)
        if changed:
            column.choices = rewritten
            column.save(update_fields=["choices"])

    # Existing prepared-ticket drafts can carry the workflow in their pending request payload.
    for prepared in PreparedProblemSample.objects.all().iterator():
        payload = dict(prepared.payload or {})
        custom = dict(payload.get("custom_values") or {})
        changed = False
        if custom.get(FIELD_KEY) == old:
            custom[FIELD_KEY] = new
            payload["custom_values"] = custom
            changed = True
        if payload.get("current_workflow") == old:
            payload["current_workflow"] = new
            changed = True
        if changed:
            prepared.payload = payload
            prepared.save(update_fields=["payload"])

    # Intercolumn Controller rules may use Current Workflow as either side of a rule.
    workflow_columns = {
        str(column.pk): column
        for column in ProblemColumn.objects.filter(field_key=FIELD_KEY)
    }
    workflow_ids = set(workflow_columns)
    for controller in ProblemColumn.objects.exclude(intercolumn_rules=[]).iterator():
        rules = list(controller.intercolumn_rules or [])
        changed = False
        controller_is_workflow = str(controller.pk) in workflow_ids
        rewritten = []
        for raw_rule in rules:
            rule = dict(raw_rule or {})
            other_is_workflow = str(rule.get("other_column_id") or "") in workflow_ids
            if controller_is_workflow:
                for key in ("when_controller_equals", "set_controller_to"):
                    if rule.get(key) == old:
                        rule[key] = new
                        changed = True
            if other_is_workflow:
                for key in ("when_other_equals", "set_other_to"):
                    if rule.get(key) == old:
                        rule[key] = new
                        changed = True
            rewritten.append(rule)
        if changed:
            controller.intercolumn_rules = rewritten
            controller.save(update_fields=["intercolumn_rules"])

    # Disposal undo snapshots can preserve the pre-disposal workflow, so rename it there too.
    for container in ProblemContainer.objects.exclude(disposal_snapshot={}).iterator():
        snapshot = dict(container.disposal_snapshot or {})
        changed = False
        for key, saved in snapshot.items():
            if key.startswith("_") or not isinstance(saved, dict):
                continue
            if saved.get("current_workflow") == old:
                saved["current_workflow"] = new
                changed = True
            custom = dict(saved.get("custom_values") or {})
            if custom.get(FIELD_KEY) == old:
                custom[FIELD_KEY] = new
                saved["custom_values"] = custom
                changed = True
        if changed:
            container.disposal_snapshot = snapshot
            container.save(update_fields=["disposal_snapshot"])


def forwards(apps, schema_editor):
    rename_workflow(apps, schema_editor, OLD_WORKFLOW, NEW_WORKFLOW)


def backwards(apps, schema_editor):
    rename_workflow(apps, schema_editor, NEW_WORKFLOW, OLD_WORKFLOW)


class Migration(migrations.Migration):
    dependencies = [("problem_samples", "0069_remove_builtin_status")]

    operations = [migrations.RunPython(forwards, backwards)]
